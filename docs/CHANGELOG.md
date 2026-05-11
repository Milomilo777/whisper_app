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
- `.gitignore` — first proper gitignore for the project
- `requirements.txt` — runtime dependencies, with Phase 1/2 additions commented for later
- `Phase 0 fixes` — see "Changed" and "Fixed" below

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
