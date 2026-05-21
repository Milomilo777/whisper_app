# Whisper Project

[![CI](https://github.com/Milomilo777/whisper_project_direct_download_v2/actions/workflows/ci.yml/badge.svg?branch=release%2Fv0.7.0-installer-3-options)](https://github.com/Milomilo777/whisper_project_direct_download_v2/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/Milomilo777/whisper_project_direct_download_v2?label=release)](https://github.com/Milomilo777/whisper_project_direct_download_v2/releases/latest)

Offline transcription + video downloader for Windows. Built on
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) and
[yt-dlp](https://github.com/yt-dlp/yt-dlp).

## Install

Three options, pick one:

| Method | Asset | Size | Best for |
|---|---|---|---|
| Portable | [`WhisperProject-v0.7.1-Portable.exe`](https://github.com/Milomilo777/whisper_project_direct_download_v2/releases/download/v0.7.1/WhisperProject-v0.7.1-Portable.exe) | 447 MB | یک فایل، بدون نصب، USB |
| Compact | [`WhisperProject-v0.7.1-Setup-Compact.exe`](https://github.com/Milomilo777/whisper_project_direct_download_v2/releases/download/v0.7.1/WhisperProject-v0.7.1-Setup-Compact.exe) | 326 MB | کاربر معمولی، start-up سریع، Start Menu shortcut |
| Standard | [`WhisperProject-v0.7.1-Setup-Standard.exe`](https://github.com/Milomilo777/whisper_project_direct_download_v2/releases/download/v0.7.1/WhisperProject-v0.7.1-Setup-Standard.exe) | 349 MB | بیشترین شفافیت، فایل‌ها روی disk قابل بازرسی |

دانلود (همه assetها در یک صفحه):
**[github.com/Milomilo777/whisper_project_direct_download_v2/releases/latest](https://github.com/Milomilo777/whisper_project_direct_download_v2/releases/latest)**

راهنمای نصب گام‌به‌گام: [docs/INSTALL.md](docs/INSTALL.md).

## Configuration + model path

User settings live in a single JSON file at:

```
%LOCALAPPDATA%\WhisperProject\config.json
```

The key that controls where the Whisper model is stored on disk is
`model_path`. By default it points at the platform cache
(`%LOCALAPPDATA%\WhisperProject\Cache\models\models--Systran--faster-whisper-large-v3`).
To use an existing model from elsewhere (a network share, a portable
drive, a custom location) edit `model_path` directly and restart the
app. If the configured path is missing or its drive isn't mounted,
the app silently falls back to the cache.

## Usage

- **Transcribe** — drag-and-drop one or many files (or click Browse).
  Optionally turn on **Voice Activity Detection**, **Word timestamps**,
  or **Identify speakers (diarization)**. Click Transcribe; the chosen
  outputs land next to your input. Eight formats supported:
  `srt`, `vtt`, `tsv`, `txt`, `json`, `lrc`, `md`, `docx`.
- **Last Result card** — every finished transcription pops a card
  with each output file (size + one-click Open) plus an
  **Open folder** button and a **View transcript** button that
  launches the in-app viewer (split-pane, click-to-seek, embedded
  VLC playback when available).
- **Download Videos** — paste a YouTube / yt-dlp-supported URL **or
  any Supreme Master TV episode link**; pick a format; the file
  saves to your chosen folder. Optionally auto-transcribe after the
  download finishes.
- **Transcription Queue** — live status of pending and running jobs;
  right-click for cancel, re-run, export to oTranscribe, or open
  output folder. Double-click a finished row to open its folder.

Keyboard shortcuts: `Ctrl+O` Browse, `Ctrl+Enter` Transcribe, `Esc`
Cancel running, `Ctrl+Q` Exit.

First launch downloads the ~3 GB Whisper model from a CDN mirror. No
network needed for transcription after that.

## Architecture

```
Tk App  ── JSON stdio ──►  Worker subprocess (faster-whisper)
        ── subprocess  ──►  yt-dlp.exe
```

Visual: [docs/architecture.svg](docs/architecture.svg).

## Documentation

- [docs/INSTALL.md](docs/INSTALL.md) — end-user install + troubleshooting
- [docs/BUILD.md](docs/BUILD.md) — three build pipelines (Portable, Compact, Standard)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — process model, threading, protocols
- [docs/ROADMAP.md](docs/ROADMAP.md) — what's done, what's next
- [docs/CHANGELOG.md](docs/CHANGELOG.md) — version history
- [docs/SESSION_LOG.md](docs/SESSION_LOG.md) — orchestration narrative
- [docs/integrations/](docs/integrations/) — oTranscribe + Supreme Master TV research/briefs
- [docs/history/](docs/history/) — archived phase-acceptance plans and session writeups

## License

Unspecified. The bundled binaries (`ffmpeg`, `ffprobe`, `yt-dlp`) and
the Whisper model are subject to their respective upstream licenses.
