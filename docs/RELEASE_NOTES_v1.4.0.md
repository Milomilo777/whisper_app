# Whisper Project v1.4.0

An engine-cleanup + safety release on top of v1.3.9.

## Highlights

- **One Parakeet engine, not two.** The incomplete sherpa-onnx `parakeet`
  engine — which only ever showed a permanent "model files missing" warning
  with no way to fix it from the UI — has been removed. The transformers-based
  NVIDIA Parakeet engine (`nvidia_asr`) is now the only one, and it works.
- **"Prepare Parakeet model now..." button** in Advanced settings installs the
  engine's dependencies and downloads the model ahead of time, so the
  one-time wait happens when you choose to trigger it, not in the middle of
  your first transcription.
- **config.json is leaner and safer.** `telemetry_opt_in`, `config_url`,
  `stats_url`, `ffplay_downloads`, and `latest_version` are no longer written
  to disk — they are app-level values re-derived on every launch, so saving
  them locally only risked pinning a stale value across an upgrade. Existing
  config files are cleaned up automatically on the next save.
- **Cleaner in-place upgrades.** Both Windows installers now silently
  uninstall the previous version before installing the new one, so files
  removed or renamed between versions no longer linger on disk. This still
  needs no manual uninstall step from you, and a model hub folder kept
  outside the install directory is never touched without an explicit prompt.

## Fixed

- The SMTV transcription `.docx` output's "Modified" document property used
  to carry straight through from the bundled template; it now reflects the
  actual transcription time.

## Builds

- **Setup-Standard** (Windows) — the recommended installer (embeddable Python;
  choose where models are stored on first run).
- **Portable** (Windows) — a ZIP of the same tree; extract and run
  `Run Whisper Project.bat`, no install.

> This release is Windows-only; macOS builds resume in a future release.

## Notes

- First launch asks where to keep the speech models (large files); the default is
  a writable per-user folder.
- Windows SmartScreen may warn on an unsigned installer — choose *More info → Run
  anyway*.
