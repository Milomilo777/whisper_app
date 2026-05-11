# Whisper Project — Offline Transcription + Video Downloader

A Windows-first desktop app that does two things well:

1. **Download** audio or audio + video from any site `yt-dlp` supports, with optional automatic subtitles in any of 30+ languages.
2. **Transcribe** local audio/video files into SRT subtitles using `faster-whisper`, fully offline.

Built for the workflow of producing bilingual subtitle files (English ↔ Persian and others) for TV broadcast, where every download eventually needs accurate, well-timed captions.

## What sets it apart

- **Truly offline transcription.** Once the model is downloaded (one time, ~3 GB), no network is required for transcription. No data leaves the machine.
- **Bundled binaries.** `ffmpeg`, `ffprobe`, and `yt-dlp` ship in `bin/`. No system install required.
- **Resumable, verified model download.** The model is fetched as a ZIP from a CDN mirror, then every extracted file is MD5-verified. Interrupted downloads resume; corrupt extracts are detected and retried.
- **Crash isolation.** Transcription runs in a long-lived subprocess worker; if the model crashes the UI stays up.
- **Multiple parallel workers** for transcription, each holding the model in memory.
- **Per-phase status** during downloads — you see when the subtitle phase succeeds, fails, or has no captions available, separately from the media phase.

## Status

Working draft. See [docs/AUDIT.md](docs/AUDIT.md) for known issues and [docs/ROADMAP.md](docs/ROADMAP.md) for the planned trajectory.

The app is usable today for the core flows. The roadmap describes how it gets from "useful for one person" to "best-in-class for the niche."

## Quick start

### Prerequisites

- Windows 10 / 11 (Linux and macOS are not officially supported yet, but the Python code is mostly portable)
- Python 3.11 or newer
- ~3 GB free disk for the Whisper `large-v3` model
- An NVIDIA GPU with CUDA is recommended; CPU works but is much slower

### Install

```powershell
git clone <repo-url>
cd whisper_project_direct_download_v2

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

Then ensure the bundled binaries are in `bin/`:

```
bin/
├── ffmpeg.exe       # ~100 MB
├── ffprobe.exe      # ~100 MB
└── yt-dlp.exe       # ~18 MB
```

These are not checked into git. Download from:

- ffmpeg / ffprobe: <https://www.gyan.dev/ffmpeg/builds/> (release essentials build)
- yt-dlp: <https://github.com/yt-dlp/yt-dlp/releases/latest>

### Run

```powershell
python gui.py
```

On the first launch, the app will check for the Whisper model. If it isn't found at `config.json:model_path`, a dialog appears, downloads the ZIP, verifies it, and extracts it. Subsequent launches are instant.

## Tabs

### Transcribe

Pick a local audio or video file. The transcribe button enqueues it for the worker subprocess. SRT and JSON are written next to the input file with the same base name.

### Transcription Queue

Live status of all enqueued transcription jobs. Right-click a row to cancel a running job or remove a finished one.

### Download Videos

Paste a URL; the app auto-loads format options via `yt-dlp --dump-single-json`. Choose audio-only or audio+video, format, output extension. Optionally check "Download subtitles" and pick a language (Automatic detects from the video's metadata).

Files land in the folder you choose. The folder, subtitle preference, and subtitle language are remembered across sessions.

## Configuration

Settings live in `config.json` next to `gui.py`. See [docs/CONFIG.md](docs/CONFIG.md) (coming) for the full field reference.

Key fields:

| Field | Default | Notes |
|---|---|---|
| `model.url` | smch.ir mirror | The ZIP source for `ensure_model` |
| `model.md5` | `<url>.md5` | The file-by-file MD5 manifest |
| `model_path` | (user-specific) | Where the extracted model goes |
| `device` | `auto` | `auto` / `cuda` / `cpu` |
| `compute_type` | `int8` | faster-whisper compute_type |
| `parallel_workers` | `2` | Max concurrent transcription workers |
| `download_folder` | (last used) | Default target for new downloads |

## Architecture in 30 seconds

```
                 ┌──────────────────────────────────┐
                 │           App (Tk main)          │
                 │  - widgets, three tabs           │
                 │  - polls 3 event queues @ 100ms  │
                 └──┬───────────────────────┬───────┘
                    │ JSON over stdio       │ subprocess
                    ▼                       ▼
       ┌──────────────────────┐   ┌──────────────────────┐
       │  Worker subprocess   │   │  yt-dlp.exe          │
       │  - one model load    │   │  - bundled in bin/   │
       │  - many transcribes  │   │  - one per download  │
       └──────────────────────┘   └──────────────────────┘
```

Full details in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Project documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the code is organized today
- [docs/AUDIT.md](docs/AUDIT.md) — findings, bugs, gaps; honest assessment
- [docs/ROADMAP.md](docs/ROADMAP.md) — prioritized plan to elevate the project
- [docs/auto-subtitles-feature.md](docs/auto-subtitles-feature.md) — deep dive on the subtitle download feature
- [docs/CHANGELOG.md](docs/CHANGELOG.md) — release notes

## Known limitations

See [docs/AUDIT.md](docs/AUDIT.md) for the full list. The most important ones today:

- `yt-dlp --update` runs unconditionally before every download — breaks offline use until fixed (Phase 0)
- `ffprobe` is called from `PATH`, not from `bin/` — breaks on clean machines (Phase 0)
- No theming, no drag-and-drop, no folder watcher, no model picker — see roadmap Phases 1-2
- No tests, no CI — see roadmap Phase 1

## License

Not specified yet. See `LICENSE` (coming).

## Acknowledgements

This project stands on the shoulders of:

- [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) — the CTranslate2-backed Whisper port that powers transcription
- [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) — the most capable media downloader in existence
- [FFmpeg](https://ffmpeg.org/) — the multimedia Swiss army knife
- [OpenAI Whisper](https://github.com/openai/whisper) — the original speech model
