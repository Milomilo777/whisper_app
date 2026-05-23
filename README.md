# Whisper Project — basic

A radically simplified offline transcription desktop app for Windows. Drop a media file, click **Transcribe**, get `.srt`, `.json`, and `.txt` next to the source.

One screen. No tabs. No advanced dialog. No video download. No diarisation. Just speech → subtitles, with great defaults and clear error messages.

## What it does

- Drag-and-drop or **Browse…** a media file.
- Click **Transcribe** — runs [faster-whisper](https://github.com/SYSTRAN/faster-whisper) `large-v3` locally.
- Writes `<filename>.srt`, `<filename>.json`, `<filename>.txt` next to the source media.
- Cancel any running job (Esc or right-click).
- Pick the best available device automatically (CUDA when present, otherwise CPU).

## What it does NOT do

- No video download / YouTube / SMTV / sponsorblock.
- No diarisation, chapters, voiceprint, LLM, Demucs, alignment.
- No alternative backends (whisper.cpp, Parakeet) — only faster-whisper.
- No transcript viewer, search, history, watched folder, tray.
- No DOCX / PDF / LRC / VTT / TSV writers.
- No advanced dialog, no theme switcher.

If you need any of these, use the full-fat repo:
https://github.com/Milomilo777/whisper_project_direct_download_v2

## Quick start (from source)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python gui.py
```

The first launch shows a hub-folder picker (default: `<app_dir>/hub`). The first **Transcribe** click downloads the model (~3 GB, MD5-verified).

## Build the portable exe

```
pip install pyinstaller
pyinstaller --noconfirm --clean whisper_project_basic.spec
```

Output: `dist/WhisperProjectBasic-Portable.exe`.

## Self-diagnostics

If anything misbehaves:

- **Help → Diagnose** — re-runs the startup checks and offers a Copy button.
- **Help → Show recent log** — last 200 lines of the app log.
- **Help → Open log folder** — opens the OS file manager on the log directory.

## License

MIT. See [LICENSE](LICENSE).
