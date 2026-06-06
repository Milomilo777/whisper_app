# Configuration Reference

`config.json` lives at `%LOCALAPPDATA%\WhisperProject\config.json` on Windows (`platformdirs.user_config_dir("WhisperProject")` on every platform). On first launch, a legacy `config.json` next to `gui.py` is copied to the new location and the original renamed to `.migrated.bak`. Subsequent launches read only from the platformdirs path.

The file is read once at startup and written when the user changes a persisted setting (download folder, subtitle preferences, theme, etc.). Manual edits take effect on next launch.

## Three-level merged configuration (P4-1)

The effective config is merged from **three layers**, in priority order:

1. **Local `config.json`** — the user's file (described above). **Highest priority.** A local override file is the place for expert / per-machine overrides; it may set ANY key, including the local-only ones the online layer is forbidden from touching (paths, API keys, credentials, the model hub folder, user preferences).
2. **Online app config** — a JSON the maintainer hosts at `config_url`, fetched on startup. It lets **app-level** settings change **without redistributing the program** (the model catalog, the usage-stats endpoint, the latest version, the ffplay download links). It is restricted to a **safe allowlist** (`stats_url`, `latest_version`, `ffplay_downloads`, `model_catalog`) — it can **never** override user-private / local-only keys.
3. **Hard-coded `DEFAULT_CONFIG`** — the in-code baseline. **Lowest priority.**

A key missing from a higher-priority layer falls through to the next. Dict-valued keys (e.g. `model`, `model_catalog`) are deep-merged, so a partial override keeps the sibling keys from the lower layer.

The online fetch is **fail-safe**: a short timeout, the last good response cached under `user_cache_dir()/app_config_cache.json`, and a fall-through to the cache (then to nothing) when offline. It **never blocks or crashes startup**. The hot worker-subprocess code paths (`core.transcriber` import, `core.worker.main`, the faster-whisper model load) skip the fetch entirely (`load_config(fetch_online=False)`), so a worker spawn is never delayed by the network.

The merge itself is pure and testable: `core.config.merge_config_sources(hardcoded, online, local)`. The fetch is the separate `core.config.fetch_online_config(url, cache_path=...)` helper. `core.config.load_config()` wires the two together; `load_config(fetch_online=False)` uses only the local + hard-coded layers.

| Field | Type | Default | Description |
|---|---|---|---|
| `config_url` | string | `https://smch.ir/whisper/app_config.json` (placeholder — owner sets the real URL) | URL of the online app-level config JSON. Fetched best-effort on startup; cached for offline fallback. Empty disables the online layer. A local `config.json` may override this (e.g. a staging URL). |
| `model_catalog` | object | `{}` | Online/local-supplied catalog of selectable models, same shape as `core.model_manager.MODEL_REGISTRY` (`slug → {label, name, url, md5, approx_size_gb}`). Overlaid on the built-in catalog so new models can ship without an app update. **Allowlisted** for the online layer. |
| `stats_url` | string | `""` | Usage-stats POST endpoint (the app POSTs anonymous stats here when telemetry is opted in). **Allowlisted** for the online layer so it can be set/changed remotely. |
| `latest_version` | string | `""` | Newest published version string (informational; complements the GitHub update check). **Allowlisted** for the online layer. |
| `ffplay_downloads` | object | `{}` | Platform → ffplay download URL map (e.g. `{"windows": "...", "macos": "..."}`) for the Video-Tiling ffplay binary (not bundled). **Allowlisted** for the online layer. |

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
| `whisper_model` | string | `"large-v3"` | Slug of the selected model in the merged catalog (built-in `MODEL_REGISTRY` + online `model_catalog`). Set by the **Advanced > Whisper model** combo, which also rewrites `model` + `model_path` so the new model downloads on the next transcription. See the Models section below. |
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

### Models (config-driven catalog, P4-2)

The selectable model list shown in **Advanced > Whisper model** comes from the **merged catalog**: the built-in `core.model_manager.MODEL_REGISTRY` overlaid with the `model_catalog` key from the merged config (so the online config can add or re-point models without an app update). Read it via `core.model_manager.catalog_models(config)` and `catalog_resolve_entry(config, slug)`.

`large-v3` is the **default** (best accuracy, slower). Built-in entries:

| Slug | `model.name` | Notes |
|---|---|---|
| `large-v3` | `faster-whisper-large-v3` | **Default.** Best accuracy, ~3 GB. |
| `large-v3-turbo` | `faster-whisper-large-v3-turbo` | ~5× faster, similar accuracy, ~1.6 GB. |
| `distil-large-v3.5` | `faster-distil-whisper-large-v3.5` | Fastest English-only, ~1.5 GB. |
| `medium` | `faster-whisper-medium` | Faster, lower accuracy, ~1.5 GB. **Owner action: confirm/upload the `models--Systran--faster-whisper-medium.zip` (+ `.md5`) artifact on `smch.ir`** (or point the online `model_catalog` at the real location) before this entry can download. |

A bigger/denser model is slower — `large-v3` stays the default; the combo just lets the user pick. Switching the model triggers `ensure_model` for the new slug on the next load.

To add a model from the **online** config (no app update), put it under `model_catalog` in the hosted JSON:

```json
{
  "model_catalog": {
    "my-new-model": {
      "label": "My New Model (~2 GB)",
      "name": "faster-whisper-my-new-model",
      "url": "https://host/models--Systran--faster-whisper-my-new-model.zip",
      "md5": "https://host/models--Systran--faster-whisper-my-new-model.zip.md5",
      "approx_size_gb": 2.0
    }
  }
}
```

A malformed catalog entry (missing `name`/`url`/`md5`, or not a dict) is skipped so a bad online payload never breaks the picker — the built-ins always survive.

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

