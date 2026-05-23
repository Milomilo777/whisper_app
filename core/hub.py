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
