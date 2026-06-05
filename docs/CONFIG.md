# Configuration Reference

`config.json` lives at `%LOCALAPPDATA%\WhisperProject\config.json` on Windows (`platformdirs.user_config_dir("WhisperProject")` on every platform). On first launch, a legacy `config.json` next to `gui.py` is copied to the new location and the original renamed to `.migrated.bak`. Subsequent launches read only from the platformdirs path.

The file is read once at startup and written when the user changes a persisted setting (download folder, subtitle preferences, theme, etc.). Manual edits take effect on next launch.

## Where things live (Phase 1.2)

| Purpose | Path (Windows) | Helper |
|---|---|---|
| `config.json` | `%LOCALAPPDATA%\WhisperProject\config.json` | `core.config.config_path()` |
| Model hub (default `hub_folder`) | `%LOCALAPPDATA%\WhisperProject\Cache\models\` | `core.hub.default_hub_folder()` |
| Cached models (default `model_path`) | `%LOCALAPPDATA%\WhisperProject\Cache\models\<model-folder>\` | `core.config.user_cache_dir()` |
| Rotating logs | `%LOCALAPPDATA%\WhisperProject\Logs\app.log` (5 MB × 3) | `core.config.user_log_dir()` |

`platformdirs` chooses the equivalent paths on macOS and Linux. The "Help → Open log folder" menu item opens the log directory.

## Field reference

| Field | Type | Default | Description |
|---|---|---|---|
| `model` | object | (see below) | The active model's source and verification info |
| `model.name` | string | `"faster-whisper-large-v3"` | Display name in logs |
| `model.url` | string | `https://smch.ir/models/...zip` | ZIP archive of the model |
| `model.md5` | string | `<url>.md5` | URL of the per-file MD5 manifest |
| `hub_folder` | string | `""` (first-run dialog) | Parent folder that holds the `models--Vendor--name` model directories. Empty triggers the first-run picker, which pre-fills `%LOCALAPPDATA%\WhisperProject\Cache\models` — a per-user, always-writable location (never the Program Files install dir). |
| `model_path` | string | (derived from `hub_folder`) | Absolute path where the model is extracted. When empty it is derived at startup from `hub_folder + model.name`; with no hub set it falls back to `%LOCALAPPDATA%\WhisperProject\Cache\models\<name>`. A non-empty value is a per-model override. |
| `device` | string | `"auto"` | `"auto"` / `"cuda"` / `"cpu"`. With `"auto"`, the autodetect only selects CUDA when ctranslate2 reports a GPU **and** the cuDNN/cuBLAS runtime libraries actually load; otherwise it falls back to CPU. At model-load time a CUDA load that still fails self-heals to CPU `int8` instead of crashing the worker — the active tab shows a GPU/CPU badge and (once) a "running on CPU (slower)" warning. |
| `compute_type` | string | `"int8"` | `faster-whisper` compute type. Common values: `int8`, `int8_float16`, `float16`, `float32`. `int8` is the smallest/fastest on CPU; `float16` is preferred on GPU. |
| `cpu_warning_shown` | bool | `false` | Set to `true` after the one-time "running on CPU (slower)" warning has been shown, so it never repeats. The warning only appears when a GPU was detected-but-unusable or a CUDA→CPU downgrade happened — never on a genuine CPU-only machine. |
| `parallel_workers` | int | `2` | Maximum simultaneous transcription worker subprocesses. Each loads the model and uses ~3 GB RAM (or VRAM on GPU). |
| `download_folder` | string | `""` | Default destination for video downloads. Updated by the Folder Browse button. |
| `download_subtitles_enabled` | bool | `false` | Last state of the subtitle checkbox on the Download Videos tab |
| `download_subtitle_lang` | string | `"Automatic"` | Last-selected subtitle language (display name from `SUBTITLE_LANGUAGES`, not the code). |
| `theme` | string | `"dark"` | `"light"` / `"dark"` / `"system"` — applied via `sv_ttk` (Phase 1.1). `"system"` falls back to `"dark"` if the optional `darkdetect` package is not installed. |
| `log_level` | string | `"INFO"` | Python logging level for the file handler (Phase 1.3) |
| `auto_update_yt_dlp` | bool | `false` | Phase 0 fix to AUDIT A1: yt-dlp's `--update` is now opt-in and gated to once per launch (with `last_yt_dlp_update_check`). When this is `false`, downloads never wait on `--update`. |
| `last_yt_dlp_update_check` | string (ISO date) | `""` | Timestamp of the last update attempt (used by the once-per-day guard inside `maybe_update_yt_dlp`) |
| `update_check_enabled` | bool | `true` | Opt-in GitHub "update available" check (`core.updates`). When on, a quiet launch check runs at most once per day (throttled by `last_update_check`) and stays SILENT unless a newer release exists — never nagging when up to date, offline, or when the repo is private (a 404 is swallowed). When a newer release is found it offers to open the download page. It is **notify-only**: it never auto-downloads or auto-installs. Set to `false` to disable the quiet launch check; the **Help → Check for updates...** menu item still runs on demand. |
| `last_update_check` | string (ISO date) | `""` | Date (`YYYY-MM-DD`) of the last *quiet* update check, used only for the once-per-day throttle. The manual **Help → Check for updates...** menu item ignores it. |

