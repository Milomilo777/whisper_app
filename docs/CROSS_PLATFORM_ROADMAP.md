# Cross-platform + new-features roadmap

Goal: keep the Windows app as-is, and additionally make it run well on
**Linux** (one-line install) and **macOS** (easy install despite Gatekeeper
blocking unsigned apps), plus add a **Video Tiling** tab. The shipped
Windows build embeds Python (v1.3.5), which the maintainer prefers because
updates are just file swaps — the Linux/Mac stories follow the same
"bring/own a Python, install deps, fetch ffmpeg+yt-dlp, run from source"
shape so updates stay easy everywhere.

This doc is the source of truth for the effort. Status legend:
`[ ]` todo · `[~]` in progress · `[x]` done · `[!]` needs real-device test.

## Honest testability note

Development happens on Windows. Therefore:
- **Windows**: fully testable (pyright + hermetic suite + real-worker E2E).
- **Linux**: the Python is verifiable on Windows (pyright/tests), and the
  install script is shell-lint/structure-checkable, but a real end-to-end
  run needs a Linux box. The maintainer confirmed transcription already
  works on a Linux web server, so the core is sound.
- **macOS**: cannot be built or run here at all. Everything for Mac is
  research-backed groundwork + scripts + docs, marked `[!]` until someone
  validates on a real Mac.

"Green" for this effort = Windows stays 0-regression (gate green), the
cross-platform code paths are correct by construction + reviewed, and the
Linux/Mac install assets are complete and documented.

## Phase 1 — Cross-platform core hardening  (foundation)

Make the core run unchanged on Linux/Mac. Audit found: 12 `CREATE_NO_WINDOW`
uses, 6 `winreg` (VLC), ~50 `.exe` references, 23 existing `os.name` guards.

- [ ] Central binary resolver: `ffmpeg`/`ffprobe`/`yt-dlp` resolve to the
  platform name (`.exe` only on Windows; bare name + `bin/` + PATH elsewhere).
- [ ] Guard every `creationflags=CREATE_NO_WINDOW` behind `os.name == "nt"`
  (a no-op flag of 0 on POSIX) — confirm none are unguarded.
- [ ] VLC discovery: keep `winreg` on Windows, add POSIX fallbacks
  (`/Applications/VLC.app` on Mac, `which vlc` / common dirs on Linux).
- [ ] Verify on Windows: pyright 0/0/0 + hermetic suite stay green.

## Phase 2 — Video Tiling tab

Source: `github.com/translation-robot/video-tiler` (yt-dlp piped into
`ffplay`, N tiles positioned in a grid). Notes: needs **ffplay** (not in
`bin/` today — only ffmpeg/ffprobe), and window-positioning is win32 on
Windows. Plan:
- [ ] New `app/widgets/tabs.py` tab + a `core/tiling.py` controller.
- [ ] Resolve `ffplay` via the Phase-1 resolver; if missing, show a clear
  "Video Tiling needs ffplay — install it / enable it" message instead of
  crashing (keeps the base download small; ffplay is opt-in).
- [ ] Windows: grid via window geometry. Linux/Mac: launch tiled ffplay
  windows with `-x/-y/-left/-top` where supported; degrade gracefully.
- [ ] Do NOT copy the reference script's hard-coded author email.

## Phase 3 — Linux one-line install

- [ ] `platform/linux/install.sh`: create a venv, `pip install` deps,
  fetch a static `ffmpeg`/`ffprobe` + `yt-dlp`, write a `.desktop` entry
  and a `whisper-project` launcher. Idempotent; re-runnable for updates.
- [ ] One-liner: `curl -fsSL <raw>/platform/linux/install.sh | bash`.
- [ ] `platform/linux/README.md` documenting it.

## Phase 4 — macOS groundwork + Gatekeeper  [!]

- [ ] `platform/macos/install.command`: venv + deps + ffmpeg/yt-dlp, like Linux.
- [ ] Gatekeeper: ship instructions + a helper that runs
  `xattr -dr com.apple.quarantine <app>` (the standard unsigned-app unblock),
  and document the right-click→Open and System-Settings→"Open Anyway" flows.
- [ ] Research + cite how comparable unsigned OSS apps (e.g. yt-dlp GUIs,
  MacWhisper-likes, Python Tk apps) ship without a paid Apple cert.
- [ ] `platform/macos/README.md`. All marked `[!]` (no Mac to verify).

## Phase 5 — Validate, commit, release

- [ ] pyright 0/0/0 + hermetic suite green after every batch.
- [ ] Batch commits by phase; push to master.
- [ ] If the Windows deliverable changed (new tab), cut a release.
