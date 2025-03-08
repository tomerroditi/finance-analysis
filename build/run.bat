@echo off
setlocal

echo ==================================================
echo      Finance Analysis App - Launcher
echo ==================================================

cd /d "%~dp0"
cd ..

:: Activate environment
call .venv\Scripts\activate.bat

:: Launch app
streamlit run main.py --server.port 8501
start http://localhost:8501/

endlocal
