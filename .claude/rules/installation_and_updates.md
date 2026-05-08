# Installation, Updates, and Uninstallation

How the desktop app is installed, upgraded, and removed on Windows
and macOS. Read this before touching anything in `build/`,
`backend/uninstall/`, `backend/services/update_service.py`, or the
`/api/updates` and `/api/uninstall` routes.

## Three flows, one cleanup module

```
Windows NSIS Uninstall.exe         ─┐
   FinanceAnalysis.exe              │
   --uninstall-cleanup --wipe|--keep-data
                                    │
macOS uninstall.command            ─┤  backend/uninstall/cleanup.py
   (double-clicked, calls          │  ─────────────────────────────▶  Keychain entries removed
    Resources/.../FinanceAnalysis  │  ── (single source of truth ──▶  ~/.finance-analysis/ wiped
    --uninstall-cleanup ...)        │     for what counts as state)    (only when --wipe)
                                    │
macOS POST /api/uninstall          ─┘
   (Settings → Uninstall, calls
    cleanup.run() in-process)
```

The bundled binary exposes `--uninstall-cleanup` as a CLI mode
(`build/app_entry.py`) so NSIS and the macOS uninstall.command can
reach `backend.uninstall.cleanup.run` without needing a venv-hosted
Python interpreter. The in-app uninstall route imports the module
directly.

The three uninstall surfaces all delegate to **one** Python module
(`backend/uninstall/cleanup.py`) so they agree on:

- The Keychain service names (`finance-analysis-app`,
  `finance-analysis-app-demo`).
- The user-data directory (`~/.finance-analysis/`).
- The credential field names (`password`, `secret`, `otp_key`,
  `otpLongTermToken`).

Add a new field name to `CredentialsRepository`? Add it to
`CREDENTIAL_FIELDS` in `cleanup.py` too — otherwise that secret
survives uninstall. The unit tests for `cleanup.py` lock the field
list in.

## Update notifier

```
┌─ Frontend ─────────────────────────────────────────────────────┐
│ useUpdateCheck() (TanStack Query, 6h staleTime, dev-disabled)  │
│   ↓                                                             │
│ /api/updates/check (excluded from PWA cache + IndexedDB persist)│
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─ Backend ───────────────────────────────────────────────────────┐
│ UpdateService                                                   │
│   - GitHub releases probe (httpx, 5s timeout)                   │
│   - on-disk cache: ~/.finance-analysis/.update_cache.json (24h) │
│   - asset_url is OS-aware (.dmg darwin, .exe win32)             │
│   - any failure → UpdateInfo(error="unavailable") (never raises)│
└─────────────────────────────────────────────────────────────────┘
```

**Toast (`UpdateAvailableToast.tsx`):** appears 5s after mount; per-version
dismissal in localStorage; never appears in `npm run dev`.

**About panel (`AboutPanel.tsx`):** lives in Settings; shows current vs
latest, "Check now" button (POSTs `/api/updates/check`, force-refresh).

**Why the cache lives on the backend, not in the browser:** the PWA
persists React Query results to IndexedDB. If the cache also lived
there, every cold load would re-hit GitHub, blowing through the
unauthenticated 60 req/hour/IP rate limit fast on shared networks.
A backend file cache is shared by all open windows on the machine and
respected by the per-window TanStack Query (its `staleTime` is just a
client-side optimisation on top).

## Build pipeline (both platforms)

`python build/build_app.py` is the single orchestrator. It:

1. `cd frontend && npm ci && npm run build`.
2. Provisions Playwright's Chromium into `build/.playwright-cache`
   (build-local, not `~/.cache`, so the bundle is hermetic).
3. Runs PyInstaller against `build/finance_analysis.spec`. Output:
   `dist/Finance Analysis.app` on macOS, `dist/FinanceAnalysis/` on
   Windows.
4. Wraps the result: `build/build_dmg.sh` produces the DMG on macOS,
   `makensis build/installer_script.nsi` produces the EXE on Windows.

Local dev is unaffected — `poetry run uvicorn backend.main:app --reload`
and `npm run dev` work as before. The build pipeline is opt-in.

## Windows install (NSIS)

`build/installer_script.nsi` is now a thin wrapper around the
PyInstaller-produced self-contained directory.

- **Per-user install** at `$LOCALAPPDATA\Programs\Finance Analysis`.
  No `RequestExecutionLevel admin`, no UAC prompts on install or upgrade.
- **No `setup.bat`, no `.venv`, no Python/Node bootstrap.** The
  bundled `FinanceAnalysis.exe` ships with everything baked in.
- **HKCU `Uninstall` registry entry** populates Add/Remove Programs
  with `DisplayName`, `DisplayVersion`, `Publisher`, `DisplayIcon`,
  `InstallLocation`, `UninstallString`, `QuietUninstallString`,
  `URLInfoAbout`, `URLUpdateInfo`, `EstimatedSize`, `NoModify`,
  `NoRepair`. Supports `winget uninstall`.
