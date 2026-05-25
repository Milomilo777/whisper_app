# Whisper Project v1.3.3

Features + fixes on top of v1.3.2. Your settings and downloaded models
are kept.

## New

- **Position slider in the Download tab.** Once a video is loaded, drag
  the Start / End sliders along the video's length to set the time range —
  no need to type timecodes. Leave both at 0:00:00 for the whole video.

## Fixed

- **Cancelling then resuming a trimmed transcription** no longer keeps
  going past the end of your selected slice.
- **A reversed time range** (end earlier than start) no longer downloads
  nothing — it now downloads from the start to the end of the video.
- The new sliders don't overwrite a range you typed by hand, and ignore
  accidental drags before a video is loaded.
- The "this site may need login" download hint no longer pops up on
  unrelated errors.

## Downloads

- **Setup-Standard** (`...-Setup-Standard.exe`) — installs to Program Files.
- **Portable** (`...-Portable.zip`) — no install: extract and double-click
  **Run Whisper Project.bat**. It's the full Python environment, so you can
  update later by dropping in newer `app\` / `core\` / `gui.py` files.

## License

This project's source is now under the **BSD 3-Clause License** (was MIT).
Bundled components (FFmpeg, yt-dlp, Python, packages) keep their own
licenses — see `THIRD_PARTY_NOTICES.md`.
