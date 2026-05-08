#!/bin/bash
# Build a "Finance Analysis.app" bundle and wrap it in a drag-to-Applications DMG.
# Requires: dist/ to be populated by build_installer.py first.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$PROJECT_ROOT/dist"
ICON_PNG="$PROJECT_ROOT/frontend/public/icons/icon-512.png"
LAUNCHER_SRC="$SCRIPT_DIR/macos/launcher.sh"

APP_NAME="Finance Analysis"
APP_BUNDLE="$SCRIPT_DIR/$APP_NAME.app"
DMG_NAME="FinanceAnalysis.dmg"
DMG_PATH="$SCRIPT_DIR/$DMG_NAME"

if [ ! -d "$DIST_DIR" ]; then
    echo "ERROR: dist/ directory not found. Run 'python build/build_installer.py' first."
    exit 1
fi
if [ ! -f "$ICON_PNG" ]; then
    echo "ERROR: icon source not found at $ICON_PNG"
    exit 1
fi
if [ ! -f "$LAUNCHER_SRC" ]; then
    echo "ERROR: launcher script not found at $LAUNCHER_SRC"
    exit 1
fi

VERSION=$(awk -F'"' '/^version[[:space:]]*=/ { print $2; exit }' "$PROJECT_ROOT/pyproject.toml")
if [ -z "$VERSION" ]; then
    echo "ERROR: could not parse version from pyproject.toml"
    exit 1
fi

rm -rf "$APP_BUNDLE"
rm -f "$DMG_PATH"

echo "Building $APP_NAME.app (version $VERSION)..."
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

cp "$LAUNCHER_SRC" "$APP_BUNDLE/Contents/MacOS/FinanceAnalysis"
chmod +x "$APP_BUNDLE/Contents/MacOS/FinanceAnalysis"

ditto "$DIST_DIR" "$APP_BUNDLE/Contents/Resources/app"

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
iconutil -c icns "$ICONSET" -o "$APP_BUNDLE/Contents/Resources/icon.icns"
rm -rf "$ICONSET_PARENT"

echo "Writing Info.plist..."
cat > "$APP_BUNDLE/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundleDisplayName</key>
    <string>$APP_NAME</string>
    <key>CFBundleIdentifier</key>
    <string>com.tomerroditi.finance-analysis</string>
    <key>CFBundleVersion</key>
    <string>$VERSION</string>
    <key>CFBundleShortVersionString</key>
    <string>$VERSION</string>
    <key>CFBundleExecutable</key>
    <string>FinanceAnalysis</string>
    <key>CFBundleIconFile</key>
    <string>icon.icns</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
</dict>
</plist>
PLIST

echo "Building $DMG_NAME..."
STAGING=$(mktemp -d)
cp -R "$APP_BUNDLE" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$STAGING" \
    -ov \
    -format UDBZ \
    "$DMG_PATH"

rm -rf "$STAGING"

echo "DMG created at: $DMG_PATH"
