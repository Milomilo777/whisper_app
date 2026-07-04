# Whisper Project

> 📍 **Start at [`PROJECT_INDEX.md`](PROJECT_INDEX.md)** — a generated, tool-neutral repo map for fast, low-token onboarding by any AI agent or human.

[![CI](https://github.com/Milomilo777/whisper_app/actions/workflows/ci.yml/badge.svg)](https://github.com/Milomilo777/whisper_app/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/Milomilo777/whisper_app?label=release)](https://github.com/Milomilo777/whisper_app/releases/latest)
[![codecov](https://codecov.io/gh/Milomilo777/whisper_app/graph/badge.svg)](https://codecov.io/gh/Milomilo777/whisper_app)

**A Windows desktop app that transcribes audio and video files locally
using OpenAI's Whisper model.** Drag a file in, get back `.srt`,
`.vtt`, `.json`, `.docx`, `.pdf`, and more (a "Convert transcript"
picker adds oTranscribe/ELAN/InqScribe and other formats on demand).
No cloud, no account, no upload. Also downloads from any site `yt-dlp`
supports.

Two deliverables for two audiences (replace `X.Y.Z` with whatever
[the latest release](https://github.com/Milomilo777/whisper_app/releases/latest)
actually is):

| Method | Asset | Size | Best for |
|---|---|---|---|
| **Portable** | `WhisperProject-vX.Y.Z-Portable.zip` | ~340 MB | unzip and run, no install, USB-stick friendly |
| **Standard** | `WhisperProject-vX.Y.Z-Setup-Standard.exe` | ~230 MB | proper installer — Start-menu shortcut, files live on disk, Python visible for debugging |

Download from the latest release:
**[github.com/Milomilo777/whisper_app/releases/latest](https://github.com/Milomilo777/whisper_app/releases/latest)**

Step-by-step install guide: [docs/INSTALL.md](docs/INSTALL.md).

---

## What it does

- **Transcribe** — drag-and-drop one or many files. Optional: Voice
  Activity Detection, word-level timestamps, speaker diarisation.
  Outputs land next to your input in `srt`, `vtt`, `tsv`, `txt`,
  `json`, `lrc`, `md`, `docx`, `pdf` — plus a separate "Convert
  transcript" picker that re-emits any existing transcript file into
  those formats or into oTranscribe/ELAN/InqScribe/Express Scribe.
- **Last-Result card** — every finished transcription opens a card
  with file sizes, one-click "Open file" buttons, an "Open folder"
  shortcut, and a "View transcript" button that launches the in-app
  viewer (split-pane, click-to-seek, embedded VLC playback when
  available).
- **Download Videos** — paste any URL `yt-dlp` supports OR any
  Supreme Master TV episode link, pick a format, save to your
  folder. Optionally auto-transcribe after the download.
- **Transcription Queue** — live status of pending + running jobs.
  An always-visible action bar under the list gives every task a
  one-click **Pause / Resume / Cancel / Re-run / Remove** (buttons
  enable for the selected row's state); a single click on a running
  or paused row's status/progress cell toggles pause/resume. The same
  actions stay on the right-click menu, and `Esc` still cancels the
  running job. Double-click a finished row to jump to its folder.
- **Download Videos action bar** — the same per-task controls under the
  download list: **Pause / Resume / Cancel / Re-run / Remove / Open**.
  Because `yt-dlp` has no live pause signal, download **Pause is
  "stop-and-continue"**: it stops the download but keeps the partial
  file, and Resume continues from where it left off (via `yt-dlp`'s
  `-c`/`--continue`) instead of restarting. Pause is unavailable for
  Supreme Master TV downloads, which have no resume point.
- **Video Tiling** — play one live stream as a full-screen N×N grid (a
  "video wall") of identical tiles. One stream is downloaded once and
  tiled; pick a quality band (Auto/1080p…/144p), mute, and — across
  several monitors — a **Multi-monitor** wall with one window per screen
  (use **Monitors…** to choose screens, with **Identify** to flash each
  monitor's number). Reconnect is automatic with exponential backoff, and
  yt-dlp self-heals (updates) after repeated drops. Needs `ffplay` on PATH
  or in the app's `bin/` folder (it is not bundled).

Keyboard: `Ctrl+O` Browse · `Ctrl+Enter` Transcribe · `Esc` Cancel ·
`Ctrl+Q` Exit.

First launch downloads the ~3 GB Whisper model from a CDN mirror.
Everything after that is fully offline.

---

## First-run setup — the Model Hub Folder

On the first launch, the app asks where to store the Whisper model
files via a folder-picker dialog. The default suggestion is a private
per-user cache folder, `%LOCALAPPDATA%\WhisperProject\Cache\models`, which
is always writable (never the Program Files install dir); the user can
pick any location (an external drive, a network share, etc.). The
choice is persisted to `%LOCALAPPDATA%\WhisperProject\config.json`
under the `hub_folder` key and the dialog never asks again.

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
| `transcribe_backend` | One of `faster_whisper` (default), `whisper_cpp`, `parakeet`, `cloud_stt`, `google_cloud_stt` |
| `auto_chapters_enabled`, `hallucination_detect_enabled` | Post-process toggles |
| `update_check_enabled` | Opt-in GitHub "update available" check (on by default; notify-only, never auto-downloads) |
| `last_update_check` | ISO date of the last quiet update check (once-per-day throttle) |

Full reference: [docs/CONFIG.md](docs/CONFIG.md).

### Optional cloud backend (uploads your audio)

There are two **opt-in, non-offline** backends, both set in
**Advanced > Backend**. Each **breaks the offline guarantee** — use them
only for content you may send to a cloud service. All default backends
remain fully offline.

- `cloud_stt` — Google **Gemini API**, authenticated with a free API key
  you paste. Quickest setup. Details:
  [docs/CLOUD_STT.md](docs/CLOUD_STT.md).
- `google_cloud_stt` — the full **Google Cloud Speech-to-Text** service,
  authenticated with a service-account JSON file you download. Gives 60
  free minutes/month, speaker labels, and a cheaper batch mode. Details:
  [docs/CLOUD_STT_GOOGLE.md](docs/CLOUD_STT_GOOGLE.md).

---

## Updating to a newer version

**In-place upgrade — no uninstall needed.** The Standard installer uses a
stable application ID, so to move to a newer version you simply download
the new `...-Setup-Standard.exe` and run it; it upgrades over the existing
install (keeping your Start-menu shortcut and settings). You do **not** need
to uninstall the previous version first. The Portable build is self-contained
— just replace the old folder/EXE with the new one.

**Optional update check.** The app can check GitHub for a newer release.
It is **opt-in** (on by default, toggle `update_check_enabled`) and
**notify-only**: it never downloads or installs anything. A quiet check
runs at most once per day on launch and stays silent unless a newer
version exists; if one does, it offers to open the download page in your
browser. **Help → Check for updates...** runs the same check on demand
and also tells you when you're already up to date. The check fails
silently when offline (nothing is shown).

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

### Optional: share it on your local network

Instead of installing the app on every machine, you can let people on a
trusted network transcribe through a browser. The easiest way is the
**Web / LAN access** tab in the app: one button turns it on/off, with an
optional port, a "Share on local network" checkbox, and an optional access
password — all explained in plain language right on the tab.

For headless / scripted use there is an equivalent command-line server
(same stdlib-only HTTP engine):

```cmd
python gui.py serve          REM loopback only (no firewall prompt)
python gui.py serve --lan    REM share on the LAN (allow the firewall prompt)
```

See [docs/SERVER.md](docs/SERVER.md) for the one-click toggle, routes, the
upload cap, the optional password / `--token`, and the trusted-network
security caveats.

---

## Documentation

| Doc | Audience |
|---|---|
| [INSTALL.md](docs/INSTALL.md) | End-user install + troubleshooting |
| [SERVER.md](docs/SERVER.md) | Optional local-network / web server mode (`gui.py serve`) |
| [BUILD.md](docs/BUILD.md) | Build the three deliverables yourself |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Process model + threading + protocols |
| [CONFIG.md](docs/CONFIG.md) | Every config key with defaults |
| [CLOUD_STT.md](docs/CLOUD_STT.md) | Optional Gemini-API cloud backend (paste a key) |
| [CLOUD_STT_GOOGLE.md](docs/CLOUD_STT_GOOGLE.md) | Optional Google Cloud Speech-to-Text backend (service-account JSON, batch mode) |
| [RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md) | How to ship a new version |
| [CHANGELOG.md](docs/CHANGELOG.md) | Version history |
| [DECISIONS.md](docs/DECISIONS.md) | Non-obvious design choices + why |

Newer audit + roadmap docs:

- [SENIOR_REVIEW_2026-05-21.md](docs/history/SENIOR_REVIEW_2026-05-21.md)
- [EXECUTION_ROADMAP.md](docs/history/EXECUTION_ROADMAP.md)
- [FINAL_FREEZE_AUDIT_2026-05-21.md](docs/history/FINAL_FREEZE_AUDIT_2026-05-21.md)
- [roadmap/](docs/roadmap/) — future-release research

---

## Build from source

```cmd
git clone https://github.com/Milomilo777/whisper_app.git
cd whisper_app
pip install -r requirements.txt
python gui.py
```

See [docs/BUILD.md](docs/BUILD.md) for the build pipelines (which two
are actually shipped vs. optional) and
[docs/RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md) for the ship
sequence.

---

## Status

Actively maintained; see the CI badge above for live build status and
[docs/CHANGELOG.md](docs/CHANGELOG.md) for what shipped recently.
Earlier freeze/stability audits are archived under
[docs/history/](docs/history/) once superseded by newer work.

Quality bar enforced on every commit:

- pyright `app/ core/` — 0 errors, 0 warnings, 0 informations
- the hermetic unit + integration suite (`pytest tests/
  --ignore=tests/smoke`) runs on every push on both Windows and
  Ubuntu — see [docs/TESTING.md](docs/TESTING.md)

---

## Contributing

Issues, PRs, and [Discussions](https://github.com/Milomilo777/whisper_app/discussions)
are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the dev setup,
quality bar, and PR conventions, and look for issues labeled
[`good first issue`](https://github.com/Milomilo777/whisper_app/labels/good%20first%20issue)
if you're new here. This project follows the
[Contributor Covenant](.github/CODE_OF_CONDUCT.md).

---

## Author

Written by **translation-robot** — <https://github.com/translation-robot>.

## License

This project's own source code is licensed under the **BSD 3-Clause
License** — see the [LICENSE](LICENSE) file for the full text.

Bundled binaries (`ffmpeg`, `ffprobe`, `yt-dlp`), the bundled Python
runtime + packages, and the Whisper model keep their own upstream
licenses — see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for a
summary and what to include when redistributing.
