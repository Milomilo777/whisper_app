# Whisper Project v1.3.5

Real Pause/Resume/Cancel, and a round of hardening. Your settings and
downloaded models are kept.

## Pause, Resume, Cancel — now real

- **Pause** a running transcription and it truly stops at the next
  segment; **Resume** continues from there.
- **Cancel** now saves a resumable checkpoint, so **Re-run** picks up
  where you stopped instead of starting over. (Before, Cancel threw the
  partial work away.)

## Fixed

- **A docx-only or pdf-only result no longer shows "no output files
  found".** The result card and history now list the files actually
  written (docx/pdf included).
- **Cancel an auto-transcribe from the Download row** — right-click now
  offers Cancel while a downloaded file is being transcribed.
- A sub-second download **end time** no longer corrupts the range.
- One broken output format no longer discards the formats that wrote
  fine.
- Smaller polish: pausing a not-yet-started task, and progress bars with
  odd values, no longer misbehave.

## Under the hood

- On-demand feature installs (the optional ~700 MB download) are now
  serialized and log safely to the window.
- The slim build trims a leftover ~30–40 MB and guards against the
  docx/pdf writers ever being dropped again.

## Downloads

- **Setup-Standard** (`...-Setup-Standard.exe`) — installs to Program Files.
- **Portable** (`...-Portable.zip`) — extract and run **Run Whisper
  Project.bat**.

Full detail: `docs/CHANGELOG.md`.