### Video Tiling

Persisted choices for the Video Tiling tab (the `core.tiling.TilingController`
video-wall engine). All are remembered between launches.

| Field | Type | Default | Description |
|---|---|---|---|
| `tiling_quality` | string | `"Auto"` | yt-dlp quality band: `Auto` / `1080p` / `720p` / `480p` / `360p` / `240p` / `144p`. `Auto` lowers resolution as the grid gets denser (a dense grid needs far less than 1080p). Always ends in `/best` so playback never fails on a missing resolution. |
| `tiling_mute` | bool | `false` | Mute audio. In a multi-monitor wall only the first window keeps audio anyway (to avoid echo); this mutes that one too. |
| `tiling_multi_monitor` | bool | `false` | Fan the one download out to one `ffplay` window per selected monitor (a multi-screen wall) instead of a single full-screen window. |
| `tiling_selected_monitors` | array of int | `[]` | Spatial monitor indices (from `core.monitors`, `0` = left-most) ticked in the **Monitors…** chooser. Empty = all monitors when multi-monitor is on, or the primary when off. Stale indices (a monitor that has been unplugged) are ignored at start. |
| `tiling_auto_restart` | bool | `true` | Reconnect automatically with exponential backoff (3s→30s) when the stream drops; after repeated quick failures the engine self-heals by updating yt-dlp. Off = a drop just stops. |

### Cloud Speech-to-Text (optional, Google Gemini API)

Off by default. These keys only take effect when `transcribe_backend` is
set to `cloud_stt` (in **Advanced > Backend**). Selecting this backend
**uploads your audio to Google** — it breaks the offline guarantee. See
[`CLOUD_STT.md`](CLOUD_STT.md) for the full setup, privacy, and quota
notes. The API key is stored in **cleartext** in `config.json`,
consistent with how cookies/paths are already stored (the file is
per-user under `%LOCALAPPDATA%\WhisperProject` and is not encrypted).

| Field | Type | Default | Description |
|---|---|---|---|
| `cloud_stt_api_key` | string | `""` | Google API key pasted from aistudio.google.com. Empty = the backend reports "No Google API key set". Stored in cleartext. |
| `cloud_stt_model` | string | `"gemini-3.5-flash"` | The Gemini model used for transcription. A config value so a renamed/newer model needs no code change; an unavailable model surfaces a clear "model not found" error (HTTP 404), not a crash. |
| `cloud_stt_minutes_used` | float | `0.0` | Minutes of audio transcribed via the cloud backend so far, accumulated **locally** after each successful run. The dollar free-credit balance is NOT readable from an API key, so this local counter is the only usage signal shown. |
| `cloud_stt_free_minutes_cap` | int | `60` | Informational free-tier figure shown in the Advanced dialog. Not enforced — it does not block transcription. |
| `cloud_stt_chunk_seconds` | int | `480` | Window size (seconds, ~8 min) the audio is split into before upload. Smaller windows give finer progress/cancel granularity and smaller uploads; larger windows mean fewer requests. |

## Coming in later phases

| Field | Type | Default | Description |
|---|---|---|---|
| `crash_reporting` | bool | `false` | Opt-in to Sentry crash reports (ROADMAP 1.8) |

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
  "hub_folder": "C:\\Users\\Owner\\AppData\\Local\\WhisperProject\\Cache\\models",
  "model_path": "",
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
