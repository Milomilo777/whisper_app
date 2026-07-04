# PROJECT INDEX — Whisper Project (offline audio/video to text)

> **Read this first.** Onboarding map for any coding agent (Claude Code, Codex, Cursor, Copilot, …) or human — written so you can understand the repo *without re-scanning it*, saving tokens and time.
>
> Semantic sections built **2026-06-03** by the `project-index` workflow. The Structure block at the bottom is regenerated deterministically (no AI) by `tools/index_refresh.py` — never hand-edit between the AUTO-INDEX markers.

## What it is
Windows desktop app (Tkinter) that transcribes audio/video locally with faster-whisper and downloads media via yt-dlp/Supreme Master TV — fully offline after first-run model download.

A drag-and-drop Windows desktop app that runs OpenAI Whisper locally to turn audio/video files into subtitles and transcripts, with no cloud, account, or upload. Each job writes outputs next to the input in up to nine formats (srt, vtt, tsv, txt, json, lrc, md, docx, pdf) and supports VAD, word-level timestamps, speaker diarisation, auto-chapters, and hallucination detection. It also downloads from any yt-dlp-supported site (plus Supreme Master TV episode links) with optional auto-transcribe, and offers an oTranscribe round-trip, an in-app transcript viewer with VLC playback, a live queue, and a folder watcher. On first launch it downloads a ~3 GB Whisper model from a CDN mirror; everything afterward is offline. Ships as two installers (Portable EXE and Standard Setup) built from a slim embeddable-Python tree.

## Run it
```
Run from source (dev): pip install -r requirements.txt  then  python gui.py
Editable install with extras: pip install -e .[dev]  (optional extras: backend_cpp, alignment, crash_reporting, theme_detection)
CLI one-shot transcription (no UI): python gui.py transcribe PATH\TO\file.mp4 --language en --formats srt json docx
Reset / recover first-run state: python gui.py --safe-mode  (backs up %LOCALAPPDATA%\WhisperProject\config.json and re-fires the hub-folder dialog)
Full local gate (pyright + hermetic unit tests): run_tests.bat  (equivalent to: pyright app core  &&  python -m pytest tests/ --ignore=tests/smoke -q)
Unit tests only: python -m pytest tests/ --ignore=tests/smoke -q  (smoke/E2E under tests/smoke need the real model, a test video, and live network — skip otherwise)
Build deliverables (Windows): build_embed_installer.bat then installer_embed.iss (Standard); Portable is a make_archive ZIP of embed_build\. See docs/BUILD.md for all pipelines.
```

## Architecture
Single Tkinter app process (entry point gui.py -> app.run() -> app/app.py App(tk.Tk)) owns the UI and orchestration; it is the only thread that touches widgets. Background work is bridged into the Tk main loop via queue.Queue instances polled with after(). Two concurrency patterns: (1) Transcription runs in long-lived subprocess workers spawned as `python gui.py --worker` (core/worker.py) so the ~3 GB faster-whisper model loads once and stays hot; the parent and worker speak newline-delimited JSON over stdin/stdout (actions: transcribe/shutdown; events: ready/started/progress/log/done/error/startup_error/worker_exit), with a per-worker UUID token and ~5s heartbeat to survive PID recycling and detect wedges. (2) Downloads run as short-lived yt-dlp.exe subprocesses (one per task), whose stdout is read on a daemon thread, regex-parsed for progress, and pushed onto queues. The app/ package is layered: app/services (download_service, format_service, transcription_service, integrations_service) drive background work; app/domain holds task models (TranscriptionTask, VideoDownloadTask) and language enums; app/widgets builds tabs/console/tray; app/dialogs holds Toplevels (model_download, hub_setup, transcript_viewer, advanced, statistics). The core/ package is the engine: config.py (JSON at %LOCALAPPDATA%\\WhisperProject\\config.json), model_manager.py + hub.py (resumable MD5-verified ZIP model download/extract), transcriber.py with pluggable backends (core/backends: faster_whisper, whisper_cpp, parakeet), pre/post-processing (alignment, diarization, chapters, hallucination, separator, voiceprint), pluggable output writers (core/writers: srt/vtt/tsv/txt/json/lrc/md/otr/docx/pdf), integrations (core/integrations: otranscribe, smtv), and infra (paths, history SQLite, logging_setup, watcher, recorder, _proc, _threads). NOTE: docs/ARCHITECTURE.md still describes an older single-file gui.py layout; the code has since been refactored into the app/ and core/ packages described here.

**Tech stack:** Python >=3.11 (3.11/3.12/3.13), Tkinter + sv-ttk + tkinterdnd2 (drag-and-drop) for the GUI, faster-whisper (CTranslate2) as default transcription backend; optional pywhispercpp (whisper.cpp) and parakeet backends, stable-ts (word-level alignment, opt-in, pulls torch); sherpa-onnx (pyannote ONNX speaker diarisation, no HF token), yt-dlp.exe + bundled ffmpeg/ffprobe for media download and merging, python-vlc for embedded playback; python-docx + reportlab for docx/pdf output, platformdirs, requests, watchdog (folder watcher), pystray + Pillow (system tray), SQLite (history), Tooling: pytest + pytest-cov + responses, pyright (basic mode, 0/0/0 baseline on app/ core/), GitHub Actions CI, Packaging: PyInstaller (.spec files, unshipped) and Inno Setup (.iss) over an embeddable-Python tree; BSD-3-Clause license

## Key docs
| Doc | Covers |
|---|---|
| `README.md` | Product overview, feature list, two-deliverable model, first-run hub-folder setup, config key summary, build-from-source quickstart |
| `CLAUDE.md` | Durable session rules: commit-often/push-batched/slow-release cadence, single master mainline, pre-authorised git/gh ops, English-only scope, pyright 0/0/0 gate; points to SESSION_HANDOFF_NEXT.md as source of truth |
| `docs/SESSION_HANDOFF_NEXT.md` | READ FIRST each session — current state (v1.3.7 published), latest audit results, deferred/known items, and live re-validation steps |
| `docs/ARCHITECTURE.md` | Process/threading model, worker JSON-stdio protocol, queue table, cancellation contract — but written against the older single-file gui.py layout (now refactored into app/ + core/) |
| `docs/CONFIG.md` | Every config.json key with defaults (hub_folder, model_path, whisper_model, transcribe_backend, post-process toggles) |
| `docs/DECISIONS.md` | Architecture Decision Records: why subprocess workers, vendored yt-dlp, MD5 ZIP model distribution, tkinter, SRT+JSON-beside-input |
| `docs/BUILD.md` | The three build pipelines (Portable / Compact / Standard embeddable-Python) and post-build sanity checks |
| `docs/RELEASE_PROCESS.md` | Ship sequence: version bump locations, tagging, gh release create/edit, release pruning policy |
| `docs/CHANGELOG.md` | Version history including the [Unreleased] deep-audit hardening batches (large file — sample, do not read in full) |

## Onboarding tips
- Read docs/SESSION_HANDOFF_NEXT.md FIRST every session — it is the declared source of truth for current state (currently v1.3.7), and CLAUDE.md encodes the workflow rules (commit local + often, push in batches, slow release cadence, single master mainline, never force-push/move published v1.0.3+ tags).
- ARCHITECTURE.md is partly stale: it describes a monolithic gui.py, but the real code lives in the app/ (services/domain/widgets/dialogs) and core/ (backends/writers/integrations/engine) packages. gui.py is now just a thin entry/CLI/worker dispatcher. Trust the package layout over that doc's file map.
- The hard quality gate is run_tests.bat = pyright app core (must be 0 errors/0 warnings/0 informations) plus the hermetic pytest suite (tests/ minus tests/smoke). Run it before any commit; the v1.3.7 baseline is 0/0/0 and must stay green.
- Tests under tests/smoke are NOT hermetic — they need the real ~3 GB Whisper model, a local test video (e.g. E:\3029-NWN-Daily-Scroll-2m_0002.mp4), and live network for SMTV E2E. They are gated by env vars / skipped when resources are absent; do not expect them to run in CI or a clean checkout.
- Transcription is a subprocess worker (`python gui.py --worker`, core/worker.py) that talks line-delimited JSON over stdio — the `--worker` shape is a spawn-contract used by every deliverable; do not rename/remove it. Tkinter is single-threaded: only the after()-driven poll_* methods touch widgets; all background work communicates through queue.Queue.
- When adding a module, update BOTH whisper_project_onefile.spec and whisper_project_onedir.spec hidden-import lists so the unshipped PyInstaller pipelines don't bit-rot, even though only the embeddable-Python Standard + Portable builds are actually published. Heavy backends (whisper.cpp, stable-ts/torch) are lazy-imported, opt-in extras — absence disables the feature without crashing.

