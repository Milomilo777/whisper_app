from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import platformdirs

logger = logging.getLogger(__name__)

APP_NAME = "WhisperProject"
APP_AUTHOR = False  # platformdirs: omit author segment on Windows

DEFAULT_CONFIG = {
    "model": {
        "name": "faster-whisper-large-v3",
        "url": "https://smch.ir/models/models--Systran--faster-whisper-large-v3.zip",
        "md5": "https://smch.ir/models/models--Systran--faster-whisper-large-v3.zip.md5",
    },
    "model_path": "",
    "device": "auto",
    "compute_type": "int8",
    "parallel_workers": 2,
    "download_folder": "",
    "download_subtitles_enabled": False,
    "download_subtitle_lang": "Automatic",
    "auto_update_yt_dlp": False,
    "last_yt_dlp_update_check": "",
    "theme": "dark",
    "log_level": "INFO",
    # Phase 2a — Whisper masterpiece
    "vad_enabled": True,
    "vad_min_silence_ms": 500,
    "vad_threshold": 0.5,
    "vad_speech_pad_ms": 400,
    "word_timestamps": False,
    "output_formats": ["srt", "json"],
    "batch_size": 16,
    "initial_prompt": "",
    "hotwords": "",
    # Phase 3a — yt-dlp killer features
    "auto_transcribe_after_download": False,
    "sponsorblock_categories": [],
    # v0.7.1 — diarization (off by default; opt-in via Transcribe tab)
    "diarization_enabled": False,
    "diarization_num_speakers": -1,         # -1 = auto-cluster
    "diarization_cluster_threshold": 0.5,
    # v0.7.1 — Transcribe tab quick options
    "transcribe_language": "Auto",   # display name; resolves to code at task build
    # v0.7.1 — UX persistence + new features
    "window_geometry": "",
    "chime_on_complete": True,
    # v0.7.1 — filename templating; tokens {base}, {ext}, {lang}, {date}, {speaker_count}
    "output_filename_template": "{base}.{ext}",
    # v0.7.1 — watched folder (off by default)
    "watched_folder": "",
    "watched_folder_enabled": False,
    # v0.7.1 — backend selection (faster_whisper is the default and bundled
    # default; whisper_cpp is opt-in via pywhispercpp; future backends slot in
    # here).
    "transcribe_backend": "faster_whisper",
}


def _legacy_config_path() -> str:
    base = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else __file__)
    return os.path.abspath(os.path.join(base, "..", "config.json"))


def user_config_dir() -> Path:
    return Path(platformdirs.user_config_dir(APP_NAME, APP_AUTHOR))


def user_cache_dir() -> Path:
    return Path(platformdirs.user_cache_dir(APP_NAME, APP_AUTHOR))


def user_log_dir() -> Path:
    return Path(platformdirs.user_log_dir(APP_NAME, APP_AUTHOR))


def user_data_dir() -> Path:
    return Path(platformdirs.user_data_dir(APP_NAME, APP_AUTHOR))


def config_path() -> str:
    return str(user_config_dir() / "config.json")


def migrate_config_location() -> str:
    """Move a legacy next-to-source config.json into the platformdirs path.

    Returns the new path. Idempotent: if the new file already exists, the legacy
    one is renamed to .migrated.bak and not copied. Safe to call on every launch.
    """
    new_path = config_path()
    legacy = _legacy_config_path()
    user_config_dir().mkdir(parents=True, exist_ok=True)

    if not os.path.exists(legacy):
        return new_path
    if os.path.abspath(legacy) == os.path.abspath(new_path):
        return new_path

    if not os.path.exists(new_path):
        try:
            shutil.copy2(legacy, new_path)
            logger.info("Migrated legacy config.json from %s to %s", legacy, new_path)
        except OSError as e:
            logger.error("Failed to migrate legacy config: %s", e)
            return new_path

    backup = legacy + ".migrated.bak"
    try:
        if os.path.exists(backup):
            os.unlink(backup)
        os.replace(legacy, backup)
        logger.info("Renamed legacy config to %s", backup)
    except OSError as e:
        logger.warning("Could not rename legacy config to .migrated.bak: %s", e)

    return new_path


