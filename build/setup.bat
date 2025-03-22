@echo off
setlocal enabledelayedexpansion

echo ==================================================
echo      Finance Analysis App - One-Time Setup
echo ==================================================

:: Set working directory to script location
cd /d "%~dp0"

:: App folder and user data dir
set "APP_DIR=finance_analysis"
set "ENV_DIR=.venv"
set "USER_DIR=%USERPROFILE%\.finance-analysis"

:: -------------------------
:: Check if app repo exists
IF NOT EXIST %APP_DIR%\main.py (
    echo Cloning the finance-analysis repository...
    git clone https://github.com/tomerroditi/finance-analysis.git
) ELSE (
    echo App source already exists.
)

:: -------------------------
:: Check Git
git --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Git not found. Downloading installer...
    powershell -Command "& {Invoke-WebRequest -Uri 'https://github.com/git-for-windows/git/releases/download/v2.43.0.windows.1/Git-2.43.0-64-bit.exe' -OutFile 'git_installer.exe'}"
    start /wait git_installer.exe /VERYSILENT
    del git_installer.exe
) ELSE (
    echo Git is installed.
)

:: -------------------------
:: Check Python
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Python not found. Installing...
    powershell -Command "& {Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe' -OutFile 'python_installer.exe'}"
    start /wait python_installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
    del python_installer.exe
) ELSE (
    echo Python is installed.
)

:: -------------------------
:: Check Node.js
node --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Node.js not found. Installing...
    powershell -Command "& {Invoke-WebRequest -Uri 'https://nodejs.org/dist/v18.18.2/node-v18.18.2-x64.msi' -OutFile 'node_installer.msi'}"
    msiexec /i node_installer.msi /quiet
    del node_installer.msi
) ELSE (
    echo Node.js is installed.
)

:: -------------------------
:: Check Google Chrome
reg query "HKLM\Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Google Chrome not found. Installing...
    powershell -Command "& {Invoke-WebRequest -Uri 'https://dl.google.com/chrome/install/latest/chrome_installer.exe' -OutFile 'chrome_installer.exe'}"
    start /wait chrome_installer.exe /silent /install
    del chrome_installer.exe
) ELSE (
    echo Google Chrome is installed.
)

:: -------------------------
:: Set up user data directory
if not exist "%USER_DIR%" mkdir "%USER_DIR%"
if not exist "%USER_DIR%\data.db" (
    echo Creating empty SQLite DB...
    type nul > "%USER_DIR%\data.db"
)

:: -------------------------
:: Create .streamlit/secrets.toml dynamically
echo Creating secrets.toml for Streamlit...
mkdir "%APP_DIR%\.streamlit" >nul 2>&1
echo [connections.data] > "%APP_DIR%\.streamlit\secrets.toml"
echo url = "sqlite:///%USER_DIR:/=\%/data.db" >> "%APP_DIR%\.streamlit\secrets.toml"

:: -------------------------
:: Set up Python virtual environment
cd %APP_DIR%
IF NOT EXIST %ENV_DIR% (
    echo Creating virtual environment...
    python -m venv %ENV_DIR%
)

call %ENV_DIR%\Scripts\activate.bat

echo Upgrading pip...
python -m pip install --upgrade pip

echo Installing Python dependencies...
pip install -r requirements.txt

:: -------------------------
:: Install Node packages
IF EXIST fad\scraper\node\package.json (
    cd fad\scraper\node
    IF EXIST node_modules (
        echo Node modules already installed.
    ) ELSE (
        echo Installing Node packages...
        npm install
    )
    cd ..\..\..
)

echo.
echo ✅ Setup complete! You can now run the app using:
echo     run_finance_app.bat
echo.

cd ..
endlocal
pause
