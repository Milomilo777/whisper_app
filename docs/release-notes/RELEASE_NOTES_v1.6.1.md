# Whisper Project v1.6.1

A follow-up polish release on top of v1.6.0: a real Google Cloud STT bug
fix, more Advanced-dialog readability work, and the default Live-tab
microphone fix released for real.

## Highlights

- **Advanced dialog readability, rounds 3-4.** Consistent section headers
  across every section; the old 10-row "Whisper extras" grab-bag split into
  "Model & engine" and "Prompt, hotwords & output naming"; hover-help added
  to all 15 output-format checkboxes plus every remaining bare control (AI
  Layer's "Enable local LLM" / "Generate auto-chapter markers", Downloads'
  "Transcribe after download", the Google Cloud bucket field, "Minimise to
  system tray"); the "Jump to" nav sidebar now groups its 11 links under
  "Alternate engines" / "App preferences" captions.
- **"Restore transcription defaults" button** in the Advanced dialog —
  resets VAD, hallucination-detection, alignment, batch size, denoise,
  Demucs, auto-chapters and voiceprint back to defaults in one click.
  Output formats, prompt/hotwords text, model/backend choice, watched
  folder and credentials are left untouched.
- **LAN web page ergonomics** borrowed from `voice-pro`: an instant local
  file preview, a Reset button, a Copy button on the transcript, and a
  compact "Recent jobs" list on the Submit view.

## Fixed

- **Google Cloud STT silently discarded your "Detect speakers" choice.**
  Saving Advanced settings with that backend selected always reset
  diarization back off, even though the backend has fully supported it
  (Standard and Batch mode) since it was first added — the checkbox itself
  was never broken, the Save button was throwing the choice away. It now
  saves correctly; the tooltip explains the real behavior instead (Standard
  mode restarts Google's speaker numbering every ~1-minute chunk, so the
  same person can get a different label in different parts of the
  transcript — Batch mode does not have this limitation).
- **The Live tab's default "Microphone" source did not work out of the
  box.** `sounddevice` (and, on Windows, `PyAudioWPatch` for the "System
  audio" source) were never actually in `requirements.txt`, so every
  install hit "sounddevice not installed" the first time anyone opened the
  Live tab. Both now ship by default, the same as the app's other small UI
  dependencies.

## Builds

- **Setup-Standard** (Windows) — the recommended installer (embeddable
  Python; choose where models are stored on first run).
- **Portable** (Windows) — a ZIP of the same tree; extract and run
  `Run Whisper Project.bat`, no install.

## Notes

- First launch asks where to keep the speech models (large files); the
  default is a writable per-user folder.
- Windows SmartScreen may warn on an unsigned installer — choose *More
  info → Run anyway*.
- In-place upgrade: run the new Setup-Standard installer over an existing
  install — no need to uninstall first; your settings and hub folder
  choice survive.