- **`.onInit` migration logic:**
  1. Existing per-user install (HKCU\Software\Finance Analysis): run
     its uninstaller silently with `_?=$0` so we wait for it before
     laying down the new build. User data preserved.
  2. Legacy HKLM/Program Files install: prompt the user, run the
     legacy uninstaller via `ExecShellWait` (UAC fires once for the
     legacy half), then proceed.
- **Shortcuts** point directly at `$INSTDIR\FinanceAnalysis.exe` —
  no `run.bat` wrapper.

### Windows uninstall

Components page (`MUI_UNPAGE_COMPONENTS`) shows one optional
checkbox: **"Also delete my data and saved passwords."** Default:
unchecked.

Uninstall flow:
1. `taskkill /F /IM "FinanceAnalysis.exe"` — best-effort stop.
2. `"$INSTDIR\FinanceAnalysis.exe" --uninstall-cleanup --wipe|--keep-data`.
   The bundled exe runs in CLI mode, delegates to
   `backend.uninstall.cleanup.run`, prints a JSON report, exits.
3. `RMDir /r $INSTDIR` — removes the entire bundle directory.
4. Delete shortcuts and HKCU registry entries.

The cleanup CLI runs **before** `RMDir /r $INSTDIR` so the bundled
exe is still on disk to invoke.

## macOS install (DMG)

PyInstaller's `BUNDLE` directive in `build/finance_analysis.spec`
produces `dist/Finance Analysis.app` — a real, self-contained
application bundle. `build/build_dmg.sh` only injects the
standalone `uninstall.command` and wraps the result in a DMG.

```
Finance Analysis.app/
├── Contents/
│   ├── MacOS/FinanceAnalysis        ← PyInstaller bootloader binary
│   ├── Frameworks/                   ← Python interpreter, ext modules
│   ├── Info.plist                    ← CFBundleVersion (read from pyproject.toml)
│   └── Resources/
│       ├── frontend/dist/            ← React build, served by FastAPI StaticFiles
│       ├── playwright_browsers/      ← Bundled Chromium (~150MB)
│       ├── icon.icns
│       └── uninstall.command         ← Standalone uninstaller
```

DMG filenames are arch-tagged: `FinanceAnalysis-arm64.dmg` and
`FinanceAnalysis-x86_64.dmg`. The in-app update notifier
(`backend/services/update_service.py::_pick_asset_url`) matches the
asset to `platform.machine()` so users get the right download.

### macOS launch (no setup, no rsync)

The PyInstaller-built `.app` is fully self-contained, so the launch
path is now:

1. User double-clicks `Finance Analysis.app`.
2. `Contents/MacOS/FinanceAnalysis` (PyInstaller bootloader) starts.
3. The bootloader extracts the Python runtime to a `_MEIPASS` temp
   dir, imports `build/app_entry.py`, and runs `main()`.
4. `app_entry.py` configures file logging, picks a free port, starts
   uvicorn in-process, opens the default browser, blocks on signal.

No Terminal pop-up. No `setup.sh`. No `~/.finance-analysis/app/`
sync. Logs go to `~/.finance-analysis/logs/uvicorn.log` (rotated
2 MiB × 3). First launch is ~2s, the same as every subsequent launch.

### macOS uninstall (three surfaces)

1. **In-app:** Settings → Uninstall Finance Analysis. Calls
   `POST /api/uninstall`. Backend runs `cleanup.run(...)` synchronously,
   then writes a deferred shell script to `/tmp` and launches it in
   Terminal via `osascript`. The deferred script removes the .app +
   (if wiping) the user-data dir + kills the bundle's uvicorn process.
2. **Standalone `Uninstall Finance Analysis.command`:** found inside
   the bundle's `Contents/Resources/`. Right-Click → Show Package
   Contents → drag the `.command` to Terminal, or open it from
   inside the bundle. Asks the keep/wipe question via `read -p`,
   calls the bundled exe's `--uninstall-cleanup` mode, then removes
   the .app.
3. **Drag-to-Trash:** still works, but leaves user data + Keychain
   entries behind. macOS doesn't support "run on uninstall" hooks.
   Documented in the README so users know to use the in-app or
   standalone paths for a clean removal.

## Manual smoke test plan

Cutting a release? Run through this matrix on a clean VM (or fresh
user account on macOS):

### Windows

1. **Fresh install:**
   - Run `FinanceAppInstaller.exe`.
   - Verify: no UAC prompt, no "Python downloading…" message, install
     dir is `%LOCALAPPDATA%\Programs\Finance Analysis`.
   - Verify Add/Remove Programs entry shows publisher, version, icon,
     About URL, and accurate size.
   - Launch the desktop shortcut. Dashboard loads in the default
     browser within ~2s.

2. **Upgrade in place:**
   - With v1.X installed, run installer for v1.X+1.
   - Verify: no UAC prompt, no "an existing version is installed"
     prompt, no orphan files. The HKCU registry entry should reflect
     the new version.

