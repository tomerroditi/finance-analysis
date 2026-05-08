#!/bin/bash
# Standalone Finance Analysis uninstaller for macOS.
#
# Lives in two places after install:
#   - Inside the .app bundle at Contents/Resources/uninstall.command
#   - Copied by the launcher to ~/.finance-analysis/uninstall.command,
#     so the uninstaller still works if the bundle was later deleted.
#
# The user may double-click this file from Finder. Terminal opens, the
# script asks whether to also delete the user-data dir + Keychain
# entries, runs ``python -m backend.uninstall``, and removes the .app
# bundle from /Applications.
set -u

APP_NAME="Finance Analysis"
USER_DIR="$HOME/.finance-analysis"
USER_APP="$USER_DIR/app"
APP_BUNDLE="/Applications/${APP_NAME}.app"

echo "=================================================="
echo "     ${APP_NAME} — Uninstaller"
echo "=================================================="
echo

if [ ! -d "$APP_BUNDLE" ] && [ ! -d "$USER_APP" ] && [ ! -d "$USER_DIR" ]; then
    echo "${APP_NAME} doesn't appear to be installed on this Mac. Nothing to do."
    echo "Press any key to close this window."
    read -n 1 -s
    exit 0
fi

read -p "Also delete your data and saved passwords (transactions DB, credentials, Keychain)? [y/N] " WIPE
WIPE_FLAG="--keep-data"
WIPE_DATA="0"
if [[ "${WIPE:-}" =~ ^[Yy]$ ]]; then
    WIPE_FLAG="--wipe"
    WIPE_DATA="1"
fi

# Stop any running uvicorn from this app — best-effort, fine if it's not running.
pkill -f "uvicorn backend.main:app" 2>/dev/null || true

# Run the cleanup CLI from the synced venv when available, else fall
# back to system Python. Either way, the cleanup module knows about
# the keyring service names + the user-data dir layout.
if [ -x "$USER_APP/.venv/bin/python" ]; then
    "$USER_APP/.venv/bin/python" -m backend.uninstall "$WIPE_FLAG" || true
elif [ -x /usr/bin/python3 ]; then
    if [ -d "$USER_APP" ]; then
        ( cd "$USER_APP" && /usr/bin/python3 -m pip install --user --quiet keyring tomli >/dev/null 2>&1 || true )
        ( cd "$USER_APP" && /usr/bin/python3 -m backend.uninstall "$WIPE_FLAG" || true )
    fi
fi

# Remove the synced runtime copy.
if [ -d "$USER_APP" ]; then
    rm -rf "$USER_APP"
    echo "Removed ${USER_APP}"
fi

# Remove the .app bundle.
if [ -d "$APP_BUNDLE" ]; then
    rm -rf "$APP_BUNDLE"
    echo "Removed ${APP_BUNDLE}"
fi

# When wiping, sweep the rest of the user-data dir as a backstop —
# the cleanup module already attempted this, but if it failed for any
# reason (e.g. the DB was open) doing it after we've stopped uvicorn
# succeeds.
if [ "${WIPE_DATA}" = "1" ] && [ -d "$USER_DIR" ]; then
    rm -rf "$USER_DIR"
    echo "Removed ${USER_DIR}"
fi

echo
echo "${APP_NAME} has been uninstalled."
echo "You can close this Terminal window."
