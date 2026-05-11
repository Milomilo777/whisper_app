# Changelog

All notable changes to this project. Follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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
