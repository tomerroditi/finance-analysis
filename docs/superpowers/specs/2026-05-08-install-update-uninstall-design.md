# Install / Update / Uninstall Experience — Design

## Problem

The desktop app (Windows installer + macOS DMG) ships every push to `main`,
but the install/update/uninstall flows are lossy:

- **Update awareness:** users don't know a new release exists. They have to
  watch the GitHub releases page.
- **Update hygiene:** Windows reinstalls overwrite `Program Files` content
  but leave the in-INSTDIR `.venv` stale across dependency changes; macOS
  re-runs `setup.sh` (full `poetry install`) on every launch even when the
  bundle hasn't changed.
- **Uninstall on Windows:** silently leaves `~/.finance-analysis/` (DB,
  credentials YAML, categories YAML) and Windows Credential Manager
  entries; doesn't check whether the app is running.
- **Uninstall on macOS:** there isn't one. Drag-to-Trash leaves the
  synced `~/.finance-analysis/app/` copy, the venv, the user-data dir,
  and Keychain entries forever.
- **Install location on Windows:** `Program Files` requires admin and
  fights antivirus on every post-install pip operation.

## Goal

Make installing, upgrading, and uninstalling the app match what users
expect from a modern desktop application:

1. They learn about new releases in-app.
2. Upgrades are clean (stale `.venv` purged on Windows, fast on macOS
   when nothing changed).
3. Uninstalls are explicit, ask whether to keep user data, and clean up
   Keychain.
4. On macOS, an uninstaller is reachable both in-app (Settings) and as
   a standalone script in case the app won't launch.
5. Windows installs without admin, into `$LOCALAPPDATA\Programs`.

## Non-goals

- **Auto-update** (download + apply new build automatically). Without
  code-signing certs the post-update Gatekeeper / SmartScreen friction
  is worse than the current "click the link" flow. Documented as a
  future step pending signing.
- **Code signing / notarization.** Out of scope; documented as known
  limitation.
- **Linux packaging.** No release artifact today.
- **Migrating user-data schema.** Alembic already handles this on
  startup; no install-time migration needed.

## Architecture

```
┌─ In-app update notifier ────────────────────────────────────────┐
│ Frontend toast (5s after load) + Settings → About panel          │
│   ↓ TanStack Query, 6h staleTime, dismiss-per-version (localStorage)
│ GET/POST /api/updates/check                                      │
│   ↓ UpdateService (file-cached 24h)                              │
│ GitHub Releases API                                              │
└──────────────────────────────────────────────────────────────────┘

┌─ Cleaner OS upgrade ────────────────────────────────────────────┐
│ Windows NSIS:                                                    │
│   per-user $LOCALAPPDATA\Programs install (no admin)             │
│   .onInit detects existing install → silent uninstall (data      │
│     preserved) → fresh install                                   │
│   migrates legacy HKLM/$PROGRAMFILES install on first run        │
│ macOS launcher.sh:                                               │
│   reads CFBundleVersion vs ~/.finance-analysis/app/.installed_version│
│   skips rsync + setup.sh when versions match → fast launch       │
└──────────────────────────────────────────────────────────────────┘

┌─ Uninstall (cross-platform) ────────────────────────────────────┐
│ Single source of truth: backend/uninstall/cleanup.py             │
│   - python -m backend.uninstall {--keep-data | --wipe}           │
│   - knows: ~/.finance-analysis/, keyring service                 │
│     "finance-analysis-app" + "-demo", credential keys            │
│ Three frontends to it:                                           │
│   1. Windows NSIS uninstaller                                    │
│   2. macOS in-app Settings → Advanced → Uninstall                │
│   3. macOS Uninstall.command (bundled in .app + ~/.finance-analysis)│
│ All ask "Also delete my data + passwords?" (default unchecked).  │
└──────────────────────────────────────────────────────────────────┘
```

## Component design

### 1. Cleanup module (load-bearing)

`backend/uninstall/cleanup.py` — pure-Python module callable from a
process or a CLI:

