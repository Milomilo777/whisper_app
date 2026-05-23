"""Model Hub folder — where Whisper model files live.

A "hub" is the parent directory that holds one or more
``models--Vendor--name/`` subdirectories. We split this out from
``model_path`` so:

  * The user picks the location once at first launch and every
    supported model lands under the same root.
  * The basic edition only ever uses one model, but the layout
    matches the full-fat repo so an existing hub on the same machine
    can be reused as-is.

Resolution order in the rest of the codebase:

  1. ``config["model_path"]`` when set and the folder is reachable.
  2. ``config["hub_folder"]`` + ``models--Systran--<model_name>``.
  3. Default: ``<app_dir>/hub`` (the path the first-run dialog shows).

Tk-free so the worker subprocess can call it.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


HUB_SUBFOLDER_NAME = "hub"


def resolve_app_dir() -> Path:
    """Where the user thinks of as "the app folder".

    Frozen exe → dirname(sys.executable). Source → repo root (the
    parent of this file's parent).
    """
    if getattr(sys, "frozen", False):
        return Path(os.path.dirname(os.path.abspath(sys.executable)))
    return Path(__file__).resolve().parent.parent


def default_hub_folder() -> Path:
    """The pre-filled value the first-run dialog shows."""
    return resolve_app_dir() / HUB_SUBFOLDER_NAME


def is_hub_configured(config: dict[str, Any]) -> bool:
    """True iff the user has picked (or migrated to) a real hub folder."""
    value = (config.get("hub_folder") or "").strip()
    return bool(value)


def normalise_hub_path(raw: str | Path) -> str:
    """Trim + absolutize a user-typed path string. Empty → default."""
    if not raw:
        return str(default_hub_folder())
    return str(Path(str(raw).strip()).expanduser().resolve())


# System directories that should never be a hub folder. The download
# would either fail with a confusing PermissionError (the app does
# not have elevation) or, worse, succeed and pollute a system folder
# with 3 GB of model files (audit P1-19).
_FORBIDDEN_HUB_ROOTS: tuple[str, ...] = (
    r"c:\\windows",
    r"c:\\program files",
    r"c:\\program files (x86)",
    r"c:\\programdata",
    "/etc",
    "/usr",
    "/bin",
    "/sbin",
    "/system",  # macOS / generic
    "/private",
)


def validate_hub_path(raw: str | Path) -> tuple[bool, str]:
    """Return ``(ok, reason)`` for a candidate hub folder.

    Rejects:

    * Empty / whitespace-only input.
    * Paths under system directories (``C:\\Windows``, ``C:\\Program
      Files``, ``/etc``, ``/usr``, ...). These aren't writable
      without elevation and pollute the OS install if they were.
    * The Windows install root itself (``C:\\``, ``D:\\``).

    Used by the hub-setup dialog at OK time so the user gets a
    clear message instead of a downstream PermissionError half an
    hour into the download.
    """
    if not raw:
        return False, "Please pick a folder."
    try:
        resolved = Path(str(raw).strip()).expanduser().resolve()
    except (OSError, ValueError) as e:
        return False, f"That path isn't valid: {e}"

    text = str(resolved)
    lowered = text.lower().replace("/", os.sep)

    # Top-level drive on Windows — refuse.
    if os.name == "nt":
        if len(text) <= 3 and text.endswith(":\\"):
            return False, (
                "Don't pick a drive root — create or pick a sub-folder."
            )

    for bad in _FORBIDDEN_HUB_ROOTS:
        # Normalise comparison on case-insensitive Windows.
        bad_norm = bad.lower().replace("/", os.sep).replace("\\\\", "\\")
        if lowered == bad_norm or lowered.startswith(bad_norm + os.sep):
            return False, (
                f"That folder ({bad}) is a system directory and isn't "
                "safe for a 3 GB model cache. Pick a folder in your "
                "user profile (Documents, Desktop, an external drive, "
                "etc) instead."
            )
    return True, ""


def model_folder_for(
    hub_folder: str | Path | None,
    model_name: str,
) -> Path:
    """Compose the per-model directory inside a hub.

    ``model_name`` is the ``models--Vendor--name`` slug used by the
    HuggingFace cache layout. When the slug already starts with
    ``models--``, it's used verbatim; otherwise ``models--Systran--``
    is prepended so the layout matches the full-fat repo's cache.
    """
    if not hub_folder:
        from .config import user_cache_dir
        hub = user_cache_dir() / "models"
    else:
        hub = Path(str(hub_folder))
    name = model_name.strip()
    if not name:
        raise ValueError("model_name must be non-empty")
    if not name.startswith("models--"):
        name = f"models--Systran--{name}"
    return hub / name
