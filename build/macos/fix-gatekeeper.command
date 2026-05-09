#!/bin/bash
# Fix Gatekeeper "is damaged" error after downloading Finance Analysis from GitHub.
#
# macOS attaches a com.apple.quarantine extended attribute to files
# downloaded from the internet. For unsigned apps, Gatekeeper treats
# this as "damaged" and refuses to open them. This script removes the
# quarantine attribute so the app can launch normally.
#
# Usage:
#   1. Drag "Finance Analysis.app" from this DMG to /Applications.
#   2. Double-click this file — Terminal opens and runs the fix.
#   3. Re-launch Finance Analysis from Launchpad or /Applications.
set -euo pipefail

APP="/Applications/Finance Analysis.app"

echo "=================================================="
echo "  Finance Analysis — Fix Gatekeeper"
echo "=================================================="
echo

if [ ! -d "$APP" ]; then
    echo "ERROR: Finance Analysis.app not found in /Applications."
    echo
    echo "Please drag Finance Analysis.app from this DMG to your"
    echo "/Applications folder first, then run this script again."
    echo
    echo "Press any key to close this window."
    read -n 1 -s
    exit 1
fi

echo "Removing macOS quarantine flag from Finance Analysis.app..."
xattr -cr "$APP"
echo "Done."
echo
echo "You can now launch Finance Analysis from Launchpad or /Applications."
echo "Press any key to close this window."
read -n 1 -s