def _drive_is_mounted(path: str | Path) -> bool:
    if os.name != "nt":
        return True
    try:
        p = Path(str(path))
    except (TypeError, ValueError):
        return False
    if not p.drive:
        return True
    return Path(p.drive + os.sep).exists()


def _apply_runtime_fallbacks(config: dict[str, Any]) -> dict[str, Any]:
    model_path = (config.get("model_path") or "").strip()
    if not model_path or not _drive_is_mounted(model_path):
        model_name = (config.get("model") or {}).get("name") or "whisper-model"
        if model_name.startswith("models--"):
            folder_name = model_name
        else:
            folder_name = f"models--Systran--{model_name}"
        fallback = user_cache_dir() / "models" / folder_name
        if model_path:
            logger.warning(
                "model_path %r is unreachable on this machine; "
                "using fallback %s. Change a setting in the UI to make it permanent.",
                model_path,
                fallback,
            )
        config["model_path"] = str(fallback)

    download_folder = (config.get("download_folder") or "").strip()
    if download_folder and not _drive_is_mounted(download_folder):
        logger.warning(
            "download_folder %r is unreachable; clearing", download_folder
        )
        config["download_folder"] = ""

    return config


def _merge_with_defaults(loaded: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    for key, value in loaded.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def load_config() -> dict[str, Any]:
    migrate_config_location()
    path = config_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
    except FileNotFoundError:
        logger.warning("config.json not found at %s; using defaults", path)
        return _apply_runtime_fallbacks(json.loads(json.dumps(DEFAULT_CONFIG)))
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to read config.json (%s); using defaults", e)
        try:
            os.replace(path, path + ".corrupt")
            logger.info("Moved corrupt config to %s.corrupt", path)
        except OSError:
            pass
        return _apply_runtime_fallbacks(json.loads(json.dumps(DEFAULT_CONFIG)))

    if not isinstance(loaded, dict):
        logger.error("config.json is not a JSON object; using defaults")
        return _apply_runtime_fallbacks(json.loads(json.dumps(DEFAULT_CONFIG)))

    return _apply_runtime_fallbacks(_merge_with_defaults(loaded))


def save_config(config: dict[str, Any]) -> None:
    path = config_path()
    directory = os.path.dirname(path) or "."
    Path(directory).mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".config-", suffix=".tmp", dir=directory
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# Per-folder project overrides --------------------------------------------------

PROJECT_FILE_NAME = ".whisperproject.json"


def find_project_file(start: str | Path) -> Path | None:
    """Walk up from ``start`` looking for ``.whisperproject.json``.

    Returns the first match or ``None`` when none is found. We stop
    at the filesystem root so a misconfigured cwd never causes an
    infinite loop. Both files and directories are valid starting
    points — for a file we begin from its parent directory.
    """
    try:
        p = Path(str(start)).resolve()
    except (OSError, ValueError):
        return None
    if p.is_file():
        p = p.parent
    for candidate in [p, *p.parents]:
        f = candidate / PROJECT_FILE_NAME
        if f.is_file():
            return f
    return None


def load_project_overrides(start: str | Path) -> dict[str, Any]:
    """Read the nearest ``.whisperproject.json`` and return its keys.

    Returns an empty dict when the file is absent, malformed, or not
    a JSON object. Never raises — a bad project file should not
    block a transcription, only the in-file override.
    """
    f = find_project_file(start)
    if f is None:
        return {}
    try:
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read project overrides at %s", f)
        return {}
    if not isinstance(data, dict):
        logger.warning(
            "Project override at %s is not a JSON object; ignoring", f
        )
        return {}
    return data


def merge_project_overrides(
    base_config: dict[str, Any], source_path: str | Path
) -> dict[str, Any]:
    """Return a shallow copy of ``base_config`` with overrides applied.

    Walks up from ``source_path`` to find the nearest
    ``.whisperproject.json`` and overlays its keys on top of
    ``base_config``. Dict-valued keys are deep-merged (one level)
    so the user can override e.g. ``model.name`` without forcing the
    whole model dict.
    """
    overrides = load_project_overrides(source_path)
    if not overrides:
        return base_config
    merged: dict[str, Any] = json.loads(json.dumps(base_config))
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k].update(v)
        else:
            merged[k] = v
    return merged
