# Handoff for the next hands-off session

Branch is `release/v0.7.0-installer-3-options`. Built artifacts on
the v0.7.0 GitHub release are in sync with the branch HEAD.

The next session is hands-off — pick up exactly where this one
stopped, ship the remaining items at the same quality bar, real-
test, push, refresh the release.

## Where things stand

### Done in Sessions 12 + 13 + this session

  ✓ Diarization (sherpa-onnx, no HF token)
  ✓ In-app transcript viewer (split-pane + python-vlc fallback)
  ✓ DOCX + Markdown + PDF writers
  ✓ Drag-and-drop (tkinterdnd2)
  ✓ Recent files menu (history.db)
  ✓ Window geometry persistence
  ✓ Multi-file Browse...
  ✓ Keyboard shortcuts (Ctrl+O, Ctrl+Enter, Esc, Ctrl+Q)
  ✓ Last Result card with View transcript + Burn subtitles +
    Open folder buttons
  ✓ Queue row icons (✓ ▶ ⋯ ⊘ ✗)
  ✓ Queue row double-click → open folder
  ✓ Queue right-click → Burn subtitles
  ✓ Window title shows live progress
  ✓ Chime on completion + View menu toggle
  ✓ About dialog with version + GitHub URL
  ✓ Empty-state hints on Queue + Last Result
  ✓ Friendlier user-facing strings
  ✓ Per-file language picker on Transcribe tab
  ✓ Device picker (auto/cpu/cuda)
  ✓ Compute-type picker (int8/int8_float16/float16/float32)
  ✓ Inline hotwords entry
  ✓ YouTube/HTTP URL detection on Transcribe-tab file field
  ✓ CLI mode (`gui.py transcribe FILE`)
  ✓ Watched-folder watcher class (UI hook still pending — see
    "G4 leftovers" below)
  ✓ ffmpeg burn-subs helper + Queue right-click integration
  ✓ Atomic SRT/JSON writes (Session 12 audit)
  ✓ App typed attribute block (135 pyright errors → 0)
  ✓ History-narrowed access pattern
  ✓ Graceful worker shutdown
  ✓ JSON-stdio worker defensive emit fallback
  ✓ SMTV E2E live-network test
  ✓ Live SMTV download test
  ✓ GitHub Actions CI (Win + Ubuntu × py3.11+3.12, xvfb on Linux)
  ✓ CODE_OF_CONDUCT.md + issue templates + PR template
  ✓ tests/fixtures/sample.wav (1 s 16 kHz silence, generator
    script committed too)
  ✓ Coverage + CI badges in README
  ✓ English-only scope correction

### Remaining work, in priority order

Each entry below has: status, effort estimate, design sketch
concrete enough that a next-session agent can start coding
immediately.

#### A1. Filename / directory templating (S, easy win)

Config key `output_filename_template` already exists with
default `"{base}.{ext}"`. Tokens to support: `{base}`, `{ext}`,
`{lang}`, `{date}`, `{speaker_count}`.

  - **Where to wire**: `core/transcriber.py::_write_outputs`
    builds `path = f"{base}.{ext}"`. Replace with a template
    expansion via `string.Formatter` or `.format_map`.
  - **Pass extra fields** to `_write_outputs` (language,
    detected speaker count) — both are available in the
    `info` object + diarisation result.
  - **Test**: extend `tests/core/test_transcriber_helpers.py`
    with a template-substitution test using a mock.

#### A2. Alt engine — whisper.cpp via pywhispercpp (L)

The user explicitly wants all free alternative engines. The
biggest single win is whisper.cpp because it unlocks q4/q5
quantised models on weak CPUs.

  - **pip dep**: `pywhispercpp>=1.4`. Bundles libwhisper natively
    (~ 10 MB).
  - **Backend abstraction** to add:
    ```
    core/backends/__init__.py     get_backend(name) -> Backend
    core/backends/base.py          class Backend (ABC):
                                     load_model() -> bool
                                     transcribe(task, ...) -> None
                                     unload_model() -> None
    core/backends/faster_whisper_be.py   thin wrapper over the
                                          existing core.transcriber
    core/backends/whisper_cpp.py   pywhispercpp wrapper
    ```
  - `core/transcriber.py::transcribe` becomes a dispatcher that
    reads `config["transcribe_backend"]` and routes.
  - Add a backend picker in the Advanced dialog (already config
    default exists: `"transcribe_backend": "faster_whisper"`).
  - **Models**: ggml-large-v3-q5_0.bin (~ 1.1 GB; user must
    download via a "Download whisper.cpp model" button in the
    Advanced dialog the first time they pick that backend).
  - **Real test**: route the existing
    `tests/smoke/test_exe_real_e2e.py` through the new backend
    by setting `transcribe_backend=whisper_cpp` in config and
    spawning the worker.

