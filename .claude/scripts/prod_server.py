#!/usr/bin/env python3
"""Run the production server, keep it on the latest commit, share it on the tailnet.

Launched by ``./start.sh prod`` (which bootstraps the venv and exports the
prod environment first). One process owns the whole prod lifecycle:

1. **Serve.** Builds the frontend and runs uvicorn, which serves the API and
   the built SPA from one port. The server is restarted if it dies.
2. **Share.** When Tailscale is connected, runs ``tailscale serve`` in the
   foreground as a child, so the tailnet URL (a phone signed in to the same
   tailnet) lives exactly as long as this process. tailscaled proxies from
   loopback, so tailnet requests reach the server as trusted local clients.
3. **Follow the branch.** Every ``--poll`` seconds it fast-forwards the
   checkout from its upstream (skipped when there are uncommitted changes or
   the branch diverged), and whenever HEAD moves — by that pull or by a
   manual pull/checkout — it redeploys: rebuild the frontend into
   ``dist-next/`` while the old server keeps serving, then stop the server,
   re-sync Python deps if ``poetry.lock`` changed, swap ``dist-next/`` into
   ``dist/`` and start the new code. A failed build leaves the running
   deployment untouched.

Usage::

    python .claude/scripts/prod_server.py --port 8080 [--host 127.0.0.1]
        [--poll 60] [--no-pull]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
DIST = FRONTEND / "dist"
DIST_NEXT = FRONTEND / "dist-next"
DIST_OLD = FRONTEND / "dist-old"

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
TAILSCALE_FALLBACK_PATHS = (
    "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
    r"C:\Program Files\Tailscale\tailscale.exe",
)
_PRINT_API_TOKEN = (
    "from backend.utils.auth import get_or_create_api_token; "
    "print(get_or_create_api_token())"
)
HEALTH_TIMEOUT_SECONDS = 120
RESTART_BACKOFF_SECONDS = 15


def log(message: str) -> None:
    """Print a timestamped supervisor line."""
    print(f"[prod {time.strftime('%H:%M:%S')}] {message}", flush=True)


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command in the checkout and capture its output."""
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=check
    )


def head_commit() -> str:
    """Return the checkout's current HEAD SHA."""
    return git("rev-parse", "HEAD").stdout.strip()


# --------------------------------------------------------------------------
# Redeploy planning
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RedeployPlan:
    """What a move from one commit to another requires.

    Attributes
    ----------
    build_frontend : bool
        Anything under ``frontend/`` changed, so ``dist/`` is stale.
    install_frontend_deps : bool
        ``frontend/package-lock.json`` changed, so ``npm ci`` must run first.
    sync_python_deps : bool
        ``poetry.lock`` changed, so the venv must be re-synced while the
        server is stopped (a live server would lazily import a mix of old
        and new package versions).
    """

    build_frontend: bool
    install_frontend_deps: bool
    sync_python_deps: bool


def plan_redeploy(changed_paths: Iterable[str]) -> RedeployPlan:
    """Derive a redeploy plan from the repo-relative paths that changed.

    Parameters
    ----------
    changed_paths : Iterable[str]
        Paths as printed by ``git diff --name-only`` (forward slashes).

    Returns
    -------
    RedeployPlan
        The steps needed beyond restarting the backend, which always happens.
    """
    paths = set(changed_paths)
    return RedeployPlan(
        build_frontend=any(p.startswith("frontend/") for p in paths),
        install_frontend_deps="frontend/package-lock.json" in paths,
        sync_python_deps="poetry.lock" in paths,
    )


def changed_paths_between(old: str, new: str) -> list[str]:
    """List paths changed between two commits (all paths if ``old`` is unknown)."""
    result = git("diff", "--name-only", old, new, check=False)
    if result.returncode != 0:
        return ["frontend/package-lock.json", "poetry.lock", "frontend/"]
    return [line for line in result.stdout.splitlines() if line]


# --------------------------------------------------------------------------
# Auto-pull
# --------------------------------------------------------------------------


def pull_blocker() -> str | None:
    """Return why the checkout can't be fast-forwarded now, or None if it can."""
    upstream = git(
        "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False
    )
    if upstream.returncode != 0:
        return "the current branch has no upstream"
    if git("status", "--porcelain", "--untracked-files=no").stdout.strip():
        return "the checkout has uncommitted changes"
    return None


