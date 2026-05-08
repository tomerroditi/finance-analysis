# Installation, Updates, and Uninstallation

How the desktop app is installed, upgraded, and removed on Windows
and macOS. Read this before touching anything in `build/`,
`backend/uninstall/`, `backend/services/update_service.py`, or the
`/api/updates` and `/api/uninstall` routes.

## Three flows, one cleanup module

```
                              ┌──────────────────────────────┐
Windows NSIS Uninstall.exe ──▶│                              │
                              │                              │
macOS uninstall.command   ──▶ │  backend/uninstall/cleanup.py │──▶ Keychain entries removed
(double-clicked or in-app)    │  python -m backend.uninstall  │──▶ ~/.finance-analysis/ wiped
                              │                              │     (only when --wipe)
macOS POST /api/uninstall ──▶│                              │
                              └──────────────────────────────┘
```

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

## Windows install (NSIS)

`build/installer_script.nsi`:

- **Per-user install** at `$LOCALAPPDATA\Programs\Finance Analysis`.
  No `RequestExecutionLevel admin`. No UAC prompts on install or
  upgrade. The in-INSTDIR `.venv` lives somewhere we can write to
  without ACL friction.
- **HKCU `Uninstall` registry entry** — Add/Remove Programs sees
  `DisplayName`, `DisplayVersion`, `Publisher`, `DisplayIcon`,
  `InstallLocation`, `UninstallString`, `QuietUninstallString`,
  `URLInfoAbout`, `URLUpdateInfo`, `EstimatedSize`, `NoModify`,
  `NoRepair`. Looks like a real app, supports `winget uninstall`.
- **`.onInit` migration logic:**
  1. If a previous per-user install (HKCU\Software\Finance Analysis)
     exists, run its uninstaller silently with `_?=$0` so we wait for
     it before laying down the new files. User data preserved
     (Uninstall.exe in default mode is "remove binaries only").
  2. If a legacy HKLM/Program Files install exists, prompt the user
     and migrate. Aborts on No.

### Windows uninstall

Components page (`MUI_UNPAGE_COMPONENTS`) shows one optional
checkbox: **"Also delete my data and saved passwords."** Default:
unchecked.

Uninstall flow:
1. `taskkill /F /FI "IMAGENAME eq uvicorn.exe"` — best-effort stop.
2. `python -m backend.uninstall --wipe | --keep-data` from the
   in-INSTDIR venv. This handles Keychain (Windows Credential Manager
   via the `keyring` package) and the user-data dir, depending on the
   checkbox.
3. `RMDir /r $INSTDIR` — removes the venv and program files.
4. Delete shortcuts and HKCU registry entries.

The Python CLI runs **before** `RMDir /r $INSTDIR` so the venv-hosted
interpreter is still available. The unit tests cover the cleanup
behaviour; testing the NSIS UI itself requires a Windows VM, which is
documented in the manual smoke-test plan below.

## macOS install (DMG)

`build/build_dmg.sh` produces a real `.app` bundle inside a
drag-to-Applications DMG. The bundle layout:

```
Finance Analysis.app/
├── Contents/
│   ├── MacOS/FinanceAnalysis        ← launcher.sh (entry point)
│   ├── Info.plist                    ← CFBundleVersion
│   ├── Resources/
│   │   ├── icon.icns
│   │   ├── uninstall.command         ← standalone uninstaller (DMG-visible)
│   │   └── app/                      ← full source tree (rsynced on launch)
│   │       └── build/macos/uninstall.command
```

### macOS launcher (version-gated)

`build/macos/launcher.sh`:

1. Reads `CFBundleVersion` from `Info.plist`.
2. Compares to `~/.finance-analysis/app/.installed_version`.
3. **If they match AND `.venv` + `frontend/dist` exist** → skip rsync
   + setup, run `run.sh` directly. ~2s launch.
