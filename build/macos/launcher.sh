#!/bin/bash
# Entry point for the Finance Analysis.app bundle on macOS.
#
# What this does:
#   1. Reads CFBundleVersion from the bundle's Info.plist.
#   2. Compares against ~/.finance-analysis/app/.installed_version.
#   3. If they match AND .venv + frontend/dist look intact, skips the
#      rsync + setup.sh step and goes straight to run.sh — making
#      every launch after the first one of a build essentially instant.
#   4. Otherwise, rsyncs the bundle into ~/.finance-analysis/app, runs
#      setup.sh, and writes the version marker only after setup
#      succeeds (so a failed setup doesn't get cached as "done").
#   5. Always copies uninstall.command into ~/.finance-analysis/ so a
#      user can uninstall even after the .app is moved or removed.
set -e

LAUNCHER="${BASH_SOURCE[0]}"
MACOS_DIR="$(cd "$(dirname "$LAUNCHER")" && pwd)"
APP_BUNDLE="$(cd "$MACOS_DIR/../.." && pwd)"
APP_SRC="$APP_BUNDLE/Contents/Resources/app"
USER_DIR="$HOME/.finance-analysis"
USER_APP="$USER_DIR/app"
VERSION_MARKER="$USER_APP/.installed_version"

mkdir -p "$USER_DIR"

BUNDLE_VERSION=$(/usr/bin/defaults read "$APP_BUNDLE/Contents/Info" CFBundleVersion 2>/dev/null || echo "unknown")

INSTALLED_VERSION=""
if [ -f "$VERSION_MARKER" ]; then
    INSTALLED_VERSION=$(cat "$VERSION_MARKER" 2>/dev/null || echo "")
fi

NEEDS_SETUP="0"
if [ "$BUNDLE_VERSION" != "$INSTALLED_VERSION" ]; then
    NEEDS_SETUP="1"
elif [ ! -d "$USER_APP/.venv" ]; then
    NEEDS_SETUP="1"
elif [ ! -d "$USER_APP/frontend/dist" ]; then
    NEEDS_SETUP="1"
fi

# Always refresh the standalone uninstaller in $USER_DIR so the user
# has a working uninstaller even if the bundle is later deleted.
if [ -f "$APP_SRC/build/macos/uninstall.command" ]; then
    cp "$APP_SRC/build/macos/uninstall.command" "$USER_DIR/uninstall.command"
    chmod +x "$USER_DIR/uninstall.command"
fi

if [ "$NEEDS_SETUP" = "1" ]; then
    mkdir -p "$USER_APP"
    /usr/bin/rsync -a --delete \
        --exclude='.venv' \
        --exclude='node_modules' \
        --exclude='.installed_version' \
        "$APP_SRC/" "$USER_APP/"

    SETUP="$USER_APP/build/setup.sh"
    RUN="$USER_APP/build/run.sh"
    # The marker is written ONLY after setup.sh exits 0; otherwise
    # the next launch tries the setup again instead of skipping.
    CMD="bash '$SETUP' && echo '$BUNDLE_VERSION' > '$VERSION_MARKER' && bash '$RUN'"
else
    RUN="$USER_APP/build/run.sh"
    CMD="bash '$RUN'"
fi

osascript <<APPLESCRIPT
tell application "Terminal"
    activate
    do script "$CMD"
end tell
APPLESCRIPT
