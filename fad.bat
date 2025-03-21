@echo off
echo Checking if Docker is installed...

:: Check if Docker is installed
docker --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Docker is not installed. Installing Docker now...

    :: Download Docker installer
    powershell -Command "& {Invoke-WebRequest -Uri 'https://desktop.docker.com/win/main/amd64/Docker Desktop Installer.exe' -OutFile 'DockerInstaller.exe'}"

    echo Installing Docker...
    start /wait DockerInstaller.exe install

    echo Docker installed successfully. Restart your computer and run this script again.
    exit /b
)

:: Check if Docker Daemon is running
docker info >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Docker is not running. Starting Docker Desktop...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"

    echo Waiting for Docker to start...

    :CHECK_DOCKER
    docker info >nul 2>&1
    IF %ERRORLEVEL% NEQ 0 (
        timeout /t 5 >nul
        goto CHECK_DOCKER
    )
    echo Docker is now running!
)

:: Define user directory for persistent storage
set APP_DIR=%USERPROFILE%\.finance_analysis
if not exist %APP_DIR% mkdir %APP_DIR%

echo "Pulling the latest version of the Finance Analysis app..."
docker pull ghcr.io/tomerroditi/finance-analysis:latest

:: Run the Docker container
start /B docker run -p 8501:8501 ^
    -v %APP_DIR%:/app/finance_analysis/fad/resources ^
    --name finance_analysis ^
    --rm ghcr.io/tomerroditi/finance-analysis:latest

:: Wait for a few seconds to allow Streamlit to start
timeout /t 1 /nobreak >nul

:: Open Streamlit in the default web browser
start http://localhost:8501/