def pull_latest() -> str | None:
    """Fast-forward the checkout from its upstream.

    Returns
    -------
    str | None
        A reason the pull was skipped or failed, or None when it succeeded
        (including when there was nothing new).
    """
    blocker = pull_blocker()
    if blocker:
        return blocker
    fetch = git("fetch", "--quiet", check=False)
    if fetch.returncode != 0:
        return f"git fetch failed: {fetch.stderr.strip() or fetch.returncode}"
    merge = git("merge", "--ff-only", "--quiet", "@{u}", check=False)
    if merge.returncode != 0:
        return "the branch has diverged from its upstream (fast-forward impossible)"
    return None


# --------------------------------------------------------------------------
# Tailscale
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TailnetShare:
    """How this machine will be shared on the tailnet.

    Attributes
    ----------
    hostname : str
        The machine's MagicDNS name, e.g. ``laptop.tail1234.ts.net``.
    url : str
        The URL other tailnet devices open.
    serve_flag : str
        The ``tailscale serve`` listener flag (``--https=443`` or ``--http=80``).
    """

    hostname: str
    url: str
    serve_flag: str


def tailnet_share_from_status(status: dict) -> tuple[TailnetShare | None, str]:
    """Decide how to share, given ``tailscale status --json`` output.

    HTTPS needs tailnet certificates (``CertDomains``); without them the
    share falls back to plain HTTP, which is still WireGuard-encrypted but
    not a browser secure context, so the PWA service worker won't install.

    Parameters
    ----------
    status : dict
        Parsed ``tailscale status --json --peers=false``.

    Returns
    -------
    tuple[TailnetShare | None, str]
        The share (None when sharing is impossible) and a human-readable
        note explaining the outcome.
    """
    if status.get("BackendState") != "Running":
        return None, "Tailscale is not connected"
    hostname = ((status.get("Self") or {}).get("DNSName") or "").rstrip(".")
    if not hostname:
        return (
            None,
            "this machine has no MagicDNS name (enable MagicDNS in the admin console)",
        )
    if status.get("CertDomains"):
        return TailnetShare(hostname, f"https://{hostname}", "--https=443"), ""
    return (
        TailnetShare(hostname, f"http://{hostname}", "--http=80"),
        (
            "tailnet HTTPS certificates are off, so sharing over plain HTTP - enable "
            "them under DNS -> HTTPS Certificates in the Tailscale admin console"
        ),
    )


def find_tailscale() -> str | None:
    """Locate the Tailscale CLI on PATH or at its standard install location."""
    found = shutil.which("tailscale")
    if found:
        return found
    for candidate in TAILSCALE_FALLBACK_PATHS:
        if Path(candidate).is_file():
            return candidate
    return None


def serve_config_active(status_json: str) -> bool:
    """Whether ``tailscale serve status --json`` shows any share on this machine.

    Foreground shares (such as another running prod server's) only appear in
    the JSON form; the plain-text status reports "No serve config" for them.
    """
    try:
        return bool(json.loads(status_json or "{}"))
    except json.JSONDecodeError:
        return True