3. **Uninstall (preserve data):**
   - From Add/Remove Programs → Uninstall.
   - Leave the "Also delete my data" checkbox **unchecked**.
   - Verify: install dir gone, shortcuts gone, registry clean.
     `%USERPROFILE%\.finance-analysis\` still present, Credential
     Manager still has provider entries.
   - Re-install: verify previous data shows up.

4. **Uninstall (wipe data):**
   - Re-install if needed, then uninstall again with the checkbox
     **checked**.
   - Verify: install dir gone, `%USERPROFILE%\.finance-analysis\`
     gone, `cmdkey /list` no longer shows
     `finance-analysis-app/*` entries.

5. **Scrape with bundled Chromium:**
   - Set up a credential, kick off a scrape.
   - Verify Playwright fires without trying to download Chromium.
     Confirm via `%USERPROFILE%\.finance-analysis\logs\uvicorn.log`.

### macOS

1. **Fresh install (arch-matching DMG):**
   - On Apple Silicon, download `FinanceAnalysis-arm64.dmg`. On Intel,
     download `FinanceAnalysis-x86_64.dmg`. The in-app update notifier
     auto-picks the right one once the app is running.
   - Open the DMG, drag to Applications.
   - Launch from Launchpad. **No Terminal window.** Dashboard opens
     in the default browser within ~2s.

2. **Quit + relaunch:**
   - Cmd-Q the app (or close it from the Dock).
   - Launch again. Should be just as fast — no setup work happens.

3. **Upgrade:**
   - Replace the .app with a newer build (drag-to-Applications, overwrite).
   - Launch. Same ~2s startup as a fresh install.

4. **In-app uninstall (preserve data):**
   - Open Settings → Uninstall Finance Analysis.
   - Confirm without ticking "Also delete my data".
   - Verify: .app gone from /Applications, but `~/.finance-analysis/`
     (DB, credentials YAML) intact.
   - Re-install and re-launch — data picks up.

5. **Standalone uninstall.command:**
   - With app installed, Right-Click `Finance Analysis.app` → Show
     Package Contents → Contents/Resources → double-click `uninstall.command`.
     Type `y` at the prompt.
   - Verify the .app is removed AND the user-data dir is gone AND
     `security find-generic-password -s finance-analysis-app` returns
     nothing.

6. **Scrape with bundled Chromium:**
   - Set up a credential, kick off a scrape.
   - Verify Playwright fires without trying to download Chromium
     (no network call to playwright.azureedge.net). Confirm by checking
     `~/.finance-analysis/logs/uvicorn.log`.

7. **Drag-to-Trash regression check:**
   - Drag `Finance Analysis.app` to Trash.
   - User data should remain (documented behaviour — the .app's
     uninstall hooks aren't invoked by Trash).

## Code-signing and notarization (out of scope)

We don't sign the Windows installer (no Authenticode cert) or
notarize the macOS .app (no Apple Developer ID). This means:

- Windows: SmartScreen flags every new build for ~24-48h after
  publication. The user has to click "More info" → "Run anyway".
- macOS: Gatekeeper refuses to launch on first run; the user must
  open `Privacy & Security` and click "Open Anyway" once. We can't
  ship auto-update until this is resolved — auto-installing an
  unsigned binary is a UX disaster.

When we do invest in signing certs, the changes are:
- NSIS: add a `signtool sign` post-build step in `release.yml`.
- macOS: extend `build_dmg.sh` with `codesign` + `notarytool submit`.
- Re-evaluate the auto-update story (the in-app toast can become an
  in-app "downloading… restarting…").

## File map

```
backend/
├── routes/
│   ├── version.py       # GET /api/version
│   ├── updates.py       # GET/POST /api/updates/check
│   └── uninstall.py     # POST /api/uninstall (macOS only)
├── services/
│   └── update_service.py
├── uninstall/
│   ├── __init__.py
│   ├── __main__.py      # python -m backend.uninstall
│   └── cleanup.py       # single source of truth
└── utils/
    └── version.py       # reads pyproject.toml

build/
├── app_entry.py         # Python entry point PyInstaller wraps; modes:
│                        #   default        — start uvicorn, open browser
│                        #   --smoke-test   — boot, hit /api/version, exit
│                        #   --uninstall-cleanup --wipe|--keep-data
├── finance_analysis.spec # Single PyInstaller spec (both platforms)
├── build_app.py         # Orchestrator: frontend → playwright → pyinstaller → DMG/NSIS
├── installer_script.nsi # Slim NSIS wrapper around PyInstaller dist/
├── build_dmg.sh         # Slim macOS DMG wrapper around PyInstaller .app
└── macos/
    └── uninstall.command # Standalone uninstaller (in Contents/Resources)

# Generated, not checked in:
build/.playwright-cache/  # Build-local Chromium cache
build/.pyinstaller-work/  # PyInstaller scratch dir
dist/                     # PyInstaller output (.app on macOS, dir on Windows)

frontend/src/
├── components/
│   ├── UpdateAvailableToast.tsx
│   └── settings/
│       ├── AboutPanel.tsx
│       └── UninstallSection.tsx
├── hooks/
│   ├── useUpdateCheck.ts
│   └── useVersionInfo.ts
└── locales/{en,he}.json # `updates.*`, `uninstall.*` keys
```
