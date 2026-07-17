#!/usr/bin/env python3
"""
Start one or more servers, wait for them to be ready, run a command, then clean up.

Usage:
    # Use default configuration (Finance Analysis Backend & Frontend)
    python .claude/scripts/with_server.py -- python automation.py

    # single server (argv is parsed with shlex.split and run without a shell)
    python .claude/scripts/with_server.py --server "npm run dev" --port 5173 -- python automation.py

    # Multiple servers. Each --server is a single argv string. No shell is
    # invoked, so use ``bash -c '...'`` if you need shell features like cd &&.
    python .claude/scripts/with_server.py \
      --server "python backend/server.py" --port 3000 \
      --server "bash -c 'cd frontend && npm run dev'" --port 5173 \
      -- python test.py

Hardening notes (see .claude/rules/testing.md):
  - Before starting a server this script fails fast if the port is already
    bound (e.g. a stale dev-server task from another checkout), naming the
    offending PID/command via ``lsof`` when available. After the port
    reports "ready", it re-checks that the listening process is our own
    child (or a descendant sharing its process group) — this catches the
    case where a stale server respawns *during* our own startup window and
    silently steals the port.
  - Each server is started in its own process group/session
    (``start_new_session`` on POSIX) so teardown can kill the whole tree
    (e.g. ``bash -c "cd frontend && npm run dev"`` spawning npm -> vite ->
    esbuild) instead of orphaning children.
  - Server stdout/stderr are redirected to log files under the system temp
    directory (never piped and left unread) so a chatty server can't fill
    the OS pipe buffer and deadlock. Log paths are printed on failure, with
    a tail of each file, for CI/agent debugging.
"""

import argparse
import contextlib
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import IO, NamedTuple, Optional


class ListeningProcess(NamedTuple):
    """A process observed LISTENing on a TCP port.

    Attributes
    ----------
    pid : int
        Process ID of the listener.
    command : str
        Best-effort process/command name (from ``lsof``'s COMMAND column),
        used only to make error messages readable.
    """

    pid: int
    command: str


class ManagedServer:
    """Bookkeeping for one server this script started.

    Attributes
    ----------
    port : int
        TCP port the server is expected to listen on.
    argv : list of str
        The argv used to launch the process.
    cwd : str or None
        Working directory the process was launched in, if any.
    process : subprocess.Popen
        The launched process handle.
    log_path : pathlib.Path
        Path to the combined stdout/stderr log file for this server.
    log_handle : IO
        Open write handle backing ``log_path`` (passed as the process's
        stdout/stderr); kept around so it can be closed during teardown.
    """

    def __init__(
        self,
        port: int,
        argv: list,
        cwd: Optional[str],
        process: subprocess.Popen,
        log_path: Path,
        log_handle: IO,
    ) -> None:
        self.port = port
        self.argv = argv
        self.cwd = cwd
        self.process = process
        self.log_path = log_path
        self.log_handle = log_handle


