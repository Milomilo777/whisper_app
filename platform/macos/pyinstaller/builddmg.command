#!/usr/bin/env bash
# Package the PyInstaller-built "Whisper Project.app" into a drag-to-
# Applications .dmg, using create-dmg (`brew install create-dmg`). Mirrors
# the maintainer's machine-translate-docx/compile/mac/builddmg-gui.sh.
# Run on a Mac, AFTER building the .app from whisper_project_mac.spec.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../../.." && pwd)"

APP="dist/Whisper Project.app"
if [ ! -d "$APP" ]; then
  echo "error: $APP not found. Build it first:" >&2
  echo "  pyinstaller --noconfirm --clean platform/macos/pyinstaller/whisper_project_mac.spec" >&2
  exit 1
fi
if ! command -v create-dmg >/dev/null 2>&1; then
  echo "error: create-dmg not found. Install it: brew install create-dmg" >&2
  exit 1
fi

mkdir -p dist/dmg
rm -rf dist/dmg/*
cp -R "$APP" dist/dmg/
rm -f "dist/Whisper Project.dmg"

create-dmg \
  --volname "Whisper Project" \
  --window-pos 200 120 \
  --window-size 600 320 \
  --icon-size 100 \
  --icon "Whisper Project.app" 170 130 \
  --hide-extension "Whisper Project.app" \
  --app-drop-link 430 130 \
  "dist/Whisper Project.dmg" \
  "dist/dmg/"

echo "Built: dist/Whisper Project.dmg"
