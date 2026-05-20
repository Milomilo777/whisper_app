# Whisper Project

Offline transcription + video downloader for Windows. Built on
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) and
[yt-dlp](https://github.com/yt-dlp/yt-dlp).

## Install

Three options, pick one:

| Method | Asset | Size | Best for |
|---|---|---|---|
| Portable | `WhisperProject-v0.7.0-Portable.exe` | 190.8 MB | یک فایل، بدون نصب، USB |
| Compact | `WhisperProject-v0.7.0-Setup-Compact.exe` | 137.2 MB | کاربر معمولی، start-up سریع، Start Menu shortcut |
| Standard | `WhisperProject-v0.7.0-Setup-Standard.exe` | 153.6 MB | بیشترین شفافیت، فایل‌ها روی disk قابل بازرسی |

دانلود:
**[github.com/Milomilo777/whisper_project_direct_download_v2/releases/latest](https://github.com/Milomilo777/whisper_project_direct_download_v2/releases/latest)**

راهنمای نصب گام‌به‌گام: [docs/INSTALL.md](docs/INSTALL.md).

## Usage

- **Transcribe** — pick an audio/video file, click Transcribe;
  `.srt` and `.json` land next to it.
- **Download Videos** — paste a YouTube / yt-dlp-supported URL **or
  any Supreme Master TV episode link**; pick a format; the file
  saves to your chosen folder. Optionally auto-transcribe after the
  download finishes.
- **Transcription Queue** — live status of pending and running jobs;
  right-click for cancel, re-run, export to oTranscribe, or open
  output folder.

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
