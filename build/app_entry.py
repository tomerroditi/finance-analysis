"""Entry point for the PyInstaller-bundled Finance Analysis desktop app.

PyInstaller wraps this script in a native bootloader binary that becomes
``Contents/MacOS/FinanceAnalysis`` (macOS) and ``FinanceAnalysis.exe``
(Windows). It replaces the entire pre-PyInstaller chain — ``launcher.sh``,
``setup.sh``, ``run.sh``, ``setup.bat``, ``run.bat``, ``find_port.py`` —
with a single Python process.

Three modes, selected by argv:

* **default**: pick a free port, configure file logging, start uvicorn
  in-process, open the user's default browser, block on signal.
* **``--smoke-test``**: boot uvicorn, hit ``/api/version`` against the
  bundle's own backend, assert HTTP 200, exit. Used by CI to catch
  PyInstaller spec regressions (missing hidden imports, missing data
  files) before the artifact ships.
* **``--uninstall-cleanup [--wipe|--keep-data]``**: invoke
  ``backend.uninstall.cleanup.run`` and exit. The Windows NSIS
  uninstaller calls the bundled binary in this mode now that there's
  no in-INSTDIR venv to run ``python -m backend.uninstall`` from.

All three modes share the same env-var setup: ``FAD_USER_DIR`` defaults
to ``~/.finance-analysis``; ``PLAYWRIGHT_BROWSERS_PATH`` is pointed at
the bundled Chromium copy so Playwright doesn't try to download it on
first scrape.
"""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import signal
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

# Surface a helpful version string in --help even though the bundle's
# canonical version source is pyproject.toml (read at runtime by
# backend.utils.version.get_app_version).
__app_name__ = "Finance Analysis"


# ---------------------------------------------------------------------------
# Helpers (resource paths, env, logging, port picking).
# ---------------------------------------------------------------------------


