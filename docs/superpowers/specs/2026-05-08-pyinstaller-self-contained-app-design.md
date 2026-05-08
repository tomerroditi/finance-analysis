# Self-Contained Desktop App via PyInstaller — Design

## Problem

The current desktop install layout was driven by macOS's quirks but
ended up costing us across the board:

- **Source code lives twice on disk.** `/Applications/Finance Analysis.app/Contents/Resources/app/`
  is a duplicate of `~/.finance-analysis/app/` (the rsync target).
- **First launch is slow.** ~30–60s wasted on `setup.sh` running
  `poetry install` against a freshly-made venv every time the bundle
  changes.
- **Setup depends on user-installed runtimes.** macOS users need
  Python 3.12 + Node.js installed on their machine (`brew install`
  prompts in `setup.sh`); Windows users get a `setup.bat` that
  downloads Python 3.12 + Node 20 silently from python.org and
  nodejs.org. Both are fragile (firewalls, proxies, version mismatches,
  silent failures).
- **The .app bundle is not self-contained.** It can't be code-signed
  meaningfully because it relies on post-install mutation
  (`setup.sh` writes a venv into `~/.finance-analysis/app/`). That
  blocks future signing + notarization + auto-update work.
- **The launcher's rsync workaround is load-bearing infrastructure.**
  Every macOS launch reads `Info.plist`, compares versions, conditionally
  rsyncs, conditionally re-runs `setup.sh`. It works, but it's a lot of
  glue around a problem that shouldn't exist.

## Goal

Replace the rsync-into-`~/.finance-analysis/app/` + setup.sh approach
on **both macOS and Windows** with a self-contained PyInstaller-built
binary that bundles a frozen Python interpreter, all dependencies,
the React build, and Playwright's Chromium.

After this lands:

- macOS: a real `.app` you can drag to `/Applications` and launch
  with no setup, no Terminal pop-up, no user-installed runtimes.
- Windows: an NSIS installer that drops a self-contained directory;
  no Python/Node bootstrap; no internet required for first launch.
- Source code on disk **once**.
- First launch **~2s** (just uvicorn cold start).
- `~/.finance-analysis/` contains only **user state** (DB,
  credentials YAML, categories YAML, Keychain entries, logs).

## Dependencies

This design assumes PR #87 (in-app update notifier + cross-platform
uninstall + per-user Windows installer) is merged. It builds on
several files introduced there:

- `backend/uninstall/cleanup.py` — the cleanup module the new
  `--uninstall-cleanup` CLI delegates to.
- `backend/services/update_service.py` — extended here for
  arch-aware asset URLs.
- `build/macos/uninstall.command` — bundled into the new .app.
- The current `build/installer_script.nsi` — slimmed here, not
  re-built from scratch.

If PR #87 is held back, this work blocks until it lands.

## Non-goals

- **Code signing / notarization.** The bundle layout is designed to
  be signing-friendly — single immutable artifact, no post-install
  mutation, proper Info.plist — but actually signing is a separate
  follow-up that needs purchased certs.
- **Auto-update.** Same situation. With a self-contained bundle the
  mechanics become much simpler (replace `.app`, no setup.sh
  re-run), but the user-facing flow still depends on signing for the
  Gatekeeper / SmartScreen experience to be acceptable.
- **Native menu-bar / system tray UI.** Keep the "uvicorn + open
  browser tab" UX. A tray app would mean Qt / Tauri / pywebview,
  which is a separate project.
- **Linux packaging.** No current artifact, no current demand.
- **Migrating existing users.** There aren't any besides the author;
  the legacy `~/.finance-analysis/app/` from the old layout is
  removed manually once.

## Architecture

