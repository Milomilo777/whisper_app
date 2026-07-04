# Whisper Project v1.1.0

Maintenance release — bug fixes plus one opt-in feature. Install the
**Setup-Standard** EXE attached below; your existing settings and the
downloaded model are kept.

## New

- **Download from login-walled / age-gated sites.** A new "Cookies from
  browser" option (Advanced → Downloads) lets the app reuse your
  logged-in browser session, so Facebook / Instagram / TikTok stories
  and age-restricted YouTube Shorts can download. Off by default — pick
  your browser (Chrome / Edge / Firefox / …) to turn it on.

## Fixed

- **Video downloads had no audio** in some cases — the yt-dlp format
  selector now correctly merges the best video *and* best audio.
- **"Transcribe after download" froze the app** while the model loaded.
  The UI stays responsive now; the same fix also covers crash-resume and
  the watched folder.
- **The model-hub folder you picked was ignored** and `model_path`
  looked like it "reset" on every launch — your chosen hub now sticks.
- **The "Resume interrupted transcriptions?" prompt nagged every launch**
  even after you clicked No — declining now clears it.
- **A download folder on a removable / network drive was forgotten**
  after one launch without the drive — it's preserved now.
- **A truncated Supreme Master TV download** used to be saved and
  transcribed as if complete — it now fails cleanly instead of producing
  a corrupt clip.
- The About dialog no longer shows the source-repository URL.
- The Advanced settings dialog is now resizable and scrolls.

## Notes

- From this release on, only the **Setup-Standard** installer is
  published (the Portable build was retired).
- Full technical detail: `docs/CHANGELOG.md`; the bug-hunt method and
  findings are in `docs/AUDIT_2026-05-25_boundary_bugs.md`.