4. **Otherwise** → rsync the bundle into `~/.finance-analysis/app`,
   run `setup.sh`, write the version marker **after setup succeeds**
   (a failed setup doesn't get cached as "done"). ~30-60s launch
   on a cold install or build change.
5. Always copies `uninstall.command` to `~/.finance-analysis/`
   so the standalone uninstaller survives bundle deletion.

### macOS uninstall (three flavours)

1. **In-app:** Settings → Uninstall Finance Analysis. Calls
   `POST /api/uninstall`. Backend runs `cleanup.run(...)` synchronously,
   then writes a deferred shell script to `/tmp` and launches it in
   Terminal via `osascript`. The deferred script waits 2s (so the
   HTTP response can flush) then removes the .app + the synced
   runtime copy + (if wiping) the user-data dir + kills uvicorn.
2. **Standalone `Uninstall Finance Analysis.command`:** double-click in
   `Contents/Resources/` (inside the .app) or in `~/.finance-analysis/`
   (copied there by the launcher). Asks the keep/wipe question via
   `read -p`, calls the same Python cleanup CLI from the synced venv,
   then removes the .app.
3. **Drag-to-Trash:** still works, but leaves user data + Keychain
   entries behind. We don't try to fix this — macOS doesn't support
   "run on uninstall" hooks. Documented in the README so users know
   to use the standalone or in-app paths if they want a clean removal.

## Manual smoke test plan

Cutting a release? Run through this matrix on a clean VM (or fresh
user account on macOS):

### Windows

1. **Fresh install:**
   - Run `FinanceAppInstaller.exe`.
   - Verify: no UAC prompt, install dir is
     `%LOCALAPPDATA%\Programs\Finance Analysis`.
   - Verify Add/Remove Programs entry shows publisher, version, icon,
     About URL, and accurate size.
   - Launch the desktop shortcut. App opens, dashboard loads.

2. **Upgrade in place:**
   - With v1.X installed, run installer for v1.X+1.
   - Verify: no UAC prompt, no "an existing version is installed"
     prompt, no orphan venv. The HKCU registry entry should reflect
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

### macOS

1. **Fresh install:**
   - Open `FinanceAnalysis.dmg`, drag to Applications.
   - Launch from Launchpad. Terminal opens, setup.sh runs (~30-60s),
     dashboard appears in default browser.
   - Verify `~/.finance-analysis/app/.installed_version` equals the
     bundle's `CFBundleVersion`.

2. **Quit + relaunch:**
   - Close the browser tab and the Terminal window.
   - Launch again. Setup MUST be skipped — the version marker is
     fresh, .venv exists. Launch should feel ~instant.

3. **Upgrade:**
   - Replace the .app with a newer build (drag-to-Applications,
     overwrite).
   - Launch. Setup runs again because the version marker no longer
     matches. Marker updates after setup succeeds.

4. **In-app uninstall (preserve data):**
   - Open Settings → Uninstall Finance Analysis.
   - Confirm without ticking "Also delete my data".
   - Verify: .app gone from /Applications, `~/.finance-analysis/app/`
     gone, but the user-data files (DB, credentials YAML) intact.
   - Re-install (drag-to-Applications) and re-launch — data picks up.

5. **Standalone uninstall.command:**
   - With app installed, double-click `~/.finance-analysis/uninstall.command`.
   - Type `y` at the prompt. Verify the .app is removed AND the
     user-data dir is gone AND `security find-generic-password -s
     finance-analysis-app` returns nothing.

6. **Drag-to-Trash regression check:**
   - Drag `Finance Analysis.app` to Trash.
   - User data should remain (this is the documented behaviour).

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
├── installer_script.nsi # Windows NSIS installer
├── build_dmg.sh         # macOS DMG builder
├── build_installer.py   # dist/ tree assembler (Python)
├── setup.sh             # macOS post-install (deps install)
├── setup.bat            # Windows post-install (deps install)
├── run.sh / run.bat     # uvicorn launcher
├── find_port.py
└── macos/
    ├── launcher.sh      # CFBundleExecutable entry point
    └── uninstall.command # standalone uninstaller

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
