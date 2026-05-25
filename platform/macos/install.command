#!/usr/bin/env bash
# Whisper Project — macOS installer (double-clickable .command).
#
# Same idea as the Linux installer: a self-contained virtualenv next to the
# repo, deps + yt-dlp, a static ffmpeg when the system has none, and two
# launchers (a double-clickable "Whisper Project.command" for the GUI and a
# "whisper-transcribe" CLI for headless use).
#
# Gatekeeper: this app is UNSIGNED (no paid Apple Developer cert). The
# cleanest way to avoid Gatekeeper entirely is to get the repo via
# `git clone` or `curl` and run this from Terminal — files fetched that way
# are NOT quarantined. As a belt-and-braces step this script also strips the
# quarantine flag from the repo folder. See README.md for the full story.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
if [ ! -f "$REPO_ROOT/gui.py" ]; then
  echo "error: gui.py not found at $REPO_ROOT — run this from inside the repo checkout." >&2
  exit 1
fi
VENV="$REPO_ROOT/.venv"
APPS_DIR="$HOME/Applications"
BIN_LOCAL="$HOME/.local/bin"

say() { printf '\033[1;36m[whisper]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[whisper] WARN:\033[0m %s\n' "$*" >&2; }

# ---- de-quarantine the repo so Gatekeeper doesn't block our own scripts.
xattr -dr com.apple.quarantine "$REPO_ROOT" 2>/dev/null || true

# ---- python (need Tk for the GUI; headless CLI works without it) --------
PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "error: python3 not found. Install Python 3.11+ from https://www.python.org/downloads/macos/ (its installer includes Tk)." >&2
  exit 1
fi
PYVER="$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
say "using Python $PYVER"
if ! "$PY" -c 'import tkinter' >/dev/null 2>&1; then
  warn "tkinter missing — the GUI won't start. Use the python.org build (bundles Tk),"
  warn "or with Homebrew: brew install python-tk. The headless CLI works without it."
fi

# ---- venv + deps --------------------------------------------------------
say "creating virtualenv at $VENV"
"$PY" -m venv "$VENV"
# shellcheck disable=SC1091
. "$VENV/bin/activate"
python -m pip install --upgrade pip wheel >/dev/null
say "installing dependencies (a few minutes)…"
python -m pip install -r "$REPO_ROOT/requirements.txt"
python -m pip install --upgrade yt-dlp

# ---- ffmpeg -------------------------------------------------------------
mkdir -p "$REPO_ROOT/bin"
if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
  say "system ffmpeg/ffprobe found: $(command -v ffmpeg)"
elif command -v brew >/dev/null 2>&1; then
  say "installing ffmpeg via Homebrew…"
  brew install ffmpeg || warn "brew install ffmpeg failed — install it manually."
else
  say "no ffmpeg + no Homebrew — fetching a static build into bin/…"
  TMP="$(mktemp -d)"
  ok=1
  curl -fsSL "https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip" -o "$TMP/ffmpeg.zip" || ok=0
  curl -fsSL "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip" -o "$TMP/ffprobe.zip" || ok=0
  if [ "$ok" = 1 ]; then
    (cd "$TMP" && unzip -oq ffmpeg.zip && unzip -oq ffprobe.zip)
    cp "$TMP/ffmpeg" "$TMP/ffprobe" "$REPO_ROOT/bin/" 2>/dev/null || ok=0
    chmod +x "$REPO_ROOT/bin/ffmpeg" "$REPO_ROOT/bin/ffprobe" 2>/dev/null || true
    xattr -dr com.apple.quarantine "$REPO_ROOT/bin" 2>/dev/null || true
  fi
  [ "$ok" = 1 ] && say "installed static ffmpeg + ffprobe into bin/" || \
    warn "static ffmpeg fetch failed — install Homebrew then 'brew install ffmpeg'."
fi
deactivate

# ---- launchers ----------------------------------------------------------
mkdir -p "$APPS_DIR" "$BIN_LOCAL"
LAUNCHER="$APPS_DIR/Whisper Project.command"
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
export PATH="$REPO_ROOT/bin:$VENV/bin:\$PATH"
exec "$VENV/bin/python" "$REPO_ROOT/gui.py" "\$@"
EOF
chmod +x "$LAUNCHER"
cat > "$BIN_LOCAL/whisper-transcribe" <<EOF
#!/usr/bin/env bash
export PATH="$REPO_ROOT/bin:$VENV/bin:\$PATH"
exec "$VENV/bin/python" "$REPO_ROOT/gui.py" transcribe "\$@"
EOF
chmod +x "$BIN_LOCAL/whisper-transcribe"
# Our freshly-written launchers were created locally, so they carry no
# quarantine flag and open without a Gatekeeper prompt.
say "installed launcher: $LAUNCHER"
say "installed CLI:      $BIN_LOCAL/whisper-transcribe"

echo
say "Done."
say "Desktop app : double-click \"Whisper Project.command\" in ~/Applications"
say "              (or: open \"$LAUNCHER\")"
say "Server / CLI: whisper-transcribe /path/to/media.mp4 --formats srt json"
say "If macOS still blocks a launcher, see platform/macos/README.md or run:"
say "    bash platform/macos/unblock.command"
