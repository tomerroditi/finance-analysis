#!/bin/bash
# Fix the macOS Gatekeeper "damaged and can't be opened" error.
#
# The error is misleading: the app isn't damaged. macOS adds a
# ``com.apple.quarantine`` extended attribute to anything downloaded
# via a browser, and refuses to launch unsigned + unnotarized apps
# carrying that attribute. Stripping the xattr lets the app launch.
#
# Once code-signing + notarization are in place this script can be
# deleted — Gatekeeper will trust the signature directly.
set -u

APP_NAME="Finance Analysis"
APP_BUNDLE="/Applications/${APP_NAME}.app"

echo "=================================================="
echo "     ${APP_NAME} — Fix macOS Gatekeeper"
echo "=================================================="
echo

if [ ! -d "$APP_BUNDLE" ]; then
    echo "ERROR: ${APP_BUNDLE} not found."
    echo "Drag ${APP_NAME}.app into /Applications first, then run this script."
    echo
    echo "Press any key to close this window."
    read -n 1 -s
    exit 1
fi

echo "Removing quarantine attribute from ${APP_BUNDLE}..."
xattr -cr "$APP_BUNDLE"

echo
echo "Done. ${APP_NAME} should launch normally now."
echo "You can close this Terminal window."
