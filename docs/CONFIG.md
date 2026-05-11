# Configuration Reference

`config.json` lives next to `gui.py` (and will move to `%LOCALAPPDATA%\WhisperProject\config.json` in Phase 1.2 of `ROADMAP.md`).

The file is read once at startup and written when the user changes a persisted setting (download folder, subtitle preferences, etc.). Manual edits take effect on next launch.

## Field reference

| Field | Type | Default | Description |
|---|---|---|---|
| `model` | object | (see below) | The active model's source and verification info |
| `model.name` | string | `"faster-whisper-large-v3"` | Display name in logs |
| `model.url` | string | `https://smch.ir/models/...zip` | ZIP archive of the model |
| `model.md5` | string | `<url>.md5` | URL of the per-file MD5 manifest |
| `model_path` | string | (machine-specific) | Absolute path where the model is extracted. Default will become `<platformdirs.user_cache_dir>/WhisperProject/models/<name>` in Phase 1.2. |
| `device` | string | `"auto"` | `"auto"` / `"cuda"` / `"cpu"` |
| `compute_type` | string | `"int8"` | `faster-whisper` compute type. Common values: `int8`, `int8_float16`, `float16`, `float32`. `int8` is the smallest/fastest on CPU; `float16` is preferred on GPU. |
| `parallel_workers` | int | `2` | Maximum simultaneous transcription worker subprocesses. Each loads the model and uses ~3 GB RAM (or VRAM on GPU). |
| `download_folder` | string | `""` | Default destination for video downloads. Updated by the Folder Browse button. |
| `download_subtitles_enabled` | bool | `false` | Last state of the subtitle checkbox on the Download Videos tab |
| `download_subtitle_lang` | string | `"Automatic"` | Last-selected subtitle language (display name from `SUBTITLE_LANGUAGES`, not the code). |

## Coming in Phase 1.2

| Field | Type | Default | Description |
|---|---|---|---|
| `theme` | string | `"dark"` | `"light"` / `"dark"` / `"system"` — for `sv_ttk` |
| `log_level` | string | `"INFO"` | Python logging level for the file handler |
| `auto_update_yt_dlp` | bool | `false` | If true, check GitHub releases at most once per day on launch (no longer runs before each download — see AUDIT A1) |
| `last_yt_dlp_update_check` | string (ISO date) | `null` | Timestamp of the last successful update check |
| `crash_reporting` | bool | `false` | Opt-in to Sentry crash reports |

## Coming in Phase 2

| Field | Type | Default | Description |
|---|---|---|---|
| `models` | array of objects | (see ROADMAP 2.7) | List of available models with their URLs and active flag |
| `active_model` | string | `"large-v3"` | Which entry in `models` is currently selected |
| `vad_enabled` | bool | `true` | Voice Activity Detection on by default |
| `vad_min_silence_ms` | int | `500` | |
| `vad_threshold` | float | `0.5` | |
| `word_timestamps` | bool | `false` | |
| `initial_prompt` | string | `""` | |
| `hotwords` | string | `""` | |
| `task` | string | `"transcribe"` | `"transcribe"` / `"translate"` |
| `output_formats` | array of strings | `["srt", "json"]` | Subset of `srt / vtt / tsv / json / txt / lrc` |
| `presets_dir` | string | (platformdirs) | Where preset TOML files live |
| `active_preset` | string | `null` | Currently applied preset name |

## Coming in Phase 3

| Field | Type | Default | Description |
|---|---|---|---|
| `parallel_downloads` | int | `1` | Max concurrent yt-dlp downloads |
| `sponsorblock_categories` | array | `[]` | E.g. `["sponsor", "intro", "outro"]` |
| `cookies_from_browser` | string | `null` | `"firefox"` / `"chrome"` / `"edge"` / `"brave"` |
| `extra_ytdlp_args` | string | `""` | Free-form args to append to every yt-dlp invocation |
| `download_rate_limit` | string | `""` | E.g. `"5M"` for `--limit-rate 5M` |

## Migration policy

When a new field is introduced, `load_config` will populate it with the default if absent. Removing a field is a breaking change and bumps the minor version.

`save_config` always writes the full known schema. Unknown fields read from `config.json` are preserved (forward-compat for downgrades).

## Examples

### Minimum viable config (current)

```json
{
  "model": {
    "name": "faster-whisper-large-v3",
    "url": "https://smch.ir/models/models--Systran--faster-whisper-large-v3.zip",
    "md5": "https://smch.ir/models/models--Systran--faster-whisper-large-v3.zip.md5"
  },
  "model_path": "C:\\Users\\Owner\\AppData\\Local\\WhisperProject\\models\\faster-whisper-large-v3",
  "device": "auto",
  "compute_type": "int8",
  "parallel_workers": 2,
  "download_folder": ""
}
```

### GPU + multiple workers

```json
{
  "device": "cuda",
  "compute_type": "float16",
  "parallel_workers": 4
}
```

### CPU-only, minimum resource usage

```json
{
  "device": "cpu",
  "compute_type": "int8",
  "parallel_workers": 1
}
```

## Manual override files

Phase 1.2 introduces `config.local.json` — a file with the same shape as `config.json` whose fields override the defaults. Useful for keeping a clean baseline in source control while letting each machine customize paths.