## Subsystems

### app-gui — `app/`
The Tkinter desktop GUI for the Whisper Project: a `tk.Tk` App that wires together transcribe/download/queue/tiling tabs, modal dialogs, and background services (yt-dlp downloads, transcription worker subprocesses, format probing, integrations). `gui.py` is the top-level entry point that dispatches to GUI / worker / CLI modes.

**Key files**
- `gui.py` — Top-level entry point with three modes: bare = launch Tk app via app.run(); `--worker` = early-branch into core.worker.main() BEFORE argparse (the spawn-contract — must not rename/remove); `transcribe FILE` = headless CLI; `--safe-mode` = backs up + resets config before GUI launch.
- `app/__init__.py` — Package public surface. Exposes `run()` (launches `App().mainloop()`) and lazily re-exports `App` via module `__getattr__` so importing the package does NOT pull in tkinter / faster-whisper until App is actually requested.
- `app/app.py` — The ~2700-line `App(tk.Tk)` God-class (121KB). Owns the Tk root, per-instance queues, all event Queues, the four services, HistoryDB, menu/tabs/console construction, and the periodic `loop()` pump. Most `*_var`/`*_combo` attributes are forward-declared here but actually assigned later by tabs.py builders.
- `app/observability.py` — Strictly opt-in Sentry crash reporting + anonymous launch telemetry. No-op unless config[telemetry_opt_in] AND the matching env var (SENTRY_DSN / WHISPER_TELEMETRY_URL) are set. Provides init_sentry() and send_launch_ping_async().
- `app/services/transcription_service.py` — TranscriptionService: spawns/restarts/drains long-lived `python -m core.worker` (or `<exe> --worker`) subprocesses over JSON-stdio. Module-level pure `transcribe_command()` builds the JSON dispatched to the worker (test seam for field-crossing-process-boundary bugs).
- `app/services/download_service.py` — DownloadService: builds yt-dlp argv, runs in a daemon thread, posts events on `app.download_events`. Pure module-level helpers `build_subtitle_command` / `build_download_command` are the unit-test seams.
- `app/services/format_service.py` — FormatService: runs `yt-dlp --dump-single-json` in a daemon thread, posts parsed info to `app.format_events`. For Supreme Master TV (SMTV) URLs it bypasses yt-dlp and scrapes via core.integrations.smtv.
- `app/services/integrations_service.py` — IntegrationsService: oTranscribe round-trip (export task SRT to .otr and back) via core.integrations.otranscribe; opens otranscribe.com.
- `app/widgets/tabs.py` — Tab construction extracted from App. `build_transcribe_tab`/`build_download_tab`/`build_queue_tab`/`build_tiling_tab` attach widgets and the `*_var`/`*_combo` attributes ONTO the App instance (side-effecting, return None). Contains the self-hiding _AutoScrollbar.
- `app/widgets/tray.py` — TrayController backed by pystray + Pillow. When config[minimise_to_tray] is on, WM_DELETE_WINDOW hides instead of exits. Silently degrades to a no-op controller if pystray/Pillow import fails.
- `app/widgets/hardware_wizard.py` — Modal accelerator-tier autodetect wizard. Probes via core.hardware, persists choice to hardware.json which core.transcriber.detect_device reads on next model load. Optional 5s benchmark button.
- `app/widgets/console.py` — build_console(): the black/lime read-only Text log feed at the bottom of the window, with its own Copy/Copy-all/Clear right-click menu.
- `app/widgets/platform.py` — Cross-platform UI helpers, notably open_folder() (os.startfile on Windows, open on macOS, xdg-open on Linux).
- `app/domain/tasks.py` — Task models for the queues. Re-exports core.task.TranscriptionTask and defines VideoDownloadTask (download job state: status/progress/section_start-end slice/history_id/saved_path/linked transcription_task).
- `app/domain/languages.py` — SUBTITLE_LANGUAGES table: display name to comma-separated yt-dlp subtitle language codes, shared by UI and download services.
- `app/dialogs/advanced.py` — AdvancedDialog: VAD knobs, word-timestamps, output-format checkboxes, SponsorBlock categories, auto-transcribe-after-download, telemetry opt-in; saves via core.config.save_config.
- `app/dialogs/model_download.py` — ModelDownloadDialog: modal that drives core.model_manager.ensure_model() download with progress; raises/handles DownloadCancelled.
- `app/dialogs/model_loading.py` — ModelLoadingDialog: simpler modal shown while a worker subprocess loads the already-downloaded model into RAM. Does NOT spawn the worker; TranscriptionService flips its `success`/destroys it via the main-thread-calls queue.
- `app/dialogs/hub_setup.py` — First-run Model Hub Folder picker; fires whenever config[hub_folder] is unset (and on --safe-mode reset).
- `app/dialogs/transcript_viewer.py` — TranscriptViewer modal: reads core/writers JSON transcript, optional python-vlc playback with click-to-seek + karaoke word highlight, find/replace, speaker rename, filler-word strip; `open_viewer` imported by app.py.
- `app/dialogs/statistics.py` — Read-only summary dialog over core.history SQLite (downloads/transcriptions counts, top languages). show_statistics(app).

**Entry points**
- gui.py main() — process entry: `--worker` early-branch, `--safe-mode`, `transcribe` subcommand, else `from app import run; run()`
- app.run() in app/__init__.py — constructs App and calls mainloop()
- app.App.__init__ (app/app.py:161) — builds the whole UI, services, queues, and schedules the after()-callbacks
- app.App.loop (app/app.py:2727) — the 500ms pump: refresh() + transcription_service.dispatch_waiting() + download_service.process_queue()
- pyproject.toml console-script `whisper-project = "app:run"`

**Commands**
```
run_tests.bat — the everyday gate: `pyright app core` (must be 0 errors) then `python -m pytest tests/ --ignore=tests/smoke -q`
pyright app core — type check (v1.0.3 baseline is 0 errors/warnings/infos; protect it before every commit)
python gui.py — launch the desktop GUI
python gui.py transcribe FILE [--language X] [--formats srt vtt ...] [--diarization] — headless CLI transcription
python gui.py --worker — spawn the JSON-stdio transcription worker (used internally by the App, do not invoke manually)
python gui.py --safe-mode — launch with user config backed up + reset to defaults (recovery)
```

**Depends on**
- core.worker (spawned subprocess; the --worker spawn-contract)
- core.transcriber / core.task / core.config / core.history / core.model_manager / core.hub / core.hardware
- core.integrations.smtv (SMTV scrape), core.integrations.otranscribe (oTranscribe round-trip)
- core.writers (output formats; transcript_viewer reads its JSON)
- core.tiling.TilingController, core.watcher.FolderWatcher, core.paths, core.logging_setup, core._proc, core._threads, core.optional_deps
- Third-party: tkinter, sv_ttk (theme), faster-whisper (in worker), yt-dlp + ffmpeg (subprocess binaries), pystray+Pillow (tray, optional), tkinterdnd2 (drag-drop, optional), python-vlc/libvlc (viewer, optional), darkdetect (system theme, optional), sentry-sdk (optional)

