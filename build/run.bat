@echo off
setlocal

echo ==================================================
echo      Finance Analysis App - Launcher
echo ==================================================

cd /d "%~dp0\finance-analysis"

:: Activate environment
call .venv\Scripts\activate.bat

:: Launch app
start http://localhost:8501/
streamlit run main.py --server.port 8501

endlocal
