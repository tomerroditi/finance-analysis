#!/usr/bin/env python3
"""
Run the Playwright e2e suite in parallel across N *fully isolated* backends.

Why this exists
---------------
Demo Mode is a process-global backend singleton (one shared SQLite DB for the
whole uvicorn process), so the default suite cannot safely run at ``workers > 1``
against a single backend — concurrent specs race the shared demo DB. Profiling
also showed the suite is CPU-bound on browser-side Plotly rendering, so naive
client-side parallelism against one shared backend regressed (the serialized
SQLite path saturates and cold dashboards time out).

This orchestrator removes the shared state entirely: it starts **N independent
(backend + frontend) pairs**, each with its own port and its own
``FAD_USER_DIR`` (hence its own demo SQLite file), then runs Playwright
``--shard=i/N`` once per pair — each shard pinned to its own backend via
``BASE_URL`` (browser origin) and ``E2E_API_BASE`` (Node-side API calls in
helpers.ts). With no shared DB, every shard runs concurrently with zero
cross-shard races, and the only ceiling is real CPU cores.

This is an **opt-in local tool** (``npm run test:e2e:isolated``). It does not
change CI, which keeps its proven single-backend ``--shard=X/4`` matrix.

Server ownership
----------------
Pinning a shard to a server this run did not start is silent poison: the shard
drives a *previous* run's frontend, serving whatever source that checkout had,
and specs fail in ways that never reproduce in isolation. Four things keep
ownership honest, and all four are load-bearing:

* children run in their own process group (``start_new_session``) and are torn
  down with ``killpg`` — ``npm run dev`` forks ``vite``, so terminating npm
  alone leaves vite holding the port;
* a preflight refuses to start when a target port is already listening
  (``--reclaim-ports`` kills the squatters instead);
* Vite runs with ``--strictPort`` so a taken port is a hard failure rather than
  a silent fall-forward to the next free one;
* readiness means *our* server answered — the backend must have created
  ``data.db`` inside this shard's ``FAD_USER_DIR``, which a squatter cannot
  fake — and server output goes to per-shard log files, not ``/dev/null``.

Usage
-----
    # From repo root (venv need not be on PATH — the script finds .venv):
    python .claude/scripts/e2e_parallel_isolated.py            # auto-pick shard count
    python .claude/scripts/e2e_parallel_isolated.py --shards 4
    python .claude/scripts/e2e_parallel_isolated.py --reclaim-ports
    python .claude/scripts/e2e_parallel_isolated.py --shards 3 -- --grep @smoke

Anything after ``--`` is forwarded verbatim to every ``playwright test`` shard.
"""

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"
LOG_DIR = Path(tempfile.gettempdir())

# Bases chosen to avoid the default dev ports (8000 / 5173) and the per-worktree
# ports, so this can run alongside a normal dev session without clashing.
BACKEND_PORT_BASE = 8100
FRONTEND_PORT_BASE = 5273

# Per-spec wall times from the last successful run, used to pack shards evenly.
# Committed on purpose: absolute times are machine-specific but the *ratios*
# are stable, and that is all the packer needs — so a fresh clone gets balanced
# shards on its first run instead of paying for a calibration run.
TIMINGS_PATH = Path(__file__).resolve().parent / "e2e_shard_timings.json"

# Their projects (`demo-setup` / `demo-teardown`) match only these files, so
# every shard must list them or Demo Mode is never enabled for that shard.
LIFECYCLE_SPECS = ["e2e/demo.setup.ts", "e2e/demo.teardown.ts"]


def spec_files() -> list[str]:
    """Every `.spec.ts` under `frontend/e2e`, as paths relative to `frontend/`."""
    return sorted(
        str(path.relative_to(FRONTEND_DIR))
        for path in (FRONTEND_DIR / "e2e").rglob("*.spec.ts")
    )


def load_timings() -> dict[str, float]:
    try:
        return json.loads(TIMINGS_PATH.read_text())
    except (OSError, ValueError):
        return {}


