#!/bin/bash
echo "Checking if Docker is installed..."

if ! command -v docker &> /dev/null
then
    echo "Docker is not installed. Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    newgrp docker
fi

echo "Pulling the latest version of the Finance Analysis app..."
docker pull ghcr.io/tomerroditi/finance-analysis:latest

:: Define user directory for persistent storage
set APP_DIR=$HOME/.finance_analysis
if not exist %APP_DIR% mkdir %APP_DIR%

echo "Running the Finance Analysis app..."
docker run -p 8501:8501 \
    -v "$HOME/.finance_analysis:/app/finance_analysis/fad/resources" \
    --name finance_local \
    --rm ghcr.io/tomerroditi/finance-analysis:latest


:: Wait for a few seconds to allow Streamlit to start
timeout /t 5 /nobreak >nul

:: Open Streamlit in the default web browser
start http://localhost:8501/