```
Today
  /Applications/Finance Analysis.app          (~50KB stub)
    └─ launcher.sh
       └─ rsync source → ~/.finance-analysis/app/
       └─ setup.sh     (poetry install into a fresh venv)
       └─ run.sh       (activate venv, open browser, run uvicorn)
  Requires: user-installed Python 3.12 + Node.js
  First launch: 30-60s
  Source on disk twice (bundle + ~/.finance-analysis/app/)

After
  /Applications/Finance Analysis.app          (~300MB self-contained)
    └─ Contents/
       ├─ MacOS/FinanceAnalysis                (PyInstaller bootloader binary)
       ├─ Frameworks/                          (Python 3.12 dylib + ext modules)
       ├─ Resources/
       │   ├─ frontend/dist/                   (built React app, served by FastAPI StaticFiles)
       │   ├─ playwright_browsers/chromium-*/  (~150MB, bundled headless Chromium)
       │   ├─ icon.icns
       │   └─ uninstall.command                (unchanged from current install/update PR)
       └─ Info.plist
  Requires: nothing
  First launch: ~2s
  ~/.finance-analysis/ contains ONLY user state (DB, credentials, logs)

Windows
  FinanceAppInstaller.exe (NSIS wrapper, per-user install, no admin)
    └─ Finance Analysis/                       (~280MB self-contained)
       ├─ FinanceAnalysis.exe                  (PyInstaller binary)
       ├─ _internal/                           (Python interpreter, deps, frontend, Chromium)
       └─ Uninstall.exe
  setup.bat goes away. No more "Python not found, downloading..."
```

The launcher disappears. PyInstaller's bootloader becomes
`Contents/MacOS/FinanceAnalysis`. The Python entry point
(`build/app_entry.py`) does five things:

1. Pick a free port via the existing `find_port.py` logic.
2. Set `FAD_USER_DIR` and `PLAYWRIGHT_BROWSERS_PATH` (pointing at
   the bundled Chromium).
3. Configure `logging.basicConfig` to write to
   `~/.finance-analysis/logs/uvicorn.log` *before* any backend
   import.
4. Start uvicorn programmatically in a background thread; open the
   default browser to `http://127.0.0.1:<port>` once the socket
   accepts.
5. `server.run()` — blocks until the OS sends SIGTERM (Cmd-Q,
   window close, or `kill`).

No more Terminal pop-up. The .app launches as a regular background
process; logs go to a rotated file.

## Components

### Bundling — `build/finance_analysis.spec`

Single PyInstaller spec, both platforms. Selects mac-vs-win behaviour
inside the spec via `sys.platform`. Key parts:

- **`Analysis(...)`**: pathex = repo root; backend + scraper
  submodules collected via `collect_submodules`.
- **`datas`**: `frontend/dist`, `backend/resources` (default
  categories YAML, icons), `alembic/`, `alembic.ini`,
  `pyproject.toml` (the version source of truth), and the bundled
  Chromium directory pointed at by `PLAYWRIGHT_BROWSERS_PATH`
  (set by `build_app.py` before invoking PyInstaller).
- **`hiddenimports`**: things PyInstaller's static analysis misses —
  `uvicorn.loops.auto`, `uvicorn.protocols.http.auto`,
  `uvicorn.protocols.websockets.auto`, `uvicorn.lifespan.on`,
  `sqlalchemy.dialects.sqlite`, `playwright._impl._driver`. The
  list is curated, not pasted from a tutorial — every entry has a
  comment explaining what would break without it.
- **`excludes`**: `tkinter`, `test`, `unittest`, `pytest` —
  reduces bloat by ~40 MB.
- **macOS `BUNDLE`**: `bundle_identifier`, `CFBundleVersion`,
  `LSMinimumSystemVersion = 10.15`, `NSHighResolutionCapable`,
  `LSUIElement = False` (Dock-visible).

### Entry point — `build/app_entry.py`

PyInstaller wraps this script as the `.app`'s
`CFBundleExecutable` / Windows `FinanceAnalysis.exe`. Its
responsibilities are tightly bounded: env setup, port, logging,
launch uvicorn, open browser, block on signal.

