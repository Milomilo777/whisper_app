# Changelog

All notable changes to this project. Follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Session 8** — `tests/smoke/` integration suite for the compiled exe. Three pytest files (`test_exe_real_e2e.py`, `test_app_headless.py`, plus a `conftest.py` with skip-guards for missing model / video / exe) and a `README.md` explaining why these tests have to live alongside the unit suite — packaging bugs are invisible from source-side. `test_exe_real_e2e.py` spawns `WhisperProject.exe --worker`, sends the actual JSON `transcribe` command, and asserts SRT + JSON land on disk; `test_app_headless.py` drives the Tk App in a withdrawn window through every service. Regression guards `test_exe_bundles_silero_vad_asset` and `test_exe_bundles_ffmpeg` lock in the Session 8 packaging fix.
- **Session 8** — `docs/SESSION_8_PACKAGING_FIX.md` documenting the silero_vad_v6.onnx packaging bug and why source-side tests didn't catch it.
- **Session 7** — `docs/architecture-diagrams.md` (Mermaid simple overview + SVG embed + pointer to prose ARCHITECTURE.md). Hyphenated filename to avoid a case-insensitive Windows clash with the existing `ARCHITECTURE.md`. The Mermaid view uses the same color palette as the SVG so the two diagrams feel related at a glance. README now links to it as the first "Project documentation" entry.
- **Session 7** — `docs/NEXT_SESSION_HANDOFF.md` — two-minute briefing for any future architect. Includes the current commit/branch/tag inventory, a 60-second orientation command list, the candidate phases ranked by impact-per-effort, the hard rules (single branch, no tokens, `bin/` ignored, Tk single-threaded, JSON protocol sacred), what's explicitly out of scope (Persian/Arabic, cloud LLMs, mobile, streaming), where to look when something feels weird, files not to touch, and a one-paragraph user prompt to start the next session.

### Fixed

- **Session 9** — `App.destroy()` now cancels every pending `tk.after()` callback before tearing down the Tcl interpreter. Previously, the service poll loops (`TranscriptionService.poll`, `FormatService.poll`, `DownloadService.poll`) reschedule themselves every tick; on shutdown those pending callbacks fired into a destroyed interpreter and spammed the log with hundreds of `invalid command name "<id>poll"` errors. Now the override iterates `tk.call("after", "info")` and calls `after_cancel` on each id before delegating to `super().destroy()`.
- **Session 9** — `core/transcriber.py:load_model_async` no longer swallows exceptions. The background-thread wrapper had a bare `except Exception: pass` that hid a real model-corruption case in the field for a whole session. Now it logs via `logger.exception` and forwards the message to `status_cb` if provided.
- **Session 9** — `core/transcriber.py:get_duration` now passes `timeout=60` and (on Windows) `creationflags=subprocess.CREATE_NO_WINDOW` to the bundled ffprobe call. A wedged ffprobe used to hang transcription indefinitely with no cancel, and the windowed exe popped a black console window for every probed file.
- **Session 9** — `messagebox.showinfo("About", ...)` now passes `parent=self` so the dialog centers on the app window instead of the screen.
- **Session 8** — `whisper_project.spec` now collects `faster_whisper`'s data files via `collect_data_files('faster_whisper')`. Without this, the compiled exe crashed the moment a user clicked **Transcribe** with VAD enabled (the default) because `silero_vad_v6.onnx` was absent from the bundle. The bug was invisible from `python gui.py` because source-side code resolves the asset from `site-packages/faster_whisper/assets/`. Only spawning the compiled `WhisperProject.exe --worker` and sending a real `transcribe` command exposed it. Now covered by the smoke suite — see Added above.
- **Session 8** — `whisper_project.spec` retains the Session 8a `contents_directory='.'` on the `EXE()` call so bundled `bin/` lands beside the exe, not inside `_internal/`. The `build.bat` xcopy fallback is no longer triggered on a clean build.

### Changed

