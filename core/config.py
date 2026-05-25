from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

import platformdirs

# Module-level lock serialises concurrent save_config calls — on
# Windows os.replace fails with PermissionError when another thread
# is also mid-replace on the same path; the lock collapses the race.
_SAVE_LOCK = threading.Lock()

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
    # Browser to read cookies from for yt-dlp, so login-walled / age-gated
    # content downloads using the user's logged-in session (Facebook,
    # Instagram, TikTok stories; some YouTube Shorts). Empty = off. One of
    # brave/chrome/chromium/edge/firefox/opera/safari/vivaldi/whale,
    # optionally with yt-dlp's :PROFILE suffix.
    "cookies_from_browser": "",
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
    # v0.8 — hallucination detector (BoH + repetition + optional VAD
    # disagreement). Flags segments in the JSON output and the viewer.
    "hallucination_detect_enabled": True,
    # v0.8 — model picker. Slug into core.model_manager.MODEL_REGISTRY.
    # When the user changes this, the Advanced dialog also rewrites
    # ``model`` + ``model_path`` so ensure_model downloads the new one.
    "whisper_model": "large-v3",
    # v0.8 Phase 2 — Demucs vocal-separation pre-process (off by default;
    # heavy dep, large model). When True + demucs installed, transcribe
    # pipeline runs the input through Demucs first and feeds Whisper the
    # vocals stem.
    "demucs_enabled": False,
    # v0.8 Phase 2 — AI Layer. ``ai_enabled`` is the global on/off; the
    # actual model file lives at ``ai_model_path`` (empty = use the
    # default cache path under ``user_cache_dir()/llm/``).
    "ai_enabled": False,
    "ai_model_path": "",
    # v0.8 Phase 3 — auto-chapter markers in the JSON sidecar. Pure
    # heuristic by default; if ai_enabled + LLM loaded, chapter titles
    # are LLM-generated.
    "auto_chapters_enabled": True,
    "chapter_min_seconds": 60.0,
    "chapter_gap_seconds": 2.5,
    # v0.8 Phase 3 — cross-file voice fingerprint matching. When True
    # AND pyannote is installed AND voices.db has enrolled speakers,
    # the diariser's per-file SPEAKER_NN labels are renamed to the
    # matching enrolled names.
    "voiceprint_enabled": True,
    # Model Hub folder — the parent directory that holds one or more
    # ``models--Vendor--name`` subdirectories. Empty by default so
    # ``app.dialogs.hub_setup`` fires its first-run picker. The
    # picker pre-fills ``core.hub.default_hub_folder()`` =
    # ``<app_dir>/hub``. ``model_path`` (above) remains as a per-
    # model override for users with an existing config; new
    # installs derive ``model_path`` from ``hub_folder + model.name``.
    "hub_folder": "",
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
        logger.exception(
            "Could not rename legacy config to .migrated.bak (path=%s): %s",
            legacy, e,
        )

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
    # UNC paths (``\\server\share\...``) — checking exists() on a
    # disconnected share can block for the SMB resolution timeout
    # (~30 s). Treat them as available; downstream code surfaces
    # the I/O error if the share is really gone. The slow probe is
    # worse than a deferred error message.
    drive = p.drive
    if drive.startswith("\\\\") or drive.startswith("//"):
        return True
    return Path(drive + os.sep).exists()


