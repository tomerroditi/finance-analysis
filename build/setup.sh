#!/bin/bash
set -e

echo "=================================================="
echo "     Finance Analysis App - One-Time Setup"
echo "=================================================="

# Set working directory to project root (one level above build/)
cd "$(dirname "$0")/.."

ENV_DIR=".venv"
USER_DIR="$HOME/.finance-analysis"

# -------------------------
# Check Python 3.12
if command -v python3.12 &>/dev/null; then
    echo "Python 3.12 is installed."
elif command -v python3 &>/dev/null; then
    echo "Python 3 is installed ($(python3 --version))."
else
    echo "Python 3 not found."
    if command -v brew &>/dev/null; then
        echo "Installing Python 3.12 via Homebrew..."
        brew install python@3.12
    else
        echo "ERROR: Python 3.12 not found and Homebrew is not installed."
        echo "Install Homebrew first: https://brew.sh"
        echo "Then run: brew install python@3.12"
        exit 1
    fi
fi

# Determine the python command to use
if command -v python3.12 &>/dev/null; then
    PYTHON=python3.12
else
    PYTHON=python3
fi

# -------------------------
# Check Node.js (needed for scraper)
if command -v node &>/dev/null; then
    echo "Node.js is installed ($(node --version))."
else
    echo "Node.js not found."
    if command -v brew &>/dev/null; then
        echo "Installing Node.js via Homebrew..."
        brew install node
    else
        echo "ERROR: Node.js not found and Homebrew is not installed."
        echo "Install Homebrew first: https://brew.sh"
        echo "Then run: brew install node"
        exit 1
    fi
fi

# -------------------------
# Set up user data directory
mkdir -p "$USER_DIR"

# -------------------------
# Set up Python virtual environment
if [ ! -d "$ENV_DIR" ]; then
    echo "Creating virtual environment..."
    $PYTHON -m venv "$ENV_DIR"
fi

source "$ENV_DIR/bin/activate"

echo "Upgrading pip..."
python -m pip install --upgrade pip

echo "Installing Python dependencies..."
pip install poetry
poetry install --no-root --no-interaction

# -------------------------
# Install scraper Node packages
if [ -f "backend/scraper/node/package.json" ]; then
    cd backend/scraper/node
    if [ ! -d "node_modules" ]; then
        echo "Installing scraper Node packages..."
        npm install --yes --loglevel=error
    else
        echo "Scraper Node modules already installed."
    fi
    cd ../../..
fi

echo ""
echo "Setup complete. You can now run the app using: bash build/run.sh"
echo ""
