# Whisper Project v1.3.2

Security + features release on top of v1.3.1. Install the
**Setup-Standard** EXE below; your settings and downloaded models are kept.

## New

- **Transcribe just part of a file.** The Transcribe tab has Start / End
  time fields — transcribe, say, 5 minutes from a specific point of a
  long recording instead of the whole thing. Leave both at 0:00:00 for
  the full file.

## Fixed

- **Failed downloads now tell you why.** Instead of a bare exit code, the
  queue shows yt-dlp's actual error. If a site needs login (Facebook,
  Instagram), it suggests turning on "Cookies from browser" in Advanced
  settings.
- **The progress number stays visible** while a transcription is starting
  up (the animated bar no longer hides it).
- **Slightly broken media files** that don't report a duration are now
  transcribed anyway instead of erroring out.

## Security

- Closed a hole where a specially-crafted "link" pasted into the Download
  box could make the downloader run an unintended command. Pasted links
  are now always treated as links, never options.
- Hardened model-archive extraction against malicious archive paths.

## Downloads

- **Setup-Standard** (`...-Setup-Standard.exe`) — installs to Program Files,
  upgrades the previous version cleanly (single Add/Remove entry).
- **Portable** (`...-Portable.zip`) — no install: extract the ZIP anywhere
  and double-click **Run Whisper Project.bat**. It's the full Python
  environment, so you can update later by dropping in newer `app\` /
  `core\` / `gui.py` files without recompiling.

## Notes

- Full technical detail: `docs/CHANGELOG.md`.
