set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../../.." && pwd)"

if ! command -v create-dmg >/dev/null 2>&1; then
  echo "error: create-dmg not found. Install it: brew install create-dmg" >&2
  exit 1
fi

rm -rf dist

pyinstaller --noconfirm --clean platform/macos/pyinstaller/whisper_project_mac.spec

rm -rf dist/dmg/
mkdir dist/dmg
cp -R "dist/Whisper Project.app" dist/dmg/

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
