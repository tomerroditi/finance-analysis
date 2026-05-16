# Installation, Updates, and Uninstallation

How the desktop app is installed, upgraded, and removed. Read this
before touching anything in `build/`, `backend/uninstall/`,
`backend/services/update_service.py`, or the `/api/updates` and
`/api/uninstall` routes.

## Platforms

- **Windows:** CI builds `FinanceAppInstaller.exe` and attaches it
  to every GitHub release. Users download + double-click.
- **macOS:** **no CI artifact.** macOS Tahoe (26.x) blocks every
  unsigned download path — `.app`, `.pkg`, and `.command` all hit a
  dead-end "cannot verify" dialog with no Open button (Apple removed
  the bypass in macOS 15+). The only paths that work end-to-end are
  Apple Developer ID + notarization ($99/yr) or a Terminal one-liner.
  Until the project invests in signing, **macOS users build from
  source locally**; see the README → "Packaged .app for macOS"
  section. The build/ code still produces a working `.app` and `.dmg`
  for local use; only the CI distribution + downloaded-app flow is
  retired. Don't re-enable a macOS matrix entry in release.yml without
  also setting up notarization.

## Two uninstall flows, one cleanup module

```
Windows NSIS Uninstall.exe         ─┐
   FinanceAnalysis.exe              │
   --uninstall-cleanup --wipe|--keep-data
                                    │  backend/uninstall/cleanup.py
                                    │  ─────────────────────────────▶  Credential Manager / Keychain wiped
macOS POST /api/uninstall          ─┤  ── (single source of truth ──▶  ~/.finance-analysis/ wiped
   (Settings → Uninstall, calls    │     for what counts as state)    (only when --wipe)
    cleanup.run() in-process)       │
                                    │
macOS uninstall.command            ─┘
   (inside .app bundle, run from
    Terminal: bash <path>)
```

The bundled Windows binary exposes `--uninstall-cleanup` as a CLI
mode (`build/app_entry.py`) so NSIS can reach
`backend.uninstall.cleanup.run` without a venv-hosted Python
interpreter. The macOS in-app uninstall route imports the module
directly (no shell-out needed).

All uninstall surfaces delegate to **one** Python module
(`backend/uninstall/cleanup.py`) so they agree on:

- The Keychain / Credential Manager service names
  (`finance-analysis-app`, `finance-analysis-app-demo`).
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
│   - asset_url is OS-aware (.exe on win32; None on darwin/linux  │
│     since there's no downloadable artifact for them)            │
│   - any failure → UpdateInfo(error="unavailable") (never raises)│
└─────────────────────────────────────────────────────────────────┘
```

**Toast (`UpdateAvailableToast.tsx`):** appears 5s after mount; per-version
dismissal in localStorage; never appears in `npm run dev`. When
`asset_url` is null (macOS / Linux), the Download button links to
`html_url` (the release page) instead of a direct file download. The
macOS user lands on the release page, reads the "build from source"
note in the release body, and pulls + rebuilds.

**About panel (`AboutPanel.tsx`):** lives in Settings; shows current vs
latest, "Check now" button (POSTs `/api/updates/check`, force-refresh).
Same fallback as the toast for null `asset_url`.

**Why the cache lives on the backend, not in the browser:** the PWA
persists React Query results to IndexedDB. If the cache also lived
there, every cold load would re-hit GitHub, blowing through the
unauthenticated 60 req/hour/IP rate limit fast on shared networks.
A backend file cache is shared by all open windows on the machine and
respected by the per-window TanStack Query (its `staleTime` is just a
client-side optimisation on top).

## Build pipeline

`python build/build_app.py` is the single orchestrator. It works on
both platforms locally:

1. `cd frontend && npm ci && npm run build`.
2. Runs PyInstaller against `build/finance_analysis.spec`. Output:
   `dist/Finance Analysis.app` on macOS, `dist/FinanceAnalysis/` on
   Windows.
3. Wraps the result: `build/build_dmg.sh` produces the DMG on macOS
   (local use only — not published anywhere), `makensis
   build/installer_script.nsi` produces the EXE on Windows.

CI runs steps 1-3 on `windows-latest` only and uploads the resulting
`FinanceAppInstaller.exe` to the GitHub release. macOS local builds
work the same way — `python build/build_app.py` on a Mac produces a
`dist/Finance Analysis.app` + `build/FinanceAnalysis.dmg`, both
launchable directly because nothing applied the quarantine xattr.

Local dev is unaffected — `poetry run uvicorn backend.main:app --reload`
and `npm run dev` work as before. The packaged-bundle build is opt-in.

## Browser dependency (NOT bundled)

The scraper uses Playwright but does **not** ship Playwright's bundled
Chromium build. `BrowserScraper.initialize()` calls
`chromium.launch(channel="chrome")` first, falling back to
`channel="msedge"` on `BrowserType.NotInstalledError`. Both channels
drive the user's installed browser via CDP.

Why we don't bundle Chromium:

- Bundle size: a Playwright-bundled Chromium adds ~800MB to the
  artifact (chromium-NNNN + chromium_headless_shell-NNNN), pushing
  the installer from ~80MB to ~400MB compressed and the on-disk
  install from ~450MB to ~1.5GB.
- Anti-bot fingerprinting: a frozen Chromium revision looks more
  suspicious to bank fingerprinting over time. The user's Chrome
  auto-updates and stays current with web platform features — that
  makes scrapes more robust, not less.

User-facing implication:

- **Windows users**: zero friction. Edge ships pre-installed since
  Windows 10; the Edge fallback covers 100% of Windows installs.
- **macOS users**: ~55% have Chrome already. Users who only have
  Safari (Playwright can't drive Safari for automation) see a clear
  "install Chrome from chrome.google.com" error on first scrape,
  surfaced via the existing scraping error toast.

## Windows install (NSIS)

`build/installer_script.nsi` is a thin wrapper around the
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

## macOS install (build from source)

There is no shipped `.dmg` or `.pkg`. To install:

```bash
git clone https://github.com/tomerroditi/finance-analysis.git
cd finance-analysis
python3.12 -m venv .venv && source .venv/bin/activate
pip install poetry && poetry install --no-root --with build
cd frontend && npm install && cd ..

# Produce dist/Finance Analysis.app (skip the DMG wrap step)
python build/build_app.py --no-wrap

mv "dist/Finance Analysis.app" /Applications/
```

The resulting `.app` has no `com.apple.quarantine` xattr (because it
was built locally, not downloaded), so Gatekeeper allows the ad-hoc
PyInstaller signature to launch with no warnings. Double-click from
Launchpad / Finder works.

Bundle layout (PyInstaller's `BUNDLE` output, unchanged from when we
shipped the DMG):

```
Finance Analysis.app/
├── Contents/
│   ├── MacOS/FinanceAnalysis        ← PyInstaller bootloader binary
│   ├── Frameworks/                   ← Python interpreter, ext modules
│   ├── Info.plist                    ← CFBundleVersion (read from pyproject.toml)
│   └── Resources/
│       ├── frontend/dist/            ← React build, served by FastAPI StaticFiles
│       │                             ← (no playwright_browsers/ — uses system Chrome)
│       ├── icon.icns
│       └── uninstall.command         ← Standalone uninstaller
```

### macOS launch

1. User double-clicks `Finance Analysis.app`.
2. `Contents/MacOS/FinanceAnalysis` (PyInstaller bootloader) starts.
3. The bootloader extracts the Python runtime to a `_MEIPASS` temp
   dir, imports `build/app_entry.py`, and runs `main()`.
4. `app_entry.py` configures file logging, picks a free port, starts
   uvicorn in-process, opens the default browser, blocks on signal.

No Terminal pop-up. No `setup.sh`. Logs go to
`~/.finance-analysis/logs/uvicorn.log` (rotated 2 MiB × 3). First
launch is ~2s, the same as every subsequent launch.

### macOS upgrade

Rebuild from a fresh git pull:

```bash
cd ~/finance-analysis && git pull
source .venv/bin/activate
poetry install --no-root --with build
cd frontend && npm install && cd ..
python build/build_app.py --no-wrap
rm -rf "/Applications/Finance Analysis.app"
mv "dist/Finance Analysis.app" /Applications/
```

The in-app update notifier (Toast + About panel) detects new releases
the same way it does on Windows; on macOS the "Download" button
points at the GitHub release page (no `.exe` to direct-link), where
the release body re-states the rebuild command.

### macOS uninstall

1. **In-app:** Settings → Uninstall Finance Analysis. Calls
   `POST /api/uninstall`. Backend runs `cleanup.run(...)` synchronously,
   then writes a deferred shell script to `/tmp` and launches it in
   Terminal via `osascript`. The deferred script removes the .app +
   (if wiping) the user-data dir + kills the bundle's uvicorn process.
2. **Standalone `uninstall.command`** inside the bundle's
   `Contents/Resources/`. Right-click `Finance Analysis.app` → Show
   Package Contents → drag the `.command` into a Terminal window
   (don't double-click — even your own locally-built `.command`
   wouldn't get blocked since it has no quarantine xattr, but the
   in-app flow is cleaner anyway). Asks the keep/wipe question via
   `read -p`, deletes the `.app` and (if wiping) the user-data dir.
3. **Drag-to-Trash:** still works, but leaves user data + Keychain
   entries behind. macOS doesn't support "run on uninstall" hooks.
   Documented in the README so users know to use the in-app path for
   a clean removal.

## Manual smoke test plan

Cutting a release? Run through this matrix:

### Windows

1. **Fresh install:**
   - Double-click `FinanceAppInstaller.exe`.
   - **SmartScreen warning** ("Windows protected your PC") — click
     **More info → Run anyway**. This is unavoidable until we sign
     the installer with an Authenticode cert; see "Code-signing"
     below.
   - Verify: no UAC prompt, no "Python downloading…" message, install
     dir is `%LOCALAPPDATA%\Programs\Finance Analysis`.
   - Verify Add/Remove Programs entry shows publisher, version, the
     Finance Analysis icon (NOT the generic NSIS uninstaller icon —
     this is what `UninstallIcon` in the NSI sets), About URL, and
     accurate size.
   - Launch the desktop shortcut. The shortcut should also show the
     Finance Analysis icon. Dashboard loads in the default browser
     within ~2s.

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

5. **Scrape using system browser:**
   - Set up a credential, kick off a scrape.
   - Verify Playwright launches Edge (or Chrome if installed) and
     drives it. The log line "scraper using channel=msedge" (or
     "channel=chrome") in `%USERPROFILE%\.finance-analysis\logs\uvicorn.log`
     confirms the channel.

### macOS (Apple Silicon)

We don't ship a downloaded artifact, but the source-build path
needs the same coverage to make sure each release still produces a
working bundle locally.

1. **Fresh build + install:**
   - `git pull && poetry install --no-root --with build && (cd frontend && npm install)`.
   - `python build/build_app.py --no-wrap` — verify the build
     completes and `dist/Finance Analysis.app` exists.
   - `mv "dist/Finance Analysis.app" /Applications/` — drag-replace
     any existing version.
   - Launch from Launchpad. **No "is damaged" / "cannot verify"
     dialog.** Dashboard opens in the default browser within ~2s.

2. **Smoke-test the binary directly:**
   - `"/Applications/Finance Analysis.app/Contents/MacOS/FinanceAnalysis" --smoke-test`.
   - Verify all four probes (`/api/version`, `/`, `/assets/*.js`,
     `/api/onboarding/status`) print `smoke-test ok:`.

3. **In-app uninstall (preserve data):**
   - Open Settings → Uninstall Finance Analysis.
   - Confirm without ticking "Also delete my data".
   - Verify: `.app` gone from /Applications, but
     `~/.finance-analysis/` (DB, credentials YAML) intact.
   - Rebuild and re-launch — data picks up.

4. **In-app uninstall (wipe data):**
   - Repeat (3) with "Also delete my data" ticked.
   - Verify: `.app` gone AND `~/.finance-analysis/` gone AND
     `security find-generic-password -s finance-analysis-app` returns
     nothing.

5. **Scrape using system browser:**
   - With Chrome installed, set up a credential and kick off a scrape.
   - Verify the log line "scraper using channel=chrome" in
     `~/.finance-analysis/logs/uvicorn.log`.
   - Then test the no-browser path: temporarily move
     `/Applications/Google Chrome.app` aside, kick off a scrape, and
     confirm the UI surfaces "Install Google Chrome…" — the scraper
     must not silently hang or download Chromium.

## Code-signing and notarization (out of scope)

We don't sign the Windows installer (no Authenticode cert) or
notarize the macOS .app (no Apple Developer ID). This means:

- **Windows: SmartScreen warning** — "Windows protected your PC.
  Microsoft Defender SmartScreen prevented an unrecognized app from
  starting." This appears for every new unsigned build for ~24-48h
  after publication, then SmartScreen's reputation system stops
  flagging it. The user clicks **More info → Run anyway**.

  *Why no fix-smartscreen.bat:* SmartScreen reads NTFS's "Mark of the
  Web" Alternate Data Stream that Edge / Chrome attach to downloaded
  files — the Windows analog of macOS's quarantine xattr. The
  PowerShell `Unblock-File` cmdlet removes the marker, but a
  `.bat` / `.ps1` we shipped to do it would itself be MOTW-blocked by
  SmartScreen. Chicken-and-egg. The realistic path is the click-through.

- **macOS: every download path is blocked on Tahoe.** This is why we
  stopped shipping a `.dmg`. The full diagnosis:
  - Unsigned `.app` + quarantine xattr → "is damaged" dialog with no
    bypass button (macOS 15+).
  - `.command` shell script + quarantine → "cannot verify developer"
    dialog with no Open button.
  - `.pkg` installer + quarantine → "Apple could not verify… free of
    malware" dialog with no Open button.
  - Right-click → Open: shows the same dead-end dialog as
    double-click on macOS 15+ (Apple removed the bypass from the
    context-menu path too).
  - System Settings → Privacy & Security → "Open Anyway": works, but
    is too many steps for a "casual install" UX.
  - Terminal `xattr -cr <path> && open <path>`: works, but is a
    command-line workflow.

  The only real fix is Apple Developer ID + notarization. Until then,
  macOS users build from source (see "macOS install" above), which
  produces a bundle without the quarantine xattr in the first place.

When we do invest in signing certs, the changes are:

- NSIS: add a `signtool sign` post-build step in `release.yml`.
- macOS: extend `build_dmg.sh` with `codesign` + `notarytool submit`,
  then re-add the `macos-15` (or newer) entry to the release.yml
  build matrix.
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
├── build_app.py         # Orchestrator: frontend → pyinstaller → DMG/NSIS
├── installer_script.nsi # Slim NSIS wrapper around PyInstaller dist/
├── build_dmg.sh         # Slim macOS DMG wrapper around PyInstaller .app
│                        # (local use only — not invoked by CI; macOS
│                        #  users typically run build_app.py --no-wrap
│                        #  and skip the DMG step entirely)
└── macos/
    ├── uninstall.command       # Standalone uninstaller (inside .app's Resources)
    └── fix-gatekeeper.command  # Was placed in the DMG root to strip
                                # quarantine. Kept in the repo for the
                                # local-DMG flow (some macOS users still
                                # build the DMG locally and share it
                                # between their own machines), but
                                # never reaches a public download.

# Generated, not checked in:
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
