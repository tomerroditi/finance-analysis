# Full-Stack Release CI/CD Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the legacy Streamlit CI/CD pipeline with a full-stack release workflow that runs CI checks, bumps the version, builds an NSIS installer bundling FastAPI + React, and creates a GitHub Release.

**Architecture:** Single GitHub Actions workflow with 4 sequential jobs: ci-checks → bump-version → build-installer → create-release. FastAPI serves the pre-built React app via a conditional StaticFiles mount in production. The Windows installer bundles everything for single-port (8765) operation.

**Tech Stack:** GitHub Actions, Commitizen, NSIS, FastAPI StaticFiles, Vite build

---

### Task 1: Update Commitizen version_files config

**Files:**
- Modify: `pyproject.toml:36-44`

**Step 1: Add frontend/package.json to version_files**

In `pyproject.toml`, replace the `version_files` list:

```toml
version_files = [
    "pyproject.toml:tool.poetry.version",
    "frontend/package.json:\"version\"",
    "build/installer_script.nsi:^!define APP_VERSION \".*\"$",
]
```

**Step 2: Sync frontend/package.json version**

In `frontend/package.json`, update the version from `"0.0.0"` to `"1.0.0"` to match `pyproject.toml`.

**Step 3: Verify commitizen config loads**

Run: `cd /Users/tomer/Desktop/finance-analysis && poetry run cz version`
Expected: `1.0.0`

**Step 4: Commit**

```bash
git add pyproject.toml frontend/package.json
git commit -m "build: sync version across pyproject.toml, package.json, and NSIS"
```

---

### Task 2: Add static file serving to FastAPI for production

**Files:**
- Modify: `backend/main.py`

**Step 1: Add StaticFiles + catch-all route**

After all `app.include_router(...)` calls and exception handlers, add the following at the bottom of `backend/main.py` (replacing the existing `root` endpoint):

```python
import os
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Serve frontend static build in production
_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="static-assets")

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        """Serve the React SPA for all non-API routes."""
        file_path = _frontend_dist / path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_frontend_dist / "index.html")
```

Remove the existing `root()` endpoint (`@app.get("/")`) since the SPA catch-all will handle `/`.

Keep the `/health` endpoint above the catch-all so it still works.

**Step 2: Verify dev mode is unaffected**

