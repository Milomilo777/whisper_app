# Whisper Project v1.3.4

Smaller install + a docx fix. Your settings and downloaded models are kept.

## Smaller install

- The installed app is now about **800 MB** instead of ~1.5 GB. PyTorch
  and the heavy libraries it pulls in are no longer bundled — they were
  only needed by two optional features (see below).

## On-demand optional features

- **Word-timestamp alignment** (stable-ts) and the **openai-whisper
  backend** now download what they need (~700 MB, one time) the first time
  you use them — like the Whisper model download. A prompt asks before
  downloading; choose No to run without that feature.
- Everything else — transcription, subtitles, speaker detection,
  downloads, the time-range slider — works out of the box with no extra
  download.

## Fixed

- **DOCX (and PDF) output now actually gets written.** Selecting docx in
  Advanced settings used to be silently ignored; it works now.

## Downloads

- **Setup-Standard** (`...-Setup-Standard.exe`) — installs to Program Files.
- **Portable** (`...-Portable.zip`) — extract and run **Run Whisper
  Project.bat**, no install.

## Notes

- License: BSD-3-Clause; bundled components keep their own licenses
  (`THIRD_PARTY_NOTICES.md`).
- Full technical detail: `docs/CHANGELOG.md`.