- **Session 7** — `docs/MANUAL_STEPS.md` scrubbed: the `## A. Security` block that named two leaked GitHub PAT prefixes was removed. Sections re-lettered (B → A through H → G) so the file still reads cleanly. The Summary was rewritten to drop the "two human-required items" framing; there's now exactly one open human decision — which Phase to ship next.
- **Session 7** — `README.md` "Project documentation" footer now points at `architecture-diagrams.md` first, then the direct SVG link, then the prose ARCHITECTURE.md, so a new reader hits the visuals before the prose.

### Notes

- The leaked PAT prefixes still appear in this repo's history at commit `6d97a5f`'s diff. With the tokens revoked (which the user was asked to do; see Session 7's pending-actions note in `SESSION_LOG.md`), those strings are inert. Standard guidance for accidental-token-commit is "revoke + move on" rather than rewrite history; we followed it.

- **Session 6 research** — `docs/COMPETITIVE_ANALYSIS_2026.md` (~2900 words, ~40 cited sources). 2026 STT landscape scoped to EN + CJK + FR + DE (Persian/Arabic explicitly excluded). Covers Alibaba FunAudioLLM (SenseVoice / FunASR / CapsWriter), NVIDIA NeMo (Parakeet-TDT-0.6B-v3 / Canary-1B-v2), Whisper speedups (Insanely-Fast-Whisper / WhisperX / stable-ts / WhisperKit / Whisper-Streaming / WhisperLive / pywhispercpp), Tencent Covo-Audio, and 17 commercial products (Deepgram Nova-3, AssemblyAI Universal-3-Pro + LeMUR, ElevenLabs Scribe v2, Descript, MacWhisper 12, Apple Voice Memos iOS 18, etc.). Synthesizes 15 candidate features ranked by impact, Chinese-language gotchas (tokenization, punctuation, simplified/traditional, line-length, CPS), best-model-per-language matrix, and a five-feature Descript-style Phase 4 editor blueprint.
- **`docs/architecture.svg`** — 1500×1100 layered system diagram, color-coded by role (user / UI / core / subprocess workers / external processes / filesystem / test+build / external network). Drop shadows, dashed-for-async arrows, red "killer flow" callout for Phase 3a auto-transcribe-after-download. Renders inline on GitHub. Authored after four reflection passes.
- **`docs/ROADMAP.md`** restructured (Session 6) — new **Phase 6 — CJK polish + pluggable backends** with 8 sub-items: SenseVoice + Parakeet pluggable backends, Chinese punctuation post-processor (FunASR `ct-punc`), CJK-aware line splitting per Netflix style guide, simplified↔traditional via OpenCC, number/date normalization via cn2an, hallucination + repetition cleanup, stable-ts integration for word-perfect timestamps, sound-event tagging for SDH. Old Phase 6 (Hardening) renumbered to Phase 7 with no content loss. **Phase 4 (editor) rewritten** to drop the RTL Persian items (de-scoped — user audience is now 94% Chinese) and adopt the Descript-style blueprint: edit-back-to-subtitle with re-flowed timestamps, gap/silence panel, speaker labels with global rename, multilingual filler-word bulk operations (EN/FR/DE/ZH dictionaries) with dual caption-only vs. cut modes, CJK-aware subtitle linter.
- `README.md` documentation footer updated to point at `docs/architecture.svg` and `docs/COMPETITIVE_ANALYSIS_2026.md`.
- **Final compile** — `whisper_project.spec` (PyInstaller `--onedir`, deterministic, committed) + `build.bat` at the repo root with documented exit codes (0 success / 1 PyInstaller failure / 2 verification failure / 3 smoke launch failure). Build verifies the four required runtime files (`WhisperProject.exe` plus `bin/ffmpeg.exe`, `bin/ffprobe.exe`, `bin/yt-dlp.exe`) and falls back to a manual `xcopy` of `bin/` if PyInstaller's `datas` silently dropped it (which it does — caught on the first build). `docs/BUILD.md` documents modes, exit codes, the `bin/` fallback, and explains why `config.json` is intentionally not in `dist/` (Phase 1.2 placed it in `%LOCALAPPDATA%`). `.gitignore` now keeps the committed `whisper_project.spec` while ignoring stray local `.spec` files.
- **Phase 3a** — yt-dlp killer features. New SQLite history DB at `%LOCALAPPDATA%\WhisperProject\history.db` with `downloads` and `transcriptions` tables, `mark_interrupted()` on startup, and a `Statistics` menu item showing download/transcription counts, total minutes, and top languages. SponsorBlock category checkboxes in the Advanced dialog (`sponsorblock_categories` config key) — when set, the categories are appended to yt-dlp via `--sponsorblock-remove`. Auto-transcribe-after-download wiring is fully active: a finished media download with `auto_transcribe_after_download=True` enqueues a `TranscriptionTask` with the captured language hint. The `--progress-template "%(progress)j"` JSON parser landed in Phase 1b is now the live progress source for download rows. Right-click history actions on both queue tabs: `Open output folder`, `Re-run`, `Remove`. 17 new unit tests (history 11, auto-transcribe wiring 6).
- **Phase 2a** — Whisper masterpiece. VAD on by default, configurable via three knobs (`vad_min_silence_ms`, `vad_threshold`, `vad_speech_pad_ms`). Word-level timestamps as an opt-in (`word_timestamps`). Language detection captured from `info.language`/`info.language_probability`, posted via a new `language_detected` worker event, and rendered in a new `language` column on the Transcription Queue tab. New `core/writers/` package — six pure writers (`srt`, `vtt`, `tsv`, `txt`, `json`, `lrc`) + a `get_writer` registry. Output formats are user-selectable from a new `Advanced...` dialog (defaults: `["srt", "json"]`). VTT emits karaoke-style `<HH:MM:SS.ms><c>word</c>` cues when words are present. `BatchedInferencePipeline` wraps the model on CUDA when available. `initial_prompt` and `hotwords` plumbing in place (UI in Phase 2b). 39 new unit tests + 4 real-audio smoke tests + 3 end-to-end tests.
- **Phase 1b** — Foundation refactor. The 1296-line `gui.py` becomes an 11-line `--worker`-aware entry point; the rest is now an `app/` package with `app.py` (Tk root, ~430 lines), `dialogs/`, `domain/`, `services/` (DownloadService, FormatService, TranscriptionService, IntegrationsService), `widgets/` (console + tab builders), and `observability.py` (env-gated Sentry). Per-instance queues replace module globals (closes AUDIT B3). `pyproject.toml` lands at the repo root with `[project.optional-dependencies]` for `dev`, `crash_reporting`, `theme_detection`. (PHASE_NEXT_BRIEF Phase 1b)
- **Phase 1b / tests** — `tests/core/` adds 71 new unit tests (config 9, model_manager 10, worker_protocol 10, subtitle_lang_args 10, download_command 20, transcriber_helpers 12). `core/` line coverage rises to 77% overall; testable modules sit at 81–92%.
- **Phase 1b / type hints** — `from __future__ import annotations` + complete type signatures across every `core/` module. `pyright core/` is clean (0 errors, 0 warnings).
- **Phase 1b / observability** — `app/observability.py` opt-in Sentry hook. Activated only when `SENTRY_DSN` env var is set. No DSN ever in code, config, or git history.
- **Phase 1b / acceptance** — `docs/PHASE_1B_ACCEPTANCE.md` with grep-able tests 1B-T1 through 1B-T7.
- `README.md` at project root — first-class entry point for new readers
- `docs/ARCHITECTURE.md` — describes the current process model, layout, key flows, and design rationale
- `docs/AUDIT.md` — full audit findings tagged critical / high / medium / low
- `docs/ROADMAP.md` — six-phase plan based on competitive analysis of nine Whisper GUI projects and eight yt-dlp GUI projects
- `docs/CHANGELOG.md` — this file
- `docs/CONFIG.md` — `config.json` field reference
- `docs/DECISIONS.md` — short ADRs for the load-bearing architectural choices
- `docs/PHASE_1_ACCEPTANCE.md` — machine-parseable test plan for Phase 1a (theme + platformdirs + logging)
- `.gitignore` — first proper gitignore for the project
- `requirements.txt` — runtime dependencies, with Phase 1/2 additions commented for later
- `Phase 0 fixes` — see "Changed" and "Fixed" below
- **Phase 1.1** — Sun Valley theme via `sv-ttk`. Selectable Light / Dark / System under `View` menu, persisted via the new `theme` config key. Transcribe tab `tk.Label`/`tk.Button`/`tk.Entry` widgets converted to `ttk` equivalents so the theme applies uniformly. (ROADMAP 1.1)
- **Phase 1.2** — `platformdirs`-backed config, cache, and log directories. `core/config.py` now exposes `user_config_dir()`, `user_cache_dir()`, `user_log_dir()`, `user_data_dir()`. New `migrate_config_location()` runs on every `load_config()` call: a legacy `config.json` next to source is copied to `%LOCALAPPDATA%\WhisperProject\config.json` and the original renamed to `.migrated.bak`. `model_path` defaults derived from `user_cache_dir()`. (ROADMAP 1.2)
- **Phase 1.3** — `core/logging_setup.py` with `setup_logging()`, `get_ui_logger()`, and `open_log_folder()`. `RotatingFileHandler` writes to `<user_log_dir>/app.log` (5 MB × 3). Both `gui.py` and `core/worker.py` call `setup_logging` at startup. Every previous `print()` outside the worker's JSON `emit()` is now a `logging.getLogger(__name__).info/warning/error` call. New `Help → Open log folder` menu item. (ROADMAP 1.3)
- **Phase 1.5** — `sv-ttk>=2.6.0` and `platformdirs>=4.0.0` promoted from "Phase 1 additions (uncomment when implementing)" to active dependencies. (ROADMAP 1.5)
- `docs/integrations/` — new home for cross-tool integration notes. Contains a `README.md` index, a research note + implementation brief for **oTranscribe** (web-based manual transcription tool). The pattern is: every integration gets a research note authored before code, a hands-off brief that drives an autonomous session, and an acceptance plan added when the work lands. Documents survive the merge — never deleted.
- `docs/integrations/otranscribe-research.md` — full schema of the `.otr` file format (plain JSON with four keys: `text` HTML, `media`, `media-source`, `media-time`), the timestamp `<span>` HTML structure, oTranscribe's import/export limitations (imports only `.otr`; exports `.otr`/`.txt`/`.md` with no SRT/VTT), keyboard shortcuts, and a three-tier integration plan (MVP converters / UI buttons / power features).
- `docs/integrations/otranscribe-brief.md` — implementation brief modeled on `docs/PHASE_1_BRIEF.md`. Three public functions (`srt_to_otr`, `whisper_json_to_otr`, `otr_to_srt`), three UI additions (Export menu item, Import button, Help → Open oTranscribe), pytest fixtures, nine grep-able acceptance tests, hands-off push policy, and the eight known traps that survived Phase 1's discovery (newlines inside `text`, NBSP after the timestamp span, no zero-padding on the hour, etc.).
- **Phase 2-oTranscribe** — bidirectional `.otr` file-format converter at `core/integrations/otranscribe.py`. Public surface: `fmt_otr_time`, `srt_to_otr`, `whisper_json_to_otr`, `otr_to_srt`. Stdlib only (`json`, `html`, `html.parser`, `re`, `pathlib`); zero new runtime deps.
- **Phase 2-oTranscribe / UI** — `Transcription Queue` right-click on a `finished` task gains `Export → oTranscribe (.otr)` (writes `<base>.otr` next to the existing `<base>.srt`). `Transcribe` tab gains an `Import .otr → SRT...` button that runs through two file pickers. `Help → Open oTranscribe...` opens the official site in the user's browser.
- **Phase 2-oTranscribe / tests** — `tests/integrations/test_otranscribe.py` with nine pytest cases (display format, ASCII round-trip, Persian round-trip, whisper-JSON conversion, NBSP boundary, single-line `text`, last-segment end inference, `media` basename only, smoke). Fixtures under `tests/integrations/fixtures/`.
- `docs/integrations/otranscribe-acceptance.md` — machine-parseable acceptance plan for the oTranscribe integration with a mandatory final JSON block.

### Fixed

- **CRITICAL**: `yt-dlp --update` no longer blocks every download. The unconditional pre-download update call previously broke offline use and any case where GitHub was rate-limiting. Update is now gated to once per launch (and only when the user opts in via `auto_update_yt_dlp` setting). Failures log and continue. (AUDIT A1)
- **CRITICAL**: `core/transcriber.py`'s `detect_device` no longer swallows `KeyboardInterrupt` and `SystemExit` via a bare `except:` (AUDIT A2)
- **CRITICAL**: `get_duration` in `core/transcriber.py` now resolves `ffprobe` from the bundled `bin/` folder instead of expecting it on `PATH` (AUDIT A3)
- **HIGH**: `current_video_language` is now only captured when the lookup result still matches the current URL — fixes wrong-language hint after rapid URL changes (AUDIT A4)
- **HIGH**: Partial subtitle files are deleted when the subtitle phase is cancelled mid-write (AUDIT A5)
- **HIGH**: `config.json` is written atomically (`.tmp` + `os.replace`) so a crash during save can no longer leave the file corrupt (AUDIT C1)
- **HIGH**: `load_config` falls back to baked-in defaults if `config.json` is missing or invalid, instead of crashing at startup (AUDIT C2)
- **CRITICAL**: `load_config` now repairs unreachable `model_path` (e.g. config referencing an unmounted drive like `X:\`) by substituting `%LOCALAPPDATA%\WhisperProject\models\<model-folder>`. Unreachable `download_folder` is cleared so the UI re-prompts. This fixes the `[WinError 3] The system cannot find the path specified: 'X:\\'` crash during model setup. (AUDIT C7, escalated from LOW after a real user hit it.)

### Changed

- `transcriber.py`'s busy-wait loop in `transcribe()` replaced with an `assert MODEL_READY` since the only call path goes through `load_existing_model` first (AUDIT B6)

---

## [0.3.0] — 2026-05-11

### Added

- Automatic subtitle download in the "Download Videos" tab — checkbox plus 30-language combo (`docs/auto-subtitles-feature.md`)
- Per-phase status indicator next to the subtitle combo
- `download_subtitles_enabled` and `download_subtitle_lang` persisted to `config.json`
- Subtitle phase explicit `--- Subtitle phase: … ---` markers in the console log
- `--write-auto-subs` AND `--write-subs` in one yt-dlp call — yt-dlp prefers manual captions when available

### Changed

- `SUBTITLE_LANGUAGES` reordered to Automatic, English, then alphabetical (was: arbitrary regional grouping)
- Multi-variant language entries collapse `zh-Hans,zh-CN`, `no,nb`, `he,iw`, `id,in`, `pt,pt-BR,pt-PT`, `es,es-419`
- Subtitle combo starts in `state="disabled"` to avoid a readonly→disabled flash on launch

### Fixed

- `--sub-langs en.*` was matching translated captions like `en-de-DE`, `en-ja`, `en-pt-BR`, downloading 7 files instead of 1. Now uses exact codes joined with commas.
- "no subtitles" detection regex now matches yt-dlp's actual output (`There are no subtitles for the requested languages` / `no automatic captions for the requested languages`) instead of the never-triggered `WARNING: There are no` pattern

---

## [0.2.0] — 2026-05-07

### Added

- Bundled `yt-dlp.exe` in `bin/` for video downloads
- "Download Videos" tab with URL input, format detection via `yt-dlp --dump-single-json`, audio-only and audio+video modes, output format selection
- Download queue with progress, cancel, remove

---

## [0.1.0] — Initial version

### Added

- Tk GUI for `faster-whisper` transcription
- Worker subprocess model with JSON event protocol
- Resumable, MD5-verified model download from a CDN mirror
- Transcription queue with cancel, pause/resume, retry
- Multiple parallel workers (`parallel_workers` config)
- SRT and JSON output next to the input file
