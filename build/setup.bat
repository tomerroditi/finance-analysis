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
