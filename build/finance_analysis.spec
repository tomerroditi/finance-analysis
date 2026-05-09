# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Finance Analysis desktop app.

Single spec, both platforms. The macOS-vs-Windows split is at the
bottom, where we either emit ``BUNDLE`` (for the .app) or stop after
``COLLECT`` (Windows; NSIS wraps the resulting directory).

Invoked indirectly via ``python build/build_app.py``, which sets
``PLAYWRIGHT_BROWSERS_PATH`` to a build-local cache so the bundle is
hermetic — independent of the developer's ``~/.cache``.
"""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# ``SPECPATH`` is set by PyInstaller to the dir containing this .spec file.
ROOT = Path(SPECPATH).parent  # noqa: F821  (SPECPATH injected by PyInstaller)


# ---------------------------------------------------------------------------
# Version (read from pyproject.toml so it always matches the running build).
# ---------------------------------------------------------------------------


def _read_version() -> str:
    pyproject = ROOT / "pyproject.toml"
    with pyproject.open("rb") as fh:
        return tomllib.load(fh)["tool"]["poetry"]["version"]


APP_VERSION = _read_version()
APP_NAME_DARWIN = "Finance Analysis"  # display name with space (macOS bundle)
APP_NAME_WIN = "FinanceAnalysis"      # no space, Windows-friendly
BUNDLE_ID = "com.tomerroditi.finance-analysis"


# ---------------------------------------------------------------------------
# Source code: collect every backend + scraper submodule. PyInstaller's
# static analysis follows imports it can see; ``collect_submodules`` makes
# sure the dynamic imports the lifespan startup performs (alembic stamp,
# tagging seed, etc.) come along too.
# ---------------------------------------------------------------------------

backend_modules = collect_submodules("backend") + collect_submodules("scraper")


# ---------------------------------------------------------------------------
# Data files: built React app, default categories YAML, alembic migrations,
# pyproject.toml (the version source of truth at runtime), and the bundled
# Chromium directory.
# ---------------------------------------------------------------------------

datas = [
    (str(ROOT / "frontend" / "dist"),               "frontend/dist"),
    (str(ROOT / "backend" / "resources"),           "backend/resources"),
    (str(ROOT / "backend" / "alembic"),             "backend/alembic"),
    (str(ROOT / "alembic.ini"),                     "."),
    (str(ROOT / "pyproject.toml"),                  "."),
    (str(ROOT / "icon.ico"),                        "."),
]

# Playwright ships its driver script (a Node binary + JS) outside our
# control. ``collect_data_files`` picks it up.
datas += collect_data_files("playwright")

# NOTE: Chromium is **not** bundled. The scraper (BrowserScraper.initialize)
# launches Playwright with ``channel="chrome"`` and falls back to
# ``channel="msedge"`` on Windows, driving the user's installed browser
# via CDP. That avoids a ~800MB bundle add and keeps the browser
# auto-updated against bank fingerprinting changes — both meaningful
# wins. On the rare machine without Chrome or Edge installed, the
# scraper raises a "please install Chrome" error which the scraping
# route surfaces in the UI.


# ---------------------------------------------------------------------------
# Hidden imports: things PyInstaller's static analysis misses. Each line
# has a comment because adding to this list later (when something breaks
# in production) is easier if every existing entry's reason is recorded.
# ---------------------------------------------------------------------------

hiddenimports = backend_modules + [
    # uvicorn picks its event loop / HTTP / WebSocket implementations at
    # runtime via importlib; PyInstaller can't see them statically.
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    # SQLAlchemy 2.x looks up dialect modules by string name at engine
    # creation time. We only use sqlite, but PyInstaller can't see the
    # string-based import.
    "sqlalchemy.dialects.sqlite",
    # Playwright loads its driver via importlib at first use.
    "playwright._impl._driver",
    # FastAPI / Pydantic v2 sometimes pulls extra encoder modules
    # depending on the route's response model.
    "email_validator",
]


# ---------------------------------------------------------------------------
# Modules to exclude. PyInstaller pulls Python's stdlib eagerly; trimming
# unused parts cuts ~30-40 MB off the bundle.
# ---------------------------------------------------------------------------

excludes = [
    "tkinter",
    "test",
    "unittest",
    "pytest",
    "_pytest",
    "pydoc_data",
    # IPython / Jupyter sometimes get pulled transitively through
    # interactive-friendly libs we don't actually use.
    "IPython",
    "ipykernel",
    "notebook",
    "matplotlib",
]


# ---------------------------------------------------------------------------
# PyInstaller graph.
# ---------------------------------------------------------------------------

a = Analysis(
    [str(ROOT / "build" / "app_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)


# ---------------------------------------------------------------------------
# Per-platform output.
# ---------------------------------------------------------------------------

if sys.platform == "darwin":
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="FinanceAnalysis",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        target_arch=None,  # let PyInstaller use the runner's native arch
        codesign_identity=None,
        entitlements_file=None,
        # ``build/icon.icns`` is generated by build_app.py::_step_icns
        # BEFORE PyInstaller runs. We reference it unconditionally — if
        # it's missing, PyInstaller errors loudly here rather than
        # silently producing a .app with the generic Python icon (which
        # was happening before, when icns generation lived in
        # build_dmg.sh and ran AFTER PyInstaller had already written
        # Info.plist's CFBundleIconFile).
        icon=str(ROOT / "build" / "icon.icns"),
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="FinanceAnalysis",
    )

    app = BUNDLE(
        coll,
        name=f"{APP_NAME_DARWIN}.app",
        icon=str(ROOT / "build" / "icon.icns"),
        bundle_identifier=BUNDLE_ID,
        version=APP_VERSION,
        info_plist={
            "CFBundleName": APP_NAME_DARWIN,
            "CFBundleDisplayName": APP_NAME_DARWIN,
            "CFBundleIdentifier": BUNDLE_ID,
            "CFBundleVersion": APP_VERSION,
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundlePackageType": "APPL",
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            # We want a normal Dock-visible app, not a background-only one.
            # Flip to True later if we ship a tray-only variant.
            "LSUIElement": False,
            # Privacy strings are required by macOS for any Playwright
            # navigation that touches camera/mic/keychain APIs (it
            # doesn't, but Apple's tooling sometimes complains during
            # notarization without these stubs).
            "NSAppleEventsUsageDescription": "Finance Analysis automates browser logins to your bank.",
        },
    )

else:  # Windows
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=APP_NAME_WIN,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        # ``icon.ico`` is committed at the repo root and read directly by
        # PyInstaller's Windows EXE step (it embeds the icon into the
        # PE resource table so Windows shows it in the taskbar / desktop
        # shortcut / Add/Remove Programs DisplayIcon entry). We
        # reference it unconditionally — same reasoning as the .icns
        # path above: silent fall-through to no-icon ships a generic
        # Python exe, which is the bug we're fixing.
        icon=str(ROOT / "icon.ico"),
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name=APP_NAME_WIN,
    )