Run: `poetry run uvicorn backend.main:app --reload`
Expected: Server starts without errors. `GET /` returns API JSON (since `frontend/dist` doesn't exist in dev). `GET /health` returns `{"status": "healthy"}`.

**Step 3: Verify static serving works when dist exists**

Run:
```bash
cd frontend && npm run build && cd ..
poetry run uvicorn backend.main:app --port 8765
```
Expected: Browser at `http://localhost:8765` serves the React app. `GET /api/health` still works. `GET /health` still works.

Clean up after test:
```bash
rm -rf frontend/dist
```

**Step 4: Commit**

```bash
git add backend/main.py
git commit -m "feat: serve React static build from FastAPI in production"
```

---

### Task 3: Update build_installer.py for full-stack

**Files:**
- Modify: `build/build_installer.py`

**Step 1: Rewrite build_installer.py**

Replace the entire file contents:

```python
import shutil
from pathlib import Path

EXCLUDE_DIRS = {"__pycache__", "node_modules", ".mypy_cache", ".pytest_cache"}
EXCLUDE_FILES = {"build_installer.py", "installer_script.nsi", "FinanceAppInstaller.exe"}

# New full-stack source layout
SOURCE_ITEMS = [
    "backend",
    "build",
    "icon.ico",
    "pyproject.toml",
    "poetry.lock",
]

# frontend/dist is copied separately (pre-built React app)
FRONTEND_DIST = "frontend/dist"

SRC = Path(__file__).parent.parent
DEST = Path(__file__).parent.parent / "dist"


def should_exclude(path):
    parts = set(path.parts)
    return parts & EXCLUDE_DIRS or path.name in EXCLUDE_FILES


def copy_clean():
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir()

    for src in SOURCE_ITEMS:
        src_path = SRC / src
        dst_path = DEST / src_path.name

        if src_path.is_file():
            shutil.copy2(src_path, dst_path)
        elif src_path.is_dir():
            for path in src_path.rglob("*"):
                if path.is_file() and not should_exclude(path):
                    rel = path.relative_to(src_path)
                    target = dst_path / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)

    # Copy pre-built frontend
    frontend_src = SRC / FRONTEND_DIST
    if frontend_src.is_dir():
        frontend_dst = DEST / "frontend" / "dist"
        shutil.copytree(frontend_src, frontend_dst)
    else:
        print("WARNING: frontend/dist not found. Build frontend first: cd frontend && npm run build")


if __name__ == "__main__":
    copy_clean()
    print("Build directory ready at: dist/")
```

**Step 2: Test the build script**

Run:
```bash
cd frontend && npm run build && cd ..
python build/build_installer.py
ls dist/
```
Expected: `dist/` contains `backend/`, `frontend/dist/`, `build/`, `icon.ico`, `pyproject.toml`, `poetry.lock`. No `fad/`, no `main.py`.

Clean up:
```bash
rm -rf dist frontend/dist
```

**Step 3: Commit**

```bash
git add build/build_installer.py
git commit -m "build: update build_installer.py for full-stack app layout"
```

---

### Task 4: Update setup.bat for full-stack

**Files:**
- Modify: `build/setup.bat`

**Step 1: Rewrite setup.bat**

Replace the entire file:

```bat
@echo off
setlocal enabledelayedexpansion

echo ==================================================
echo      Finance Analysis App - One-Time Setup
echo ==================================================

:: Set working directory to project root (one level above build/)
cd /d "%~dp0"
cd ..

set "ENV_DIR=.venv"
set "USER_DIR=%USERPROFILE%\.finance-analysis"

:: -------------------------
:: Check Python 3.12
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Python not found. Installing Python 3.12...
    powershell -Command "& {Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.6/python-3.12.6-amd64.exe' -OutFile 'python_installer.exe'}"
    start /wait python_installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
    del python_installer.exe
) ELSE (
    echo Python is installed.
)

:: -------------------------
:: Check Node.js (needed for scraper)
node --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Node.js not found. Installing...
    powershell -Command "& {Invoke-WebRequest -Uri 'https://nodejs.org/dist/v20.11.0/node-v20.11.0-x64.msi' -OutFile 'node_installer.msi'}"
    msiexec /i node_installer.msi /quiet
    del node_installer.msi
) ELSE (
    echo Node.js is installed.
)

:: -------------------------
:: Set up user data directory
if not exist "%USER_DIR%" mkdir "%USER_DIR%"

:: -------------------------
:: Set up Python virtual environment
IF NOT EXIST %ENV_DIR% (
    echo Creating virtual environment...
    python -m venv %ENV_DIR%
)

call %ENV_DIR%\Scripts\activate.bat

echo Upgrading pip...
python -m pip install --upgrade pip

echo Installing Python dependencies...
pip install poetry
poetry install --no-root --no-interaction

:: -------------------------
:: Install scraper Node packages
IF EXIST backend\scraper\node\package.json (
    cd backend\scraper\node
    IF NOT EXIST node_modules (
        echo Installing scraper Node packages...
        npm install --yes --loglevel=error
    ) ELSE (
        echo Scraper Node modules already installed.
    )
    cd ..\..\..
)

IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo Installation failed. Press any key to close...
    pause > nul
)

echo.
echo Setup complete. You can now run the app using: run.bat
echo.
```

**Step 2: Commit**

```bash
git add build/setup.bat
git commit -m "build: update setup.bat for full-stack app"
```

---

### Task 5: Update run.bat for FastAPI

**Files:**
- Modify: `build/run.bat`

**Step 1: Rewrite run.bat**

Replace the entire file:

```bat
@echo off
setlocal

echo ==================================================
echo      Finance Analysis App - Launcher
echo ==================================================

cd /d "%~dp0"
cd ..

:: Activate environment
call .venv\Scripts\activate.bat

:: Launch FastAPI server (serves both API and frontend)
start "" http://localhost:8765
uvicorn backend.main:app --host 127.0.0.1 --port 8765

endlocal
```

**Step 2: Commit**

```bash
git add build/run.bat
git commit -m "build: update run.bat to launch FastAPI on port 8765"
```

---

### Task 6: Update installer_script.nsi

**Files:**
- Modify: `build/installer_script.nsi`

**Step 1: Update NSIS script**

No structural changes needed — the NSIS script already copies everything from `dist/` via `File /r "..\dist\*.*"`. The `build_installer.py` changes (Task 3) ensure the right files end up in `dist/`. Just verify the version define and publisher info are correct (they are already managed by Commitizen).

No changes required unless you want to update descriptions. Verify the file is correct as-is.

**Step 2: Commit (skip if no changes)**

---

### Task 7: Replace the GitHub Actions workflow

**Files:**
- Delete: `.github/workflows/bump-version.yml`
- Create: `.github/workflows/release.yml`

**Step 1: Delete old workflow**

```bash
rm .github/workflows/bump-version.yml
```

**Step 2: Create new release.yml**

Create `.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    branches:
      - main

jobs:
  ci-checks:
    runs-on: ubuntu-latest
    if: "!startsWith(github.event.head_commit.message, 'bump:')"
    name: Run CI checks

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install Poetry and dependencies
        run: |
          pip install poetry
          poetry install --no-root

      - name: Run backend tests
        run: poetry run pytest

      - name: Set up Node 20
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json

      - name: Install frontend dependencies
        run: cd frontend && npm ci

      - name: Lint frontend
        run: cd frontend && npm run lint

      - name: Build frontend
        run: cd frontend && npm run build

  get-version:
    runs-on: ubuntu-latest
    needs: ci-checks
    name: Get current version
    outputs:
      version: ${{ steps.get-version.outputs.version }}

    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          token: "${{ secrets.PERSONAL_ACCESS_TOKEN }}"
          fetch-depth: 0

      - name: Get version from pyproject.toml
        id: get-version
        run: |
          pip install toml
          version=$(python -c "import toml; print(toml.load('pyproject.toml')['tool']['poetry']['version'])")
          echo "version=$version" >> $GITHUB_OUTPUT

  bump-version:
    runs-on: ubuntu-latest
    needs: get-version
    name: Bump version and create changelog
    outputs:
      version: ${{ steps.bump.outputs.version }}

    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          token: "${{ secrets.PERSONAL_ACCESS_TOKEN }}"
          fetch-depth: 0

      - name: Set up Node 20
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - id: bump
        name: Run Commitizen bump
        uses: commitizen-tools/commitizen-action@master
        with:
          github_token: ${{ secrets.PERSONAL_ACCESS_TOKEN }}

  build-and-release:
    needs: [get-version, bump-version]
    if: needs.bump-version.outputs.version != needs.get-version.outputs.version
    runs-on: ubuntu-latest
    name: Build installer and create release

    steps:
      - name: Checkout latest code
        uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          fetch-depth: 0
          ref: main

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Set up Node 20
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json

      - name: Build frontend
        run: cd frontend && npm ci && npm run build

      - name: Build installer dist
        run: python build/build_installer.py

      - name: Install NSIS
        run: sudo apt-get update && sudo apt-get install -y nsis

      - name: Build NSIS installer
        run: makensis build/installer_script.nsi

      - name: Verify installer exists
        run: |
          if [ ! -f build/FinanceAppInstaller.exe ]; then
            echo "Installer not found!"
            exit 1
          fi

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: v${{ needs.bump-version.outputs.version }}
          name: Release v${{ needs.bump-version.outputs.version }}
          body_path: CHANGELOG.md
          files: build/FinanceAppInstaller.exe
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Step 3: Commit**

```bash
git add .github/workflows/release.yml
git rm .github/workflows/bump-version.yml
git commit -m "ci: replace legacy Streamlit release workflow with full-stack pipeline"
```

---

### Task 8: Final verification

**Step 1: Verify backend starts clean**

Run: `poetry run uvicorn backend.main:app --reload`
Expected: No errors. `/health` returns `{"status": "healthy"}`. `/` returns API JSON (no `frontend/dist`).

**Step 2: Verify full-stack production mode**

Run:
```bash
cd frontend && npm run build && cd ..
poetry run uvicorn backend.main:app --port 8765
```
Expected: `http://localhost:8765` serves the React app. API routes still work at `/api/*`.

Clean up:
```bash
rm -rf frontend/dist
```

**Step 3: Verify build_installer.py produces correct dist**

Run:
```bash
cd frontend && npm run build && cd ..
python build/build_installer.py
ls -la dist/
ls dist/frontend/dist/
```
Expected: `dist/` contains `backend/`, `frontend/dist/`, `build/`, `icon.ico`, `pyproject.toml`, `poetry.lock`.

Clean up:
```bash
rm -rf dist frontend/dist
```

**Step 4: Validate workflow YAML syntax**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"`
Expected: No errors.

**Step 5: Commit any fixes if needed**
