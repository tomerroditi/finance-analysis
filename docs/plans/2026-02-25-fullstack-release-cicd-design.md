# Full-Stack Release CI/CD Design

## Context

The current CI/CD workflow (`bump-version.yml`) was built for the old Streamlit-based app. It builds an NSIS Windows installer that bundles the deprecated `fad/` package, `main.py`, and Streamlit config. The app has since been rewritten as a FastAPI backend + React 19 frontend. The release pipeline needs to reflect this.

## Decisions

- **Artifact:** Windows NSIS installer (updated for full-stack)
- **CI checks:** Run pytest + frontend lint/build as a gate before version bump
- **Frontend serving:** FastAPI serves the pre-built React static files via `StaticFiles` mount (single process, single port)
- **Version sync:** Commitizen bumps both `pyproject.toml` and `frontend/package.json`
- **Installed app port:** 8765 (avoids collision with dev ports 8000/5173)

## Workflow Structure

Single file `.github/workflows/release.yml`, 4 sequential jobs:

```
ci-checks → bump-version → build-installer → create-release
```

Triggers on push to `main`. Skips if commit message starts with `bump:`.

### Job 1: ci-checks

- Python 3.12: install Poetry, `poetry install --no-root`, `poetry run pytest`
- Node 20: `cd frontend && npm ci`, `npm run lint`, `npm run build`
- Gates the pipeline — failures block version bump

### Job 2: bump-version

- Commitizen bump via `commitizen-tools/commitizen-action`
- Outputs old and new version for comparison
- Same pattern as current workflow

### Job 3: build-installer

- Build frontend: `cd frontend && npm ci && npm run build`
- Run `python build/build_installer.py` to assemble `dist/`
- Run `makensis build/installer_script.nsi` to create `.exe`

### Job 4: create-release

- Only runs if version changed (new != old)
- Creates GitHub Release with changelog and `FinanceAppInstaller.exe`

## Build Installer Changes

### `build_installer.py`

Updated `SOURCE_DIRS` to copy the new app structure:

| Old | New |
|-----|-----|
| `fad/` | `backend/` |
| `main.py` | (removed) |
| — | `frontend/dist/` (pre-built React) |
| `build/` | `build/` (updated scripts) |
| `pyproject.toml` | `pyproject.toml` |
| `poetry.lock` | `poetry.lock` |
| `icon.ico` | `icon.ico` |

### `setup.bat`

Updated for full-stack:
- Installs Python 3.12, Node 20 (for scraper)
- Creates venv, installs Poetry dependencies
- Installs Node packages for scraper (`backend/scraper/node/`)
- Creates `~/.finance-analysis/` user data directory
- Removes all Streamlit config

### `run.bat`

Updated launcher:
- Activates venv
- Starts `uvicorn backend.main:app --host 127.0.0.1 --port 8765`
- Opens browser to `http://localhost:8765`

### `installer_script.nsi`

Same structure, updated file references to match new `dist/` contents.

## Backend Change: Static File Serving

Add conditional `StaticFiles` mount to `backend/main.py`:
- Mount `frontend/dist` at root when the directory exists
- Catch-all route serves `index.html` for SPA client-side routing
- Only activates in production (when `frontend/dist` is present)
- Does not affect dev workflow (Vite dev server handles frontend in dev)

## Commitizen Config Update

In `pyproject.toml`:

```toml
version_files = [
    "pyproject.toml:tool.poetry.version",
    "frontend/package.json:version",
    "build/installer_script.nsi:^!define APP_VERSION \".*\"$",
]
```

Ensures version stays in sync across backend, frontend, and installer.
