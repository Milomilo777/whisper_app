# Whisper Project v1.7.0

A settings-safety and stability release on top of v1.6.0.

## Highlights

- **New "Enable VAD (skip silent segments)" checkbox** (Advanced >
  transcription settings). Voice Activity Detection was always on with no
  way to turn it off from the desktop app. The three VAD tuning sliders
  (min silence, threshold, speech pad) now grey out while it is unchecked.
- **Transcript viewer: "Edit timestamp..."** — right-click a segment to
  hand-edit its start/end time. Only that one segment changes. A resulting
  overlap with the previous segment, or a sub-1-second duration, gets a
  light-orange row highlight as a warning; it never blocks saving.

## Fixed

- **Editing "Hotwords" in Advanced settings could be silently undone.**
  Saving Advanced settings correctly wrote the new hotwords to disk, but
  the Transcribe tab kept its own frozen copy from app launch. Touching
  the language dropdown or a checkbox on that tab afterward silently
  overwrote the fresh edit. Fixed.
- **`config.json` now refuses a drastic silent shrink and keeps a
  backup.** A real incident this cycle reduced a user's config from ~90
  keys to 3 with no clear trigger found. Saving now refuses to write a
  config with under 40% of the key count currently on disk, and keeps a
  rotating `config.json.bak` of the last good state on every normal save.
- **A rare native crash during engine/hardware detection is now
  hardened against.** A background thread probing for an optional heavy
  package (Google Cloud Speech, whisper.cpp, a torch-backed engine,
  pyannote.audio, sentence-transformers, llama-cpp-python, sherpa-onnx,
  stable-ts, or the hardware tier probe) could occasionally crash the
  whole app if Python's garbage collector ran at the wrong moment during
  the import. Every such probe now disables garbage collection for that
  one operation.
- **Semantic search could silently mis-score a stale index row** after
  switching embedding models. It now skips a dimension-mismatched row
  instead of scoring a meaningless partial comparison.

## Security

- **"Convert transcript" ELAN (`.eaf`) import now rejects a DOCTYPE.** A
  crafted `.eaf` file with a DOCTYPE/entity block could previously hang
  or balloon memory ("billion laughs") when imported. Such files are now
  refused outright with a clear error.

## Other

- The installer and Portable build no longer bundle the
  `google-cloud-speech` / `google-cloud-storage` client libraries. Google
  Cloud STT is an opt-in engine for users with their own service-account
  key; those libraries now install on demand the first time it is picked,
  the same as every other optional backend. This shrinks the normal
  install.

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
