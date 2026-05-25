# Whisper Project v1.3.0

UX + reliability release on top of v1.2.0. Install the **Setup-Standard**
EXE attached below; your settings and downloaded models are kept.

## Fixed

- **Auto-transcribe after a video+audio download now works.** When a clip
  is downloaded as separate video + audio streams (Facebook reels,
  YouTube Shorts, most modern formats), yt-dlp merges them into one file
  and deletes the pieces. The app had been trying to transcribe one of
  the deleted pieces, so "Transcribe after download" silently did nothing
  on those clips. It now transcribes the real, merged file.

## New

- **Progress bars in the queues.** Both the transcription and download
  queues now show a visual bar next to the percentage (e.g.
  `████░░░░░░ 42%`), so you can see progress at a glance.
- **The version is visible.** The window title shows
  `Whisper Project v1.3.0`, and the installed Start-menu / desktop
  shortcut is named with the version — so you always know which build
  you're running.
- **The Download tab shows transcription progress.** After a download
  with "Transcribe after download" on, the download row reads
  "transcribing" and shows the live transcription progress (instead of
  sitting at 100% looking finished), then flips to "finished" when done —
  so you can tell the slow transcription is actually working.

## Changed

- **The "Last result" card is smaller** — it no longer expands to fill
  the lower half of the Transcribe tab.
- **The language picker starts at "Auto" every launch.** It's no longer
  remembered between runs (every other setting still is), so you always
  start from auto-detect.

## Notes

- Only the **Setup-Standard** installer is published.
- The installer keeps a single, stable Add/Remove Programs entry, so this
  upgrades the previous version cleanly instead of stacking.
- Full technical detail: `docs/CHANGELOG.md`.
