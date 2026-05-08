"""End-to-end builder for the self-contained desktop app.

Run from the repo root:

    python build/build_app.py

What it does, in order:

    1. Build the React frontend (``cd frontend && npm run build``).
    2. Provision Playwright's Chromium into a build-local cache so the
       PyInstaller spec can pick it up via ``PLAYWRIGHT_BROWSERS_PATH``.
       This step is hermetic — the cache lives at
       ``./build/.playwright-cache``, NOT in ``~/.cache``, so CI runners
       and local builds produce identical bundles.
    3. Run PyInstaller against ``build/finance_analysis.spec``.
       Output lands in ``dist/Finance Analysis.app`` (macOS) or
       ``dist/FinanceAnalysis/`` (Windows).
    4. Wrap:
        * macOS: ``bash build/build_dmg.sh`` produces
          ``FinanceAnalysis-<arch>.dmg``.
        * Windows: ``makensis build/installer_script.nsi`` produces
          ``FinanceAppInstaller.exe``.

Skips the ``npm run build`` and ``playwright install`` steps with
``--no-frontend`` and ``--no-playwright`` respectively, useful when
iterating on the spec without redoing the slow steps.
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
PLAYWRIGHT_CACHE = BUILD_DIR / ".playwright-cache"


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None) -> None:
    """Run ``cmd`` and raise ``SystemExit`` on non-zero exit.

    Inherits stdout/stderr so the developer sees real-time progress
    from npm / pyinstaller / makensis. The shell is intentionally not
    invoked — every command is a known argv list.
    """
    print(f"\n>> {' '.join(cmd)}  (cwd={cwd or ROOT})")
    completed = subprocess.run(cmd, cwd=cwd or ROOT, env=env)
    if completed.returncode != 0:
        sys.exit(f"command failed (exit {completed.returncode}): {' '.join(cmd)}")


def _step_frontend() -> None:
    """Build the React app into ``frontend/dist/``."""
    _run(["npm", "ci"], cwd=ROOT / "frontend")
    _run(["npm", "run", "build"], cwd=ROOT / "frontend")


def _step_playwright() -> None:
    """Populate the build-local Chromium cache.

    We force ``PLAYWRIGHT_BROWSERS_PATH`` to a build-tree subdirectory
    so the bundle is hermetic. Side-effect: nothing is written to the
    developer's ``~/.cache``.
    """
    PLAYWRIGHT_CACHE.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(PLAYWRIGHT_CACHE)}
    # Use the python interpreter we're running under so we hit the
    # poetry venv's playwright install — not whatever is on PATH.
    _run([sys.executable, "-m", "playwright", "install", "chromium"], env=env)


def _step_pyinstaller() -> None:
    """Invoke PyInstaller on the spec.

    Removes ``dist/`` first so we never accidentally ship leftover
    files from a previous build.
    """
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(PLAYWRIGHT_CACHE)}
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
        env=env,
    )


def _bundle_resources_dir() -> Path:
    """Where bundled data lives in the PyInstaller output, post-build.

    macOS .app bundle:  dist/Finance Analysis.app/Contents/Resources/
    Windows directory:  dist/FinanceAnalysis/_internal/

    These two locations are what runtime ``sys._MEIPASS`` resolves to.
    Anything we copy here at build time is reachable from
    ``app_entry._resource_root() / "<sub>"`` at runtime.
    """
    if sys.platform == "darwin":
        return DIST_DIR / "Finance Analysis.app" / "Contents" / "Resources"
    return DIST_DIR / "FinanceAnalysis" / "_internal"


def _step_inject_chromium() -> None:
    """Copy the cached Chromium into the PyInstaller output.

    Done outside the PyInstaller spec because PyInstaller's macOS
    binary-processing pass mangles Chromium's signed Mach-O binaries
    when they're declared via ``datas``. The post-build copy keeps
    Chromium opaque — ``shutil.copytree`` is a plain file copy with
    no install_name rewriting.

    Picks every ``chromium-*`` and ``chromium_headless_shell-*`` dir
    in the cache. Playwright looks up subdirs by name at runtime
    based on its bundled version; copying the whole cache means we
    don't need to know which version maps to which dir.
    """
    target = _bundle_resources_dir() / "playwright_browsers"
    target.mkdir(parents=True, exist_ok=True)

    if not PLAYWRIGHT_CACHE.exists():
        raise SystemExit(
            f"Playwright cache not found at {PLAYWRIGHT_CACHE}. "
            "Run with --no-playwright disabled, or pre-populate the cache."
        )

    copied = 0
    for entry in PLAYWRIGHT_CACHE.iterdir():
        if entry.is_symlink():
            entry = entry.resolve()
        if not entry.is_dir():
            continue
        # Only Chromium + its headless shell. ffmpeg / mcp-chrome / etc
        # would be wasted bytes — Playwright doesn't ship those for
        # the chromium channel we use.
        if not (
            entry.name.startswith("chromium-")
            or entry.name.startswith("chromium_headless_shell-")
        ):
            continue
        dest = target / entry.name
        if dest.exists():
            shutil.rmtree(dest)
        # ``copy_function=shutil.copy2`` preserves mtimes; ``symlinks=False``
        # resolves any cache-side symlinks (like the build-local symlink
        # that local dev uses to point at the system cache).
        shutil.copytree(entry, dest, symlinks=False)
        copied += 1

    if copied == 0:
        raise SystemExit(
            f"No chromium-* dirs found under {PLAYWRIGHT_CACHE}. "
            "The cache is empty or only contains other browsers."
        )
    print(f"  copied {copied} Chromium subdir(s) into {target}")


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
        "--no-playwright",
        action="store_true",
        help="Skip `playwright install chromium` (when iterating on the spec).",
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
    if not args.no_playwright:
        _step_playwright()
    _step_pyinstaller()
    _step_inject_chromium()
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