**Gotchas**
- gui.py `--worker` is a spawn-contract: it is handled BEFORE argparse and must NOT be renamed/removed — every transcription path spawns `<self-exe> --worker`. The module docstring explicitly warns this.
- app/app.py is a ~2700-line single class. Many App attributes (`fv`, `pb`, `tree`, every `*_var`/`*_combo`) are only forward-declared as annotations in app.py; the REAL assignment happens inside app/widgets/tabs.py build_* functions, which mutate the App instance as a side effect. Renaming a var means touching both files.
- app/__init__.py uses lazy `__getattr__` + a TYPE_CHECKING-only import of App specifically so importing the package does not drag in tkinter/faster-whisper. Don't add a top-level `from .app import App` — it breaks the worker/CLI/headless import paths.
- Threading model: background threads (watchdog watcher, burn-subs, hardware benchmark, tray clicks, download/format daemons) must NOT call self.after() directly — on Python 3.14 that raises RuntimeError. They push onto `_watched_path_queue` or `_main_thread_calls`, drained on the Tk main thread by `_drain_watched_paths`/`_drain_main_calls`. Services post results onto bounded Queues (`worker_events`, `download_events`, `format_events`, maxsize=2000) consumed by the main loop.
- Pyright must report 0 errors on app/ and core/ before every commit (v1.0.3 baseline 0/0/0). run_tests.bat is the gate.
- Adding a new module under app/ requires updating the hidden-import lists in BOTH whisper_project_onefile.spec and whisper_project_onedir.spec (per CLAUDE.md) so the unshipped PyInstaller pipelines don't bit-rot — even though the shipped build is the embed installer.
- Optional dependencies degrade silently to no-ops: pystray/Pillow (tray), tkinterdnd2 (drag-drop), python-vlc/libvlc (transcript viewer playback), darkdetect (system theme). Missing them must never block App startup.
- observability.py sends nothing unless BOTH config[telemetry_opt_in] is true AND the matching env var (SENTRY_DSN / WHISPER_TELEMETRY_URL) is set; packaged installers ship no DSN so they stay quiet.
- CLI path (gui.py _cli_transcribe) must refresh `core.transcriber.config` via `_trans.config.update(cfg)` after save_config — the worker/transcriber module reads config once at import time, so without this the first CLI run silently ignored new --formats/--diarization.
- VideoDownloadTask.section_start/section_end (yt-dlp time-slice) are deliberately distinct from start_time/end_time (running-task wall clocks for the Elapsed column) — easy to confuse. SMTV downloads ignore the slice (CDN has no server-side slicing) and just WARN.
- English-only repository policy (CLAUDE.md): no Persian/Arabic/RTL in app/ code, comments, or commit messages, even though the SMTV scraper accepts non-English content URLs.
- Glob `app/**/*` returned nothing in this environment (path/case quirk); use `ls`/Read on absolute paths instead. The __init__.py files in services/domain/widgets/dialogs are effectively empty (1 line).

### core — `core/`
The headless, Tk-free engine layer of the Whisper Project: model download/lifecycle, the transcription pipeline (VAD, word timestamps, diarization, hallucination flagging, multi-format output), pluggable backends, the long-lived worker subprocess protocol, persistence (config, history, checkpoints), and feature modules (recorder, separator, LLM, search, chapters, etc.). The GUI in app/ drives everything here through core.worker.