#### A3. Alt engine — stable-ts for word-level alignment (M)

`stable-ts` is a drop-in replacement for `whisper.transcribe`
that produces ±50 ms word timestamps via DTW. It works on top
of `faster-whisper` so no new backend per se — just a flag.

  - **pip dep**: `stable-ts>=2.17`.
  - **Wire**: in `core/transcriber.py`, when
    `config["alignment"] == "stable_ts"`, post-process the
    Whisper segments via
    `stable_whisper.refine_word_timestamps(...)`. Stash the
    refined word timestamps in `segments_data[i]["words"]`.
  - **UI**: a third option on the device-row dropdown: alignment
    {none, stable-ts}. Default none.
  - **No backend abstraction needed** — this is a post-processor.

#### A4. Alt engines — defer with reasoning (XL each)

The following are real but out of scope for any single session.
ROADMAP §6 already covers them. Don't start unless the user
explicitly prioritises one:

  - **WhisperX**: 700 MB PyTorch + pyannote pipeline. We
    already have sherpa-onnx diarisation; the gain is
    word-level alignment which A3 above gives more cheaply.
  - **Insanely-Fast-Whisper**: GPU-only, BetterTransformer +
    FlashAttention-2. Only useful on a CUDA setup; would need
    a config gate.
  - **NeMo Parakeet / Canary**: 600 MB NVIDIA NeMo dep. Real
    multilingual gain but heavy. The English-only scope makes
    it lower-priority than whisper.cpp.
  - **SenseVoice (Alibaba)**: Chinese-focused; out of scope for
    English-only.
  - **Demucs voice separation**: pre-processor. Heavy PyTorch
    dep. Useful only on noisy / music-heavy content.

#### B1. Viewer enhancements (M, queued separately)

Right-now the in-app viewer (`app/dialogs/transcript_viewer.py`)
has: segment table, search filter, click-to-seek (when VLC up),
"Open in system player" fallback. Pending items:

  - **Find-and-replace** dialog on Ctrl+F → opens an entry +
    "Find next" + "Replace" + "Replace all" buttons. Operates
    on segment text in-memory; on Save Changes button writes
    back to the JSON via `core/writers/json_writer.write`.
  - **Speaker rename (global)**: right-click on a "Speaker 00"
    cell → "Rename..." → input dialog → updates every segment
    with that speaker → saves the JSON.
  - **Word-confidence colour coding**: when a segment carries
    `words` with `probability`, colour the segment row's text
    by min/max probability across the words (green ≥ 0.85,
    yellow 0.6–0.85, red < 0.6). Use Treeview tags.
  - **Filler-word remove tool**: button in the viewer toolbar
    that runs a regex over all segments removing common
    fillers (`uh`, `um`, `er`, `eh`, `like`, …) from segment
    text, then re-saves the JSON.

#### B2. Karaoke-style word highlight (M, needs B1's word
data and a click-to-seek wired to VLC)

When VLC is playing and the segment list scrolls past words,
highlight the active word. Needs:

  - The viewer's VLC player to emit a position-tick (already
    has `_update_position` every 250 ms).
  - A method that finds the current word given the playhead
    position and the segment's `words` list, then re-renders
    the active segment cell with a highlight tag.
  - This is the killer Descript-like feature; it needs the
    polish of B1 first.

#### C1. System tray icon + minimise-to-tray (M)

Already added `pystray>=0.19` + `Pillow>=10.0` to
requirements.txt. Not wired.

  - **Where**: `app/widgets/tray.py` new module with a
    `TrayController` class.
  - **API**:
    ```
    class TrayController:
        def __init__(self, app):  ...
        def start(self):          ...   # daemon-thread the icon
        def stop(self):           ...
    ```
  - **Behaviour**: tray icon mirrors the recording / idle state
    (blue → idle, red dot → active job). Right-click menu:
    Show / Hide / Exit. WM_DELETE_WINDOW handler in app.py
    should optionally minimise-to-tray instead of exit when a
    config flag is on (default off).

#### C2. Toast notifications on completion (S)

Already `chime` (system bell) on completion. Native Windows
toast adds visibility when the app is minimised.

  - **pip dep**: `winsdk` or `winrt-Windows.UI.Notifications`.
    Or use `pystray.Icon.notify(...)` — already bundled.
  - **Wire**: in `App.show_last_result`, after the bell call,
    also call `tray_controller.notify(title, body)` when the
    tray controller exists.

#### C3. High-DPI scaling (XS)

One line at App.__init__:

    self.tk.call("tk", "scaling", 1.5)

…or compute from `self.winfo_fpixels("1i")` divided by 72.
Test on a 150 % Windows display.

