# Whisper Project v1.5.0

An SMTV release on top of v1.4.0.

## Highlights

- **SMTV docx header now shows the detected language.** Row 2 / column 3 used
  to always read the literal "Foreign Language"; it now shows the language
  faster-whisper detected (e.g. "Korean"), matching the title row and the
  "[... starts]" cue. With no detected language the header keeps its
  original generic text.
- **SMTV added to File → Convert transcript.** The format picker now offers
  `smtv_docx` alongside the existing text targets, for turning any already
  -produced transcript into the team's SMTV template.
- **Project renamed** to `whisper_app` (GitHub repo + local folder).

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
