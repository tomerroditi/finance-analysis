#!/bin/bash
# Entry point for the Finance Analysis.app bundle on macOS.
# Syncs the bundled app source to ~/.finance-analysis/app, then runs setup + uvicorn
# in a Terminal window so the user can see logs.
set -e

LAUNCHER="${BASH_SOURCE[0]}"
MACOS_DIR="$(cd "$(dirname "$LAUNCHER")" && pwd)"
APP_BUNDLE="$(cd "$MACOS_DIR/../.." && pwd)"
APP_SRC="$APP_BUNDLE/Contents/Resources/app"
USER_DIR="$HOME/.finance-analysis"
USER_APP="$USER_DIR/app"

mkdir -p "$USER_APP"

/usr/bin/rsync -a --delete \
    --exclude='.venv' \
    --exclude='node_modules' \
    "$APP_SRC/" "$USER_APP/"

SETUP="$USER_APP/build/setup.sh"
RUN="$USER_APP/build/run.sh"
CMD="bash '$SETUP' && bash '$RUN'"

osascript <<APPLESCRIPT
tell application "Terminal"
    activate
    do script "$CMD"
end tell
APPLESCRIPT