### Google Cloud Speech-to-Text (optional, service-account)

A second, more capable cloud option, selected by setting
`transcribe_backend` to `google_cloud_stt` (in **Advanced > Backend** —
labelled "Google Cloud Speech-to-Text"). Unlike the Gemini backend above,
it authenticates with a **service-account JSON key file** (not a pasted
API key) and uses the official `google-cloud-speech` **v2** client, which
is installed **on demand on first use** (it is not bundled). Like every
cloud option it **uploads your audio to Google** and breaks the offline
guarantee. Full setup, the Standard-vs-Batch trade-off, and the honest
usage note are in [`CLOUD_STT_GOOGLE.md`](CLOUD_STT_GOOGLE.md).

| Field | Type | Default | Description |
|---|---|---|---|
| `gcloud_stt_credentials_json` | string | `""` | Absolute path to the service-account JSON key file downloaded from the Google Cloud console. Empty = the backend reports a clear "pick your JSON file" error. The `project_id` is read out of this file. |
| `gcloud_stt_model` | string | `"chirp_2"` | The v2 recognizer model. `"chirp_2"` is the default — it supports language auto-detect and multilingual input (the older `"long"` rejected `"auto"`). `"long"` / `"short"` / `"telephony"` are also valid. A config value so a renamed/newer model needs no code change; an unavailable model surfaces a clear error, not a crash. |
| `gcloud_stt_location` | string | `"us-central1"` | API location/region. `"us-central1"` is the default region that hosts `chirp_2`; `"global"` works for the common older models and some newer models are region-only (e.g. `"europe-west4"`), in which case the backend talks to that regional endpoint. |
| `gcloud_stt_batch_mode` | bool | `false` | `false` = **Standard / online** chunked-inline `recognize()` (~$0.016/min, no bucket needed — the default). `true` = the cheaper GCS **Batch** path (`BatchRecognize`, ~$0.004/min, ~75 % cheaper) at the cost of up to ~24 h turnaround. Batch **requires** `gcloud_stt_bucket`. |
| `gcloud_stt_bucket` | string | `""` | A Google Cloud Storage bucket name the service account can write to (the `gs://` target). Required **only** for batch mode — the decoded audio is uploaded there, transcribed, then the blob is deleted. The service account needs **Storage Object Admin** on it. |
| `gcloud_stt_diarization` | bool | `false` | Enable speaker diarization (adds a per-segment `speaker` label). |
| `gcloud_stt_min_speakers` | int | `0` | Lower bound on the diarized speaker count. `0` = let Google decide. |
| `gcloud_stt_max_speakers` | int | `0` | Upper bound on the diarized speaker count. `0` = let Google decide. |
| `gcloud_stt_chunk_seconds` | int | `55` | Standard-mode chunk length (seconds). Kept under the ~1-minute online-`recognize()` inline cap; each chunk's timestamps are offset and stitched back into one timeline. |
| `gcloud_stt_batch_timeout_s` | int | `3600` | How long (seconds) to wait on the batch long-running operation before giving up. Batch turnaround can be long; raise this if a large job times out. |
| `gcloud_stt_minutes_used` | float | `0.0` | Minutes of audio transcribed via this backend **this calendar month**, accumulated locally after each successful run. Resets when `gcloud_stt_minutes_month` rolls over. The real $300-credit balance is NOT readable from a service-account key, so this local counter (and its cost estimate) is the only usage signal shown. |
| `gcloud_stt_minutes_month` | string | `""` | The `"YYYY-MM"` marker for the month `gcloud_stt_minutes_used` belongs to. When the current month differs, the counter resets to 0 before the run is added. |
| `gcloud_stt_free_minutes_cap` | int | `60` | Informational free-tier figure (60 min/month) shown in the live usage display. Not enforced — it does not block transcription. |

### Web / LAN access (optional local HTTP job server)

Backs both the `gui.py serve` CLI and the one-click **Web / LAN access**
tab. The server is a stdlib-only HTTP server (no new dependency) that lets
a phone or another PC send a file or a URL to transcribe from a browser.
It binds **loopback (`127.0.0.1`) by default** — no Windows firewall prompt
— and LAN sharing is an explicit opt-in. See [`SERVER.md`](SERVER.md).

| Field | Type | Default | Description |
|---|---|---|---|
| `server_port` | int | `8765` | Default listen port for the server. If the port is busy when started from the tab, a free-port fallback picks another and shows the actual URL. |
| `server_max_upload_mb` | int | `512` | Caps a single browser upload (MB). The worker's ~1 MB command guard does NOT cover browser uploads, so this is the upload size limit for the web path. |
| `server_share_lan` | bool | `false` | When `true`, the tab's Start binds `0.0.0.0` (all interfaces — other devices on the network can reach it) instead of `127.0.0.1` (this machine only). Persisted from the **Share on local network** checkbox; this is the path that triggers the Windows firewall prompt. The CLI uses `--lan` instead of this key. |
| `server_token` | string | `""` | Optional shared-secret password. When non-empty, every request must present it (`X-Auth-Token` header or `?token=` query). Stored in **cleartext** here, consistent with cookies / API keys (the file is per-user under `%LOCALAPPDATA%\WhisperProject` and is not encrypted). |

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

## Manual / expert override files

Two override mechanisms exist, both higher-priority than the hard-coded defaults:

- The user's **`config.json`** itself is the highest-priority layer in the three-level merge (see *Three-level merged configuration* above) — edit it for per-machine expert overrides, including the local-only keys the online layer cannot touch.
- A per-folder **`.whisperproject.json`** (nearest one walking up from the input file) deep-merges on top for that job only — see `core.config.merge_project_overrides`. Wrong-typed keys are dropped + logged.
