#!/bin/bash
# SmartiAI release build script for macOS
set -e

VERSION="${1:-0.69.0}"
echo "Building SmartiAI Release version $VERSION for macOS..."

# Ensure we are in the repository root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# Clean previous build files
echo "Cleaning old build files..."
rm -rf build dist release
mkdir -p release

# Package the app using PyInstaller
echo "Running PyInstaller..."
./.venv/bin/pyinstaller --noconfirm SmartiAI.spec

# Create the release package (portable ZIP)
if [ -d "dist/SmartiAI.app" ]; then
    echo "Signing SmartiAI.app deeply..."
    codesign --force --deep --sign - dist/SmartiAI.app
    echo "Creating ZIP release package..."
    cd dist
    zip -r ../release/SmartiAI-Agent-for-macOS-$VERSION-portable.zip SmartiAI.app
    cd ..
    echo "Release packaged successfully: release/SmartiAI-Agent-for-macOS-$VERSION-portable.zip"
else
    echo "ERROR: SmartiAI.app was not created by PyInstaller."
    exit 1
fi

echo "Build process completed successfully!"