#### C4. Sentry crash reporting + opt-in telemetry (S)

  - `sentry-sdk` is in pyproject.toml optional-deps; uncomment.
  - `app/observability.py::init_sentry()` already exists; add a
    config gate (`telemetry_opt_in`) so it's strictly opt-in.
  - Anonymous telemetry: one POST per launch with
    `{os, version, anonymized_id}` — gated on the same opt-in.

#### D1. Auto-resume after crash (S)

`history.db.mark_interrupted()` already runs at startup. Build
a prompt at App boot:

  - If `interrupted > 0`, show a dialog
    "We found N transcriptions interrupted by a previous crash.
    Resume them?" with Yes/No.
  - Yes → enqueue the corresponding `file_path`s as fresh
    Transcription tasks.

#### D2. Per-project / per-folder settings (M)

A `.whisperproject.json` file in a folder overrides the global
config when that folder is the source of an enqueued file.
Use `pathlib.Path.parents` to find the nearest
`.whisperproject.json` walking up; merge with the global config.

#### E1. Right-click "Transcribe this" in Explorer (M)

Windows shell extension via a registry entry installed by the
Inno Setup script:

    HKCR\*\shell\WhisperProject\command @= "WhisperProject.exe transcribe \"%1\""

Hits the new CLI mode automatically. The Inno script needs a
`[Registry]` block; only the Setup-Compact and Setup-Standard
methods can ship this (Portable can't register handlers).

#### E2. Other niche video site scrapers (M each)

The SMTV scraper pattern is in `core/integrations/smtv.py`.
Mirror that for any new site:

  - `core/integrations/<site>.py` with `is_<site>_url`,
    `parse_<site>_id`, `fetch_episode`, `best_url_for_mode`,
    `filename_for`, `transcript_filename`.
  - Add hidden-import to both specs.
  - Route in `format_service.lookup_formats` + `download_service._is_smtv_task`-style helper.

#### F1. Live mic transcription (XL — own session)

ROADMAP §5.1c already sketches the system-wide dictation hotkey
version. The simpler "click-a-button-and-talk" version:

  - **pip dep**: `sounddevice>=0.4`.
  - **UI**: "Live transcribe" button on the Transcribe tab that
    spawns a 30 s recording, then runs Whisper on it once. Far
    simpler than full streaming.
  - For real streaming with low latency, use Whisper-Streaming's
    LocalAgreement-n policy. Bigger lift.

## Build pipeline reminders

Three deliverables, all rebuilt by:

```
pyinstaller --noconfirm --clean whisper_project_onefile.spec
pyinstaller --noconfirm --clean --distpath dist_onedir whisper_project_onedir.spec
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer.iss
build_embed_installer.bat
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer_embed.iss
```

Both specs need every new module added to `hiddenimports`. The
embed installer pulls dependencies via the bundled pip-install
step in `build_embed_installer.bat`.

The diarization ONNX models live in `bin/diarization/`
(gitignored). Use `tools/download_diarization_models.bat`
to fetch them on a fresh dev machine before building.

## Tests

  - Unit suite: 191 passing. Run with
    `python -m pytest tests/ --ignore=tests/smoke`.
  - Smoke suite uses real local resources (Whisper model,
    test video at `E:\3029-NWN-Daily-Scroll-2m_0002.mp4`).
    Skip on machines without them.
  - Live SMTV smokes hit the real CDN; skip via
    `WHISPER_OFFLINE_TESTS=1`.

## Release management

The v0.7.0 tag has been force-moved multiple times this and
last session as the underlying bytes evolved. Don't be afraid
to move it again — the user explicitly authorised it. The
process is:

```
git tag -fa v0.7.0 -m "..."
git push --force origin refs/tags/v0.7.0
gh release upload v0.7.0 dist/*.exe dist_installer/*.exe --clobber
gh release edit v0.7.0 --notes-file docs/RELEASE_NOTES_v0.7.0.md
```

## Forbidden actions (still hold from earlier prompts)

  - Don't merge to master.
  - Don't checkout master.
  - Don't push master.
  - Don't touch `.git/config`.
  - Don't run code-signing.
  - English-only — no i18n, no RTL, no Persian section in
    INSTALL.md.

## The 2-line restart prompt

Paste this verbatim to start the next session:

```
ادامه برنچ release/v0.7.0-installer-3-options را پیش ببر طبق docs/HANDOFF_NEXT_SESSION.md — همه آیتم‌های "Remaining work" را به ترتیب با کیفیت بالا پیاده کن، تست واقعی بگیر، کامیت و پوش کن، رلیز را آپدیت کن. هیچ سوالی از من نپرس، تا انتها هندزفری پیش برو.
```
