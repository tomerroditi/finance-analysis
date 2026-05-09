#!/bin/bash
# Wrap the PyInstaller-produced "Finance Analysis.app" in a DMG.
#
# This script no longer assembles the .app from a launcher script.
# PyInstaller's BUNDLE step (in finance_analysis.spec) does that and
# produces a self-contained .app at dist/Finance Analysis.app.
#
# Our remaining responsibilities:
#   1. Inject build/macos/uninstall.command as a Resource so users have a
#      standalone uninstaller alongside Settings → Uninstall.
#   2. Inject build/macos/fix-gatekeeper.command into the DMG root so
#      users can clear the macOS quarantine xattr after dragging.
#   3. Generate icon.icns from the project's 512px PNG (only if the spec
#      didn't already supply one — keeps a single source of truth for
#      the icon at frontend/public/icons/icon-512.png).
#   4. hdiutil-wrap into FinanceAnalysis.dmg with the drag-to-Applications
#      symlink.
#
# Single arm64 build only — see release.yml for why we don't ship x86_64.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$PROJECT_ROOT/dist"
APP_NAME="Finance Analysis"
APP_BUNDLE="$DIST_DIR/$APP_NAME.app"
ICON_PNG="$PROJECT_ROOT/frontend/public/icons/icon-512.png"
UNINSTALL_SRC="$SCRIPT_DIR/macos/uninstall.command"

DMG_NAME="FinanceAnalysis.dmg"
DMG_PATH="$SCRIPT_DIR/$DMG_NAME"

if [ ! -d "$APP_BUNDLE" ]; then
    echo "ERROR: $APP_BUNDLE not found. Run 'python build/build_app.py' first."
    exit 1
fi
if [ ! -f "$UNINSTALL_SRC" ]; then
    echo "ERROR: uninstall.command not found at $UNINSTALL_SRC"
    exit 1
fi

# 1. Inject the standalone uninstaller into the bundle's Resources.
#    The launcher used to copy it to ~/.finance-analysis/ on first run,
#    but that launcher is gone now. The uninstaller is reachable from
#    inside the .app's Resources folder (via Right-Click → Show Package
#    Contents) and from the in-app Settings → Uninstall button. The
#    user-facing instructions (in installation_and_updates.md) cover both.
RESOURCES="$APP_BUNDLE/Contents/Resources"
mkdir -p "$RESOURCES"
cp "$UNINSTALL_SRC" "$RESOURCES/uninstall.command"
chmod +x "$RESOURCES/uninstall.command"

# 2. Icon: PyInstaller's BUNDLE accepts an .icns path; if we provided
#    one (build/icon.icns) the bundle already has Resources/icon.icns.
#    Otherwise, generate one from the 512 PNG. Most local dev runs
#    will already have an .icns; CI will fall through to the generator.
if [ ! -f "$RESOURCES/icon.icns" ]; then
    if [ ! -f "$ICON_PNG" ]; then
        echo "ERROR: icon source not found at $ICON_PNG"
        exit 1
    fi
    echo "Generating .icns icon from $ICON_PNG..."
    ICONSET_PARENT=$(mktemp -d)
    ICONSET="$ICONSET_PARENT/icon.iconset"
    mkdir -p "$ICONSET"
    for SIZE in 16 32 64 128 256 512; do
        sips -z "$SIZE" "$SIZE" "$ICON_PNG" --out "$ICONSET/icon_${SIZE}x${SIZE}.png" >/dev/null
    done
    for SIZE in 16 32 128 256 512; do
        DOUBLE=$((SIZE * 2))
        sips -z "$DOUBLE" "$DOUBLE" "$ICON_PNG" --out "$ICONSET/icon_${SIZE}x${SIZE}@2x.png" >/dev/null
    done
    iconutil -c icns "$ICONSET" -o "$RESOURCES/icon.icns"
    rm -rf "$ICONSET_PARENT"
fi

# 3. Build the DMG.
echo "Building $DMG_NAME..."
rm -f "$DMG_PATH"

# Defensive cleanup: detach any stale "Finance Analysis" volumes
# from previous builds before calling hdiutil create. Without this,
# ``hdiutil create`` fails with "Resource busy" when an earlier run
# (in CI on a warm runner, or in local-dev iteration) left a
# /Volumes/Finance\ Analysis mount behind. Iterates over every
# disk image whose mount-point matches our volume name, ignoring
# missing mounts (set -e is already on, hence ``|| true``).
for vol in "/Volumes/$APP_NAME" "/Volumes/$APP_NAME "*; do
    if [ -d "$vol" ]; then
        hdiutil detach -force "$vol" >/dev/null 2>&1 || true
    fi
done

STAGING=$(mktemp -d)
cp -R "$APP_BUNDLE" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$STAGING" \
    -ov \
    -format UDZO \
    "$DMG_PATH"
# UDZO (zlib) is Apple's default DMG format and what almost every
# modern macOS distribution uses. We previously used UDBZ (bzip2),
# which yields ~5% smaller files at significant cost: it's slower
# to mount on the user's Mac and triggers extra inspection passes
# in Chrome's macOS download path that visibly throttle downloads
# past ~70 MB. UDZO sidesteps all of that.

rm -rf "$STAGING"

echo "DMG created at: $DMG_PATH"
