# Whisper Project

[![CI](https://github.com/Milomilo777/whisper_project_direct_download_v2/actions/workflows/ci.yml/badge.svg?branch=chore%2Fcleanup-hardening)](https://github.com/Milomilo777/whisper_project_direct_download_v2/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/Milomilo777/whisper_project_direct_download_v2?label=release)](https://github.com/Milomilo777/whisper_project_direct_download_v2/releases/latest)

**A Windows desktop app that transcribes audio and video files locally
using OpenAI's Whisper model.** Drag a file in, get an `.srt` + `.json`
+ `.docx` back. No cloud, no account, no upload. Also downloads from
any site `yt-dlp` supports.

Two deliverables for two audiences:

| Method | Asset | Size | Best for |
|---|---|---|---|
| **Portable** | `WhisperProject-v1.0.3-Portable.exe` | ~450 MB | one file, no install, USB-stick friendly |
| **Standard** | `WhisperProject-v1.0.3-Setup-Standard.exe` | ~350 MB | proper installer — Start-menu shortcut, files live on disk, Python visible for debugging |

Download from the latest release:
**[github.com/Milomilo777/whisper_project_direct_download_v2/releases/latest](https://github.com/Milomilo777/whisper_project_direct_download_v2/releases/latest)**

Step-by-step install guide: [docs/INSTALL.md](docs/INSTALL.md).

---

## What it does

- **Transcribe** — drag-and-drop one or many files. Optional: Voice
  Activity Detection, word-level timestamps, speaker diarisation.
  Outputs land next to your input in eight formats: `srt`, `vtt`,
  `tsv`, `txt`, `json`, `lrc`, `md`, `docx`.
- **Last-Result card** — every finished transcription opens a card
  with file sizes, one-click "Open file" buttons, an "Open folder"
  shortcut, and a "View transcript" button that launches the in-app
  viewer (split-pane, click-to-seek, embedded VLC playback when
  available).
- **Download Videos** — paste any URL `yt-dlp` supports OR any
  Supreme Master TV episode link, pick a format, save to your
  folder. Optionally auto-transcribe after the download.
- **Transcription Queue** — live status of pending + running jobs.
  Right-click for cancel, re-run, export to oTranscribe, or open the
  output folder. Double-click a finished row to jump to its folder.

Keyboard: `Ctrl+O` Browse · `Ctrl+Enter` Transcribe · `Esc` Cancel ·
`Ctrl+Q` Exit.

First launch downloads the ~3 GB Whisper model from a CDN mirror.
Everything after that is fully offline.

---

## First-run setup — the Model Hub Folder

On the first launch, the app asks where to store the Whisper model
files via a folder-picker dialog. The default suggestion is a `hub`
sub-folder next to the application; the user can pick any location
(an external drive, a network share, etc.). The choice is persisted
to `%LOCALAPPDATA%\WhisperProject\config.json` under the
`hub_folder` key and the dialog never asks again.

If you ever need to reset, run with `--safe-mode`:

```cmd
WhisperProject.exe --safe-mode
```

This backs up the user config aside and re-fires the first-run
dialog with the defaults.

---

## Configuration

User settings live at:

```
%LOCALAPPDATA%\WhisperProject\config.json
```

Key fields:

| Key | What it controls |
|---|---|
| `hub_folder` | Where Whisper model files are stored (set by first-run dialog) |
| `model_path` | Per-model override; derived from `hub_folder + model.name` when unset |
| `whisper_model` | One of `large-v3` (default), `large-v3-turbo`, `distil-large-v3.5` |
| `transcribe_backend` | One of `faster_whisper` (default), `whisper_cpp`, `parakeet` |
| `auto_chapters_enabled`, `hallucination_detect_enabled` | Post-process toggles |

Full reference: [docs/CONFIG.md](docs/CONFIG.md).

---

## Architecture (one paragraph)

The Tk GUI runs in the main process. Each transcription job runs in
a long-lived subprocess worker that holds the Whisper model in
memory and talks back to the GUI via newline-delimited JSON over
stdin/stdout. yt-dlp runs as its own subprocess per download. A
per-worker UUID token and 5-second heartbeat keep IPC routing
robust against PID recycling and wedge-detection.

```
Tk App  ── JSON stdio ──►  Worker subprocess (faster-whisper)
        ── subprocess  ──►  yt-dlp.exe
```

Visuals: [docs/architecture.svg](docs/architecture.svg) (full
diagram) · [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (prose).

---

## Documentation

| Doc | Audience |
|---|---|
| [INSTALL.md](docs/INSTALL.md) | End-user install + troubleshooting |
| [BUILD.md](docs/BUILD.md) | Build the three deliverables yourself |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Process model + threading + protocols |
| [CONFIG.md](docs/CONFIG.md) | Every config key with defaults |
| [RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md) | How to ship a new version |
| [CHANGELOG.md](docs/CHANGELOG.md) | Version history |
| [DECISIONS.md](docs/DECISIONS.md) | Non-obvious design choices + why |

Newer audit + roadmap docs:

- [SENIOR_REVIEW_2026-05-21.md](docs/SENIOR_REVIEW_2026-05-21.md)
- [EXECUTION_ROADMAP.md](docs/EXECUTION_ROADMAP.md)
- [FINAL_FREEZE_AUDIT_2026-05-21.md](docs/FINAL_FREEZE_AUDIT_2026-05-21.md)
- [roadmap/](docs/roadmap/) — future-release research

---

## Build from source

```cmd
git clone https://github.com/Milomilo777/whisper_project_direct_download_v2.git
cd whisper_project_direct_download_v2
pip install -r requirements.txt
python gui.py
```

See [docs/BUILD.md](docs/BUILD.md) for the three build pipelines and
[docs/RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md) for the ship
sequence.

---

## Status

Stable at v1.0.3. The full audit + freeze-readiness review is in
[docs/FINAL_FREEZE_AUDIT_2026-05-21.md](docs/FINAL_FREEZE_AUDIT_2026-05-21.md);
the multi-day stability audit is in
[docs/STABILITY_AUDIT_2026-05-23.md](docs/STABILITY_AUDIT_2026-05-23.md).

Quality bars at v1.0.3:

- pyright `app/ core/` — 0 errors, 0 warnings, 0 informations
- unit + integration suite — 551 tests passing
- real-file end-to-end against the SMTV reference clip — 10/10
- transcribe smoke + end-to-end — 7/7

---

## License

This project's own source code is licensed under the **BSD 3-Clause
License** — see the [LICENSE](LICENSE) file for the full text.

Bundled binaries (`ffmpeg`, `ffprobe`, `yt-dlp`), the bundled Python
runtime + packages, and the Whisper model keep their own upstream
licenses — see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for a
summary and what to include when redistributing.
