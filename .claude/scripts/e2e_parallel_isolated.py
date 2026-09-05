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
* ports are **allocated, not assumed**: the bases below are a starting point and
  the allocator walks upward to the first port it can actually *bind*, naming
  whoever holds the one it skipped. Two worktrees running this concurrently
  therefore each get their own pair instead of fighting over :5273. Both bases
  are overridable (``--backend-port-base`` / ``--frontend-port-base``, or
  ``E2E_BACKEND_PORT_BASE`` / ``E2E_FRONTEND_PORT_BASE``);
* Vite runs with ``--strictPort`` so a taken port is a hard failure rather than
  a silent fall-forward to the next free one — and a server that loses the race
  between the free-port probe and its own bind is retried on fresh ports;
* readiness means *our* server answered — the backend must have created
  ``data.db`` inside this shard's ``FAD_USER_DIR``, which a squatter cannot
  fake — and server output goes to per-shard log files, not ``/dev/null``.

Usage
-----
    # From repo root (venv need not be on PATH — the script finds .venv):
    python .claude/scripts/e2e_parallel_isolated.py            # auto-pick shard count
    python .claude/scripts/e2e_parallel_isolated.py --shards 4
    python .claude/scripts/e2e_parallel_isolated.py --frontend-port-base 5400
    python .claude/scripts/e2e_parallel_isolated.py --reclaim-ports
    python .claude/scripts/e2e_parallel_isolated.py --shards 3 -- --grep @smoke