def is_server_ready(port: int, timeout: int = 30) -> bool:
    """Wait for a server to be ready by polling the port.

    Parameters
    ----------
    port : int
        TCP port to poll.
    timeout : int, optional
        Maximum number of seconds to wait, by default 30.

    Returns
    -------
    bool
        True if a TCP connection to the port succeeded within ``timeout``
        seconds, False otherwise.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                return True
        except (socket.error, ConnectionRefusedError):
            time.sleep(0.5)
    return False


def _lsof_on_path() -> bool:
    """Return whether ``lsof`` is available for port-ownership checks."""
    return shutil.which("lsof") is not None


def _listening_processes(port: int) -> "list[ListeningProcess]":
    """Return every process currently LISTENing on ``port``.

    Uses ``lsof`` (present on macOS and most Linux dev environments/CI
    images). Treat an empty return as "unknown, not necessarily free" if
    ``lsof`` isn't on PATH -- callers that need a hard guarantee should check
    ``_lsof_on_path()`` separately.

    Parameters
    ----------
    port : int
        TCP port to inspect.

    Returns
    -------
    list of ListeningProcess
        One entry per distinct (pid, command) bound to the port in LISTEN
        state. Empty if none are listening, or if ``lsof`` is unavailable
        or errors out.
    """
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []

    listeners = []
    seen = set()
    for line in result.stdout.strip().splitlines()[1:]:  # skip header row
        parts = line.split()
        if len(parts) < 2:
            continue
        command, pid_str = parts[0], parts[1]
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        key = (pid, command)
        if key not in seen:
            seen.add(key)
            listeners.append(ListeningProcess(pid=pid, command=command))
    return listeners


def ensure_port_free(port: int) -> None:
    """Fail fast if ``port`` is already bound before starting a server on it.

    Prefers ``lsof`` to name the offending PID/command in the error message.
    Falls back to a raw connect probe (no external tool required) when
    ``lsof`` isn't on PATH, so the fail-fast check still works -- just
    without naming the culprit.

    Parameters
    ----------
    port : int
        TCP port the next server is about to bind.

    Raises
    ------
    RuntimeError
        If something is already listening on ``port``.
    """
    listeners = _listening_processes(port)
    if listeners:
        details = ", ".join(f"pid={p.pid} ({p.command})" for p in listeners)
        raise RuntimeError(
            f"Port {port} is already in use by: {details}. Another server "
            f"(e.g. a stale dev-server task from a different checkout/VS "
            f"Code task) is squatting on this port -- starting our own "
            f"server here would silently run tests against the wrong "
            f"backend/frontend. Stop the other process yourself and re-run; "
            f"this script will not kill it for you."
        )

    if _lsof_on_path():
        return  # lsof found nothing listening -- genuinely free.

    # No lsof available: fall back to a connect probe. Less informative
    # (can't name the PID) but still catches "port already bound".
    with contextlib.suppress(OSError):
        with socket.create_connection(("localhost", port), timeout=0.5):
            raise RuntimeError(
                f"Port {port} is already in use by an unknown process "
                f"('lsof' is unavailable here to identify it). Free the "
                f"port before running this script."
            )


def verify_port_ownership(port: int, process: subprocess.Popen) -> Optional[str]:
    """Confirm the process listening on ``port`` is ours, after readiness.

    Guards against the failure mode where a *different* process grabs the
    port during our own child's startup window (e.g. a stale server
    respawning) -- ``is_server_ready`` only confirms that *something*
    answers the socket, not that it's the process we just launched.

    Parameters
    ----------
    port : int
        Port that just reported ready.
    process : subprocess.Popen
        The process we started for this server.

    Returns
    -------
    str or None
        None if ownership was confirmed (or could not be checked because
        ``lsof``/process-group APIs are unavailable, e.g. non-POSIX). A
        human-readable warning string if ownership could not be verified but
        we're proceeding anyway. Raises instead of returning if ownership is
        actively contradicted.

    Raises
    ------
    RuntimeError
        If the child process has already exited, or a listener on the port
        belongs to a different process group than our child.
    """
    if process.poll() is not None:
        raise RuntimeError(
            f"Server process for port {port} exited (code {process.returncode}) "
            f"even though the port answered a connection -- something else "
            f"must already be listening there. Check for a stale process."
        )

    if os.name != "posix":
        return (
            "port-ownership verification skipped (requires POSIX process "
            "groups; not supported on this platform)"
        )

    listeners = _listening_processes(port)
    if not listeners:
        return (
            f"could not verify which process owns port {port} "
            f"('lsof' unavailable or returned no rows)"
        )

    try:
        expected_pgid = os.getpgid(process.pid)
    except ProcessLookupError:
        expected_pgid = None

    mismatched = []
    for listener in listeners:
        try:
            actual_pgid = os.getpgid(listener.pid)
        except ProcessLookupError:
            continue  # exited between the lsof snapshot and this check
        if expected_pgid is None or actual_pgid != expected_pgid:
            mismatched.append(listener)

    if expected_pgid is None or mismatched:
        details = ", ".join(f"pid={p.pid} ({p.command})" for p in mismatched) or "unknown"
        raise RuntimeError(
            f"Port {port} is being served by an unexpected process: {details}. "
            f"Expected our own server (pid={process.pid}). This means another "
            f"process bound the port during startup (e.g. a stale dev server "
            f"respawning mid-run) -- the command we're about to run would "
            f"silently target the wrong server. Aborting."
        )
    return None


def make_log_file(port: int) -> "tuple[Path, IO]":
    """Create a fresh combined stdout/stderr log file for a server.

    Uses the system temp directory rather than the repo, so there's no
    ``.gitignore`` upkeep and it works even against a read-only checkout.

    Parameters
    ----------
    port : int
        Port the server will listen on; embedded in the filename so
        multiple servers' logs are easy to tell apart.

    Returns
    -------
    tuple of (pathlib.Path, IO)
        The log file's path, and an open line-buffered write handle for it
        suitable for passing as ``stdout``/``stderr`` to ``subprocess.Popen``.
    """
    fd, path_str = tempfile.mkstemp(prefix=f"with_server_port{port}_", suffix=".log")
    os.close(fd)
    path = Path(path_str)
    handle = path.open("w", buffering=1)
    return path, handle


def tail_log(path: Path, lines: int = 50) -> str:
    """Return the last ``lines`` lines of a log file for failure diagnostics.

    Parameters
    ----------
    path : pathlib.Path
        Log file to read.
    lines : int, optional
        Number of trailing lines to return, by default 50.

    Returns
    -------
    str
        The trailing lines joined with newlines, or a note explaining why
        the file couldn't be read.
    """
    try:
        content = path.read_text(errors="replace").splitlines()
    except OSError as exc:
        return f"(could not read log file {path}: {exc})"
    return "\n".join(content[-lines:]) if content else "(log file is empty)"


def terminate_server(process: subprocess.Popen, grace_seconds: float = 5.0) -> None:
    """Terminate a server and its whole process tree, escalating if needed.

    Started with its own session/process group (POSIX) or process group
    (Windows) so this can reach grandchildren -- e.g. a
    ``bash -c "cd frontend && npm run dev"`` wrapper's npm -> vite -> esbuild
    chain -- instead of orphaning them when only the wrapper is killed.

    Parameters
    ----------
    process : subprocess.Popen
        The server process to stop.
    grace_seconds : float, optional
        Seconds to wait for graceful shutdown (SIGTERM) before escalating to
        SIGKILL, by default 5.0.
    """
    if process.poll() is not None:
        return  # already exited

    if os.name == "posix":
        try:
            pgid = os.getpgid(process.pid)
        except ProcessLookupError:
            return
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pgid, signal.SIGTERM)
        try:
            process.wait(timeout=grace_seconds)
            return
        except subprocess.TimeoutExpired:
            pass
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pgid, signal.SIGKILL)
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=grace_seconds)
    else:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
        )
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=grace_seconds)


def main() -> None:
    """Parse arguments, start servers, run the target command, then tear down."""
    parser = argparse.ArgumentParser(description="Run command with one or more servers")
    parser.add_argument(
        "--server",
        action="append",
        dest="servers",
        help="Server command (can be repeated)",
    )
    parser.add_argument(
        "--port",
        action="append",
        dest="ports",
        type=int,
        help="Port for each server (must match --server count)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout in seconds per server (default: 30)",
    )
    parser.add_argument(
        "command", nargs=argparse.REMAINDER, help="Command to run after server(s) ready"
    )

    args = parser.parse_args()

    # Remove the '--' separator if present
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]

    if not args.command:
        print("Error: No command specified to run")
        sys.exit(1)

    servers = []
    if args.servers:
        if not args.ports or len(args.servers) != len(args.ports):
            print("Error: Number of --server and --port arguments must match")
            sys.exit(1)
        for cmd, port in zip(args.servers, args.ports):
            servers.append({"cmd": cmd, "port": port})
    else:
        # Default configuration for Finance Analysis repo. Each entry carries
        # a ready-to-exec argv list plus the directory it should run in, so we
        # never have to invoke a shell to interpret ``cd`` or ``&&``.
        print("Using default Finance Analysis configuration...")
        servers = [
            {
                "argv": ["poetry", "run", "uvicorn", "backend.main:app", "--port", "8000"],
                "cwd": None,
                "port": 8000,
            },
            {
                "argv": ["npm", "run", "dev"],
                "cwd": "frontend",
                "port": 5173,
            },
        ]

    managed_servers = []

    try:
        # Start all servers
        for i, server in enumerate(servers):
            # When the user supplied --server strings we parse them with
            # ``shlex.split`` so the command is tokenised safely, and we invoke
            # the process with ``shell=False``. This prevents shell-metachar
            # injection (e.g. ``--server "foo; rm -rf /"``) from escaping into
            # the developer's shell.
            argv = server.get("argv")
            cwd = server.get("cwd")
            port = server["port"]
            if argv is None:
                argv = shlex.split(server["cmd"])
            display_cmd = " ".join(shlex.quote(a) for a in argv)
            where = f" (cwd={cwd})" if cwd else ""
            print(f"Starting server {i + 1}/{len(servers)}: {display_cmd}{where}")

            print(f"Checking port {port} is free...")
            ensure_port_free(port)

            log_path, log_handle = make_log_file(port)
            print(f"  logging server {i + 1} output to {log_path}")

            popen_kwargs = {}
            if os.name == "posix":
                popen_kwargs["start_new_session"] = True
            else:
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

            process = subprocess.Popen(
                argv,
                cwd=cwd if cwd is None else os.path.abspath(cwd),
                shell=False,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                **popen_kwargs,
            )
            managed = ManagedServer(
                port=port,
                argv=argv,
                cwd=cwd,
                process=process,
                log_path=log_path,
                log_handle=log_handle,
            )
            managed_servers.append(managed)

            # Wait for this server to be ready
            print(f"Waiting for server on port {port}...")
            if not is_server_ready(port, timeout=args.timeout):
                print(f"\n--- last output from {log_path} ---")
                print(tail_log(log_path))
                print("--- end log ---\n")
                raise RuntimeError(
                    f"Server failed to start on port {port} within {args.timeout}s "
                    f"(see {log_path} for its output)"
                )

            warning = verify_port_ownership(port, process)
            if warning:
                print(f"  warning: {warning}")

            print(f"Server ready on port {port}")

        print(f"\nAll {len(managed_servers)} server(s) ready")

        # Run the command
        print(f"Running: {' '.join(args.command)}\n")
        result = subprocess.run(args.command)
        sys.exit(result.returncode)

    except RuntimeError as exc:
        print(f"\nError: {exc}")
        if managed_servers:
            print("\nServer logs for debugging:")
            for managed in managed_servers:
                print(f"  port {managed.port}: {managed.log_path}")
        sys.exit(1)

    finally:
        # Clean up all servers
        print(f"\nStopping {len(managed_servers)} server(s)...")
        for i, managed in enumerate(managed_servers):
            terminate_server(managed.process)
            with contextlib.suppress(OSError):
                managed.log_handle.close()
            print(f"Server {i + 1} stopped")
        print("All servers stopped")


if __name__ == "__main__":
    main()
