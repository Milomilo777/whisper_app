# v0.7.0 — Three installation options

This release ships three independent installation methods. Pick the
one that fits your machine and your priorities — they're all built
from the same source on the same branch
(`release/v0.7.0-installer-3-options`).

## Pick one

| | **Portable** | **Setup-Compact** | **Setup-Standard** |
|---|---|---|---|
| Asset | `WhisperProject-v0.7.0-Portable.exe` | `WhisperProject-v0.7.0-Setup-Compact.exe` | `WhisperProject-v0.7.0-Setup-Standard.exe` |
| Size on disk | 190.8 MB | 137.2 MB | 153.6 MB |
| Install step | none — double-click | silent ~20 s | silent ~45 s |
| Start-up | ~6 s (every launch unpacks) | ~3 s | ~3 s |
| Disk footprint after install | n/a (runs from %TEMP%) | ~470 MB | ~660 MB |
| AV exposure | onefile binaries trigger more false positives | lower | lowest (real CPython on disk) |
| Source-tree visibility for debug | none | none (PyInstaller-bundled) | full — every `.py` is readable |
| Best for | one-off use, USB sticks, easy hand-off | most Windows users | developers and the AV-paranoid |

## What's new in 0.7.0

- **Three install methods, one source.** v0.7.0 is the first release
  to publish Portable + Compact + Standard side by side.
- **Supreme Master TV download** (Session 11). Paste any
  `/v/<id>.html` episode URL into the Download tab to pull the page's
  HD 1080p / 720p / 396p MP4 or its direct MP3. Multi-part series get
  a "Download all parts" checkbox; the page transcript saves as
  `<base>.txt` next to the media.
- **Per-method clean-machine verification.** Every artefact in this
  release was tested by silent-installing to a clean temp location
  on a Windows machine and running the real-video transcribe smoke
  test from that location.

## How to choose

- **One-off transcription** or running off a USB stick → **Portable**.
- **Daily driver, normal Windows machine** → **Setup-Compact**. Best
  start-up time and disk footprint.
- **Developer machine** or you want to inspect what's actually
  running → **Setup-Standard**. The full Python source tree lives
  on disk under the install dir and is open to read or patch.

## Whisper model

Unchanged from v0.6.0: the 3 GB faster-whisper-large-v3 model is
fetched from a CDN mirror on first launch and cached under
`%LOCALAPPDATA%\WhisperProject\Cache\models\`. No internet needed
for transcription after that.

## Tested on

- Windows 10 x64 (build 19045)
- Windows 11 x64 (assumed equivalent — the build matrix has no
  Windows-version-specific code paths)
- Real-video smoke: `E:\3029-NWN-Daily-Scroll-2m_0002.mp4` (60 s
  English news clip) transcribed end-to-end on all three install
  flavours, producing byte-identical SRT (860 B) and JSON (1117 B).

## Post-release audit (2026-05-20, refresh)

After the initial v0.7.0 cut, a deep audit pass over the entire
codebase shipped these corrections under the same tag:

- **Atomic SRT/JSON writes.** Each transcription writer now goes
  through `<path>.part` → `os.replace`, so a process killed
  mid-write can no longer leave the user with a half-written
  subtitle file. (`core/transcriber.py::_write_outputs`)
- **Type-level cleanup of the App class.** The 23 attributes the
  tab builders assign post-construction (`fv`, `pb`, every
  `*_var`, every `*_combo`, `tree`, `download_tree`, `_smtv_*`,
  `history`, `txt`, …) are now forward-declared on the class.
  Pyright went from 135 errors to 0 across `app/` and `core/`.
- **Format-service state reset.** Switching from an SMTV URL to a
  non-SMTV URL now clears `app._smtv_episode` and hides the
  "Download all parts" checkbox during the new lookup, closing a
  small UI race.
- **Graceful worker shutdown.** `TranscriptionService.stop_worker`
  now waits up to 2 s after writing the `shutdown` command before
  falling through to `terminate()`, so the worker's final stdout
  events aren't truncated.
- **Defensive `emit()` in the worker.** If a future caller passes
  a non-serialisable payload, the JSON-stdio protocol still emits
  something (with a `_emit_warning` marker) instead of silently
  swallowing the event.
- **Project metadata fix.** `pyproject.toml` version was 0.3.0 even
  though the project shipped 0.6.x then 0.7.0; now bumped.

Plus two new regression tests under
`tests/core/test_transcriber_helpers.py` pin the atomic-write
contract, and a new live-network E2E suite under
`tests/smoke/test_smtv_download_e2e.py` exercises the **full SMTV
download path** against the real CDN: it scrapes a live episode,
streams a real MP4 to a temp dir, verifies the bytes carry a real
``ftyp`` MP4 box, confirms the page transcript landed as
``<base>.txt`` alongside, validates the `done_full` event payload
that auto-transcribe-after-download keys on, and a second test
proves cancellation cleans up the ``.part`` + final file. This
closes the previous gap where the SMTV pipeline was only tested
against HTML fixtures + a CDN HEAD — never with a real download.
Unit + smoke now: 164 unit + 6 SMTV-related smoke passes.

All three deliverables were rebuilt and clean-machine-tested
end-to-end:

| Method | Smoke | Notes |
|---|---|---|
| Portable | 3 passed | transcribed real video, byte-identical SRT |
| Setup-Compact | 2 passed, 1 skipped | size check N/A for onedir |
| Setup-Standard | 2 passed, 1 skipped | size check N/A for embeddable Python |

Source-of-truth commit for this refresh: `5f7c141`.

## UX refresh (2026-05-20, second refresh)

After the audit, a second pass focused on a recurring user
complaint: "the app finishes but it's not obvious — no notification,
no visible output file path". Eight surgical UI changes:

- **Last Result card** on the Transcribe tab. After every
  transcription, shows the input filename, every output file
  (.srt / .json / .vtt / .tsv / .txt / .lrc) with size and a
  per-file **Open** button, plus a single **Open folder** button.
- **Status icons** in the Queue table (`✓ ▶ ⋯ ⊘ ✗ ⏸`) — glanceable
  state without reading the word.
- **Double-click a finished Queue row** to open its folder.
- **Window title shows progress** — `"Whisper — 34% transcribing
  foo.mp4"` when busy, idle when not. Visible in taskbar / Alt-Tab.
