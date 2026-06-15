#!/bin/bash
# Script to create a macOS DMG (Disk Image) installer for SmartiAI
set -e

echo "Creating DMG installer for SmartiAI..."

# Ensure we are in the repository root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

APP_PATH="dist/SmartiAI.app"
DMG_TEMP="dist/dmg_temp"
DMG_NAME="release/SmartiAI-Installer.dmg"

if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: SmartiAI.app not found. Please run the build script first."
    exit 1
fi

# Clean old temporary and release files
rm -rf "$DMG_TEMP"
rm -f "$DMG_NAME"
mkdir -p "$DMG_TEMP"
mkdir -p "release"

# Copy App to temp folder
echo "Copying SmartiAI.app to installer workspace..."
cp -R "$APP_PATH" "$DMG_TEMP/"

# Create symlink to /Applications folder
echo "Creating Applications folder symlink..."
ln -s /Applications "$DMG_TEMP/Applications"

# Create the DMG file using native hdiutil
echo "Generating macOS Disk Image (DMG)..."
hdiutil create -volname "SmartiAI" -srcfolder "$DMG_TEMP" -ov -format UDZO "$DMG_NAME"

# Clean up temporary folder
rm -rf "$DMG_TEMP"

echo "DMG Installer created successfully at: $DMG_NAME"