**Key files**
- `core/transcriber.py` — Heart of the pipeline (~73 KB). Holds module-global MODEL/PIPELINE/_ALT_BACKEND state; public API transcribe(), resume_transcription(), load_existing_model(), detect_device(), get_model_error(). Normalizes language codes (_normalize_language strips BCP-47 to Whisper's ISO codes), wires VAD/word-timestamps/diarization/hallucination/writers, and drives periodic checkpointing.
- `core/worker.py` — Long-lived worker subprocess. Reads JSON commands from stdin (transcribe/cancel/pause/resume/shutdown), emits JSON events on stdout (ready/started/progress/done/error/language_detected/log/startup_error). A dedicated reader thread applies control commands while the main thread is blocked in transcribe(). Protocol is FROZEN — add fields only, never rename/remove.
- `core/config.py` — Single source of truth for DEFAULT_CONFIG and load_config()/save_config(); platformdirs path helpers (user_data_dir, user_cache_dir, user_config_dir, user_log_dir). save_config is serialized by a module-level _SAVE_LOCK + atomic os.replace to dodge Windows PermissionError races.
- `core/model_manager.py` — Whisper model download/verify/extract. MODEL_REGISTRY (large-v3 default, turbo, distil) maps slugs to name/url/md5 mirrors on smch.ir; ensure_model() downloads+md5-verifies+unzips with MAX_DOWNLOAD_ATTEMPTS cap; raises DownloadCancelled.
- `core/__init__.py` — Bundled __version__ (currently 1.3.7) — the canonical runtime version read by About dialog + telemetry. Must be bumped alongside pyproject.toml and both .iss files on release.
- `core/backends/base.py` — Abstract Backend ABC + LanguageInfo dataclass. Defines the load/is_ready/transcribe_to_segments/unload/get_error contract every engine implements.
- `core/backends/__init__.py` — get_backend(name) factory; dispatches faster_whisper (default) / whisper_cpp / parakeet, silently falling back to faster_whisper on unknown names.
- `core/backends/faster_whisper_be.py` — Default CTranslate2 backend; thin adapter over the legacy module-global MODEL/PIPELINE state so the worker loads the model once.
- `core/backends/whisper_cpp.py` — pywhispercpp/ggml backend (quantized, smaller, weak-CPU friendly; opt-in).
- `core/backends/parakeet.py` — NVIDIA Parakeet TDT v3 via sherpa-onnx (RNN-T/TDT decoder, 3 .onnx files + tokens.txt under user_cache_dir()/parakeet).
- `core/writers/__init__.py` — Format-writer registry: WRITERS (text: srt/vtt/tsv/txt/json/lrc/md) + BINARY_WRITERS (docx/pdf). Use get_writer/get_binary_writer/is_binary/supported_formats. New formats register here.
- `core/writers/base.py` — Shared writer helpers: fmt_srt_time/fmt_vtt_time/fmt_lrc_time, normalize_text, sanitize_for_xml (strips XML-illegal control chars for docx), escape_cue_separator (literal --> in cue text), speaker_prefix.
- `core/_checkpoint.py` — Periodic partial-transcript checkpoints under user_data_dir()/partials/<sha1(abs_src)>.json, atomic .tmp+os.replace. SCHEMA_VERSION=1 (bump only on breaking change). Imports nothing from transcriber to keep deps one-way.
- `core/_proc.py` — Cross-platform process-tree kill (Windows taskkill /T, POSIX killpg) + new_session_kwargs() Popen flags. Best-effort, never raises. Required so ffmpeg/yt-dlp/demucs grandchildren aren't orphaned on Windows.
- `core/_errors.py` — fmt_err(action, exc) uniform error-string formatter + with_retries() exponential-backoff retry helper.
- `core/_threads.py` — Thread helpers used across the engine layer.
- `core/_liveness_tick.py` — liveness_tick(log_cb, label) context manager that emits a heartbeat log line every interval so silent long C calls (sherpa/ctranslate2/demucs/llama/stable-ts) don't trip the parent's LIVENESS_TIMEOUT_S watchdog and get SIGTERM'd.
- `core/task.py` — TranscriptionTask data holder: file_path, status, progress, language, resume flag, clip_start/clip_end, output_formats (per-task, overrides worker's stale import-time config snapshot), output_paths, history_id, source_download back-reference.
- `core/paths.py` — resource_base()/bin_dir()/bundled_binary() — resolve bundled assets across onefile(_MEIPASS)/onedir(exe dir)/source(repo root). Persistent data goes through config.py platformdirs, NOT here.
- `core/hardware.py` — Tk-free hardware autodetect (CUDA fp16 -> int8 -> QNN/Intel NPU -> OpenVINO -> DirectML -> CPU int8); persists choice to hardware.json. Backs the Hardware Wizard; detect_device() consumes load_hardware_choice().
- `core/history.py` — SQLite history.db (downloads + transcriptions tables) under user_data_dir(); idempotent schema, one connection per HistoryDB.
- `core/diarization.py` — Offline speaker diarization via sherpa-onnx (segmentation.onnx + embedding.onnx under bin/diarization/). diarize(audio_path) -> [{start,end,speaker}]. No HF token, no torch.
- `core/hallucination.py` — annotate_segments() flags suspect segments (Bag-of-Hallucinations phrases, repetition loops, VAD disagreement) by setting seg['suspect'] and seg['suspect_reason'].
- `core/separator.py` — Demucs vocal-separation pre-process; separate_vocals() returns vocals WAV or the input path unchanged when demucs missing/disabled. Cache under user_cache_dir()/demucs.
- `core/optional_deps.py` — On-demand pip-install of heavy extras (stable-ts alignment, openai-whisper backend; both pull torch) into a user-writable sys.path dir. FEATURES map; serialized by _install_lock; DEFAULT_INSTALL_TIMEOUT_S cap.
- `core/llm.py` — Local LLM panel (Qwen2.5-1.5B via llama-cpp-python): summarise/action-items/ask/translate. Download-on-first-use to user_cache_dir()/llm; lazy import; singleton LLMRunner; raises LLMUnavailable when dep absent.
- `core/recorder.py` — Mic + WASAPI system-loopback recording (sounddevice / pyaudiowpatch) to mono 16kHz int16 WAV; daemon thread, non-blocking stop, errors via Recorder.last_error.
- `core/search.py` — search() over saved transcripts: semantic (all-MiniLM-L6-v2 ONNX, sidecar embeddings table) with transparent FTS5 fallback; both walk history.db, return SearchHit list.
- `core/chapters.py` — Auto-chapter detection from silences (detect_chapter_boundaries pure-Python; optional title_chapters_with_llm).
- `core/voiceprint.py` — Cross-file speaker fingerprints in voices.db via pyannote/embedding; enrol + relabel SPEAKER_NN -> names; raises VoiceprintUnavailable without pyannote.audio.
- `core/alignment.py` — Opt-in word-timestamp refinement via stable-ts; calls model.align() on a WhisperResult built from existing segments (NOT stable_whisper.align(), which silently aborted before).
- `core/hub.py` — Model-hub folder resolution: model_path override -> hub_folder/<model dir> -> user_cache_dir()/models fallback.
- `core/watcher.py` — Watched-folder auto-enqueue via lazy watchdog; gated by config watched_folder + watched_folder_enabled.
- `core/tiling.py` — Video-wall: yt-dlp | ffplay tile filter. ffplay is NOT bundled — resolved via bundled_binary, degrades gracefully if missing.
- `core/burn_subs.py` — burn(video, srt, out) — ffmpeg subtitles filter overlay; synchronous, run on a background thread by callers.
- `core/integrations/smtv.py` — Supreme Master TV episode scraper (stdlib urllib, parses videoPlayerData + article-text transcript). No yt-dlp, no new deps. DOM contract documented in docs/integrations/.
- `core/integrations/otranscribe.py` — .otr <-> srt/whisper-json converter; exactly five public names (incl. segments_to_otr for the writer-shaped dict contract), stdlib only.
- `core/logging_setup.py` — setup_logging() — configures logging for app + worker processes.

**Entry points**
- core.worker — spawned as a subprocess by app/ (the GUI service layer); JSON-over-stdio is the primary integration boundary
- core.transcriber.transcribe() / resume_transcription() — in-process transcription entry (also used directly by tests/smoke)
- core.transcriber.load_existing_model() / detect_device() — model load + device selection
- core.model_manager.ensure_model() — download/verify/extract the Whisper model
- core.backends.get_backend() — backend factory selected by config['transcribe_backend']
- core.config.load_config() / save_config() — config read/write used app-wide

**Commands**
```
run_tests.bat (Windows) — runs the hermetic unit suite (tests/ minus tests/smoke/)
pyright app/ core/  — MUST report 0 errors/0 warnings/0 informations before every commit (v1.0.3 baseline; protect it)
Smoke tests under tests/smoke/ need real resources (Whisper model, a test video, live network); skipped via env vars when absent
```

**Depends on**
- faster_whisper (CTranslate2) — hard import in transcriber.py and faster_whisper_be.py; BatchedInferencePipeline optional on older wheels
- requests, platformdirs — used by model_manager / config
- Bundled binaries in bin/ (ffmpeg, ffprobe, yt-dlp; ffplay NOT bundled) resolved via core.paths.bundled_binary
- Optional/lazy: sherpa-onnx (diarization, parakeet), demucs+torch (separator), llama-cpp-python (llm), pyannote.audio (voiceprint), stable-ts (alignment), openai-whisper (whisper_backend), pywhispercpp (whisper_cpp backend), sounddevice/pyaudiowpatch (recorder), watchdog (watcher), sentence-transformers (semantic search)
- app/ (GUI service layer) is the main consumer; core must stay Tk-free
- bin/diarization/{segmentation,embedding}.onnx for diarization; ONNX models bundled via PyInstaller specs

**Gotchas**
- core MUST stay Tk-free — hardware.py / transcriber.py run inside the worker subprocess; importing tkinter there breaks the worker. (Explicit note in hardware.py.)
- core.worker stdin/stdout JSON protocol is FROZEN: adding fields is safe, renaming/removing breaks the parent UI.
- transcriber keeps module-GLOBAL state (MODEL, PIPELINE, MODEL_READY, MODEL_ERROR, _ALT_BACKEND). Many tests monkeypatch transcriber.config; the default faster_whisper path deliberately keeps using MODEL/PIPELINE globals so those tests keep working. Non-default backends route through _ALT_BACKEND.
- Language codes: faster-whisper accepts ISO-639-1 (+ a few) only, never BCP-47 (en-US/pt-BR). _normalize_language() strips region/script suffixes; passing an unnormalized code makes transcribe() raise and silently produce NO output.
- TranscriptionTask.output_formats / output_paths exist because the long-lived worker's import-time config snapshot goes stale — formats must be passed per-task at dispatch (this was the 'docx never written' bug).
- Bump __version__ in core/__init__.py together with pyproject.toml and BOTH .iss files on every release; it is the canonical runtime version (pip metadata is unavailable in frozen/embed builds).
- Adding a new core module requires updating the hidden-import lists in BOTH whisper_project_onefile.spec and whisper_project_onedir.spec (per CLAUDE.md) or the unshipped PyInstaller pipelines bit-rot.
- config.save_config is guarded by a module-level _SAVE_LOCK + atomic os.replace specifically to survive concurrent Windows os.replace PermissionError races — don't bypass it.
- Wrap any long silent C-level call (sherpa-onnx, ctranslate2, demucs subprocess, llama-cpp, stable-ts align) in core._liveness_tick.liveness_tick(...) or the parent's liveness watchdog SIGTERMs the worker mid-pass on slow hardware.
- On Windows, kill workers/children via core._proc.kill_process_tree (taskkill /T) — Popen.terminate() does NOT cascade and orphans ffmpeg/yt-dlp/demucs grandchildren that keep file handles + GPU allocations.
- _checkpoint.py intentionally imports nothing from transcriber and uses no third-party modules (one-way dep, testable without faster_whisper). SCHEMA_VERSION bumps only on a breaking on-disk change; resume refuses if model/config keys changed since the checkpoint.
- Optional-feature modules (separator, llm, voiceprint, alignment, recorder, watcher, search, whisper_cpp/parakeet backends) are no-ops or raise *Unavailable when their heavy deps are missing — never assume they're importable/active; optional_deps installs some on first use (pulls torch, ~700 MB).
- writers.sanitize_for_xml must be applied before the docx writer (python-docx raises ValueError on XML-illegal control chars); escape_cue_separator handles literal '-->' inside SRT/VTT cue text.
- Repository is English-only (handover prep) — no Persian/Arabic/RTL in core code, comments, or commit messages.
- ffplay (tiling.py) is NOT bundled in bin/; only ffmpeg/ffprobe/yt-dlp are. Feature degrades to an 'add ffplay' message.

### platform — `platform/`
Non-Windows packaging and installation: Linux source-venv installer/updater/uninstaller, macOS source-venv installer with Gatekeeper handling, a ready-but-unpublished Homebrew tap formula, and an unbuilt PyInstaller .app/.dmg pipeline for macOS. The shipped product is Windows-only (built elsewhere); everything here is groundwork for Mac/Linux from-source use.

**Key files**
- `platform/linux/install.sh` — Linux in-place installer: builds .venv next to repo, pip-installs requirements.txt + yt-dlp, fetches a static ffmpeg/ffprobe (johnvansickle.com) into bin/ when system lacks it, and writes ~/.local/bin/whisper-project (GUI) + whisper-transcribe (headless CLI) launchers plus a .desktop entry. Idempotent; re-run to update.
- `platform/linux/update.sh` — git pull --ff-only + pip --upgrade requirements.txt and yt-dlp inside the existing .venv. Aborts if no .venv.
- `platform/linux/uninstall.sh` — Removes launchers, .desktop entry, and .venv. Deliberately KEEPS the repo and user data under ~/.config/WhisperProject and ~/.cache/WhisperProject.
- `platform/linux/README.md` — Linux usage docs: install/desktop/headless-server (incl. a systemd user one-shot template), update, uninstall. Notes model cache (~3 GB) at ~/.cache/WhisperProject and config at ~/.config/WhisperProject/config.json.
- `platform/macos/install.command` — macOS installer (.command). Rebuilds .venv FROM SCRATCH each run, de-quarantines repo via xattr, prefers python.org/Homebrew python over Apple's system python3 (Tk 8.5 trap), symlinks ffmpeg/ffprobe into bin/, and builds a real ~/Applications/Whisper Project.app bundle (ad-hoc codesigned) plus a whisper-transcribe CLI.
- `platform/macos/unblock.command` — Gatekeeper helper: strips com.apple.quarantine from the repo and the installed Whisper Project.app.
- `platform/macos/README.md` — macOS usage + Gatekeeper explainer (unsigned app). Documents the Tk-8.5 blur trap, the two supported paths (this script vs Homebrew), VLC-at-/Applications/VLC.app requirement for the embedded preview, and Apple-Silicon/Rosetta caveats. Marked beta/unvalidated on a real Mac.
- `platform/macos/homebrew/whisper-project.rb` — Personal-tap Homebrew formula. Uses virtualenv_create against python@3.12, depends on ffmpeg + python-tk@3.12, pip-installs requirements.txt + yt-dlp. url pinned to tag v1.3.6; sha256 is a literal placeholder 'PUT_SHA256_OF_THE_TARBALL_HERE'.
- `platform/macos/homebrew/README.md` — How to publish the tap (homebrew-tap repo, refresh url+sha256 per release) and install. Requires the GitHub repo to be PUBLIC; currently private so the tap is staged, not live.
- `platform/macos/pyinstaller/whisper_project_mac.spec` — PyInstaller spec to build dist/Whisper Project.app. Adapted from Windows whisper_project_onedir.spec; hiddenimports/datas mirror it. Bundles bin/, assets/, faster_whisper/whispercpp/stable_whisper/whisper/tiktoken data; bundle_identifier com.translation-robot.whisperproject; version 1.3.6. MUST be built on a Mac; never built/verified here.
- `platform/macos/pyinstaller/builddmg.command` — Wraps the built Whisper Project.app into dist/Whisper Project.dmg via create-dmg. cd's up to repo root; errors out if the .app or create-dmg is missing.
- `platform/macos/pyinstaller/README.md` — Build steps for the PyInstaller .app/.dmg path (highest-confidence Mac deliverable, mirrors maintainer's machine-translate-docx pipeline). Still unsigned; built on Mac only.

**Entry points**
- All launchers/bundles created here ultimately exec the repo-root gui.py: 'gui.py' for the GUI, 'gui.py transcribe ...' for the headless CLI.
- platform/linux/install.sh -> ~/.local/bin/whisper-project + whisper-transcribe + whisper-project.desktop
- platform/macos/install.command -> ~/Applications/Whisper Project.app + ~/.local/bin/whisper-transcribe
- platform/macos/pyinstaller/whisper_project_mac.spec -> dist/Whisper Project.app (then builddmg.command -> dist/Whisper Project.dmg)
- platform/macos/homebrew/whisper-project.rb -> brew bin/whisper-project + whisper-transcribe

**Commands**
```
bash platform/linux/install.sh        # Linux install (idempotent; PYTHON=... to override interpreter)
bash platform/linux/update.sh         # Linux: git pull + refresh venv
bash platform/linux/uninstall.sh      # Linux: remove launchers + venv, keep data
bash platform/macos/install.command   # macOS install (PYTHON=/usr/local/bin/python3 to force python.org Tk 8.6)
bash platform/macos/unblock.command   # macOS: strip com.apple.quarantine
pyinstaller --noconfirm --clean platform/macos/pyinstaller/whisper_project_mac.spec   # build .app (Mac only)
bash platform/macos/pyinstaller/builddmg.command   # wrap .app into .dmg (needs brew install create-dmg)
brew install translation-robot/tap/whisper-project  # only after repo is public + tap published
```

**Depends on**
- Repo root gui.py — the single entry point every launcher/bundle here invokes (GUI default, 'transcribe' subcommand for CLI).
- requirements.txt (repo root) — pip-installed by every installer and by the Homebrew formula.
- core.paths.bundled_binary() — resolves ffmpeg/ffprobe/ffplay from the repo bin/ dir; this is WHY the macOS installer symlinks system/brew ffmpeg into bin/ (a Finder-launched .app gets a minimal PATH lacking /opt/homebrew/bin and /usr/local/bin).
- bin/ dir — must hold platform-native ffmpeg/ffprobe (and ffplay on macOS for Video Tiling); the .exe ones are wrong for Mac/Linux builds.
- assets/whisper.png (Linux .desktop icon) and optional assets/whisper.icns (PyInstaller .app icon).
- Windows spec whisper_project_onedir.spec — the Mac .spec is a hand-synced copy of its hiddenimports/datas; the two will drift if not updated together.
- External: yt-dlp (pip), faster-whisper/ctranslate2 native wheels, optional stable_whisper/whisper/tiktoken/pywhispercpp/sherpa_onnx/docx/reportlab backends, python3-tk, ffmpeg, and (macOS preview) VLC at /Applications/VLC.app.

**Gotchas**
- Version string 1.3.6 is HARD-CODED in two macOS files (install.command Info.plist CFBundleVersion, and whisper_project_mac.spec CFBundleShortVersionString/CFBundleVersion) and the tag v1.3.6 is in whisper-project.rb url — none auto-derive from the repo version, so a release bump must update all three by hand.
- whisper_project_mac.spec hiddenimports is a manual mirror of the Windows whisper_project_onedir.spec list (per CLAUDE.md: 'adding a new module = update both spec hidden-import lists'). The Mac spec is a THIRD copy that also needs the same edit or it silently bit-rots; it has never been built or verified on a Mac.
- macOS installer DELETES and rebuilds the .venv on every run (rm -rf $VENV) — intentional, to avoid a stale venv built against the wrong Tk; do not 'optimize' this into reuse. Linux install.sh, by contrast, reuses/updates its venv and is idempotent.
- macOS Tk trap: Apple's system python3 links deprecated Tk 8.5 which imports fine but renders a blurry/unstable GUI. The installer checks tkinter.TkVersion (the PATCH/major), not just importability; preserve that check. Override with PYTHON=/usr/local/bin/python3.
- ffmpeg MUST be symlinked into repo bin/ on macOS even when it exists in Homebrew/system, because a Finder/LaunchServices-launched .app inherits only /usr/bin:/bin and won't see /opt/homebrew/bin or /usr/local/bin; core.paths.bundled_binary() then can't find it. The launcher scripts set PATH but the GUI worker still resolves via bin/.
- Gatekeeper: this whole macOS surface ships UNSIGNED (no paid Apple cert). The strategy is to obtain the repo via git clone/curl (not quarantined). The .app is ad-hoc signed ('codesign -s -') ONLY for a stable code identity so TCC grants survive re-installs — it does NOT bypass Gatekeeper for browser-downloaded copies.
- Homebrew sha256 in whisper-project.rb is the literal placeholder 'PUT_SHA256_OF_THE_TARBALL_HERE' and the tap is NOT published (repo is private). The formula will not install as-is.
- Static-ffmpeg fallbacks differ by OS and arch: Linux uses johnvansickle.com (amd64/arm64); macOS uses evermeet.cx which is Intel x86_64 only (runs under Rosetta on Apple Silicon) — prefer Homebrew on M-series. macOS unzip step is deliberately made non-fatal under set -e to avoid aborting the installer on a truncated-but-HTTP-200 download.
- Glob 'platform/**/*' returned nothing on this Windows host even though the files exist; enumerate with a direct file listing instead. There is no Windows packaging here — that lives at the repo root (build_embed_installer.bat, installer_embed.iss, whisper_project_onefile.spec, whisper_project_onedir.spec, installer.iss), not under platform/.
- Linux uninstall.sh and the macOS docs treat ~/.config/WhisperProject and ~/.cache/WhisperProject as user data that is intentionally preserved; the ~3 GB Whisper model lives in the cache dir. Don't add code that wipes these during uninstall/update.

### tools-bin — `tools/, bin/`
Build-time and dev-time support assets for the Whisper transcription app: bin/ holds the third-party native binaries (ffmpeg, ffprobe, yt-dlp) and diarization ONNX models bundled into every shipped build, while tools/ holds standalone dev scripts (a startup-time benchmark, two live end-to-end drivers, and the diarization-model downloader). Neither directory is imported by the app at runtime; the app only reads files out of bin/ at execution time.

**Key files**
- `bin/ffmpeg.exe` — Bundled FFmpeg (~97MB, gitignored). Located at runtime via core.paths.bundled_binary('ffmpeg'); used for audio decode/resample (e.g. core/diarization.py resamples to the rate sherpa-onnx needs).
- `bin/ffprobe.exe` — Bundled FFprobe (~97MB, gitignored). Media probing companion to ffmpeg, resolved the same way via bundled_binary.
- `bin/yt-dlp.exe` — Bundled yt-dlp (~18MB, gitignored). Used by app/app.py for URL/video downloads; app prefers bin/yt-dlp.exe when present, else falls back to bare 'yt-dlp' on PATH.
- `bin/diarization/segmentation.onnx` — pyannote-segmentation-3.0 ONNX (~6MB, gitignored), exported by sherpa-onnx. Loaded by core/diarization.py via model_path().
- `bin/diarization/segmentation.int8.onnx` — int8-quantized segmentation model (~1.5MB), extracted alongside the fp32 one by the downloader.
- `bin/diarization/embedding.onnx` — 3D-Speaker CAMPlus EN speaker-embedding ONNX (~28MB, gitignored, English-leaning, trained on VoxCeleb).
- `bin/diarization/segmentation.tar.bz2` — Leftover download archive of the segmentation models; gitignored. The downloader normally deletes this, so its presence indicates a partial/interrupted run.
- `tools/download_diarization_models.bat` — Windows batch that downloads + extracts the two diarization ONNX models from k2-fsa/sherpa-onnx GitHub releases into bin/diarization/. Idempotent (skips if files exist). Must be run once before any build; NOT run by CI.
- `tools/measure_startup.py` — Dependency-free (ctypes Win32 EnumWindows) benchmark: spawns WhisperProject.exe and times until the 'Transcription helper' window appears; runs 3x and reports median/min/max. Defaults to dist/WhisperProject.exe.
- `tools/e2e_slim_pastbugs.py` — Live past-bug release gate: drives the REAL worker (embed_build/gui.py --worker) over its JSON stdin/stdout protocol, transcribing a real video and asserting srt/json/docx/txt all land (docx must have PK zip magic). Run with the slim embed interpreter.
- `tools/e2e_cancel_pause.py` — Live E2E for cooperative pause/resume/cancel: spawns python -m core.worker, asserts pause stalls progress, resume completes, and cancel keeps the worker alive. Skips if test video/model absent.

**Entry points**
- tools/download_diarization_models.bat (run once before building)
- python tools/measure_startup.py [path/to/WhisperProject.exe]
- embed_build\python\python.exe tools/e2e_slim_pastbugs.py
- python tools/e2e_cancel_pause.py

**Commands**
```
tools\download_diarization_models.bat
python tools/measure_startup.py
python tools/measure_startup.py dist/WhisperProject.exe
embed_build\python\python.exe tools\e2e_slim_pastbugs.py
python tools/e2e_cancel_pause.py
```

**Depends on**
- core/paths.py (resource_base / bin_dir / bundled_binary resolve bin/ across onefile/onedir/source contexts)
- core/diarization.py (consumes bin/diarization/*.onnx + bin/ffmpeg.exe)
- app/app.py (prefers bin/yt-dlp.exe)
- core.worker / core.transcriber / core._checkpoint (driven by the e2e scripts)
- embed_build/gui.py (worker entry point driven by e2e_slim_pastbugs.py)
- PyInstaller specs whisper_project_onefile.spec & whisper_project_onedir.spec (bundle bin/ via datas=('bin','bin'))
- External GitHub releases: k2-fsa/sherpa-onnx (diarization model source)

**Gotchas**
- ALL of bin/ is gitignored (ffmpeg/ffprobe/yt-dlp .exe via lines 53-55; diarization *.onnx + *.tar.bz2 via 60-61). A clean checkout has an empty/partial bin/ — builds will silently ship without these unless ffmpeg/ffprobe/yt-dlp are dropped in manually and tools/download_diarization_models.bat is run first.
- bin/ is bundled into the exe via datas=('bin','bin') in BOTH whisper_project_onefile.spec and whisper_project_onedir.spec. At runtime core/paths.bundled_binary resolves it under sys._MEIPASS (onefile) / exe dir (onedir) / repo root (source). Renaming or restructuring bin/ silently breaks ffmpeg, yt-dlp, and diarization in shipped builds.
- bundled_binary() falls back to the bare name (PATH lookup) when bin/<name>.exe is missing — so a missing bundled ffmpeg fails late/quietly rather than at startup. diarization.py raises DiarizationUnavailable in that path.
- The diarization downloader pulls from k2-fsa/sherpa-onnx GitHub release URLs hardcoded in the .bat; it uses Windows tar.exe + Invoke-WebRequest and is Windows-only. CI does NOT run it — it is a manual build-time prerequisite.
- The embedding model is English-leaning (3D-Speaker CAMPlus EN, VoxCeleb); diarization quality on non-English audio is a known limitation tied to this specific bundled file.
- Both e2e scripts and measure_startup are NOT pytest tests and live OUTSIDE tests/ — they are manual live drivers requiring real resources (a test video defaulting to E:\3029-NWN-Daily-Scroll-2m_0002.mp4 via WHISPER_SMOKE_VIDEO env var, and the model). They exit 0 / print SKIP when resources are absent, so a green run can mean 'skipped', not 'passed'.
- e2e_slim_pastbugs.py must run under the SLIM EMBED interpreter (embed_build\python\python.exe) and targets embed_build/gui.py --worker; e2e_cancel_pause.py runs under the dev interpreter and targets python -m core.worker. They are not interchangeable.
- measure_startup.py matches the window by exact title 'Transcription helper' (PID matching is intentionally omitted) and calls taskkill /F /IM WhisperProject.exe between runs — changing the main window title silently breaks it; leaked _MEI* temp dirs can skew the 3rd run.
- embed_build/ and dist_onedir/ contain their own bin/ and tools/ copies (bundled Python site-packages + build artifacts) — those are NOT the source subsystem; only top-level tools/ and bin/ are authored here.

### build-packaging — `whisper_project_direct_download_v2/ (root-level build scripts, specs, installers)`
Windows build and packaging pipeline that turns the Python source (gui.py + app/ + core/ + bin/) into distributable artefacts. The two SHIPPED deliverables are both embeddable-Python based: a Standard Inno Setup installer and a Portable ZIP of the embed tree; two PyInstaller (onefile + onedir) pipelines also exist but are unshipped and kept only to avoid bit-rot.

**Key files**
- `build_embed_installer.bat` — PRIMARY shipped build. Downloads python-build-standalone CPython 3.11.15 (tag 20260510, install_only tarball — has tkinter, unlike python.org embeddable zip), extracts with System32 tar.exe, pip-installs requirements.txt into Lib/site-packages, PRUNES heavy optional libs (torch/torchaudio/whisper/stable_whisper/numba/llvmlite/sympy/networkx/mpmath + .libs dirs) to shrink ~1.5GB->~800MB, copies app/core/bin/gui.py, writes Run Whisper Project.bat + sitecustomize.py, then runs sanity import + ast.parse checks. Produces embed_build/.
- `installer_embed.iss` — Inno Setup script wrapping embed_build/ into dist_installer/WhisperProject-v{MyAppVersion}-Setup-Standard.exe. Has its own #define MyAppVersion (currently 1.3.7). Shortcuts launch python\pythonw.exe gui.py. Registers Explorer shell-extension verb. Has [Code] hub-folder uninstall prompt (parses %LOCALAPPDATA%\WhisperProject\config.json).
- `whisper_project_onefile.spec` — PyInstaller Method A (Portable single-file EXE). UNSHIPPED but maintained. EXE() with embedded binaries+datas, no COLLECT. Hardcodes name='WhisperProject-v1.0.3-Portable' (STALE version). Bundles bin/, assets/, faster_whisper VAD assets, pywhispercpp/_pywhispercpp, stable_whisper/whisper/tiktoken via collect_all + a large hiddenimports list.
- `whisper_project_onedir.spec` — PyInstaller Method B (onedir tree for Compact installer). UNSHIPPED but maintained. EXE(exclude_binaries=True, contents_directory='.') + COLLECT, name='WhisperProject'. Flattens bin/DLLs beside the exe so core.paths.resource_base() resolves via dirname(sys.executable). Identical hiddenimports list to onefile spec.
- `installer.iss` — Inno Setup Method B (Compact). UNSHIPPED. Wraps dist_onedir/WhisperProject/ into WhisperProject-v1.3.7-Setup-Compact.exe. Same stable AppId GUID as Standard (single Add/Remove entry). Same hub-folder uninstall [Code] block.
- `build.bat` — STALE/likely-broken legacy verifier. References pyinstaller whisper_project.spec which DOES NOT EXIST, and verifies an onedir dist\WhisperProject\WhisperProject.exe layout that no current spec produces. Has clean/verify/smoke modes. Do not trust without fixing the spec name first.
- `docs/BUILD.md` — Authoritative build doc for the three methods (A Portable / B Compact / C Standard) with exact commands. Version strings inside are stale (v1.0.3).
- `docs/RELEASE_PROCESS.md` — Step-by-step release runbook: version bump, changelog, validation matrix (pyright 0/0/0 + pytest), build all deliverables, manual install/uninstall test, tag+push.
- `platform/macos/pyinstaller/whisper_project_mac.spec` — macOS .app/.dmg PyInstaller spec (BUNDLE + builddmg.command). NEVER BUILT/VERIFIED on a Mac — starting point only. info_plist version is 1.3.6 (stale). Must run on a real Mac with Mac ffmpeg binaries in bin/.
- `pyproject.toml` — version = "1.3.7" — one of the version sources PyInstaller specs read automatically per docs.
- `core/__init__.py` — __version__ = "1.3.7" — the bundled runtime source-of-truth version (About dialog + telemetry). Must be bumped with pyproject.toml + both .iss every release.

**Entry points**
- build_embed_installer.bat (build the shipped Standard embed tree)
- ISCC.exe installer_embed.iss (compile the shipped Standard installer)
- shutil.make_archive / Compress-Archive of embed_build/ (the shipped Portable ZIP — done MANUALLY, no committed script)
- pyinstaller --noconfirm --clean whisper_project_onefile.spec (unshipped Portable EXE)
- pyinstaller --noconfirm --clean --distpath dist_onedir whisper_project_onedir.spec then ISCC.exe installer.iss (unshipped Compact)

**Commands**
```
build_embed_installer.bat
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer_embed.iss
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer.iss
pyinstaller --noconfirm --clean whisper_project_onefile.spec
pyinstaller --noconfirm --clean --distpath dist_onedir whisper_project_onedir.spec
python -m pytest tests\ --ignore=tests\smoke
run_tests.bat (pyright 0/0/0 app/+core/ plus hermetic suite — the release gate)
```

**Depends on**
- python-build-standalone (astral-sh GitHub release) for the embeddable CPython 3.11.15 runtime
- Inno Setup 6 (ISCC.exe at %LOCALAPPDATA%\Programs\Inno Setup 6\) for both .iss installers
- PyInstaller (for the two unshipped spec pipelines)
- %SystemRoot%\System32\tar.exe (Windows bsdtar — NOT Git's tar) to extract the Python tarball
- requirements.txt (runtime deps pip-installed into the embed tree)
- bin/ffmpeg.exe, bin/ffprobe.exe, bin/yt-dlp.exe (bundled into every artefact)
- app/, core/, gui.py source tree (gui.py is the frozen entry point and the --worker subprocess)
- core/paths.py::resource_base() (runtime resolves bundled bin/ via _MEIPASS in onefile, dirname(sys.executable) in onedir/embed)
- core/optional_deps.py (pip-installs the pruned torch/stable-ts/whisper deps on first use at runtime)

**Gotchas**
- VERSION TRAP: version lives in FOUR places that must be bumped together — pyproject.toml, core/__init__.py __version__, installer.iss AppVersion+OutputBaseFilename, installer_embed.iss #define MyAppVersion. Current real version is 1.3.7, but whisper_project_onefile.spec hardcodes 'WhisperProject-v1.0.3-Portable', mac spec says 1.3.6, and BUILD.md/RELEASE_PROCESS.md still show v1.0.3/v0.7.1. Don't trust embedded version strings — check pyproject.toml/core.__init__.
- build.bat IS STALE/BROKEN: it runs `pyinstaller whisper_project.spec` but that file does NOT exist (real names are whisper_project_onefile.spec and whisper_project_onedir.spec), and it verifies an onedir dist\WhisperProject\ layout. It is not part of the current shipped pipeline; fix the spec name + dist path before relying on it.
- SHIPPED set is Standard installer + Portable ZIP, BOTH from the embed tree (build_embed_installer.bat). The Portable ZIP is a MANUAL shutil.make_archive / Compress-Archive of embed_build\ — there is NO committed script for it. The PyInstaller onefile/onedir + Compact installer are UNSHIPPED (kept only so specs don't bit-rot).
- Adding any new app/ or core/ module REQUIRES updating the hiddenimports lists in BOTH whisper_project_onefile.spec AND whisper_project_onedir.spec (and ideally the mac spec) or the unshipped frozen builds break with a runtime ImportError. The embed build doesn't need this (it ships the real source tree).
- The prune step in build_embed_installer.bat MUST NOT remove docx or reportlab — they back the docx/pdf writers and were re-introduced after a 'docx-never-written' bug. The sanity import line explicitly imports docx+reportlab so a future prune mistake fails the build loudly. Pruned libs (torch/whisper/stable-ts/numba etc.) are installed on-demand at runtime via core/optional_deps.py.
- Must use the python-build-standalone 'install_only' tarball, NOT python.org's embeddable zip — the embeddable zip strips tkinter/Tcl-Tk which the Tk UI needs. The .bat verifies `import tkinter` right after extraction.
- Tarball extraction must use %SystemRoot%\System32\tar.exe; Git's tar misreads the C:\ path as a remote host ('Cannot connect to C:') and fails.
- sitecustomize.py written into python\Lib\ is what teaches the embedded interpreter to prepend the bundle's Lib\site-packages to sys.path — without it the embed build can't find its deps.
- Both .iss files share the SAME AppId GUID {734B46B9-5E70-4C4E-8833-0A7506A64376} on purpose (single upgradable Add/Remove Programs entry). Both carry a duplicated [Code] hub-folder uninstall block (Inno has no [Include]); parity is checked by tests/core/test_inno_uninstall_parser.py — keep them in sync.
- Build outputs are gitignored: dist/, dist_onedir/, dist_installer/, embed_build/, build/, build_logs/. Commit ONLY specs, .bat scripts, and .iss files. embed_build/python/ (the extracted CPython runtime, thousands of .pyd/.h/.dll) appearing under the tree is a generated artefact — never read it in full or edit it.
- config.json is intentionally NOT shipped next to the exe — load_config() creates it on first launch at %LOCALAPPDATA%\WhisperProject\config.json; the installers parse that path for the hub-folder uninstall prompt.
- Release policy (CLAUDE.md, 2026-05-26): keep ONLY the latest GitHub release (plus the separate basic-v0.1.0 edition) and prune older ones on each release; git tags + local dist_installer/ artefacts are the backup. Do not move/delete published tags v1.0.3+ without explicit ask.

### tests-docs — `tests/, docs/, plus root project-config files (pyproject.toml, requirements.txt, README.md, CLAUDE.md, THIRD_PARTY_NOTICES.md, run_tests.bat)`
The test suite (hermetic unit tests + real-resource smoke/e2e tests) and the project's documentation/config metadata for the Whisper Project — a Windows-first local Whisper transcription desktop app with yt-dlp/SMTV download and oTranscribe round-trip.

**Key files**
- `pyproject.toml` — Single source of build + tooling config: pytest (testpaths=["tests"], addopts="-q", minversion 8.0), coverage (source=core,app; omit tests), pyright (include core,app; exclude tests; pythonVersion 3.11; typeCheckingMode basic). Declares project v1.3.7, runtime deps, and optional-dependency extras: dev/crash_reporting/theme_detection/backend_cpp/alignment. Packages found = app*,core* only (tests/build/dist/docs excluded).
- `run_tests.bat` — THE everyday green-gate. Runs (1) `pyright app core` (must be 0 errors) then (2) `python -m pytest tests/ --ignore=tests/smoke -q`; prints PASS/FAIL and exits non-zero on any failure. This is the exact hermetic-suite command future sessions should run.
- `tests/core/` — ~70 hermetic unit test files (test_config, test_download_command, test_history_db, test_writers, test_transcriber_helpers, test_worker_protocol, test_smtv_stream, etc.). No model/network/GUI. Import core/app directly (e.g. `from core import config`). This is the suite run_tests.bat runs.
- `tests/smoke/` — Real-resource integration suite (test_app_headless.py, test_exe_real_e2e.py, test_smtv_smoke.py, test_smtv_download_e2e.py). Excluded from the everyday gate; catches PyInstaller packaging bugs by spawning the compiled exe `--worker`. Each test self-skips when prerequisites are absent.
- `tests/smoke/conftest.py` — Only conftest in the repo. Session-scoped fixtures (test_video, model_dir, exe_path, gui_script, repo_root) that pytest.skip when resources are missing. Defines defaults + env-var overrides for smoke runs.
- `tests/integrations/` — Hermetic integration-unit tests: test_smtv.py (URL recognition/page parsing for core.integrations.smtv), test_otranscribe.py. Plus tests/integrations/fixtures/ (sample SRT/JSON + canned SMTV HTML pages).
- `tests/fixtures/` — Committed test assets: sample.wav, audio/silent_1s.wav + tone_440hz_2s.wav, smtv_clip/ (real 91s mp3 + expected json/srt/chapters), and generate_sample_wav.py (regenerator, source-of-truth for the WAV).
- `docs/TESTING.md` — Quick guide: run_tests.bat as the gate, one-time setup (pip install -r requirements.txt + pyright/pytest), what test files cover, how to run smoke tests with WHISPER_SMOKE_* env vars, how to run the app (`python gui.py`).
- `docs/README.md` — Documentation index / reading order: bucketizes ~40 docs into Start-here (INSTALL/BUILD/ARCHITECTURE/CONFIG), Reference, Per-feature, Release notes, Development state.
- `docs/SESSION_HANDOFF_NEXT.md` — Per CLAUDE.md, the source-of-truth for what work is left; read on session start, update on session end. The 1-line restart prompt references it.
- `CLAUDE.md` — Durable repo-wide instructions: commit-often/push-in-batches/release-slowly cadence; single mainline `master`; English-only; tests live under tests/ (hermetic = tests/ minus tests/smoke/); pyright must be 0 errors on app/+core/.
- `requirements.txt` — Runtime deps only (faster-whisper, requests, sv-ttk, tkinterdnd2, python-vlc, platformdirs, python-docx, reportlab, sherpa-onnx, watchdog, pystray, Pillow, pywhispercpp, stable-ts). Dev/test deps live in pyproject extras, NOT here.
- `THIRD_PARTY_NOTICES.md` — License summary for bundled third-party software (CPython, FFmpeg LGPL/GPL, yt-dlp, faster-whisper, ctranslate2, torch, etc.). Project's own code is BSD-3-Clause.
- `docs/integrations/` — Per-integration research+brief+acceptance docs (oTranscribe, SMTV). README.md defines the research->brief->ship->acceptance pattern for adding new integrations.
- `docs/CHANGELOG.md` — Version history (~60KB). SKIM only — large generated-style file.

**Entry points**
- run_tests.bat — the everyday gate (pyright app core, then pytest tests/ --ignore=tests/smoke -q)
- tests/core/ — hermetic unit suite (default pytest target via testpaths)
- tests/smoke/ — real-resource suite, run manually only
- docs/README.md — documentation reading-order index
- docs/TESTING.md — how to run tests and the app

**Commands**
```
run_tests.bat
pyright app core
python -m pytest tests/ --ignore=tests/smoke -q
python -m pytest tests/smoke/ -v -s
python -m pytest tests/smoke/test_exe_real_e2e.py
pip install -r requirements.txt
pip install pyright pytest
python gui.py
python tests/fixtures/generate_sample_wav.py
```

**Depends on**
- core/ and app/ packages — every unit test imports these directly (e.g. `from core import config`, `from core.integrations import smtv`); pyproject restricts packaging to app*/core* only
- pyright + pytest>=8.0 (dev tools, from pyproject [project.optional-dependencies].dev)
- faster-whisper / tkinter / numpy / PIL — optional at test time, gated via pytest.importorskip so absence skips rather than fails
- The compiled exe under dist/ or an embeddable-Python gui.py — required by tests/smoke/test_exe_real_e2e.py
- gui.py (repo-root app entry) — smoke headless/e2e tests reference it

**Gotchas**
- Hermetic suite is DEFINED as `tests/ minus tests/smoke/`. Never let a network/model/GUI dependency creep into tests/core/ or tests/integrations/ — those must stay runnable offline with no model. Use pytest.importorskip / skipif (os.name, WHISPER_OFFLINE_TESTS) like the existing tests do.
- There is NO conftest.py at tests/ root or tests/core/ — the ONLY conftest is tests/smoke/conftest.py. Unit tests import core/app because pytest adds the repo root (rootdir) to sys.path via the tests/ package layout (tests/__init__.py, tests/core/__init__.py exist). tests/integrations/test_otranscribe.py and tests/smoke/test_app_headless.py additionally do explicit sys.path.insert(0, REPO_ROOT). Don't delete the __init__.py files or rename tests/ — imports will break.
- pyright MUST report 0 errors on app/ AND core/ before every commit (the v1.0.3 baseline of 0/0/0 is protected per CLAUDE.md). tests/ is excluded from pyright, so test-file type errors won't fail run_tests.bat's pyright step but WILL fail nothing — they're simply unchecked.
- Smoke env-var contract (tests/smoke/conftest.py): WHISPER_SMOKE_VIDEO (default E:\3029-NWN-Daily-Scroll-2m_0002.mp4), WHISPER_SMOKE_MODEL (default %LOCALAPPDATA%\WhisperProject\Cache\models\models--Systran--faster-whisper-large-v3, must contain model.bin), WHISPER_SMOKE_EXE (default dist/WhisperProject.exe), WHISPER_SMOKE_GUI (set this AND WHISPER_SMOKE_EXE=pythonw.exe for the embeddable 'Method C' build). Missing prereqs => pytest.skip, not failure.
- Live-network smoke tests (test_smtv_smoke.py, test_smtv_download_e2e.py) honor WHISPER_OFFLINE_TESTS=1 to force-skip, and override URLs via WHISPER_SMTV_TEST_URL / WHISPER_SMTV_DOWNLOAD_TEST_URL.
- test_exe_real_e2e.py drives the worker over a JSON stdin/stdout protocol (events: ready, startup_error, language_detected, progress, done, error; actions: transcribe, shutdown). It asserts progress reaches >=90% and that SRT/JSON land next to the input. This is the ONLY layer that catches PyInstaller missing-data-file bugs (the Session-8 silero_vad_v6.onnx incident documented in tests/smoke/README.md).
- Dev/test dependencies are NOT in requirements.txt (which is runtime-only) — they live in pyproject.toml [project.optional-dependencies].dev. Installing only requirements.txt won't give you pyright/pytest/pytest-cov/responses.
- docs/ is mostly historical/process narrative (SESSION_LOG.md ~86KB, ROADMAP.md ~40KB, many RELEASE_NOTES_v*.md, AUDIT*/PHASE* files under history/). For current state read docs/SESSION_HANDOFF_NEXT.md; for orientation read docs/README.md. Do not treat old AUDIT/PHASE/ROADMAP docs as current truth.
- English-only repository rule (CLAUDE.md): no Persian/Arabic/RTL in docs, comments, or commit messages — even though the SMTV scraper handles non-English content URLs.
- Adding a new core/app module requires updating BOTH whisper_project_onefile.spec and whisper_project_onedir.spec hidden-import lists (per CLAUDE.md) so the unshipped PyInstaller pipelines don't bit-rot — not a tests/docs file, but a release-gate the test suite cannot catch (only smoke e2e can).
- pyproject project.version (1.3.7) is a separate source of truth from git tags and docs/RELEASE_NOTES_*; keep them in sync at release time.

---

<!-- AUTO-INDEX:STRUCTURE:START -->
## Structure (auto-refreshed — do not hand-edit this block)

- **Source files tracked:** 407
- **Structure refreshed:** 2026-07-04T15:15:32
- **Semantic sections last built:** 2026-06-03T15:55:57
- **Drift since semantic build:** +173 added · ~82 changed · -34 removed

> ⚠️ **STALE** — the source tree changed a lot since the semantic sections were built. Re-run `/project-index` to regenerate purposes / gotchas / subsystem maps.
>
> Notable: `.claude/briefs/A.json`, `.claude/briefs/B.json`, `.claude/briefs/C.json`, `.claude/briefs/D.json`, `.claude/briefs/E.json`, `.claude/briefs/F.json`, `.claude/briefs/G.json`, `.claude/briefs/G2.json`

| Top-level | Source files |
|---|---|
| `tests` | 173 |
| `docs` | 79 |
| `core` | 64 |
| `app` | 24 |
| `.claude` | 20 |
| `(root)` | 16 |
| `.github` | 13 |
| `platform` | 10 |
| `tools` | 6 |
| `assets` | 1 |
| `creds` | 1 |

**By type:** `.py`×263  `.md`×92  `.json`×17  `.yml`×11  `.bat`×4  `.spec`×4  `.html`×4  `.sh`×4  `.iss`×2  `.ps1`×2  `.toml`×1  `.txt`×1  `.js`×1  `.rb`×1

<!-- AUTO-INDEX:STRUCTURE:END -->
