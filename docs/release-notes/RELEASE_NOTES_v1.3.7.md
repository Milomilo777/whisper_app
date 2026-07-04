# Whisper Project v1.3.7

A **stability, security, and correctness** release — the output of a
deep, line-by-line audit of the whole app. No new features and no
workflow changes: your settings, downloaded models, and the way you use
the app are all unchanged. This is the "everything just works more
reliably" release.

## Security

- **Burning subtitles no longer breaks on normal titles.** Videos whose
  title contains an apostrophe, comma, or brackets (e.g. *Rock 'n' Roll*,
  *clip [HD], part 2*) used to make the subtitle-burn step fail with an
  obscure ffmpeg error — and a hostile title could even tamper with the
  command. Burning is now done safely regardless of the filename.

## Reliability fixes

- **No more leftover background programs.** Cancelling or closing the app
  while a transcription or download was running could leave a hidden
  `ffmpeg`/`demucs` process running — eating CPU/RAM and locking files.
  The app now stops the whole process tree cleanly.
- **The "Loading model…" window can't get stuck.** If the model failed to
  load (corrupt/partial files), the spinner used to hang forever. It now
  closes and tells you what happened.
- **Bad-mirror protection.** If a model download keeps failing its
  integrity check, the app now stops after a few tries with a clear error
  instead of re-downloading ~3 GB over and over.
- **The optional one-time feature download** (Word-timestamp alignment /
  the alternate engine) now has a working **Cancel** button and a timeout,
  and a failed install can't leave a broken half-installed package behind.
- **Long recordings won't run out of memory** — the recorder now writes to
  disk as it captures instead of holding the whole take in RAM.
- **Format loading recovers** instead of silently dying for the rest of
  the session if a site returns an unexpected response.

## Correctness fixes

- **Time-range transcription now works on every engine** (it was silently
  transcribing the whole file on the non-default engines).
- **Suspect-segment flags** from the hallucination detector now actually
  appear (red rows) in the transcript viewer.
- Smaller fixes: the resume progress bar now moves instead of sitting at
  99%; subtitle export no longer chokes on certain word data; history
  records the right output paths; per-folder project settings no longer
  bleed into the next file; and several shutdown-time glitches are gone.

The About dialog also stopped listing two capabilities that weren't
actually wired up yet (cross-file voiceprint matching, semantic search).

## Cross-platform

- macOS install script now finds Homebrew/system **ffmpeg** for the
  double-clicked app. *(macOS still needs validation on a real Mac.)*

## Downloads

- **Setup-Standard** (`...-Setup-Standard.exe`) — installs to Program Files.
- **Portable** (`...-Portable.zip`) — extract and run **Run Whisper Project.bat**.

Full technical detail: `docs/CHANGELOG.md`.
