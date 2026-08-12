# Whisper Project v1.6.0

A Live-transcription + denoise release on top of v1.5.0.

## Highlights

- **New Live tab.** Transcribe a microphone or the system audio as it
  happens. Text appears while you speak instead of after a file finishes.
  Chunks are cut at natural pauses so words are not split in half, silence
  is never sent to the model, and the tab says so when the machine cannot
  keep up rather than skipping audio silently. System-audio capture is
  Windows-only. See `docs/LIVE.md`.
- **Adaptive audio denoise before transcription** (**Advanced > AI Layer**,
  off by default). Cuts hallucinated lines and misheard words on noisy
  recordings. It measures each file first, leaves already-clean audio
  untouched, then checks its own output and falls back to the original if
  the filter removed speech instead of noise. Bundled ffmpeg only — no
  extra download. See `docs/DENOISE.md`.
- **ASS / SSA subtitle support.** A new `ass` output format, and `.ass` /
  `.ssa` files can now be converted from as well. ASS is what video editors
  and karaoke tools expect, and it is the first format that carries our
  per-word timings as real karaoke highlighting.
- **`platform\windows\update.bat`** — a one-command updater for a source
  (git clone) install on Windows.
- **The README is now available in 7 more languages** — Chinese, Japanese,
  Korean, German, Spanish, French, Portuguese — reachable from a flag
  switcher at the top of each one.

## Fixed

- **The `nvidia_asr` (Parakeet) backend could fail to import** with a
  `tokenizers>=X,<=Y is required` error on a build done the wrong day.
  `tokenizers` and `transformers` are now pinned to a verified matching
  pair, and the backend's error message and status probe both report the
  real cause.
- **The default engine is always offline faster-whisper again.** It no
  longer flips to Google Cloud STT because a key file exists next to the
  app — that bundled key was revoked; see `SECURITY.md`.
- **Resuming a cancelled job now re-checks the pre-processing settings.**
  Changing vocal separation or denoise between cancel and resume used to
  splice differently-conditioned halves into one transcript; the partial
  is now invalidated and re-run instead.

## Builds

- **Setup-Standard** (Windows) — the recommended installer (embeddable
  Python; choose where models are stored on first run).
- **Portable** (Windows) — a ZIP of the same tree; extract and run
  `Run Whisper Project.bat`, no install.

> macOS: no new build this round. The v1.5.0 release still has
> `WhisperProject-v1.5.0-macOS-x64.dmg` (Intel/x64-only) for Mac users
> until a future session rebuilds it.

## Notes

- First launch asks where to keep the speech models (large files); the
  default is a writable per-user folder.
- Windows SmartScreen may warn on an unsigned installer — choose *More
  info → Run anyway*.
- The v1.5.0 release stays published (not deleted) alongside this one.
