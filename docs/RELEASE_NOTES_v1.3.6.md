# Whisper Project v1.3.6

A new **Video Tiling** tab, plus the groundwork to run on **Linux** and
**macOS**. Your settings and downloaded models are kept.

## New: Video Tiling tab

Paste a live-stream URL (YouTube, X/Twitter, and the many other yt-dlp
sites), pick a grid size, and the stream fills the screen as an N×N
"video wall". Stop with the button, or Q/Esc in the video window.

- Tiling uses **ffplay**, which isn't bundled (to keep the download the
  same size). If it's missing, the tab tells you how to add it: drop
  `ffplay.exe` into the app's `bin` folder (it ships inside the full
  ffmpeg build) or install ffmpeg so ffplay is on your PATH.

## New: Linux and macOS

The app now runs from source on Linux and macOS, not just Windows:

- **Linux** — `platform/linux/install.sh` sets everything up (a venv,
  dependencies, yt-dlp, a static ffmpeg if needed, a desktop launcher),
  plus a headless `whisper-transcribe` command for servers.
- **macOS** — `platform/macos/install.command` does the same; an
  `unblock.command` clears Apple's Gatekeeper block for the unsigned app.
  (macOS is freshly prepared and still needs validation on a real Mac.)

The Windows installer/portable downloads below are unchanged in size and
behaviour — the cross-platform work happens under the hood.

## Downloads

- **Setup-Standard** (`...-Setup-Standard.exe`) — installs to Program Files.
- **Portable** (`...-Portable.zip`) — extract and run **Run Whisper
  Project.bat**.

Full detail: `docs/CHANGELOG.md`. Cross-platform plan + status:
`docs/CROSS_PLATFORM_ROADMAP.md`.