def pack_shards(files: list[str], timings: dict[str, float], n: int) -> list[list[str]]:
    """
    Split `files` into `n` groups of roughly equal duration.

    Playwright's own `--shard` splits by test *count*, which on this suite left
    one shard at 31 s and another at 1.5 m — the slowest sets the wall clock, so
    a third of the parallelism was wasted. This is longest-processing-time-first
    greedy bin packing: place the slowest spec into whichever shard is currently
    lightest. It is within 4/3 of optimal, which is far inside the noise here.

    Unknown files (new specs, or no timings file yet) are assumed to take the
    median of what we do know, so one new spec cannot swamp a shard.
    """
    known = sorted(timings.values())
    fallback = known[len(known) // 2] if known else 1.0
    cost = lambda f: timings.get(f, fallback)  # noqa: E731

    shards: list[list[str]] = [[] for _ in range(n)]
    loads = [0.0] * n
    for spec in sorted(files, key=cost, reverse=True):
        lightest = loads.index(min(loads))
        shards[lightest].append(spec)
        loads[lightest] += cost(spec)
    return shards


def collect_timings(report_paths: list[Path]) -> dict[str, float]:
    """Sum each spec file's test durations across the shards' JSON reports."""
    totals: dict[str, float] = {}

    def walk(suite: dict, file_hint: str | None = None) -> None:
        current = suite.get("file") or file_hint
        for spec in suite.get("specs", []):
            path = spec.get("file") or current
            if not path:
                continue
            key = path if path.startswith("e2e/") else f"e2e/{path}"
            for test in spec.get("tests", []):
                for result in test.get("results", []):
                    totals[key] = totals.get(key, 0.0) + result.get("duration", 0) / 1000
        for child in suite.get("suites", []):
            walk(child, current)

    for path in report_paths:
        try:
            report = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        for suite in report.get("suites", []):
            walk(suite)
    return totals


def read_log(path: Path) -> str:
    """Read a server/shard log defensively.

    Playwright and Vite emit box-drawing and progress bytes that are not valid
    UTF-8 in every locale; a strict decode here used to abort the whole summary
    loop with `UnicodeDecodeError`, throwing away every shard's result after the
    first one even when the tests themselves were fine.
    """
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def log_tail(path: Path, lines: int = 15) -> str:
    """Last `lines` of a log, indented, for embedding in an error message."""
    tail = read_log(path).splitlines()[-lines:]
    return "\n".join(f"      {line}" for line in tail) or "      (log empty)"


def port_is_listening(port: int) -> bool:
    """True if anything accepts a TCP connection on `port` (v4 or v6 loopback)."""
    for host in ("127.0.0.1", "::1"):
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            continue
    return False


def listening_pids(port: int) -> list[int]:
    """PIDs holding a LISTEN socket on `port` (best effort, via lsof)."""
    try:
        completed = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return sorted({int(tok) for tok in completed.stdout.split() if tok.isdigit()})


def reclaim_port(port: int) -> bool:
    """Kill whatever holds `port`; return True once it is free.

    Signals the *listening* pid directly rather than its process group: a
    squatter is by definition not ours, and its group could well be the user's
    own shell session.
    """
    pids = listening_pids(port)
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in pids:
            try:
                os.kill(pid, sig)
            except OSError:
                pass
        deadline = time.time() + 5
        while time.time() < deadline:
            if not port_is_listening(port):
                return True
            time.sleep(0.2)
    return not port_is_listening(port)


def wait_for_port(port: int, timeout: float, proc: subprocess.Popen | None = None) -> str | None:
    """Wait until `port` accepts a connection.

    Returns None on success, or a short reason on failure. When `proc` is given,
    its death short-circuits the wait — a server that failed to bind (uvicorn on
    a taken port, Vite under `--strictPort`) should surface immediately instead
    of burning the full readiness timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            return f"process exited with code {proc.returncode} before binding :{port}"
        if port_is_listening(port):
            return None
        time.sleep(0.25)
    return f"timed out after {timeout:.0f}s waiting for :{port}"


def uvicorn_argv(port: int) -> list[str]:
    """Prefer the worktree's own venv uvicorn; fall back to PATH."""
    venv_uvicorn = REPO_ROOT / ".venv" / "bin" / "uvicorn"
    exe = str(venv_uvicorn) if venv_uvicorn.exists() else "uvicorn"
    return [exe, "backend.main:app", "--port", str(port)]


def default_shard_count() -> int:
    """~1 shard per 3 cores (each shard drives a CPU-heavy Chromium), clamped 2..6."""
    cores = os.cpu_count() or 4
    return max(2, min(6, cores // 3))


def terminate_group(proc: subprocess.Popen) -> None:
    """Kill a child *and every process it spawned*.

    `npm run dev` execs `npm`, which forks `vite` as a child, so terminating the
    npm process alone left vite holding the frontend port — which is exactly how
    later runs ended up silently driving a previous run's servers. Children are
    started with `start_new_session=True`, so each is its own process-group
    leader (pgid == pid) and a single killpg takes the whole tree down.
    """
    pgid = proc.pid
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            continue
        if sig is signal.SIGTERM:
            # Leader reaped; sweep any straggler still in the group.
            try:
                os.killpg(pgid, signal.SIGKILL)
            except OSError:
                pass
        return


class Pair:
    """One isolated (backend + frontend) pair for a single shard."""

    def __init__(self, index: int):
        self.index = index
        self.backend_port = BACKEND_PORT_BASE + index
        self.frontend_port = FRONTEND_PORT_BASE + index
        self.user_dir = tempfile.mkdtemp(prefix=f"e2e-isolated-{index}-")
        self.backend: subprocess.Popen | None = None
        self.frontend: subprocess.Popen | None = None
        self.backend_log = LOG_DIR / f"e2e-isolated-backend-{index}.log"
        self.frontend_log = LOG_DIR / f"e2e-isolated-frontend-{index}.log"
        self._log_handles: list = []

    @property
    def ports(self) -> tuple[int, int]:
        return (self.backend_port, self.frontend_port)

    @property
    def api_base(self) -> str:
        return f"http://localhost:{self.backend_port}/api"

    @property
    def base_url(self) -> str:
        return f"http://localhost:{self.frontend_port}"

    def _spawn(self, argv: list[str], cwd: Path, env: dict, log_path: Path) -> subprocess.Popen:
        handle = open(log_path, "w")
        self._log_handles.append(handle)
        return subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            # Own process group, so teardown can killpg the whole tree.
            start_new_session=True,
        )

    def start(self, timeout: int) -> None:
        self.backend = self._spawn(
            uvicorn_argv(self.backend_port),
            REPO_ROOT,
            {**os.environ, "FAD_USER_DIR": self.user_dir},
            self.backend_log,
        )

        self.frontend = self._spawn(
            # `--strictPort`: without it Vite quietly falls forward to the next
            # free port when its assigned one is taken, and this run would then
            # pin its shard to a server it neither started nor can kill.
            ["npm", "run", "dev", "--", "--strictPort"],
            FRONTEND_DIR,
            {
                **os.environ,
                "PORT": str(self.frontend_port),
                "VITE_BACKEND_URL": f"http://127.0.0.1:{self.backend_port}",
            },
            self.frontend_log,
        )

        print(
            f"  shard {self.index}: backend :{self.backend_port} "
            f"(FAD_USER_DIR={self.user_dir}), frontend :{self.frontend_port}"
        )
        self._await("backend", self.backend, self.backend_port, self.backend_log, timeout)
        self._await_backend_identity(timeout)
        self._await("frontend", self.frontend, self.frontend_port, self.frontend_log, timeout)

    def _await(
        self,
        label: str,
        proc: subprocess.Popen,
        port: int,
        log_path: Path,
        timeout: int,
    ) -> None:
        reason = wait_for_port(port, timeout, proc)
        if reason is None:
            return
        raise RuntimeError(
            f"shard {self.index} {label} failed on :{port} — {reason}\n"
            f"    log: {log_path}\n{log_tail(log_path)}"
        )

    def _await_backend_identity(self, timeout: int) -> None:
        """Confirm the backend answering on our port is the one we started.

        A bare TCP accept proves only that *something* listens — an orphan from
        an earlier run satisfies it instantly, which is how a run could report
        "ready in 0s" and then drive stale servers. Our backend creates
        `data.db` inside this shard's private `FAD_USER_DIR` during startup, so
        that file's existence is identity a squatter cannot fake.
        """
        marker = Path(self.user_dir) / "data.db"
        deadline = time.time() + timeout
        while time.time() < deadline:
            if marker.exists():
                return
            if self.backend is not None and self.backend.poll() is not None:
                break
            time.sleep(0.25)
        raise RuntimeError(
            f"shard {self.index} backend on :{self.backend_port} is not ours — it never "
            f"created {marker}.\n"
            f"    Something else is listening on that port; this run would have tested "
            f"against it.\n"
            f"    log: {self.backend_log}\n{log_tail(self.backend_log)}"
        )

    def stop(self) -> None:
        for proc in (self.frontend, self.backend):
            if proc is not None:
                terminate_group(proc)
        for handle in self._log_handles:
            handle.close()
        self._log_handles.clear()
        leaked = [port for port in self.ports if port_is_listening(port)]
        if leaked:
            print(
                f"  WARNING: shard {self.index} left listeners on "
                f"{', '.join(str(p) for p in leaked)} — the next run will refuse to start"
            )
        shutil.rmtree(self.user_dir, ignore_errors=True)


def preflight_ports(pairs: list[Pair], reclaim: bool) -> None:
    """Refuse to race a server this run does not own (or reclaim the port)."""
    busy = [(pair, port) for pair in pairs for port in pair.ports if port_is_listening(port)]
    if not busy:
        return

    if reclaim:
        print("Reclaiming ports held by a previous run...")
        for _, port in busy:
            freed = reclaim_port(port)
            print(f"  :{port} -> {'freed' if freed else 'STILL BUSY'}")
        still = [str(port) for _, port in busy if port_is_listening(port)]
        if still:
            raise RuntimeError(f"could not free port(s): {', '.join(still)}")
        print()
        return

    ports = sorted({port for _, port in busy})
    pattern = "|".join(str(port) for port in ports)
    raise RuntimeError(
        "ports already in use: " + ", ".join(str(p) for p in ports) + "\n"
        "  A previous run left its servers behind (or something else owns these ports).\n"
        "  Starting anyway would pin shards to servers this run does not control: they\n"
        "  serve whatever source they were started with, so specs fail here and pass in\n"
        "  isolation.\n"
        f"  Inspect: lsof -nP -iTCP -sTCP:LISTEN | grep -E ':({pattern}) '\n"
        "  Reclaim: python .claude/scripts/e2e_parallel_isolated.py --reclaim-ports"
    )


def install_signal_handlers() -> None:
    """Turn SIGTERM/SIGHUP into SystemExit so the teardown `finally` still runs."""

    def _exit(signum, _frame):
        raise SystemExit(128 + signum)

    for sig in (signal.SIGTERM, signal.SIGHUP):
        try:
            signal.signal(sig, _exit)
        except (OSError, ValueError):
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shards", type=int, default=default_shard_count())
    parser.add_argument("--timeout", type=int, default=90, help="per-server readiness timeout (s)")
    parser.add_argument(
        "--reclaim-ports",
        action="store_true",
        help="kill whatever is listening on this run's ports instead of refusing to start",
    )
    parser.add_argument("playwright_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    install_signal_handlers()

    extra = args.playwright_args
    if extra and extra[0] == "--":
        extra = extra[1:]

    n = args.shards

    # A forwarded positional (a file/grep filter) would fight our own file
    # lists, so hand those runs back to Playwright's count-based sharding.
    forwards_paths = any(not a.startswith("-") for a in extra)
    timings = {} if forwards_paths else load_timings()
    buckets = None if forwards_paths else pack_shards(spec_files(), timings, n)

    print(f"Isolated parallel e2e: {n} shards on {os.cpu_count()} cores")
    if buckets is None:
        print("  splitting with Playwright --shard (positional filter forwarded)\n")
    elif timings:
        est = [sum(timings.get(f, 0.0) for f in b) for b in buckets]
        print(
            "  packed by recorded duration — estimated "
            + ", ".join(f"{e:.0f}s" for e in est)
            + "\n"
        )
    else:
        print("  no timings recorded yet; this run will write them\n")

    pairs: list[Pair] = [Pair(i) for i in range(n)]
    shard_procs: list[subprocess.Popen] = []
    logs: list[Path] = []
    reports: list[Path] = []
    returncodes: list[int] = []
    started = time.time()

    try:
        preflight_ports(pairs, args.reclaim_ports)
    except RuntimeError as exc:
        for pair in pairs:
            shutil.rmtree(pair.user_dir, ignore_errors=True)
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 2

    try:
        print("Starting isolated backend+frontend pairs...")
        for pair in pairs:
            pair.start(args.timeout)
        print(f"\nAll {n} pairs ready in {time.time() - started:.0f}s. Launching shards...\n")

        for pair in pairs:
            log_path = LOG_DIR / f"e2e-isolated-shard-{pair.index}.log"
            logs.append(log_path)
            report_path = LOG_DIR / f"e2e-isolated-report-{pair.index}.json"
            reports.append(report_path)
            shard_env = {
                **os.environ,
                "BASE_URL": pair.base_url,
                "E2E_API_BASE": pair.api_base,
                "PLAYWRIGHT_JSON_OUTPUT_NAME": str(report_path),
            }
            # --retries=1 matches CI (playwright.config sets retries:1 under CI).
            # Running N heavy Chromium+Plotly shards saturates the CPU, and
            # timing-sensitive specs (mouse-drag scroll, transient-state
            # selectors) can flake under that load with retries:0. A retry
            # absorbs the load transient without masking a real failure — the
            # specs pass deterministically on their own. `*extra` comes last so
            # a user-forwarded --retries overrides this default.
            split = (
                [f"--shard={pair.index + 1}/{n}"]
                if buckets is None
                else [*LIFECYCLE_SPECS, *buckets[pair.index]]
            )
            cmd = [
                "npx",
                "playwright",
                "test",
                # `json` alongside `list` so the run records its own per-spec
                # durations for the next run's packing.
                "--reporter=list,json",
                "--retries=1",
                *split,
                *extra,
            ]
            with open(log_path, "w") as log:
                shard_procs.append(
                    subprocess.Popen(cmd, cwd=str(FRONTEND_DIR), env=shard_env, stdout=log, stderr=subprocess.STDOUT)
                )

        returncodes = [proc.wait() for proc in shard_procs]
    except (RuntimeError, KeyboardInterrupt, SystemExit) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 2
    finally:
        # Shards first: a still-running Playwright would otherwise keep hitting
        # servers we are about to kill and spray connection errors into its log.
        for proc in shard_procs:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        print("\nStopping all pairs...")
        for pair in pairs:
            pair.stop()

    elapsed = time.time() - started
    print(f"\n{'=' * 60}\nIsolated parallel run finished in {elapsed:.0f}s ({elapsed / 60:.1f}m)\n{'=' * 60}")
    for i, (rc, log_path) in enumerate(zip(returncodes, logs)):
        status = "PASS" if rc == 0 else f"FAIL (exit {rc})"
        summary = ""
        if log_path.exists():
            tail = [ln for ln in read_log(log_path).splitlines() if "passed" in ln or "failed" in ln]
            summary = tail[-1].strip() if tail else ""
        print(f"  shard {i + 1}/{n}: {status}  {summary}    (log: {log_path})")

    # Record durations even on failure — a red spec still timed itself, and the
    # next run's packing should not regress just because something broke. Only
    # rewrite when the run actually measured most of the suite, so a `--grep`
    # or an early crash cannot shrink the table to a handful of specs.
    measured = collect_timings(reports)
    if len(measured) >= 0.8 * len(spec_files()):
        merged = {**load_timings(), **measured}
        TIMINGS_PATH.write_text(json.dumps(dict(sorted(merged.items())), indent=2) + "\n")
        print(f"\nRecorded {len(measured)} spec timings -> {TIMINGS_PATH.name}")

    return 0 if all(rc == 0 for rc in returncodes) else 1


if __name__ == "__main__":
    sys.exit(main())