It also exposes a `--uninstall-cleanup [--wipe|--keep-data]` CLI
flag that delegates to `backend.uninstall.cleanup.run`. This is
how the Windows NSIS uninstaller invokes the cleanup module after
PyInstaller (no more `python -m backend.uninstall` from a venv —
the venv doesn't exist anymore). Same code path; different
invocation surface.

Logging is configured first, before `backend.main` is imported,
because the lifespan hook does work that produces log lines.

A SIGTERM handler tells uvicorn to shut down gracefully on Cmd-Q
/ window-close so we don't leave orphan processes.

### Build orchestrator — `build/build_app.py`

Single Python script you run from the repo root:

    python build/build_app.py

Steps, in order:

1. `cd frontend && npm ci && npm run build`.
2. `PLAYWRIGHT_BROWSERS_PATH=$(pwd)/build/.playwright-cache poetry run playwright install chromium`
   — provisions Chromium into a build-local cache so the bundle
   is hermetic (independent of the developer's `~/.cache`).
3. `pyinstaller build/finance_analysis.spec`. Output:
   `dist/Finance Analysis.app` on macOS, `dist/FinanceAnalysis/`
   on Windows.
4. Wrap:
   - macOS: `bash build/build_dmg.sh` produces
     `FinanceAnalysis-arm64.dmg` or `FinanceAnalysis-x86_64.dmg`
     depending on the runner.
   - Windows: `makensis build/installer_script.nsi`.

`build_app.py` auto-detects platform via `sys.platform` and
architecture via `platform.machine()`.

### macOS — `build/build_dmg.sh`

Slimmed. It no longer assembles the `.app` from a launcher.sh
(PyInstaller did that). It only:

1. Copies `build/macos/uninstall.command` into
   `Contents/Resources/`.
2. Generates `icon.icns` from the 512px PNG (only if not already
   present from PyInstaller's BUNDLE).
3. `hdiutil create` with the drag-to-Applications symlink. Output
   filename includes the architecture suffix.

### Windows — `build/installer_script.nsi`

Slimmed. It no longer:

- Invokes `setup.bat`.
- Bootstraps Python or Node.
- Creates a `.venv` inside `$INSTDIR`.

It still:

- Per-user installs at `$LOCALAPPDATA\Programs\Finance Analysis`,
  no admin.
- Detects existing per-user installs and silent-uninstalls them.
- Detects legacy HKLM Program Files installs and offers to migrate.
- Writes the full Add/Remove Programs metadata.
- Offers the optional "Also delete my data and saved passwords"
  uninstall component.

The uninstall section's Python invocation changes from
`"$INSTDIR\.venv\Scripts\python.exe" -m backend.uninstall --wipe`
to `"$INSTDIR\FinanceAnalysis.exe" --uninstall-cleanup --wipe`.
The bundled binary IS the cleanup CLI now.

### Backend — small changes only

- `backend/main.py`: when `getattr(sys, "frozen", False)`, mount
  the React app from `Path(sys._MEIPASS) / "frontend" / "dist"`
  instead of the relative `frontend/dist`. The `_MEIPASS` constant
  is set by PyInstaller's bootloader at runtime.
- `backend/services/update_service.py`: `_pick_asset_url` extended
  to match `arm64` / `x86_64` against `platform.machine()`, since
  macOS now ships two DMGs.
- `backend/uninstall/cleanup.py`: extended with the
  `--uninstall-cleanup` argparse interface used by the bundled
  binary's CLI mode (entry point in `app_entry.py`).

### Files to delete

- `build/setup.sh`
- `build/setup.bat`
- `build/run.sh`
- `build/run.bat`
- `build/find_port.py` (logic merged into `app_entry.py`)
- `build/macos/launcher.sh`
- `build/build_installer.py`

### Files to add

- `build/finance_analysis.spec`
- `build/app_entry.py`
- `build/build_app.py`

### Files to modify

- `build/build_dmg.sh` — slimmed
- `build/installer_script.nsi` — slimmed
- `backend/main.py` — `_MEIPASS`-aware StaticFiles
- `backend/services/update_service.py` — arch-aware asset URL
- `backend/uninstall/cleanup.py` — CLI-via-bundled-binary
- `pyproject.toml` — add optional `[tool.poetry.group.build]`
  with `pyinstaller`, `playwright`
- `.github/workflows/release.yml` — three matrix builds, new install
  steps
- `.claude/rules/installation_and_updates.md` — rewritten

## CI

`release.yml` matrix:

| os             | arch    | artifact                          |
|----------------|---------|-----------------------------------|
| macos-14       | arm64   | FinanceAnalysis-arm64.dmg         |
| macos-13       | x86_64  | FinanceAnalysis-x86_64.dmg        |
| windows-latest | x86_64  | FinanceAppInstaller.exe           |

Each runner builds for its native arch — no cross-compilation.
Per-runner steps: checkout, setup-python 3.12, setup-node 20,
`npm ci && npm run build`, `pip install poetry`,
`poetry install --with build`, `python build/build_app.py`,
upload artifact to release.

CI cost: ~25 min total (was ~12 min). One-per-PR-merge cadence.

## Local dev unaffected

`poetry run uvicorn backend.main:app --reload` and `npm run dev`
work exactly as today. The build pipeline is opt-in via
`python build/build_app.py`.

## Testing

### Unit tests

- `tests/build/test_app_entry.py`:
  - `_resource_root()` returns `_MEIPASS` when `sys.frozen` is
    set, repo root otherwise.
  - `_pick_port()` returns a valid free port.
  - `_setup_env()` populates `PLAYWRIGHT_BROWSERS_PATH` and
    creates the logs directory.
  - The `--uninstall-cleanup` CLI flag delegates to
    `backend.uninstall.cleanup.run` with the right `wipe_data`
    value. Mocked `webbrowser.open` and `uvicorn.Server.run`
    so the test never opens a real browser or binds a port.

### Build-time smoke tests

Run inside CI right after the artifact is produced:

- Launch the bundle with `--smoke-test` (env-var-driven mode in
  `app_entry.py` that exits cleanly after one self-issued HTTP
  request). Assert `GET /api/version` returns 200 with the
  expected version string. Catches missing `hiddenimports` /
  data files before the artifact ships.
- Assert artifact size is < 500 MB. Catches accidental dep bloat
  (a forgotten dev dep slipping into `[build]`).

### Manual smoke test matrix

| Platform              | Test                                                            |
|-----------------------|-----------------------------------------------------------------|
| macOS arm64           | DMG mounts → drag → first launch < 5s → dashboard loads         |
| macOS arm64           | Demo Mode toggle works                                          |
| macOS arm64           | Scrape a real provider (Playwright + bundled Chromium fires)    |
| macOS arm64           | In-app uninstall removes .app + Keychain entries                |
| macOS arm64           | Cmd-Q quits cleanly; uvicorn process gone                       |
| macOS x86_64          | All of the above on an Intel Mac                                |
| Windows 11 x64        | Installer runs without admin, no Python/Node prompts            |
| Windows 11 x64        | First launch < 5s → dashboard loads                             |
| Windows 11 x64        | Scrape works, uninstall works (with + without "delete data")    |
| Windows 10 x64        | Same                                                            |

## Risks + mitigations

| Risk                                                          | Mitigation                                                          |
|---------------------------------------------------------------|---------------------------------------------------------------------|
| PyInstaller misses a runtime import (e.g., new SQLAlchemy dialect) | Build-time smoke test catches at CI; `hiddenimports` is curated and commented |
| Playwright + bundled Chromium version drift                   | Pin Playwright in `[build]` group; bumping is a deliberate PR with re-run of scrape smoke test |
| numpy/pandas wheels not available for an arch                 | macos-13 (Intel) uses x86_64 wheels; macos-14 (M-series) uses arm64; both ship from PyPI today |
| First-launch logging fails before `logging.basicConfig` runs  | `app_entry.py` configures logging *first*, before any backend import — order matters |
| Bundle bloat from accidental dep inclusion                    | `excludes=["test","unittest","pytest"]` in spec; size assertion in CI |
| User has no default browser registered                        | `webbrowser.open` returns False → log a warning with the URL so user can copy it manually |
| Uvicorn doesn't shut down on .app quit (orphan process)       | `signal.signal(SIGTERM, ...)` in `app_entry.py`; macOS sends SIGTERM on Cmd-Q |
| GitHub Releases asset URL doesn't include arch suffix         | `_pick_asset_url` extended in `update_service.py` to match `arm64`/`x86_64` against `platform.machine()` |
| Notarization eventually needed                                | Bundle layout is signing-friendly today (single bundle, no post-install mutation, proper Info.plist) — no architectural barrier when certs arrive |

## Code-signing future work (out of scope)

Once we have certs:

- macOS: `codesign --deep --sign "Developer ID Application: ..." dist/Finance Analysis.app`
  followed by `xcrun notarytool submit FinanceAnalysis.dmg --wait`. Done.
- Windows: `signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a build/FinanceAppInstaller.exe`.
- Re-evaluate auto-update: with a signed self-contained bundle, in-app
  "Restart and install" becomes feasible (download new DMG, mount,
  copy-replace the .app, relaunch). The toast in
  `UpdateAvailableToast.tsx` would gain a "Restart and install"
  button alongside the existing "Download" link.