- **Bell on completion** + new `View → Chime on completion` toggle.
- **About dialog** gains version + GitHub URL.
- **Empty-state hints** in the Queue tab and Last Result card.
- **Friendlier text** at the most-confusing user touchpoints
  (model-required prompt, download finish line, "pick a file
  first" guidance).

Source-of-truth commit for the UX refresh: `bfd067a`.

## Major feature push (2026-05-20, third refresh — gap-closing)

After the UX refresh, a focused push closed four of the five
priorities flagged in `GAPS_AGAINST_PEERS_2026.md`:

### Speaker diarization (Priority 1, ✓)

Identify who's speaking. Toggle on the Transcribe tab ("Identify
speakers (diarization)") — no HuggingFace token required. The
pipeline is sherpa-onnx + pyannote-segmentation-3.0 + 3D-Speaker
CAMPlus EN voxceleb, all ONNX, runs on the same onnxruntime we
already ship for VAD. Bundle weight: +35 MB of ONNX models + a
small wheel. Real-tested end-to-end on a 60 s news clip — 3
speakers detected, labels propagate into SRT (`Speaker 00: …`),
JSON (`{..., "speaker": "Speaker 00"}`), Markdown (`_Speaker 00:_`),
and DOCX (bold speaker prefix).

### In-app transcript viewer (Priority 2, ✓)

`Help → Open transcript viewer…` opens a split-pane Toplevel with:

- A clickable segment table (Time / Speaker / Text), type-as-you-
  search filter, and double-click to seek.
- An embedded media player when VLC is installed on the system
  (python-vlc binds libvlc.dll). Gracefully falls back to "Open
  in system player" if libvlc isn't present.
- A "View transcript" button on the Last Result card after every
  finished transcription — one click into the viewer.

### DOCX + Markdown export (Priority 3, ✓)

Two new writers:

- `core/writers/docx_writer.py` — python-docx-backed. Heading +
  meta line + one paragraph per segment with bold `[HH:MM:SS]`
  prefix and bold speaker. Binary-mode write path in the
  transcriber atomic-rename harness.
- `core/writers/md.py` — pure stdlib. Markdown with title heading,
  `**HH:MM:SS**` timestamps, optional `_Speaker N:_` italics.

Both extend the `output_formats` config — pick any combination of
`srt`, `vtt`, `tsv`, `txt`, `json`, `lrc`, `md`, `docx`.

### System-wide dictation hotkey (Priority 4 — deferred)

XL effort that warrants its own session. Full design sketch
recorded in `docs/ROADMAP.md` §5.1b — global hotkey + audio
capture + real-time inference + text injection + system tray
icon. Next session can pick it up cleanly.

### GitHub Actions CI (Priority 5, ✓)

`.github/workflows/ci.yml` runs Pyright + the unit suite (164 →
197 tests) on every push and PR. Matrix: Windows + Ubuntu,
Python 3.11 + 3.12. Ubuntu wraps pytest in `xvfb-run` so the
Tk-touching tests can find a display server. Coverage report
uploads as an artifact on the Ubuntu 3.12 leg.

### UX adds along the way

- Drag-and-drop one or many files (or a URL) into the window.
- Recent files submenu under File, populated from history.db.
- Window geometry persistence — reopens at the same size and
  position as last close.
- Multi-file Browse… — selecting many files enqueues them all.
- Keyboard shortcuts: `Ctrl+O` Browse, `Ctrl+Enter` Transcribe,
  `Esc` Cancel running, `Ctrl+Q` Exit.

### Asset size impact

|                | Pre-push   | This refresh |
|----------------|-----------:|-------------:|
| Portable       | 190.8 MB   | **241.7 MB** |
| Setup-Compact  | 137.2 MB   | **182.1 MB** |
| Setup-Standard | 153.6 MB   | **200.2 MB** |

Growth driven by the ONNX diarization models (~35 MB) plus
sherpa-onnx + python-docx + tkinterdnd2 + python-vlc binding
weight (~15 MB net). All three still well under the original
400 MB upper bound.

Source-of-truth commits for this refresh: `cb4e1a0` (writers)
through `9137e57` (CI xvfb fix).

## Hands-off polish push (2026-05-20, fourth refresh)

The final refresh under the `release/v0.7.0-installer-3-options`
branch shipped every item still open in
`docs/HANDOFF_NEXT_SESSION.md`. Highlights:

### Backends (A2)

A pluggable `core/backends/` package now sits between the
transcriber dispatcher and the underlying engine. `faster_whisper`
remains the default; **whisper.cpp** is opt-in via pywhispercpp on
quantised ggml models — much smaller (~1.1 GB for large-v3-q5_0)
and runs on weaker CPUs that struggle with the float16 path. The
Advanced dialog gains a backend picker + a "Download whisper.cpp
model..." button that fetches the model into
`%LOCALAPPDATA%\WhisperProject\Cache\whisper_cpp\`.

### Word-level alignment (A3)

`config["alignment"] = "stable_ts"` runs a DTW pass via stable-ts
after the main transcribe, refining word timestamps to ±50 ms.
Opt-in; faster_whisper installs that don't enable it skip the dep
entirely.

### Viewer polish (B1 + B2)

The in-app transcript viewer now supports:

- `Ctrl+F` find-and-replace, case-insensitive by default
- Right-click → "Rename speaker (everywhere)..."
- Word-confidence colour coding (green ≥ 0.85 / amber / red)
- One-click "Remove fillers" (uh / um / er / …)
- `Ctrl+S` atomic save through the JSON writer
- Karaoke-style word highlight following the VLC playhead

### System tray + native toast + HiDPI (C1, C2, C3)

`app/widgets/tray.py` runs the tray icon on a daemon thread;
right-click menu Show / Hide / Exit. Icon flips colour when work
is running. `config["minimise_to_tray"]` redirects window-close to
hide-window. Completed jobs raise a native toast via
`pystray.Icon.notify` so background runs are visible. Tk scaling
is now computed from system DPI on launch so fonts and paddings
stop shrinking on 150 % displays.

### Filename templating (A1)

The pre-existing `output_filename_template` key is finally wired
in. Tokens `{base} {ext} {lang} {date} {speaker_count}` resolve
at write time; sibling subdirectories
(`transcripts/{base}.{ext}`) auto-create on demand.

### Opt-in telemetry (C4)

Sentry crash reporting and a one-shot launch ping are now gated
on `config["telemetry_opt_in"]` (Advanced dialog checkbox). Both
additionally require their respective env vars — without `$SENTRY_DSN`
or `$WHISPER_TELEMETRY_URL` nothing is sent. The ping carries only
`{os, version, python, anonymised_id}`; the id is a SHA-256 of a
one-shot UUID stashed under `user_cache_dir()/telemetry_id`.

### Crash auto-resume (D1)

On launch, rows that were `running` in the previous run get
flagged `interrupted`. The new boot-time prompt offers to
re-enqueue the still-existing files.

### Per-folder `.whisperproject.json` (D2)

`core.config.merge_project_overrides` walks up from each
transcribed file and overlays the closest `.whisperproject.json`
on top of the global config. Lets a user keep "this folder always
uses these output_formats / hotwords / etc." without sharing those
keys across the whole machine.

### Watched-folder UI wiring (G4 leftover)

`core.watcher.FolderWatcher` is wired through the Advanced dialog.
Media files dropped into the configured folder are stability-checked
(size stable for 1.2 s) then auto-enqueued.

### Explorer right-click verb (E1)

Both `installer.iss` and `installer_embed.iss` now ship an
optional `shellext` task that writes the registry entries under
`HKCR\*\shell\WhisperProjectTranscribe`. Hits the existing CLI
mode (`WhisperProject.exe transcribe "%1"`).

### Test suite growth

Hermetic unit suite: 197 → **246 passing**. New tests cover the
backend dispatcher + segment normalisation, alignment, tray
helpers, observability gates, project-override merge, filename
templating, and every viewer edit operation.

## Known limitations

- **SmartScreen warning.** None of the three exes are code-signed.
  First-launch shows the standard "Windows protected your PC"
  prompt; click **More info → Run anyway**.
- **First launch is slow on Method A.** Portable unpacks ~190 MB
  to `%TEMP%\_MEI<random>\` on every launch. Methods B and C unpack
  once at install time.
- **Method C uninstall leaves behind any user-edited file under
  the install directory.** The Inno script sweeps `__pycache__` and
  the install subdirectories on uninstall, but it cannot know about
  files a curious user might have added.

## Build and contribute

See [docs/BUILD.md](BUILD.md) for the three build pipelines and
[docs/ROADMAP.md](ROADMAP.md) for where the project is heading.