Anything after ``--`` is forwarded verbatim to every ``playwright test`` shard.
"""

import argparse
import hashlib
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

# Logs and JSON reports are keyed by checkout, not just by shard index. With a
# flat `$TMPDIR/e2e-isolated-report-0.json`, two worktrees running at once
# overwrite each other's reports — and `collect_timings` would then fold the
# *other* checkout's numbers into this repo's committed timings file.
_ROOT_KEY = hashlib.sha256(str(REPO_ROOT).encode()).hexdigest()[:8]
LOG_DIR = Path(tempfile.gettempdir()) / f"e2e-isolated-{REPO_ROOT.name}-{_ROOT_KEY}"

# Preferred bases, chosen to avoid the default dev ports (8000 / 5173) and the
# per-worktree ports. They are only a *starting point*: `PortAllocator` walks
# upward from here to the first port it can bind, so a neighbouring worktree
# already on :5273 costs this run nothing.
DEFAULT_BACKEND_PORT_BASE = 8100
DEFAULT_FRONTEND_PORT_BASE = 5273
# How far past a base the allocator searches before giving up.
PORT_SEARCH_SPAN = 200

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


def port_is_free(port: int) -> bool:
    """True if we could actually *bind* `port` on every loopback family.

    A connect probe only proves nobody is accepting yet: a socket that is bound
    but not listening, or one bound on an interface the probe does not poll,
    still owns the port and would fail our server's own bind. Binding is the
    same question the server will ask, so it is the one worth asking.

    `SO_REUSEADDR` is set for the same reason — it is what uvicorn and Vite set,
    so the probe answers *their* question. Without it a port left in TIME_WAIT
    by the previous run reads as busy though both servers would happily bind it,
    and back-to-back runs drift steadily up the port range for no reason. It
    does not weaken the check: a socket already bound, listening or not, still
    refuses the second bind.
    """
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            sock = socket.socket(family, socket.SOCK_STREAM)
        except OSError:
            continue  # family unavailable on this host; nothing to check
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
        except OSError:
            return False
        finally:
            sock.close()
    return True


def describe_port_holder(port: int) -> str:
    """Best-effort "who has this port" — command, pid and working directory.

    The working directory is the useful half when the answer is "the worktree
    in the next terminal": it names which checkout, not just which binary.
    """
    pids = listening_pids(port)
    if not pids:
        return "an unidentified process"
    described = []
    for pid in pids[:3]:
        name = f"pid {pid}"
        try:
            out = subprocess.run(
                ["ps", "-p", str(pid), "-o", "comm="],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            if out:
                name = f"{Path(out).name} (pid {pid})"
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            cwd = subprocess.run(
                ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            for line in cwd.splitlines():
                if line.startswith("n"):
                    name += f" in {line[1:]}"
                    break
        except (OSError, subprocess.SubprocessError):
            pass
        described.append(name)
    return ", ".join(described)


class PortRaceError(RuntimeError):
    """A server died without binding while someone else holds its port.

    Distinct from a plain startup crash because it is worth *retrying* on a
    different port — the probe-then-bind window is small but real when several
    worktrees start runs at the same moment.
    """


class PortAllocator:
    """Hands out ports, preferring `base + index` but never insisting on it.

    Fixed ports were the root of the cross-worktree collision: the second run
    could not bind :5273, Vite silently moved to :5274, and `BASE_URL` still
    said :5273 — so its specs drove the neighbour's app. Allocating instead of
    assuming makes concurrent worktrees a non-event.
    """

    def __init__(self, backend_base: int, frontend_base: int, span: int = PORT_SEARCH_SPAN):
        self.backend_base = backend_base
        self.frontend_base = frontend_base
        self.span = span
        self.taken: set[int] = set()

    def take(self, base: int, index: int) -> int:
        preferred = base + index
        for port in range(preferred, preferred + self.span):
            if port in self.taken or not port_is_free(port):
                continue
            self.taken.add(port)
            return port
        raise RuntimeError(
            f"no free port in {preferred}-{preferred + self.span - 1}; "
            f"pass --backend-port-base / --frontend-port-base to move elsewhere"
        )

    def release(self, *ports: int) -> None:
        for port in ports:
            self.taken.discard(port)


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
        self.backend_port: int | None = None
        self.frontend_port: int | None = None
        self.user_dir = tempfile.mkdtemp(prefix=f"e2e-isolated-{index}-")
        self.backend: subprocess.Popen | None = None
        self.frontend: subprocess.Popen | None = None
        self.backend_log = LOG_DIR / f"backend-{index}.log"
        self.frontend_log = LOG_DIR / f"frontend-{index}.log"
        self._log_handles: list = []

    @property
    def ports(self) -> tuple[int, ...]:
        return tuple(p for p in (self.backend_port, self.frontend_port) if p is not None)

    def assign_ports(self, allocator: PortAllocator) -> None:
        """Claim a backend and frontend port, announcing any displacement."""
        self.backend_port = allocator.take(allocator.backend_base, self.index)
        self.frontend_port = allocator.take(allocator.frontend_base, self.index)
        for label, preferred, actual in (
            ("backend", allocator.backend_base + self.index, self.backend_port),
            ("frontend", allocator.frontend_base + self.index, self.frontend_port),
        ):
            if actual != preferred:
                # A port this run already claimed needs no lsof lookup, and
                # naming it as a stranger would be actively confusing.
                holder = (
                    "an earlier shard of this run"
                    if preferred in allocator.taken
                    else describe_port_holder(preferred)
                )
                print(
                    f"  shard {self.index}: {label} :{preferred} is held by "
                    f"{holder} — using :{actual}"
                )

    def launch(self, allocator: PortAllocator, timeout: int, attempts: int = 3) -> None:
        """Start the pair, retrying on fresh ports if we lose a bind race."""
        for attempt in range(1, attempts + 1):
            self.assign_ports(allocator)
            try:
                self.start(timeout)
                return
            except PortRaceError:
                self.stop_processes()
                allocator.release(*self.ports)
                if attempt == attempts:
                    raise
                print(f"  shard {self.index}: lost a port race, retrying on fresh ports")

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
        message = (
            f"shard {self.index} {label} failed on :{port} — {reason}\n"
            f"    log: {log_path}\n{log_tail(log_path)}"
        )
        # Exited without binding *and* someone else now owns the port: we lost
        # the window between the free-port probe and the server's own bind, so
        # this is retryable. A crash on a still-free port is a real failure.
        if proc.poll() is not None and not port_is_free(port):
            raise PortRaceError(message)
        raise RuntimeError(message)

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

    def stop_processes(self) -> None:
        """Tear down the servers, leaving the pair reusable for a retry."""
        for proc in (self.frontend, self.backend):
            if proc is not None:
                terminate_group(proc)
        self.frontend = self.backend = None
        for handle in self._log_handles:
            handle.close()
        self._log_handles.clear()

    def stop(self) -> None:
        ports = self.ports
        self.stop_processes()
        leaked = [port for port in ports if port_is_listening(port)]
        if leaked:
            print(
                f"  WARNING: shard {self.index} left listeners on "
                f"{', '.join(str(p) for p in leaked)} — the next run will refuse to start"
            )
        shutil.rmtree(self.user_dir, ignore_errors=True)


def env_port_base(name: str, default: int) -> int:
    """Read a port base from the environment, ignoring anything unusable."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        port = int(raw)
    except ValueError:
        print(f"  ignoring {name}={raw!r} (not an integer); using {default}")
        return default
    if not 1024 <= port <= 65000:
        print(f"  ignoring {name}={raw!r} (out of range 1024-65000); using {default}")
        return default
    return port


