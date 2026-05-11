import json
import logging
import os
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

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
}


def config_path():
    base = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else __file__)
    return os.path.abspath(os.path.join(base, "..", "config.json"))


def user_cache_dir():
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        return Path(base) / "WhisperProject"
    return Path.home() / ".cache" / "WhisperProject"


def _drive_is_mounted(path):
    if os.name != "nt":
        return True
    try:
        p = Path(str(path))
    except (TypeError, ValueError):
        return False
    if not p.drive:
        return True
    return Path(p.drive + os.sep).exists()


def _apply_runtime_fallbacks(config):
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


def _merge_with_defaults(loaded):
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    for key, value in loaded.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def load_config():
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


def save_config(config):
    path = config_path()
    directory = os.path.dirname(path) or "."
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
