# Whisper Project v1.3.8

A hardening + feature release on top of v1.3.7.

## Highlights
- **Cloud transcription** — Google Gemini (paste an API key) and Google Cloud
  Speech-to-Text (service-account JSON). The default engine stays **fully
  offline** (faster-whisper); cloud is opt-in per the Advanced dialog and
  uploads audio only when you choose it.
- **LAN / web access** — share transcription + downloads to phones and other
  PCs on your local network from a built-in browser page (off by default).
- **Transcript format conversion** — convert between SRT / VTT / TSV / JSON /
  TXT (and import `.otr`) from the File menu.
- **SMTV team `.docx`** — the team's 4-column transcription/translation table.
- **Multi-monitor Video Tiling** — one live stream as an N×N wall across
  monitors, with auto-reconnect and clean teardown; grid size is remembered.
- **Three-level config, multi-model picker, usage stats, ffplay auto-download.**
- **macOS support** (build from source / `.app`) — see `platform/macos/`.

## Reliability (this release)
A large, adversarial, multi-pass audit fixed a long list of confirmed bugs —
data-loss guards (transcript overwrite, cloud truncation, recorder WAV),
crash hardening across malformed input (config / converter / writers / viewer /
server), Windows process-tree teardown, the LAN server's upload + auth +
filename handling, cloud usage accounting, and the offline time-range feature
on multi-hour files (now pre-sliced instead of decoding the whole file). Every
fix ships with a regression test; the type-checker is clean and the macOS build
is green.

## Builds
- **Setup-Standard** — the recommended installer (embeddable Python; offline by
  default; you choose where models are stored on first run). The installer can
  optionally skip Video Tiling.
- **Portable** — a no-install ZIP of the same tree; unzip and run
  `Run Whisper Project.bat`.

> These trusted-distribution builds come with Google Cloud Speech-to-Text
> pre-configured, so the cloud engine works out of the box for the people this
> build is shared with. Keep the build private. Offline transcription needs no
> key and no network.

## Notes
- First launch asks where to keep the speech models (large files); the default
  is a writable per-user folder.
- Windows SmartScreen may warn on an unsigned installer — choose *More info →
  Run anyway*.