def reclaim_preferred_ports(backend_base: int, frontend_base: int, n: int) -> None:
    """Kill whatever holds the preferred ports, so this run lands on them.

    Only ever run on request (`--reclaim-ports`). Without it a busy port is
    simply skipped, which is the right default — the holder may well be a
    neighbouring worktree's live test run, and killing that is nobody's idea of
    a fix.
    """
    targets = [base + i for base in (backend_base, frontend_base) for i in range(n)]
    busy = [port for port in targets if not port_is_free(port)]
    if not busy:
        return
    print("Reclaiming preferred ports...")
    for port in busy:
        holder = describe_port_holder(port)
        freed = reclaim_port(port)
        print(f"  :{port} ({holder}) -> {'freed' if freed else 'STILL BUSY, will skip'}")
    print()


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
        "--backend-port-base",
        type=int,
        default=env_port_base("E2E_BACKEND_PORT_BASE", DEFAULT_BACKEND_PORT_BASE),
        help="first backend port to try (env: E2E_BACKEND_PORT_BASE)",
    )
    parser.add_argument(
        "--frontend-port-base",
        type=int,
        default=env_port_base("E2E_FRONTEND_PORT_BASE", DEFAULT_FRONTEND_PORT_BASE),
        help="first frontend port to try (env: E2E_FRONTEND_PORT_BASE)",
    )
    parser.add_argument(
        "--reclaim-ports",
        action="store_true",
        help="kill whatever holds the preferred ports first. Busy ports are otherwise "
        "just skipped; only use this when you know the holder is your own orphan and "
        "not a neighbouring worktree's live run",
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

    if args.reclaim_ports:
        reclaim_preferred_ports(args.backend_port_base, args.frontend_port_base, n)

    allocator = PortAllocator(args.backend_port_base, args.frontend_port_base)
    pairs: list[Pair] = [Pair(i) for i in range(n)]
    shard_procs: list[subprocess.Popen] = []
    logs: list[Path] = []
    reports: list[Path] = []
    returncodes: list[int] = []
    started = time.time()

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    try:
        print("Starting isolated backend+frontend pairs...")
        for pair in pairs:
            pair.launch(allocator, args.timeout)
        print(f"\nAll {n} pairs ready in {time.time() - started:.0f}s. Launching shards...\n")

        for pair in pairs:
            log_path = LOG_DIR / f"shard-{pair.index}.log"
            logs.append(log_path)
            report_path = LOG_DIR / f"report-{pair.index}.json"
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