def _apply_runtime_fallbacks(config: dict[str, Any]) -> dict[str, Any]:
    # Migration (v0.8 hub folder): if the user has a legacy
    # ``model_path`` set but no ``hub_folder``, derive the hub from
    # the parent directory of the model. This keeps existing
    # installs working without forcing the first-run dialog when
    # the user has clearly already pointed the app at a real model
    # folder. We don't clear model_path — it stays as an explicit
    # override per resolve order in core.hub.
    from . import hub as _hub  # local import to avoid bootstrap cycle
    model_path = (config.get("model_path") or "").strip()
    hub_folder = (config.get("hub_folder") or "").strip()
    if model_path and not hub_folder:
        derived = _hub.derive_hub_from_model_path(model_path)
        if derived:
            config["hub_folder"] = derived
            hub_folder = derived
            logger.info(
                "Migrated legacy model_path → hub_folder=%s "
                "(model_path kept as explicit override).",
                derived,
            )

    # Compute model_path on the fly when it's missing or unreachable,
    # using the hub folder when configured. Resolution order:
    # explicit model_path wins → hub_folder + model_name → the same
    # default_hub_folder() value the first-run dialog suggests.
    #
    # Using default_hub_folder() (not user_cache_dir) as the empty-
    # hub fallback fixes a re-download race: the hub-setup dialog is
    # asynchronous, so the worker subprocess starts before the user
    # has clicked OK. If the worker downloads to user_cache_dir and
    # the user then accepts the dialog's <app_dir>/hub default, the
    # next launch resolves model_path to <app_dir>/hub and triggers
    # a full re-download. Aligning the fallback with the dialog
    # default means "accept default" is a no-op for the model
    # location.
    if not model_path or not _drive_is_mounted(model_path):
        model_name = (config.get("model") or {}).get("name") or "whisper-model"
        effective_hub = hub_folder or str(_hub.default_hub_folder())
        source = "hub_folder" if hub_folder else "default_hub_fallback"
        try:
            fallback = _hub.model_folder_for(effective_hub, model_name)
        except ValueError:
            fallback = user_cache_dir() / "models" / "whisper-model"
            source = "cache_fallback_unnamed"
        if model_path:
            logger.warning(
                "model_path %r is unreachable on this machine; "
                "using fallback %s. Change a setting in the UI to make it permanent.",
                model_path,
                fallback,
            )
        # Audit B11 / QW-13: surface the resolution decision so a
        # "why is the model loading from this path?" question has a
        # one-line answer in the log.
        logger.info(
            "model_path_resolved path=%s source=%s exists=%s",
            fallback, source, fallback.exists(),
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
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, ValueError) as e:
        # UnicodeDecodeError is a ValueError that escapes the OSError
        # branch (e.g. cp1252 bytes saved by an external editor); the
        # original try/except missed it and crashed launch. ValueError
        # also catches any other JSON parser-internal raises.
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

    merged = _merge_with_defaults(loaded)
    # Coerce / drop wrong-type values for keys that ship a default —
    # e.g. parallel_workers="many" survives the merge and downstream
    # int() crashes later. Drop the bad value (restore default).
    for k, default in DEFAULT_CONFIG.items():
        if k in merged and merged[k] is not None and not isinstance(
            merged[k], type(default)
        ):
            # Special-case: bool defaults accept int (Python's bool is int).
            if isinstance(default, bool) and isinstance(merged[k], int):
                merged[k] = bool(merged[k])
                continue
            # Special-case: int defaults accept float (lossy but harmless).
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
                "reverting to default %r",
                k, type(merged[k]).__name__, type(default).__name__, default,
            )
            merged[k] = json.loads(json.dumps(default))
    return _apply_runtime_fallbacks(merged)


def _persistable_model_path(config: dict[str, Any]) -> str:
    """Return the ``model_path`` value that is safe to write to disk.

    ``_apply_runtime_fallbacks`` fills ``model_path`` in memory by
    deriving it from ``hub_folder`` (or the default hub) so the model
    loaders get a concrete path. That derived value must NOT be
    persisted: on the next load any non-empty ``model_path`` on a
    mounted drive is treated as an explicit per-model override that
    wins over ``hub_folder`` (see the resolution order in core.hub).
    Writing a derived path back therefore pins the model location to a
    stale folder and silently ignores the user's hub choice — most
    visibly, the first-run hub picker never takes effect because the
    default-hub path resolved during startup gets saved and then
    outranks the folder the user actually picked.

    Only a genuinely custom ``model_path`` — one that matches no
    hub-derived layout — is preserved. Anything that equals the path
    we would derive from the current ``hub_folder`` or the default hub
    is stored as "" so it re-derives cleanly on every launch.
    """
    from . import hub as _hub
    raw = (config.get("model_path") or "").strip()
    if not raw:
        return ""
    model = config.get("model")
    model_name = (model.get("name") if isinstance(model, dict) else "") or "whisper-model"
    hub_folder = (config.get("hub_folder") or "").strip()

    def _norm(p: str) -> str:
        return os.path.normcase(os.path.normpath(os.path.abspath(p)))

    derived: set[str] = set()
    for h in (hub_folder, str(_hub.default_hub_folder())):
        if not h:
            continue
        try:
            derived.add(_norm(str(_hub.model_folder_for(h, model_name))))
        except ValueError:
            continue
    return "" if _norm(raw) in derived else raw


def _persistable_download_folder(config: dict[str, Any]) -> str:
    """Return the ``download_folder`` value that is safe to write to disk.

    ``_apply_runtime_fallbacks`` clears ``download_folder`` to "" in
    memory when its drive is unmounted, so the UI re-prompts for this
    session. Persisting that "" would *permanently* forget a folder that
    merely lives on a removable / network drive detached at launch. So
    when the in-memory value is empty, fall back to the on-disk value if
    it points at a currently-unmounted drive — keeping the user's choice
    until the drive returns. (Same spirit as _persistable_model_path:
    don't let a session-only repair leak into a permanent loss.)
    """
    current = (config.get("download_folder") or "").strip()
    if current:
        return current
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            on_disk = json.load(f)
    except (OSError, ValueError):
        return current
    if not isinstance(on_disk, dict):
        return current
    prev = (on_disk.get("download_folder") or "").strip()
    if prev and not _drive_is_mounted(prev):
        return prev
    return current