def _resource_root() -> Path:
    """Return the directory holding bundled data files at runtime.

    PyInstaller's bootloader sets ``sys._MEIPASS`` to a temp directory
    where it has unpacked all data files declared in the .spec's
    ``datas`` list. When we're not frozen (running this script from the
    repo for tests or local dev), fall back to the repo root so we
    still find ``frontend/dist`` etc.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", "."))
    return Path(__file__).resolve().parent.parent


def _user_dir() -> Path:
    return Path(os.environ.get("FAD_USER_DIR", str(Path.home() / ".finance-analysis")))


def _setup_env() -> Path:
    """Set the env vars all three modes need; return the user-data dir."""
    user = _user_dir()
    user.mkdir(parents=True, exist_ok=True)
    (user / "logs").mkdir(parents=True, exist_ok=True)
    os.environ["FAD_USER_DIR"] = str(user)
    # Tell Playwright to look inside the bundle for its browser.
    bundled_pw = _resource_root() / "playwright_browsers"
    if bundled_pw.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(bundled_pw)
    return user


def _configure_file_logging(user_dir: Path) -> None:
    """Route uvicorn + backend logs to a rotating file.

    Must run **before** ``backend.main`` is imported because the FastAPI
    lifespan hook produces log records during startup. Without this,
    those records go to a dropped stderr (PyInstaller GUI apps on macOS
    have no console) and we'd lose the only debugging trail when a user
    files a bug.
    """
    log_path = user_dir / "logs" / "uvicorn.log"
    handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Replace any handlers PyInstaller's bootloader might have left around.
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)


def _pick_port() -> int:
    """Bind to port 0 to let the OS pick a free port, then close and reuse."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout_s: float = 10.0) -> bool:
    """Poll ``127.0.0.1:port`` until something is accepting connections.

    Used by the browser-open thread so we don't navigate the browser to
    "Connection refused" before uvicorn is actually listening.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


# ---------------------------------------------------------------------------
# Modes.
# ---------------------------------------------------------------------------


def _build_uvicorn_server(port: int):
    """Construct a uvicorn.Server bound to the FastAPI app.

    Imported lazily so ``--uninstall-cleanup`` doesn't pay the cost of
    importing all of backend (and triggering its lifespan startup) just
    to delete some files.
    """
    import uvicorn

    from backend.main import app

    config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_config=None, lifespan="on"
    )
    return uvicorn.Server(config)


def _run_default_mode() -> int:
    """Default behaviour: start uvicorn, open browser, block until signaled."""
    user = _setup_env()
    _configure_file_logging(user)
    port = _pick_port()
    server = _build_uvicorn_server(port)

    def _open_when_ready() -> None:
        if _wait_for_port(port, timeout_s=10.0):
            opened = webbrowser.open(f"http://127.0.0.1:{port}")
            if not opened:
                logging.getLogger(__name__).warning(
                    "Couldn't auto-open browser — visit http://127.0.0.1:%s manually",
                    port,
                )
        else:
            logging.getLogger(__name__).error(
                "uvicorn did not start within 10s; not opening browser"
            )

    threading.Thread(target=_open_when_ready, daemon=True).start()

    # On Cmd-Q / window-close macOS sends SIGTERM; uvicorn's default
    # signal handler turns that into a graceful shutdown. We register a
    # SIGINT handler too so Ctrl-C in a debug terminal also exits cleanly.
    def _stop(_sig, _frame):
        server.should_exit = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    server.run()
    return 0


def _run_smoke_test() -> int:
    """Boot the bundle, issue one self-request to /api/version, exit.

    This is the load-bearing CI gate. PyInstaller's static analysis
    sometimes misses hidden imports (a new SQLAlchemy dialect, a
    Pydantic validator, a uvicorn protocol loader). The build-time
    smoke test exercises a real round-trip through every layer the
    user will hit on first launch — bootloader → Python →
    backend.main lifespan → uvicorn → FastAPI → routes → response —
    and exits 0 only if it all works. A failure here means the bundle
    is broken; we surface it as a CI red-x instead of shipping.
    """
    user = _setup_env()
    _configure_file_logging(user)
    port = _pick_port()
    server = _build_uvicorn_server(port)

    failures: list[str] = []

    def _probe():
        if not _wait_for_port(port, timeout_s=15.0):
            failures.append("uvicorn never opened the port")
            server.should_exit = True
            return
        try:
            import urllib.request

            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/version", timeout=5.0
            ) as resp:
                if resp.status != 200:
                    failures.append(f"/api/version returned {resp.status}")
                else:
                    body = json.loads(resp.read().decode())
                    if not body.get("version"):
                        failures.append(f"/api/version body has no version: {body}")
                    else:
                        print(
                            f"smoke-test ok: {body['version']} on {body.get('platform')}"
                        )
        except Exception as exc:
            failures.append(f"probe raised: {exc}")
        finally:
            server.should_exit = True

    threading.Thread(target=_probe, daemon=True).start()
    server.run()

    if failures:
        for f in failures:
            print(f"smoke-test failed: {f}", file=sys.stderr)
        return 1
    return 0


def _run_uninstall_cleanup(wipe_data: bool) -> int:
    """Delegate to ``backend.uninstall.cleanup.run`` and print the JSON report.

    Invoked by the Windows NSIS uninstaller as
    ``FinanceAnalysis.exe --uninstall-cleanup [--wipe|--keep-data]``,
    replacing the previous ``python -m backend.uninstall`` invocation
    that no longer works (no venv inside ``$INSTDIR``). The cleanup
    module itself is unchanged — same source of truth, new entry path.
    """
    # No file logging here — this runs at uninstall time, when the user
    # may have already nuked ~/.finance-analysis/. Fall through to
    # stdout so NSIS captures it via nsExec::ExecToLog.
    from backend.uninstall.cleanup import run as run_cleanup

    report = run_cleanup(wipe_data=wipe_data)
    print(json.dumps(report.as_dict(), indent=2))
    return 1 if report.errors else 0


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog=__app_name__,
        description="Finance Analysis desktop app entry point.",
        add_help=True,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--smoke-test",
        action="store_true",
        help="Boot, hit /api/version, exit. Used by CI.",
    )
    mode.add_argument(
        "--uninstall-cleanup",
        action="store_true",
        help="Run the cleanup CLI. Pair with --wipe or --keep-data.",
    )
    parser.add_argument(
        "--wipe",
        action="store_true",
        help="(With --uninstall-cleanup) also delete ~/.finance-analysis.",
    )
    parser.add_argument(
        "--keep-data",
        action="store_true",
        help="(With --uninstall-cleanup) preserve ~/.finance-analysis.",
    )

    args, _ = parser.parse_known_args(argv)

    if args.uninstall_cleanup:
        if args.wipe == args.keep_data:
            parser.error("--uninstall-cleanup requires exactly one of --wipe or --keep-data")
        return _run_uninstall_cleanup(wipe_data=args.wipe)

    if args.smoke_test:
        return _run_smoke_test()

    return _run_default_mode()


if __name__ == "__main__":
    sys.exit(main())
