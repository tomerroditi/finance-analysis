import shutil
from pathlib import Path

EXCLUDE_DIRS = {"__pycache__", "node_modules", ".mypy_cache", ".pytest_cache"}
EXCLUDE_FILES = {"build_installer.py", "installer_script.nsi", "FinanceAppInstaller.exe", "build_dmg.sh", "FinanceAnalysis.dmg"}

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