def save_config(config: dict[str, Any]) -> None:
    # Serialise concurrent saves through _SAVE_LOCK — without this,
    # two threads racing to os.replace the same destination throw
    # PermissionError on Windows (NTFS rename semantics differ from
    # POSIX). Even though only one UI thread normally writes, the
    # Advanced dialog + tray + debounced auto-save can overlap.
    with _SAVE_LOCK:
        path = config_path()
        directory = os.path.dirname(path) or "."
        Path(directory).mkdir(parents=True, exist_ok=True)
        # Don't persist an auto-derived model_path — it would harden
        # into an explicit override that defeats hub_folder. See
        # _persistable_model_path for the full rationale.
        to_persist = dict(config)
        to_persist["model_path"] = _persistable_model_path(config)
        to_persist["download_folder"] = _persistable_download_folder(config)
        fd, tmp_path = tempfile.mkstemp(
            prefix=".config-", suffix=".tmp", dir=directory
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(to_persist, f, indent=2, ensure_ascii=False)
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
    block a transcription, only the in-file override. We catch
    ``UnicodeDecodeError`` explicitly because it's a ``ValueError``
    that bubbles past the OSError branch (e.g. when a user saves
    the file in cp1252 with a non-UTF8 character).

    Audit A11: returned dict is shape-validated against
    ``DEFAULT_CONFIG``. Entries whose type does NOT match the
    matching default are dropped + logged so a typo
    (``"diarization_enabled": "yes"``) surfaces as a warning
    instead of getting silently coerced to bool("yes") == True
    downstream.
    """
    f = find_project_file(start)
    if f is None:
        return {}
    try:
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Could not read project overrides at %s", f)
        return {}
    if not isinstance(data, dict):
        logger.warning(
            "Project override at %s is not a JSON object; ignoring", f
        )
        return {}
    return _validate_overrides(data, f)


def _validate_overrides(
    overrides: dict[str, Any], source: Path,
) -> dict[str, Any]:
    """Drop entries whose type doesn't match ``DEFAULT_CONFIG``.

    Permissive: keys not present in DEFAULT_CONFIG are allowed
    through unchanged (forward-compat with experimental config
    keys); known keys must have the right type or they're dropped.
    Bool defaults still accept ints (Python bool is int), and
    numeric defaults still accept floats / ints interchangeably —
    same coercion rules as ``load_config`` to keep behaviour
    consistent.
    """
    cleaned: dict[str, Any] = {}
    for key, value in overrides.items():
        if key not in DEFAULT_CONFIG:
            cleaned[key] = value
            continue
        default = DEFAULT_CONFIG[key]
        if value is None or isinstance(value, type(default)):
            cleaned[key] = value
            continue
        if isinstance(default, bool) and isinstance(value, int):
            cleaned[key] = bool(value)
            continue
        if isinstance(default, (int, float)) and isinstance(value, (int, float)):
            try:
                cleaned[key] = type(default)(value)
                continue
            except (TypeError, ValueError):
                pass
        logger.warning(
            "Project override at %s has wrong type for %r: %s "
            "(expected %s); dropping.",
            source, key, type(value).__name__, type(default).__name__,
        )
    return cleaned


def deep_merge_dicts(dest: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``src`` into ``dest`` and return ``dest``.

    Unlike ``dict.update``, nested dicts are walked depth-first so a
    project override of ``{"model": {"name": "tiny"}}`` keeps every
    other key under ``model`` (``url``, ``md5`, …) intact.
    """
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dest.get(k), dict):
            deep_merge_dicts(dest[k], v)
        else:
            dest[k] = v
    return dest


def merge_project_overrides(
    base_config: dict[str, Any], source_path: str | Path
) -> dict[str, Any]:
    """Return a deep copy of ``base_config`` with overrides applied.

    Walks up from ``source_path`` to find the nearest
    ``.whisperproject.json`` and overlays its keys on top of
    ``base_config``. Dict-valued keys are deep-merged recursively
    so the user can override ``model.name`` (or anything deeper)
    without forcing the whole sub-dict.
    """
    overrides = load_project_overrides(source_path)
    if not overrides:
        return base_config
    merged: dict[str, Any] = json.loads(json.dumps(base_config))
    return deep_merge_dicts(merged, overrides)
