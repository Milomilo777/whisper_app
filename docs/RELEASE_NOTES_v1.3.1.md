# Whisper Project v1.3.1

Reliability release on top of v1.3.0. Install the **Setup-Standard** EXE
attached below; your settings and downloaded models are kept.

## Fixed

- **Downloads with a special character in the title now transcribe.**
  When a video's title had an apostrophe, accent, emoji, or non-Latin
  text, "Transcribe after download" silently produced nothing (the app
  was looking for the file under a garbled name). Now it decodes the name
  correctly **and**, as a safety net, finds the real downloaded file even
  if the name is unusual — so the transcript always appears.
- **Choosing a non-English language no longer fails.** Picking Chinese,
  Portuguese, Hebrew, Indonesian, etc. (or a download whose language came
  through as "en-US") used to crash the transcription with no output. The
  language is now understood correctly.
- **The video + subtitle viewer finds your installed VLC.** It said "VLC
  isn't installed" even when it was. Note: the app is 64-bit, so it needs
  the **64-bit VLC** — the message now says so if a 32-bit VLC is found.
- **Cancelling and re-running downloads behave correctly.** Cancelling a
  download that had started transcribing now actually stops it, and
  re-running a trimmed download keeps your time range instead of fetching
  the whole video.
- **Optional features fail safe.** If speaker-detection or an alternate
  engine can't load, it's shown as unavailable instead of crashing the app.
- **A clear message** when you try to transcribe a file path that no
  longer exists.

## New

- **A moving "working" bar** in the queue while a task is starting up, so
  you can tell it's busy before the percentage starts.
- **The download time-range fields show 0:00:00** by default so they're
  easier to edit (leave both at 0:00:00 for the whole video).

## Notes

- Only the **Setup-Standard** installer is published.
- Upgrades the previous version cleanly (single Add/Remove entry).
- Full technical detail: `docs/CHANGELOG.md`.
