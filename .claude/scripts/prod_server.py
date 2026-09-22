#!/usr/bin/env python3
"""Run the production server, keep it on the latest commit, share it on the tailnet.

Launched by ``./start.sh prod`` (which bootstraps the venv and exports the
prod environment first). One process owns the whole prod lifecycle:

1. **Serve.** Builds the frontend and runs uvicorn, which serves the API and
   the built SPA from one port. The server is restarted if it dies, and also
   if it stops answering ``/health`` while still running: on Windows a single
   failed accept (e.g. ``WinError 10055`` under a burst of sockets) makes
   asyncio's Proactor loop close the listening socket for good, leaving a live
   process that no longer takes connections.
2. **Share.** When Tailscale is connected, runs ``tailscale serve`` in the
   foreground as a child, so the tailnet URL (a phone signed in to the same
   tailnet) lives exactly as long as this process. ``tailscale serve`` is
   pointed at a loopback port of its own (``TAILNET_INGRESS_PORT``), the only
   listener on which the backend believes the ``Tailscale-User-Login``
   identity it vouches for — another local proxy in front of ``--port``
   could otherwise relay a forged one.
3. **Follow the branch.** Every ``--poll`` seconds it checks HEAD, and
   whenever HEAD moves — by a manual pull/checkout, or, with ``--auto-pull``
   (``PROD_AUTO_PULL=1``), by fast-forwarding the checkout from its upstream
   (skipped when there are uncommitted changes or the branch diverged) — it
   redeploys: rebuild the frontend into
   ``dist-next/`` while the old server keeps serving, then stop the server,
   re-sync Python deps if ``poetry.lock`` changed, swap ``dist-next/`` into
   ``dist/`` and start the new code. A failed build leaves the running
   deployment untouched.

   The redeploy does only what the commit range actually requires, because
   everything it skips is time a browser spends on the old build. In
   particular a Commitizen ``bump:`` commit — which every release pushes ~45 s
   behind the merge it releases — rewrites nothing but version strings, and
   is therefore a bare server restart rather than a second ``npm ci`` and
   bundle build. See ``plan_redeploy``.

   Auto-pull is opt-in because it runs whatever reaches the upstream branch
   — including ``npm ci`` install scripts — within seconds, unreviewed, on
   the machine that holds the financial database and the keyring. Signature
   checks cannot vouch for it: the branch head is always the release job's
   ``bump:`` commit, which CI pushes with a token.

Usage::

    python .claude/scripts/prod_server.py --port 8080 [--host 127.0.0.1]
        [--poll 15] [--auto-pull]
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
DIST = FRONTEND / "dist"
DIST_NEXT = FRONTEND / "dist-next"
DIST_OLD = FRONTEND / "dist-old"

TAILSCALE_FALLBACK_PATHS = (
    "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
    r"C:\Program Files\Tailscale\tailscale.exe",
)
HEALTH_TIMEOUT_SECONDS = 120
RESTART_BACKOFF_SECONDS = 15
HEALTH_CHECK_INTERVAL_SECONDS = 10
HEALTH_PROBE_TIMEOUT_SECONDS = 5
HEALTH_FAILURES_BEFORE_RESTART = 3


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


# The npm manifests Commitizen rewrites on every release (``version_files``
# in pyproject.toml). Nothing else in them is touched by a bump.
VERSIONED_NPM_MANIFESTS = ("frontend/package.json", "frontend/package-lock.json")


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


def plan_redeploy(
    changed_paths: Iterable[str], version_only_paths: Iterable[str] = ()
) -> RedeployPlan:
    """Derive a redeploy plan from the repo-relative paths that changed.

    Parameters
    ----------
    changed_paths : Iterable[str]
        Paths as printed by ``git diff --name-only`` (forward slashes).
    version_only_paths : Iterable[str]
        Paths whose whole diff across this range is the app's own version
        string — see ``version_only_manifests``. They are subtracted before
        the plan is derived, because nothing they changed reaches the build.

    Returns
    -------
    RedeployPlan
        The steps needed beyond restarting the backend, which always happens.
    """
    paths = set(changed_paths) - set(version_only_paths)
    return RedeployPlan(
        build_frontend=any(p.startswith("frontend/") for p in paths),
        install_frontend_deps="frontend/package-lock.json" in paths,
        sync_python_deps="poetry.lock" in paths,
    )


def _manifest_without_app_version(commit: str, path: str) -> dict | None:
    """Read a JSON manifest at a commit with the app's own version removed.

    Returns None when the file can't be read or parsed there, which the
    caller must treat as "assume it really changed".
    """
    result = git("show", f"{commit}:{path}", check=False)
    if result.returncode != 0:
        return None
    try:
        doc = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(doc, dict):
        return None
    doc.pop("version", None)
    packages = doc.get("packages")
    # package-lock.json carries the app version twice: at the top level and
    # on the root `packages[""]` entry. Commitizen rewrites both.
    if isinstance(packages, dict) and isinstance(packages.get(""), dict):
        packages[""].pop("version", None)
    return doc


def version_only_manifests(
    old: str, new: str, changed_paths: Iterable[str]
) -> set[str]:
    """Which npm manifests moved by nothing but the app's own version string.

    Every release pushes a Commitizen ``bump:`` commit that rewrites the
    version in ``frontend/package.json`` and ``frontend/package-lock.json``.
    Judged by path alone that reads as a frontend change *and* a dependency
    change, so every single release rebuilt the bundle and reinstalled
    ``node_modules`` from scratch — minutes of work for two rewritten lines,
    and minutes during which browsers are still being served the old build.

    Nothing in the bundle depends on those lines: the frontend never imports
    its own version (Settings → About reads it from ``GET /api/version``,
    which the restarted backend answers from ``pyproject.toml``). So a
    version-only rewrite is safely subtracted from the plan.

    Comparing parsed manifests, rather than diffing text, is what keeps this
    honest: a commit that bumps the version *and* adds a dependency differs
    by more than the version and still triggers ``npm ci``.
    """
    candidates = set(changed_paths) & set(VERSIONED_NPM_MANIFESTS)
    version_only = set()
    for path in candidates:
        before = _manifest_without_app_version(old, path)
        after = _manifest_without_app_version(new, path)
        if before is not None and before == after:
            version_only.add(path)
    return version_only


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
    owner_login : str
        The Tailscale login that owns this machine (empty if unknown). Its
        devices are let in on their tailnet identity, without a token.
    """

    hostname: str
    url: str
    serve_flag: str
    owner_login: str = ""


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
    owner_id = (status.get("Self") or {}).get("UserID")
    owner = ((status.get("User") or {}).get(str(owner_id)) or {}).get("LoginName", "")
    if status.get("CertDomains"):
        return TailnetShare(hostname, f"https://{hostname}", "--https=443", owner), ""
    return (
        TailnetShare(hostname, f"http://{hostname}", "--http=80", owner),
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


def prepare_tailnet_share() -> tuple[str | None, TailnetShare | None]:
    """Probe Tailscale and, when sharing is possible, allow its origin.

    Extends ``CORS_ORIGINS`` (the CSRF guard's origin allowlist) and
    ``ALLOWED_HOSTS`` (the Host-header allowlist) in this process's
    environment, so the server started afterwards accepts the tailnet URL,
    and defaults ``TAILNET_ALLOWED_USERS`` to this machine's owner so their
    devices get in on the identity ``tailscale serve`` vouches for.
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
    cors = os.environ.get("CORS_ORIGINS", "")
    os.environ["CORS_ORIGINS"] = f"{cors},{share.url}" if cors else share.url
    hosts = os.environ.get("ALLOWED_HOSTS", "")
    os.environ["ALLOWED_HOSTS"] = (
        f"{hosts},{share.hostname}" if hosts else share.hostname
    )
    if share.owner_login and not os.environ.get("TAILNET_ALLOWED_USERS"):
        os.environ["TAILNET_ALLOWED_USERS"] = share.owner_login
    os.environ["TAILNET_INGRESS_PORT"] = str(free_loopback_port())
    return ts_bin, share


def free_loopback_port() -> int:
    """Return a loopback TCP port nothing is listening on right now."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def tailnet_ingress_port() -> int | None:
    """The loopback port reserved for ``tailscale serve``, when sharing."""
    raw = os.environ.get("TAILNET_INGRESS_PORT", "")
    return int(raw) if raw.isdigit() else None


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
        argv = [
            sys.executable,
            str(ROOT / ".claude" / "scripts" / "serve_app.py"),
            "--host",
            self.host,
            "--port",
            str(self.port),
        ]
        ingress = tailnet_ingress_port()
        if ingress is not None:
            argv += ["--tailnet-port", str(ingress)]
        self.proc = subprocess.Popen(argv, cwd=ROOT)
        deadline = time.monotonic() + HEALTH_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                return False
            if self.healthy(timeout=2):
                return True
            time.sleep(0.5)
        return False

    def healthy(self, timeout: float = HEALTH_PROBE_TIMEOUT_SECONDS) -> bool:
        """Whether ``/health`` answers 200 within ``timeout`` seconds."""
        url = f"http://127.0.0.1:{self.port}/health"
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return response.status == 200
        except (urllib.error.URLError, OSError):
            return False

    def stop(self) -> None:
        """Stop uvicorn."""
        stop_process(self.proc, "server")
        self.proc = None

    @property
    def alive(self) -> bool:
        """Whether the uvicorn process is running."""
        return self.proc is not None and self.proc.poll() is None


def build_env(environ: Mapping[str, str]) -> dict[str, str]:
    """Return ``environ`` without VS Code's Node debugger auto-attach hook.

    A VS Code terminal with auto-attach on exports ``NODE_OPTIONS=--require
    .../js-debug/bootloader.js``, so every node process of the build (npm,
    tsc, vite) attaches to the debugger and waits for it to disconnect. Any
    other ``NODE_OPTIONS`` flag is kept.
    """
    env = {k: v for k, v in environ.items() if k != "VSCODE_INSPECTOR_OPTIONS"}
    posix = os.name != "nt"
    tokens = shlex.split(env.get("NODE_OPTIONS", ""), posix=posix)
    kept: list[str] = []
    i = 0
    while i < len(tokens):
        if tokens[i] in ("--require", "-r") and i + 1 < len(tokens):
            if "js-debug" in tokens[i + 1]:
                i += 2
                continue
        elif tokens[i].startswith("--require=") and "js-debug" in tokens[i]:
            i += 1
            continue
        kept.append(tokens[i])
        i += 1
    if kept:
        env["NODE_OPTIONS"] = shlex.join(kept) if posix else " ".join(kept)
    else:
        env.pop("NODE_OPTIONS", None)
    return env


def run_step(argv: list[str], cwd: Path) -> bool:
    """Run a build step with inherited output, returning whether it succeeded."""
    return (
        subprocess.run(argv, cwd=cwd, env=build_env(os.environ), check=False).returncode
        == 0
    )


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
        self.health_failures = 0

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
        next_health_check = time.monotonic() + HEALTH_CHECK_INTERVAL_SECONDS
        last_restart = 0.0
        while True:
            time.sleep(1)
            if not self.server.alive:
                if time.monotonic() - last_restart > RESTART_BACKOFF_SECONDS:
                    log("Server exited unexpectedly - restarting.")
                    last_restart = time.monotonic()
                    self.health_failures = 0
                    self.server.start()
            elif time.monotonic() >= next_health_check:
                next_health_check = time.monotonic() + HEALTH_CHECK_INTERVAL_SECONDS
                if self.check_health():
                    last_restart = time.monotonic()
            if time.monotonic() < next_poll:
                continue
            next_poll = time.monotonic() + self.poll_seconds
            if self.auto_pull:
                self.pull()
            head = head_commit()
            if head not in (self.deployed, self.failed_commit):
                self.redeploy(head)

    def check_health(self) -> bool:
        """Probe the running server and restart it once it stops answering.

        A single missed probe is tolerated (a slow response under load); only
        ``HEALTH_FAILURES_BEFORE_RESTART`` misses in a row count as a server
        that is up but no longer serving.

        Returns
        -------
        bool
            True when this probe triggered a restart.
        """
        if self.server.healthy():
            self.health_failures = 0
            return False
        self.health_failures += 1
        if self.health_failures < HEALTH_FAILURES_BEFORE_RESTART:
            return False
        log(
            f"Server is running but has not answered /health {self.health_failures} "
            "times in a row - restarting."
        )
        self.health_failures = 0
        self.server.stop()
        self.server.start()
        return True

    def announce(self) -> None:
        """Print where the app is reachable and what the loop does."""
        log(
            f"Serving {self.deployed[:8]} on http://{self.server.host}:{self.server.port}"
        )
        if self.share and self.serve_proc:
            log(f"Tailnet: {self.share.url}")
            users = os.environ.get("TAILNET_ALLOWED_USERS", "")
            if users:
                log(f"Open it on any tailnet device signed in as: {users}")
            else:
                log("No tailnet users allowlisted - set TAILNET_ALLOWED_USERS.")
        mode = (
            "pulling from upstream and redeploying"
            if self.auto_pull
            else "redeploying (auto-pull off; PROD_AUTO_PULL=1 turns it on)"
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
        paths = changed_paths_between(self.deployed, head)
        plan = plan_redeploy(paths, version_only_manifests(self.deployed, head, paths))
        steps = [
            name
            for name, needed in (
                ("npm ci", plan.install_frontend_deps),
                ("frontend build", plan.build_frontend),
                ("poetry install", plan.sync_python_deps),
            )
            if needed
        ]
        log(
            f"HEAD moved {self.deployed[:8]} -> {head[:8]} - redeploying "
            f"({', '.join(steps + ['restart'])})."
        )
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
                f"http://127.0.0.1:{tailnet_ingress_port()}",
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
        default=int(os.environ.get("PROD_POLL_SECONDS", "15")),
        help="seconds between upstream checks (env PROD_POLL_SECONDS)",
    )
    parser.add_argument(
        "--auto-pull",
        action="store_true",
        default=os.environ.get("PROD_AUTO_PULL", "0") == "1",
        help=(
            "fast-forward from upstream and deploy whatever lands there, "
            "unreviewed (env PROD_AUTO_PULL=1); off by default"
        ),
    )
    args = parser.parse_args()

    supervisor = Supervisor(args.host, args.port, args.poll, auto_pull=args.auto_pull)
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