```python
def run(*, wipe_data: bool, dry_run: bool = False) -> CleanupReport:
    """Remove keyring entries (and optionally user data + credentials yaml).

    Returns a structured report listing what was removed and what was
    skipped. Always wipes Keychain entries (they are app-specific).
    Wipes ~/.finance-analysis/ only when wipe_data=True.
    """
```

CLI: `python -m backend.uninstall --keep-data | --wipe [--dry-run]`.
Exits 0 on success, 1 on partial failure, prints JSON report to stdout.

Knowledge encoded:
- Keyring service names: `finance-analysis-app` and `finance-analysis-app-demo`.
- Iterates the credentials DB (if reachable) to enumerate the exact
  `(service, provider, account_name, field)` keys; falls back to
  best-effort enumeration via `keyring`'s backend introspection where
  available.
- User-data dir: `Path.home() / ".finance-analysis"` (matches
  `AppConfig.user_data_dir`).

### 2. Version source of truth

- Backend reads version from `pyproject.toml` once at module load
  (Python 3.11+ stdlib `tomllib`). Replaces hardcoded `"1.0.0"` in
  `backend/main.py`.
- New endpoint: `GET /api/version → {version, platform}`.
- `platform` is `sys.platform` ("darwin" / "win32" / "linux") so the
  frontend can show macOS-only sections (the in-app uninstaller).

### 3. Update service

`backend/services/update_service.py`:

- `check(force: bool=False) -> UpdateInfo`
- Cache: `~/.finance-analysis/.update_cache.json`, TTL 24h
- Source: `https://api.github.com/repos/tomerroditi/finance-analysis/releases/latest`
- Failure → `UpdateInfo(error="unavailable")`, never raises to the route
- Picks the OS-matching asset: `.dmg` for darwin, `.exe` for win32; on
  Linux returns release page URL only.

`backend/routes/updates.py`:
- `GET /api/updates/check` — return cached/refreshed result
- `POST /api/updates/check` — force refresh

