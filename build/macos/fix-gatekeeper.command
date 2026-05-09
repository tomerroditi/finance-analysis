#!/bin/bash
# Fix the macOS Gatekeeper "damaged and can't be opened" error AND
# launch the app in one step.
#
# Why both in one script:
#   macOS attaches a ``com.apple.quarantine`` xattr to anything
#   downloaded by a browser, and refuses to launch unsigned /
#   ad-hoc-signed apps carrying that attribute (you see "Finance
#   Analysis is damaged and can't be opened").
#
#   The natural workaround — "double-click the app, see the error,
#   then run this script, then double-click again" — DOES NOT WORK on
#   macOS Sequoia / Tahoe. The first failed double-click triggers
#   App Translocation and caches the denial; subsequent ``open`` calls
#   silently no-op even after the quarantine xattr is gone, until the
#   user logs out or reboots.
#
#   So this script does both: strip the quarantine, then launch the
#   app immediately via ``open``. The user runs this ONCE — they
#   don't need to double-click the app first or after.
#
# Once code-signing + notarization are in place this script can be
# deleted — Gatekeeper will trust the signature directly.
set -u

APP_NAME="Finance Analysis"
APP_BUNDLE="/Applications/${APP_NAME}.app"

echo "=================================================="
echo "  ${APP_NAME} — Setup & Launch"
echo "=================================================="
echo

if [ ! -d "$APP_BUNDLE" ]; then
    echo "ERROR: ${APP_BUNDLE} not found."
    echo
    echo "Please drag ${APP_NAME}.app from this DMG into your"
    echo "/Applications folder first, then run this script again."
    echo
    echo "Press any key to close this window."
    read -n 1 -s
    exit 1
fi

echo "Removing macOS quarantine flag..."
xattr -cr "$APP_BUNDLE"

echo "Launching ${APP_NAME}..."
open "$APP_BUNDLE"

echo
echo "Done. ${APP_NAME} should open in your browser within a few seconds."
echo "You can close this Terminal window."
