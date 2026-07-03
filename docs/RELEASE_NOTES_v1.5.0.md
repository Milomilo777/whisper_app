# Whisper Project v1.5.0

An SMTV + usage-stats release on top of v1.4.0.

## Highlights

- **SMTV docx header now shows the detected language.** Row 2 / column 3 used
  to always read the literal "Foreign Language"; it now shows the language
  faster-whisper detected (e.g. "Korean"), matching the title row and the
  "[... starts]" cue. With no detected language the header keeps its
  original generic text.
- **SMTV added to File → Convert transcript.** The format picker now offers
  `smtv_docx` alongside the existing text targets, for turning any already
  -produced transcript into the team's SMTV template.
- **Usage-stats payload is richer.** It now includes the sending app's
  version and coarse host/hardware facts (OS, machine, CPU count, total
  RAM) — still sent only when telemetry is opted in.
- **Project renamed** to `whisper_app` (GitHub repo + local folder).

## Fixed

- **Usage-stats `word_count` was 0 whenever "json" wasn't among the chosen
  output formats**, even though the transcript itself (e.g. `.srt`/`.docx`)
  was full of real words. It now falls back to re-parsing whichever other
  produced transcript format is available.

## Builds

- **Setup-Standard** (Windows) — the recommended installer (embeddable
  Python; choose where models are stored on first run).
- **Portable** (Windows) — a ZIP of the same tree; extract and run
  `Run Whisper Project.bat`, no install.

> This release is Windows-only; macOS builds resume in a future release.

## Notes

- First launch asks where to keep the speech models (large files); the
  default is a writable per-user folder.
- Windows SmartScreen may warn on an unsigned installer — choose *More info
  → Run anyway*.