PWA: `/api/updates/*` excluded from SW runtime cache and from
IndexedDB persistence (TTL is ours, not the browser's).

### 4. Uninstall route (macOS only)

`backend/routes/uninstall.py`:
- `POST /api/uninstall {wipe_data: bool}`
- Returns 400 on non-darwin platforms.
- Synchronously runs `cleanup.run(wipe_data=...)` (Keychain + optional
  user-data wipe).
- Writes `/tmp/finance-analysis-uninstall-<pid>.sh` deferred script:
  - waits 2s (response flushes)
  - removes `/Applications/Finance Analysis.app` (if present)
  - removes `~/.finance-analysis/app/`
  - if `wipe_data`, removes `~/.finance-analysis/` entirely
  - kills uvicorn parent
- Launches the script in a Terminal window via `osascript`.

### 5. Frontend

**Update notifier:**
- `frontend/src/services/api.ts` adds `updatesApi.check()`,
  `updatesApi.refresh()`, `versionApi.get()`.
- `frontend/src/hooks/useUpdateCheck.ts` — TanStack Query hook,
  `staleTime: 6h`, `enabled: !import.meta.env.DEV`.
- `frontend/src/components/UpdateAvailableToast.tsx` — appears 5s
  after mount, dismissible per-version (localStorage key
  `update-toast-dismissed-${latest}`).
- `frontend/src/components/settings/AboutPanel.tsx` — "current X,
  latest Y, [Check now] [Download] [Open releases page]".

**Uninstall:**
- `frontend/src/components/settings/UninstallSection.tsx` — only
  rendered when `versionApi.get()` returns `platform === "darwin"`.
- Confirm modal with the keep/wipe checkbox, calls
  `uninstallApi.uninstall({wipe_data})`, shows progress then closes.

**i18n:** new keys under `updates.*` and `uninstall.*` in both
`en.json` and `he.json`.

**PWA:** `sw.ts` URL filter and `queryClient.ts`
`NON_PERSISTABLE_KEY_PREFIXES` both extended.

### 6. macOS launcher

`build/macos/launcher.sh`:
- Reads `CFBundleVersion` via `defaults read`.
- Compares to `$USER_APP/.installed_version`.
- Skips rsync + setup if marker matches and `.venv` and
  `frontend/dist` exist.
- On version mismatch: rsync, run setup.sh, then write the marker
  *after* setup succeeds (failed setup doesn't get cached as done).
- Always copies `uninstall.command` to `~/.finance-analysis/uninstall.command`
  (so the standalone uninstaller survives the .app being moved).

### 7. macOS standalone uninstaller

`build/macos/uninstall.command`:
- Bash, double-clickable, `read -p` prompt for keep/wipe.
- Runs `python -m backend.uninstall --wipe` or `--keep-data` from the
  synced venv (or system Python fallback if venv is gone).
- `pkill -f "uvicorn backend.main:app"`, then `rm -rf` the .app and
  the synced runtime copy.

`build/build_dmg.sh` adds a step to copy `uninstall.command` into
`Contents/Resources/` of the .app.

### 8. Windows installer

`build/installer_script.nsi` — full rewrite:

- `RequestExecutionLevel user`
- `InstallDir "$LOCALAPPDATA\Programs\Finance Analysis"`
- `.onInit`:
  - Detect HKCU per-user install → silent uninstall (data preserved)
  - Detect legacy HKLM install → message box → silent legacy uninstall
- Section `Install`:
  - Copy files, run `setup.bat`, populate HKCU\\...\\Uninstall key
    with full set: `DisplayName`, `DisplayVersion`, `Publisher`,
    `DisplayIcon`, `InstallLocation`, `UninstallString`,
    `QuietUninstallString`, `URLInfoAbout`, `URLUpdateInfo`,
    `NoModify`, `NoRepair`, `EstimatedSize`.
- Uninstaller adds a `MUI_UNPAGE_COMPONENTS` page with one optional
  component: "Also delete my data and saved passwords."
  - Pre-uninstall: PowerShell check for processes whose path is
    inside `$INSTDIR`; if found, prompt Retry/Cancel.
  - Calls `python -m backend.uninstall --keep-data` or `--wipe` from
    the in-INSTDIR venv *before* deleting `$INSTDIR`.
  - Removes shortcuts, registry entries.

`build/setup.bat` keeps its current Python/Node bootstrap (per-user
install means it doesn't need admin). The only change: it runs in
the per-user dir without UAC.

### 9. Documentation

- `.claude/rules/installation_and_updates.md` — architecture, who
  calls what, how releases work, how to test changes.
- README brief mention of update + uninstall flows.

## Test strategy

- **Unit tests for `backend/uninstall/cleanup.py`** with a temporary
  user-data dir + a `keyring.backends.fake` (or stubbed `keyring`
  module) — covers `--wipe`, `--keep-data`, missing data dir, missing
  keyring entries.
- **Unit tests for `backend/services/update_service.py`** — cache
  hit, cache miss + GitHub OK, GitHub 5xx → `error="unavailable"`,
  semver compare for current >= latest, asset-picker for each
  platform.
- **Route tests** for `/api/version`, `/api/updates/check` GET +
  POST, and `/api/uninstall` (mocked subprocess + non-darwin 400).
- **Frontend Vitest** for `useUpdateCheck` (mocked api, dismissal
  logic) and the toast component (renders only when outdated).
- **Manual smoke test plan** documented in
  `installation_and_updates.md` for the NSIS installer (run a
  build → install → upgrade → uninstall both with and without the
  data-deletion checkbox) and the macOS DMG (same matrix).

## Risk / migration notes

- **Windows users on the old Program Files install:** first run of
  the new installer detects the HKLM key, prompts to migrate, runs
  the old uninstaller, proceeds. Their `~/.finance-analysis/` data
  is untouched throughout.
- **macOS users on the current build:** their existing
  `~/.finance-analysis/app/` will be re-rsynced once on the next
  launch (because the new launcher will not find a
  `.installed_version` marker), and from then on the launch becomes
  fast.
- **`backend/main.py` version field** changes from `"1.0.0"` to the
  pyproject value — the FastAPI OpenAPI spec version will change.
  No external API consumers depend on this; safe.

## Out-of-band notes

- Authenticode + Apple notarization remain unsigned. Both stores
  flag every download. Documented as a future investment.
- `frontend/package-lock.json` lockfile hygiene rule (per
  `frontend_pwa.md`): no new frontend deps are required for this
  change, so the lockfile is not touched.
