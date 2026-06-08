# Whisper Project v1.3.9

A frontend-stability + cloud-default release on top of v1.3.8.

## Highlights

- **Pick your engine on the Transcribe tab** — a new *Engine* row lets you choose
  the transcription engine (offline Faster-Whisper, whisper.cpp, Parakeet, Gemini
  cloud, or Google Cloud Speech-to-Text) directly, without opening the crowded
  Advanced dialog. A short status line shows whether the chosen engine is ready
  (✓) or needs setup (⚠).
- **Google Cloud STT works out of the box** in this build — it ships with the
  service-account key pre-loaded and is the **default** engine, so cloud
  transcription just works. The Advanced dialog shows the key is loaded and
  auto-tests the connection when you open it. You can switch back to fully
  offline Faster-Whisper at any time from the Engine picker.

## Reliability (this release)

- The transcription worker's input reader no longer hangs on Windows pipes.
- The "model present" check no longer false-triggers the large download dialog
  when the model is already on disk.
- The download time-range sliders no longer cross over each other.
- Switching the engine now restarts the worker so the new engine takes effect
  immediately.
- **Model download has a fallback source** — if the mirror is missing a model
  (a 404), it is fetched from huggingface.co instead, using each model's correct
  upstream repo (so large-v3-turbo / distil models download too).
- **Google Cloud STT works immediately** — its client libraries are now bundled
  in the build instead of installed on first use, so there's no "could not
  install … check internet" wait, and a broken/wrong-version library cache from
  an earlier version is repaired automatically.
- **The engine readiness line is a real check now** (model on disk, client
  imports, key present), not a fixed "Ready" label.
- The less-important Gemini "Google API key" field now sits below the Google
  Cloud Speech-to-Text section in Advanced settings.

## Builds

- **Setup-Standard** (Windows) — the recommended installer (embeddable Python;
  choose where models are stored on first run).
- **Portable** (Windows) — a ZIP of the same tree; extract and run
  `Run Whisper Project.bat`, no install.
- **macOS** — a `.dmg` built on Apple-silicon; same cloud-default behaviour.

> These trusted-distribution builds come with Google Cloud Speech-to-Text
> pre-configured, so the cloud engine works out of the box. Keep the builds
> private — the key is inside them. Offline transcription needs no key and no
> network.

## Notes

- First launch asks where to keep the speech models (large files); the default is
  a writable per-user folder.
- Windows SmartScreen may warn on an unsigned installer — choose *More info → Run
  anyway*.
