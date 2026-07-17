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

Usage
-----
    # From repo root (venv need not be on PATH — the script finds .venv):
    python .claude/scripts/e2e_parallel_isolated.py            # auto-pick shard count
    python .claude/scripts/e2e_parallel_isolated.py --shards 4
    python .claude/scripts/e2e_parallel_isolated.py --shards 3 -- --grep @smoke

Anything after ``--`` is forwarded verbatim to every ``playwright test`` shard.
"""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"

# Bases chosen to avoid the default dev ports (8000 / 5173) and the per-worktree
# ports, so this can run alongside a normal dev session without clashing.
BACKEND_PORT_BASE = 8100
FRONTEND_PORT_BASE = 5273


def wait_for_port(port: int, timeout: float) -> bool:
    """Poll ``localhost:port`` until it accepts a connection or ``timeout`` elapses."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def uvicorn_argv(port: int) -> list[str]:
    """Prefer the worktree's own venv uvicorn; fall back to PATH."""
    venv_uvicorn = REPO_ROOT / ".venv" / "bin" / "uvicorn"
    exe = str(venv_uvicorn) if venv_uvicorn.exists() else "uvicorn"
    return [exe, "backend.main:app", "--port", str(port)]


def default_shard_count() -> int:
    """~1 shard per 3 cores (each shard drives a CPU-heavy Chromium), clamped 2..6."""
    cores = os.cpu_count() or 4
    return max(2, min(6, cores // 3))


class Pair:
    """One isolated (backend + frontend) pair for a single shard."""

    def __init__(self, index: int):
        self.index = index
        self.backend_port = BACKEND_PORT_BASE + index
        self.frontend_port = FRONTEND_PORT_BASE + index
        self.user_dir = tempfile.mkdtemp(prefix=f"e2e-isolated-{index}-")
        self.backend: subprocess.Popen | None = None
        self.frontend: subprocess.Popen | None = None

    @property
    def api_base(self) -> str:
        return f"http://localhost:{self.backend_port}/api"

    @property
    def base_url(self) -> str:
        return f"http://localhost:{self.frontend_port}"

    def start(self, timeout: int) -> None:
        backend_env = {**os.environ, "FAD_USER_DIR": self.user_dir}
        self.backend = subprocess.Popen(
            uvicorn_argv(self.backend_port),
            cwd=str(REPO_ROOT),
            env=backend_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        frontend_env = {
            **os.environ,
            "PORT": str(self.frontend_port),
            "VITE_BACKEND_URL": f"http://127.0.0.1:{self.backend_port}",
        }
        self.frontend = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=str(FRONTEND_DIR),
            env=frontend_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        print(
            f"  shard {self.index}: backend :{self.backend_port} "
            f"(FAD_USER_DIR={self.user_dir}), frontend :{self.frontend_port}"
        )
        if not wait_for_port(self.backend_port, timeout):
            raise RuntimeError(f"shard {self.index} backend failed on :{self.backend_port}")
        if not wait_for_port(self.frontend_port, timeout):
            raise RuntimeError(f"shard {self.index} frontend failed on :{self.frontend_port}")

    def stop(self) -> None:
        for proc in (self.frontend, self.backend):
            if proc is None:
                continue
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        shutil.rmtree(self.user_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shards", type=int, default=default_shard_count())
    parser.add_argument("--timeout", type=int, default=90, help="per-server readiness timeout (s)")
    parser.add_argument("playwright_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    extra = args.playwright_args
    if extra and extra[0] == "--":
        extra = extra[1:]

    n = args.shards
    print(f"Isolated parallel e2e: {n} shards on {os.cpu_count()} cores\n")

    pairs: list[Pair] = [Pair(i) for i in range(n)]
    shard_procs: list[subprocess.Popen] = []
    logs: list[Path] = []
    started = time.time()

    try:
        print("Starting isolated backend+frontend pairs...")
        for pair in pairs:
            pair.start(args.timeout)
        print(f"\nAll {n} pairs ready in {time.time() - started:.0f}s. Launching shards...\n")

        for pair in pairs:
            log_path = Path(tempfile.gettempdir()) / f"e2e-isolated-shard-{pair.index}.log"
            logs.append(log_path)
            shard_env = {
                **os.environ,
                "BASE_URL": pair.base_url,
                "E2E_API_BASE": pair.api_base,
            }
            # --retries=1 matches CI (playwright.config sets retries:1 under CI).
            # Running N heavy Chromium+Plotly shards saturates the CPU, and
            # timing-sensitive specs (mouse-drag scroll, transient-state
            # selectors) can flake under that load with retries:0. A retry
            # absorbs the load transient without masking a real failure — the
            # specs pass deterministically on their own. `*extra` comes last so
            # a user-forwarded --retries overrides this default.
            cmd = [
                "npx",
                "playwright",
                "test",
                f"--shard={pair.index + 1}/{n}",
                "--reporter=list",
                "--retries=1",
                *extra,
            ]
            with open(log_path, "w") as log:
                shard_procs.append(
                    subprocess.Popen(cmd, cwd=str(FRONTEND_DIR), env=shard_env, stdout=log, stderr=subprocess.STDOUT)
                )

        returncodes = [proc.wait() for proc in shard_procs]
    finally:
        print("\nStopping all pairs...")
        for pair in pairs:
            pair.stop()

    elapsed = time.time() - started
    print(f"\n{'=' * 60}\nIsolated parallel run finished in {elapsed:.0f}s ({elapsed / 60:.1f}m)\n{'=' * 60}")
    for i, (rc, log_path) in enumerate(zip(returncodes, logs)):
        status = "PASS" if rc == 0 else f"FAIL (exit {rc})"
        summary = ""
        if log_path.exists():
            tail = [ln for ln in log_path.read_text().splitlines() if "passed" in ln or "failed" in ln]
            summary = tail[-1].strip() if tail else ""
        print(f"  shard {i + 1}/{n}: {status}  {summary}    (log: {log_path})")

    return 0 if all(rc == 0 for rc in returncodes) else 1


if __name__ == "__main__":
    sys.exit(main())
