"""Application config: JSON file at the OS-correct platformdirs path.

The basic version exposes ZERO of these knobs in the UI. They exist
so the worker has a single source of truth and so the build can stamp
the model URL / MD5 manifest in one place.

Public surface:

* ``DEFAULT_CONFIG`` — the baked-in defaults.
* :func:`load_config` — merge defaults with the user's saved file (if any).
* :func:`save_config` — atomic write of the merged dict.
* :func:`user_config_dir`, :func:`user_cache_dir`, :func:`user_log_dir`,
  :func:`user_data_dir` — platformdirs wrappers used everywhere.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

import platformdirs

# Module-level lock serialises concurrent save_config calls — on
# Windows os.replace fails with PermissionError when another thread
# is mid-replace on the same path. The lock collapses the race.
_SAVE_LOCK = threading.Lock()

logger = logging.getLogger(__name__)

APP_NAME = "WhisperProjectBasic"
APP_AUTHOR = False  # platformdirs: omit author segment on Windows


DEFAULT_CONFIG: dict[str, Any] = {
    # Model — single fixed choice for the basic edition.
    "model": {
        "name": "faster-whisper-large-v3",
        "url": "https://smch.ir/models/models--Systran--faster-whisper-large-v3.zip",
        "md5": "https://smch.ir/models/models--Systran--faster-whisper-large-v3.zip.md5",
    },
    # Where the model files live (resolved at runtime via hub_folder
    # + model.name when this is blank, see _apply_runtime_fallbacks).
    "model_path": "",
    # Hub folder — first-run dialog populates this.
    "hub_folder": "",
    # Hardware — "auto" lets core.hardware pick at startup.
    "device": "auto",
    "compute_type": "int8",
    # VAD on by default — cuts silence cleanly with very low cost.
    "vad_enabled": True,
    # Language: "auto" → faster-whisper detects per file.
    "language": "auto",
    # Output formats — fixed list for the basic edition.
    "output_formats": ["srt", "json", "txt"],
    # Log verbosity.
    "log_level": "INFO",
    # Recent files (last 5) for the File → Open recent submenu.
    "recent_files": [],
}


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


def _drive_is_mounted(path: str | Path) -> bool:
    if os.name != "nt":
        return True
    try:
        p = Path(str(path))
    except (TypeError, ValueError):
        return False
    if not p.drive:
        return True
    drive = p.drive
    # UNC paths can stall on disconnected shares for ~30 s if probed
    # via exists(); treat as available and let downstream I/O surface
    # the real error.
    if drive.startswith("\\\\") or drive.startswith("//"):
        return True
    return Path(drive + os.sep).exists()


def _apply_runtime_fallbacks(config: dict[str, Any]) -> dict[str, Any]:
    """Fill in derived paths the user never has to type.

    * ``model_path`` defaults to ``<hub_folder>/models--Systran--<name>``
      when the user has picked a hub but no explicit path.
    * If the saved ``model_path`` lives on an unmounted drive, fall
      back to the hub-derived value instead of letting downstream
      code see a dead path.
    """
    from . import hub as _hub  # local import to avoid bootstrap cycle

    model_name = (config.get("model") or {}).get("name") or ""
    hub_folder = (config.get("hub_folder") or "").strip()
    model_path = (config.get("model_path") or "").strip()

    needs_recompute = (
        not model_path
        or not _drive_is_mounted(model_path)
    )
    if needs_recompute and model_name:
        effective_hub = hub_folder or str(_hub.default_hub_folder())
        try:
            fallback = _hub.model_folder_for(effective_hub, model_name)
        except ValueError:
            fallback = user_cache_dir() / "models" / "whisper-model"
        if model_path and not _drive_is_mounted(model_path):
            logger.warning(
                "model_path %r is unreachable; using fallback %s",
                model_path, fallback,
            )
        config["model_path"] = str(fallback)
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
    """Read ``config.json``; merge with defaults; apply runtime fallbacks.

    A missing file is fine — defaults are returned. A corrupt file is
    renamed to ``.corrupt`` and defaults are used so launch never
    blocks on a hand-edited JSON typo.
    """
    path = config_path()
    user_config_dir().mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
    except FileNotFoundError:
        return _apply_runtime_fallbacks(json.loads(json.dumps(DEFAULT_CONFIG)))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, ValueError) as e:
        logger.error("Failed to read config.json (%s); using defaults", e)
        try:
            os.replace(path, path + ".corrupt")
        except OSError:
            pass
        return _apply_runtime_fallbacks(json.loads(json.dumps(DEFAULT_CONFIG)))

    if not isinstance(loaded, dict):
        logger.error("config.json is not a JSON object; using defaults")
        return _apply_runtime_fallbacks(json.loads(json.dumps(DEFAULT_CONFIG)))

    merged = _merge_with_defaults(loaded)
    # Coerce wrong-type values back to defaults — a hand-edited
    # `"vad_enabled": "yes"` would otherwise survive the merge and
    # break downstream type assumptions.
    for k, default in DEFAULT_CONFIG.items():
        if k in merged and merged[k] is not None and not isinstance(
            merged[k], type(default)
        ):
            if isinstance(default, bool) and isinstance(merged[k], int):
                merged[k] = bool(merged[k])
                continue
            if isinstance(default, (int, float)) and isinstance(
                merged[k], (int, float)
            ):
                try:
                    merged[k] = type(default)(merged[k])
                    continue
                except (TypeError, ValueError):
                    pass
            logger.warning(
                "config key %r has wrong type %s (expected %s); "
                "reverting to default", k,
                type(merged[k]).__name__, type(default).__name__,
            )
            merged[k] = json.loads(json.dumps(default))
    return _apply_runtime_fallbacks(merged)


def save_config(config: dict[str, Any]) -> None:
    """Atomic write: temp file in the target dir, then os.replace."""
    with _SAVE_LOCK:
        path = config_path()
        directory = os.path.dirname(path) or "."
        Path(directory).mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix=".config-", suffix=".tmp", dir=directory,
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


def add_recent_file(config: dict[str, Any], file_path: str, *, limit: int = 5) -> None:
    """Push ``file_path`` to the front of ``recent_files``, deduped, cap N.

    Mutates ``config`` in place. The caller is responsible for calling
    :func:`save_config` afterwards.
    """
    if not file_path:
        return
    recent = list(config.get("recent_files") or [])
    # Case-insensitive de-dupe on Windows.
    if sys.platform == "win32":
        key = file_path.casefold()
        recent = [p for p in recent if isinstance(p, str) and p.casefold() != key]
    else:
        recent = [p for p in recent if isinstance(p, str) and p != file_path]
    recent.insert(0, file_path)
    config["recent_files"] = recent[:limit]
