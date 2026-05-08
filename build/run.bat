@echo off
setlocal

echo ==================================================
echo      Finance Analysis App - Launcher
echo ==================================================

cd /d "%~dp0"
cd ..

call .venv\Scripts\activate.bat

for /f "delims=" %%p in ('python build\find_port.py') do set PORT=%%p

echo Starting on http://localhost:%PORT%
start "" "http://localhost:%PORT%"
uvicorn backend.main:app --host 127.0.0.1 --port %PORT%

endlocal
