#!/usr/bin/env python3
"""
Start one or more servers, wait for them to be ready, run a command, then clean up.

Usage:
    # Use default configuration (Finance Analysis Backend & Frontend)
    python .claude/scripts/with_server.py -- python automation.py

    # single server
    python .claude/scripts/with_server.py --server "npm run dev" --port 5173 -- python automation.py

    # Multiple servers
    python .claude/scripts/with_server.py \
      --server "cd backend && python server.py" --port 3000 \
      --server "cd frontend && npm run dev" --port 5173 \
      -- python test.py
"""

import argparse
import os
import shlex
import socket
import subprocess
import sys
import time


def is_server_ready(port, timeout=30):
    """Wait for server to be ready by polling the port."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                return True
        except (socket.error, ConnectionRefusedError):
            time.sleep(0.5)
    return False


def main():
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

    server_processes = []

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
            if argv is None:
                argv = shlex.split(server["cmd"])
            display_cmd = " ".join(shlex.quote(a) for a in argv)
            where = f" (cwd={cwd})" if cwd else ""
            print(f"Starting server {i + 1}/{len(servers)}: {display_cmd}{where}")

            process = subprocess.Popen(
                argv,
                cwd=cwd if cwd is None else os.path.abspath(cwd),
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            server_processes.append(process)

            # Wait for this server to be ready
            print(f"Waiting for server on port {server['port']}...")
            if not is_server_ready(server["port"], timeout=args.timeout):
                raise RuntimeError(
                    f"Server failed to start on port {server['port']} within {args.timeout}s"
                )

            print(f"Server ready on port {server['port']}")

        print(f"\nAll {len(servers)} server(s) ready")

        # Run the command
        print(f"Running: {' '.join(args.command)}\n")
        result = subprocess.run(args.command)
        sys.exit(result.returncode)

    finally:
        # Clean up all servers
        print(f"\nStopping {len(server_processes)} server(s)...")
        for i, process in enumerate(server_processes):
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            print(f"Server {i + 1} stopped")
        print("All servers stopped")


if __name__ == "__main__":
    main()