def api_token() -> str:
    """Return the API token remote clients need, creating it on first use."""
    return subprocess.run(
        [
            sys.executable,
            "-c",
            _PRINT_API_TOKEN,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def prepare_tailnet_share() -> tuple[str | None, TailnetShare | None]:
    """Probe Tailscale and, when sharing is possible, allow its origin.

    Extends ``CORS_ORIGINS`` (the CSRF guard's origin allowlist) and
    ``ALLOWED_HOSTS`` (the Host-header allowlist) in this process's
    environment, so the server started afterwards accepts the tailnet URL.
    """
    ts_bin = find_tailscale()
    if not ts_bin:
        log("Tailscale CLI not found - serving on this machine only.")
        return None, None
    probe = subprocess.run(
        [ts_bin, "status", "--json", "--peers=false"],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        status = json.loads(probe.stdout)
    except json.JSONDecodeError:
        status = {}
    share, note = tailnet_share_from_status(status)
    if share is None:
        log(f"Not sharing on the tailnet: {note}.")
        return None, None
    if note:
        log(f"note: {note}.")
    existing = subprocess.run(
        [ts_bin, "serve", "status", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if serve_config_active(existing.stdout):
        log(
            "'tailscale serve' is already configured on this machine - leaving it alone "
            "('tailscale serve status' shows it, 'tailscale serve reset' clears it)."
        )
        return None, None
    cors = os.environ.get("CORS_ORIGINS") or DEFAULT_CORS_ORIGINS
    os.environ["CORS_ORIGINS"] = f"{cors},{share.url}"
    hosts = os.environ.get("ALLOWED_HOSTS", "")
    os.environ["ALLOWED_HOSTS"] = (
        f"{hosts},{share.hostname}" if hosts else share.hostname
    )
    return ts_bin, share


# --------------------------------------------------------------------------
# Processes
# --------------------------------------------------------------------------


def stop_process(proc: subprocess.Popen | None, name: str) -> None:
    """Terminate a child process, killing it if it ignores the request."""
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        log(f"{name} did not stop in time - killing it.")
        proc.kill()
        proc.wait()


class Server:
    """The uvicorn process serving the API and the built frontend."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.proc: subprocess.Popen | None = None

    def start(self) -> bool:
        """Start uvicorn and wait until ``/health`` answers."""
        self.proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.main:app",
                "--host",
                self.host,
                "--port",
                str(self.port),
            ],
            cwd=ROOT,
        )
        deadline = time.monotonic() + HEALTH_TIMEOUT_SECONDS
        url = f"http://127.0.0.1:{self.port}/health"
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                return False
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if response.status == 200:
                        return True
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(0.5)
        return False

    def stop(self) -> None:
        """Stop uvicorn."""
        stop_process(self.proc, "server")
        self.proc = None

    @property
    def alive(self) -> bool:
        """Whether the uvicorn process is running."""
        return self.proc is not None and self.proc.poll() is None


def run_step(argv: list[str], cwd: Path) -> bool:
    """Run a build step with inherited output, returning whether it succeeded."""
    return subprocess.run(argv, cwd=cwd, check=False).returncode == 0


def build_frontend(install_deps: bool) -> bool:
    """Build the frontend into ``dist-next/`` without touching the live ``dist/``."""
    npm = shutil.which("npm")
    if not npm:
        log("npm not found on PATH - cannot build the frontend.")
        return False
    if install_deps and not run_step([npm, "ci"], FRONTEND):
        return False
    shutil.rmtree(DIST_NEXT, ignore_errors=True)
    ok = run_step(
        [npm, "run", "build", "--", "--outDir", DIST_NEXT.name, "--emptyOutDir"],
        FRONTEND,
    )
    if not ok:
        shutil.rmtree(DIST_NEXT, ignore_errors=True)
    return ok


def swap_in_new_dist() -> None:
    """Replace ``dist/`` with ``dist-next/`` (call only while the server is stopped)."""
    shutil.rmtree(DIST_OLD, ignore_errors=True)
    if DIST.exists():
        DIST.rename(DIST_OLD)
    DIST_NEXT.rename(DIST)
    shutil.rmtree(DIST_OLD, ignore_errors=True)


def sync_python_deps() -> bool:
    """Re-sync the venv via the bootstrap script (it re-installs on a lock change)."""
    bash = shutil.which("bash")
    if not bash:
        log("bash not found - cannot re-sync Python dependencies.")
        return False
    return run_step([bash, ".claude/scripts/bootstrap_venv.sh"], ROOT)


# --------------------------------------------------------------------------
# Supervisor
# --------------------------------------------------------------------------


class Supervisor:
    """Owns the server, the tailnet share and the follow-the-branch loop."""

    def __init__(
        self, host: str, port: int, poll_seconds: int, auto_pull: bool
    ) -> None:
        self.server = Server(host, port)
        self.poll_seconds = poll_seconds
        self.auto_pull = auto_pull
        self.deployed = head_commit()
        self.failed_commit: str | None = None
        self.last_pull_note: str | None = None
        self.ts_bin: str | None = None
        self.share: TailnetShare | None = None
        self.serve_proc: subprocess.Popen | None = None

    def run(self) -> int:
        """Build, start and supervise until interrupted."""
        log(f"Building frontend for {self.deployed[:8]}...")
        if not build_frontend(install_deps=not (FRONTEND / "node_modules").is_dir()):
            log("Initial frontend build failed.")
            return 1
        swap_in_new_dist()
        self.ts_bin, self.share = prepare_tailnet_share()
        if not self.server.start():
            log("Server failed to start.")
            return 1
        self.start_share()
        self.announce()
        next_poll = time.monotonic() + self.poll_seconds
        last_restart = 0.0
        while True:
            time.sleep(1)
            if (
                not self.server.alive
                and time.monotonic() - last_restart > RESTART_BACKOFF_SECONDS
            ):
                log("Server exited unexpectedly - restarting.")
                last_restart = time.monotonic()
                self.server.start()
            if time.monotonic() < next_poll:
                continue
            next_poll = time.monotonic() + self.poll_seconds
            if self.auto_pull:
                self.pull()
            head = head_commit()
            if head not in (self.deployed, self.failed_commit):
                self.redeploy(head)

    def announce(self) -> None:
        """Print where the app is reachable and what the loop does."""
        log(
            f"Serving {self.deployed[:8]} on http://{self.server.host}:{self.server.port}"
        )
        if self.share and self.serve_proc:
            log(f"Tailnet: {self.share.url}")
            log(
                "Sign in a new device once with: "
                f"{self.share.url}/?apiToken={api_token()}"
            )
        mode = (
            "pulling from upstream and redeploying" if self.auto_pull else "redeploying"
        )
        log(f"Checking every {self.poll_seconds}s - {mode} when HEAD moves.")

    def pull(self) -> None:
        """Fast-forward from upstream, logging a skip reason only when it changes."""
        note = pull_latest()
        if note and note != self.last_pull_note:
            log(f"Auto-pull skipped: {note}.")
        elif not note and self.last_pull_note:
            log("Auto-pull resumed.")
        self.last_pull_note = note

    def redeploy(self, head: str) -> None:
        """Move the running deployment from ``self.deployed`` to ``head``."""
        plan = plan_redeploy(changed_paths_between(self.deployed, head))
        log(f"HEAD moved {self.deployed[:8]} -> {head[:8]} - redeploying.")
        if plan.build_frontend and not build_frontend(plan.install_frontend_deps):
            log(
                f"Frontend build failed - still serving {self.deployed[:8]}. "
                "Fix it and commit; the next commit is picked up automatically."
            )
            self.failed_commit = head
            return
        self.server.stop()
        if plan.sync_python_deps and not sync_python_deps():
            log("Python dependency sync failed - starting the server anyway.")
        if plan.build_frontend:
            swap_in_new_dist()
        self.deployed = head
        self.failed_commit = None
        if self.server.start():
            log(f"Now serving {head[:8]}.")
        else:
            log(f"Server failed to start on {head[:8]} - will keep retrying.")

    def start_share(self) -> None:
        """Run ``tailscale serve`` in the foreground as a child process."""
        if not (self.ts_bin and self.share):
            return
        self.serve_proc = subprocess.Popen(
            [
                self.ts_bin,
                "serve",
                self.share.serve_flag,
                f"http://127.0.0.1:{self.server.port}",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(2)
        if self.serve_proc.poll() is not None:
            error = (self.serve_proc.stderr.read() or "").strip()
            log(f"'tailscale serve' exited: {error or self.serve_proc.returncode}")
            self.serve_proc = None

    def shutdown(self) -> None:
        """Stop the tailnet share and the server."""
        stop_process(self.serve_proc, "tailscale serve")
        self.server.stop()


def main() -> int:
    """Parse arguments and run the supervisor until interrupted."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--poll",
        type=int,
        default=int(os.environ.get("PROD_POLL_SECONDS", "60")),
        help="seconds between upstream checks (env PROD_POLL_SECONDS)",
    )
    parser.add_argument(
        "--no-pull",
        action="store_true",
        default=os.environ.get("PROD_AUTO_PULL", "1") == "0",
        help="only redeploy on manual pulls; never fetch (env PROD_AUTO_PULL=0)",
    )
    args = parser.parse_args()

    supervisor = Supervisor(args.host, args.port, args.poll, auto_pull=not args.no_pull)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        return supervisor.run()
    except KeyboardInterrupt:
        return 0
    finally:
        log("Shutting down.")
        supervisor.shutdown()


if __name__ == "__main__":
    sys.exit(main())
