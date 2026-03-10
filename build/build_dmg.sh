#!/bin/bash
set -e

# Build a macOS .dmg from the dist/ directory
# Requires: dist/ to be populated by build_installer.py first

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$PROJECT_ROOT/dist"
DMG_NAME="FinanceAnalysis.dmg"
OUTPUT_PATH="$SCRIPT_DIR/$DMG_NAME"

if [ ! -d "$DIST_DIR" ]; then
    echo "ERROR: dist/ directory not found. Run 'python build/build_installer.py' first."
    exit 1
fi

# Remove existing DMG if present
rm -f "$OUTPUT_PATH"

echo "Creating $DMG_NAME from dist/..."
hdiutil create \
    -volname "Finance Analysis" \
    -srcfolder "$DIST_DIR" \
    -ov \
    -format UDBZ \
    "$OUTPUT_PATH"

echo "DMG created at: $OUTPUT_PATH"
