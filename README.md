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
- **oTranscribe round-trip** — export a finished transcription to `.otr` for human proofing in [oTranscribe](https://otranscribe.com/), then import the edited `.otr` back to SRT.

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

The `Import .otr → SRT...` button below the transcribe controls reads an oTranscribe-edited `.otr` file and writes a clean SRT to a folder of your choice. End times are inferred from the next segment's start; the last segment's end is the file's `media-time` (or `start + 5s`, whichever is greater).

### Transcription Queue

Live status of all enqueued transcription jobs. Right-click a row to cancel a running job, remove a finished one, or — when the job is `finished` — `Export → oTranscribe (.otr)` to write an `.otr` file next to the source media for downstream proofing in oTranscribe.

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

Full details in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). At-a-glance visuals: [docs/architecture-diagrams.md](docs/architecture-diagrams.md) — a Mermaid overview plus the colored [docs/architecture.svg](docs/architecture.svg), both layered and color-coded.

## Project documentation

- [docs/architecture-diagrams.md](docs/architecture-diagrams.md) — Mermaid (simple) + SVG (detailed) views
- [docs/architecture.svg](docs/architecture.svg) — detailed colored system diagram (direct link)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — long-form prose: process model, threading, protocols
- [docs/AUDIT.md](docs/AUDIT.md) — findings, bugs, gaps; honest assessment
- [docs/ROADMAP.md](docs/ROADMAP.md) — prioritized plan, 7 phases, status snapshot at the top
- [docs/COMPETITIVE_ANALYSIS_2026.md](docs/COMPETITIVE_ANALYSIS_2026.md) — 2026 STT landscape, models recommendation, Phase 4/6 inspiration
- [docs/SESSION_LOG.md](docs/SESSION_LOG.md) — narrative record of the orchestrated build sessions
- [docs/integrations/](docs/integrations/) — third-party interop research, briefs, acceptance plans (currently: oTranscribe)
- [docs/BUILD.md](docs/BUILD.md) — PyInstaller pipeline, exit codes, `bin/` fallback rationale, packaging-bug regression notes
- [docs/SESSION_8_PACKAGING_FIX.md](docs/SESSION_8_PACKAGING_FIX.md) — Session 8 bug write-up: silero VAD ONNX missing from bundle
- [tests/smoke/README.md](tests/smoke/README.md) — why the compiled exe needs its own integration tests
- [docs/CHANGELOG.md](docs/CHANGELOG.md) — release notes
- [docs/DECISIONS.md](docs/DECISIONS.md) — ADRs for load-bearing architectural choices
- [docs/auto-subtitles-feature.md](docs/auto-subtitles-feature.md) — deep dive on the subtitle download feature

## Known limitations

The list below reflects the current state after Sessions 1–6. For everything fixed since the project started, see [docs/CHANGELOG.md](docs/CHANGELOG.md) (Unreleased + v0.3.0). For the full backlog see [docs/ROADMAP.md](docs/ROADMAP.md).

**Working as designed but with rough edges:**

- **Chinese transcripts come out as wall-of-text.** Whisper's Mandarin output has very little punctuation by default. Mitigation strategies (initial-prompt nudge, FunASR `ct-punc` post-processor, SenseVoice backend) are documented in [Phase 6.2](docs/ROADMAP.md). Not yet implemented — manual editing in the transcript output is the current workaround.
- **Subtitle line splitting uses the Latin-text 42-char default everywhere.** For Chinese you want ~16 zh-Hans glyphs per line, not 42 cells. Width-aware splitting is [Phase 6.3](docs/ROADMAP.md) — not yet implemented.
- **No model picker UI.** The active model is hard-coded to `faster-whisper-large-v3` via `config.json` `model_path`. To use a different model, edit `%LOCALAPPDATA%\WhisperProject\config.json` manually and point `model_path` at the new folder. UI picker is part of Phase 2b (deferred).
- **No drag-and-drop, no folder watcher.** Add files via the Browse button; no batch-watch on a folder. Phase 2c.
- **No live microphone / dictation mode.** Offline file transcription only. Phase 5.3 (live mic) is a separate effort.
- **No CI yet.** 136 local unit tests + 8 smoke tests run with `pytest`, but no GitHub Actions workflow runs them on every push. Phase 7.3.
- **No in-app transcript editor.** Subtitles are written to disk as SRT/VTT/JSON; if you need to proofread, open them in oTranscribe (round-trip is built in: `Export → oTranscribe (.otr)` on the queue tab) or any subtitle editor. In-app editor is Phase 4.
- **`large-v3` model is ~3 GB on disk and needs ~5 GB VRAM on GPU at fp16, or ~3 GB RAM on CPU int8.** Smaller models (e.g. `tiny`, `base`, `medium`, `distil-large-v3`) would be a click away if the model picker landed.

**Already fixed since the project was first audited (so the original Known limitations are gone):**

- ✅ `yt-dlp --update` no longer runs unconditionally — gated behind `auto_update_yt_dlp` config flag and a 24h timestamp (Phase 0)
- ✅ `ffprobe` resolves to `bin/ffprobe.exe` via the `bundled_binary` helper (Phase 0)
- ✅ Sun Valley theme with Light/Dark/System picker under `View` menu (Phase 1.1)
- ✅ 136 unit tests + 77% coverage on `core/` + `pytest` infrastructure (Phase 1b)
- ✅ `tests/smoke/` integration suite — drives the compiled exe end-to-end (catches PyInstaller packaging bugs that source-side tests can't) (Session 8)
- ✅ Multi-format output (SRT/VTT/TSV/TXT/JSON/LRC), VAD on by default, word-level timestamps, language detection display, `BatchedInferencePipeline` on GPU (Phase 2a)
- ✅ SQLite history with restore-on-launch, SponsorBlock integration, auto-transcribe-after-download, `--progress-template "%(progress)j"` (Phase 3a)
- ✅ PyInstaller build pipeline with `build.bat`, smoke test, BUILD.md (Session 5 final compile)

## License

Not specified yet. See `LICENSE` (coming).

## Acknowledgements

This project stands on the shoulders of:

- [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) — the CTranslate2-backed Whisper port that powers transcription
- [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) — the most capable media downloader in existence
- [FFmpeg](https://ffmpeg.org/) — the multimedia Swiss army knife
- [OpenAI Whisper](https://github.com/openai/whisper) — the original speech model
