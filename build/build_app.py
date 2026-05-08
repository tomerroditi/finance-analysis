"""End-to-end builder for the self-contained desktop app.

Run from the repo root:

    python build/build_app.py

What it does, in order:

    1. Build the React frontend (``cd frontend && npm run build``).
    2. Run PyInstaller against ``build/finance_analysis.spec``.
       Output lands in ``dist/Finance Analysis.app`` (macOS) or
       ``dist/FinanceAnalysis/`` (Windows).
    3. Wrap:
        * macOS: ``bash build/build_dmg.sh`` produces
          ``FinanceAnalysis-<arch>.dmg``.
        * Windows: ``makensis build/installer_script.nsi`` produces
          ``FinanceAppInstaller.exe``.

Skip the ``npm run build`` step with ``--no-frontend`` when iterating
on the PyInstaller spec.

Note: we deliberately do NOT bundle Playwright's Chromium binary.
The scraper uses the user's installed Chrome (or Edge as a Windows
fallback) via ``channel="chrome"``. Bundling Chromium would add ~800MB
to the artifact and freeze a specific revision against bank
fingerprinting; using the system browser keeps the bundle small and
auto-updates with the user's browser. See
``scraper/base/browser_scraper.py::BrowserScraper.initialize``.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Force UTF-8 on Windows so prints with non-ASCII chars (or pyinstaller
# log lines that pass through us) don't trip the default cp1252
# codec — that crashes the build job with UnicodeEncodeError on a
# stray "->" rendered as U+2192.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None) -> None:
    """Run ``cmd`` and raise ``SystemExit`` on non-zero exit.

    Inherits stdout/stderr so the developer sees real-time progress
    from npm / pyinstaller / makensis.

    On Windows we resolve the executable through ``shutil.which`` (and
    fall back to ``shell=True``) because Python's ``subprocess.run``
    doesn't auto-append the ``.cmd``/``.bat`` extensions that npm and
    other Node-installed scripts ship as. Without this, ``npm ci``
    raises ``FileNotFoundError: [WinError 2] The system cannot find
    the file specified`` — even though ``npm`` is on PATH, it lives at
    ``npm.cmd`` and CreateProcess won't find it bare.
    """
    print(f"\n>> {' '.join(cmd)}  (cwd={cwd or ROOT})")
    if sys.platform == "win32" and cmd:
        resolved = shutil.which(cmd[0])
        if resolved:
            cmd = [resolved, *cmd[1:]]
        else:
            # Last-resort fallback: let cmd.exe resolve PATHEXT.
            completed = subprocess.run(
                " ".join(f'"{a}"' if " " in a else a for a in cmd),
                cwd=cwd or ROOT,
                env=env,
                shell=True,
            )
            if completed.returncode != 0:
                sys.exit(f"command failed (exit {completed.returncode}): {' '.join(cmd)}")
            return
    completed = subprocess.run(cmd, cwd=cwd or ROOT, env=env)
    if completed.returncode != 0:
        sys.exit(f"command failed (exit {completed.returncode}): {' '.join(cmd)}")


def _step_frontend() -> None:
    """Build the React app into ``frontend/dist/``."""
    _run(["npm", "ci"], cwd=ROOT / "frontend")
    _run(["npm", "run", "build"], cwd=ROOT / "frontend")


def _step_pyinstaller() -> None:
    """Invoke PyInstaller on the spec.

    Removes ``dist/`` first so we never accidentally ship leftover
    files from a previous build.
    """
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    _run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--workpath",
            str(BUILD_DIR / ".pyinstaller-work"),
            str(BUILD_DIR / "finance_analysis.spec"),
        ],
    )


def _step_wrap_darwin() -> None:
    """Run ``build_dmg.sh`` on macOS to produce the architecture-tagged DMG."""
    arch = platform.machine().lower()  # "arm64" or "x86_64"
    env = {**os.environ, "FINANCE_ANALYSIS_DMG_ARCH": arch}
    _run(["bash", str(BUILD_DIR / "build_dmg.sh")], env=env)


def _step_wrap_windows() -> None:
    """Run ``makensis`` to produce ``FinanceAppInstaller.exe``."""
    _run(["makensis", str(BUILD_DIR / "installer_script.nsi")])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the desktop app.")
    parser.add_argument(
        "--no-frontend",
        action="store_true",
        help="Skip `npm run build` (when iterating on the spec).",
    )
    parser.add_argument(
        "--no-wrap",
        action="store_true",
        help="Skip the DMG / NSIS wrapping step.",
    )
    args = parser.parse_args(argv)

    print(f"build_app.py - platform={sys.platform} arch={platform.machine()}")

    if not args.no_frontend:
        _step_frontend()
    _step_pyinstaller()
    if not args.no_wrap:
        if sys.platform == "darwin":
            _step_wrap_darwin()
        elif sys.platform == "win32":
            _step_wrap_windows()
        else:
            print(f"no wrapping step defined for {sys.platform}; skipping")

    print("\n[OK] build complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
