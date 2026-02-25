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
