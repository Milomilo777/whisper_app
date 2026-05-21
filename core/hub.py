"""Model Hub folder — where Whisper / Parakeet model files live.

A "hub" is just the parent directory that holds one or more
``models--Vendor--name/`` subdirectories. We split this concept out
from ``model_path`` so:

  * The user picks the location ONCE at first launch (or via the
    Advanced dialog later) and every supported model lands under
    the same root, just like a HuggingFace cache.
  * Multi-model picker (v0.8 Phase 1) can compute each variant's
    folder from ``hub_folder / models--Systran--<name>`` without
    asking the user again.
  * The installer can detect "is the hub inside the install dir?"
    and prompt the user about deleting it on uninstall.

Resolution order used by the rest of the codebase (in ``model_manager``
+ ``transcriber``):

  1. ``config["model_path"]`` if set AND the folder exists — explicit
     per-model override wins (preserves legacy user configs).
  2. ``config["hub_folder"]`` + the current model's directory name.
  3. Last-resort fallback: ``user_cache_dir() / "models" / …``
     (this is the pre-v0.8 behaviour; only hit when neither the
     hub nor an explicit model_path is configured, e.g. running
     headless from the CLI with a fresh profile).

The first-run UI dialog (``app/dialogs/hub_setup``) shows
:func:`default_hub_folder` as its initial value, which is the app's
sibling ``hub/`` directory. The user can pick a different folder
(e.g. a big external drive) and we persist that choice to
``config["hub_folder"]``.

This module is Tk-free so it can be called from worker subprocesses
and the installer-side Pascal Script (via reading the JSON file
directly).
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
    """Return the directory the user thinks of as "the app folder".

    Three runtime contexts:

      * **Onefile frozen exe** — the exe extracts its bundled assets
        to ``sys._MEIPASS`` but the exe itself lives in a stable
        directory next to a Desktop shortcut etc. We use the
        ``sys.executable`` directory, NOT the extract dir, because
        the extract dir is recreated each launch and is the wrong
        place for a persistent hub.
      * **Onedir frozen exe** (Inno Setup install) — same:
        ``dirname(sys.executable)`` is the ``{app}`` directory the
        installer wrote files to.
      * **Source / dev** — the repo root (two parents up from this
        file's directory).
    """
    if getattr(sys, "frozen", False):
        return Path(os.path.dirname(os.path.abspath(sys.executable)))
    # core/hub.py → core → repo_root
    return Path(__file__).resolve().parent.parent


def default_hub_folder() -> Path:
    """The pre-filled value the first-run dialog shows.

    ``<app_dir>/hub`` matches the user-request wording exactly.
    """
    return resolve_app_dir() / HUB_SUBFOLDER_NAME


def is_hub_configured(config: dict[str, Any]) -> bool:
    """True iff the user has picked (or migrated to) a real hub folder.

    "Configured" is intentionally permissive: as long as ``hub_folder``
    is a non-empty string, we treat the choice as made. The folder
    itself can be missing — the model-download flow creates it lazily.
    Empty-string / missing key → False (first-run dialog should fire).
    """
    value = (config.get("hub_folder") or "").strip()
    return bool(value)


def normalise_hub_path(raw: str | Path) -> str:
    """Trim + absolutize a user-typed path string.

    Empty input maps to the default. We return the user-facing string
    representation rather than a Path so the caller can write it back
    to JSON without a custom serialiser.
    """
    if not raw:
        return str(default_hub_folder())
    return str(Path(str(raw).strip()).expanduser().resolve())


def model_folder_for(
    hub_folder: str | Path | None,
    model_name: str,
) -> Path:
    """Compose the per-model directory inside a hub.

    ``model_name`` is the ``models--Vendor--name`` slug used by the
    existing cache layout — see ``DEFAULT_CONFIG["model"]["name"]``
    and ``MODEL_REGISTRY`` entries. When the slug already starts with
    ``models--``, it's used verbatim; otherwise we prepend
    ``models--Systran--`` to keep parity with the original cache
    convention.
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


def is_path_inside(child: str | Path, parent: str | Path) -> bool:
    """True when ``child`` is at or below ``parent`` in the filesystem.

    Used by both the installer-side Pascal Script (via mirroring the
    same logic in NSI / Inno) AND by tests. Returns False on any
    filesystem error so an unreadable path never tricks the
    uninstaller into thinking it's "inside" and skip the prompt.
    """
    try:
        c = Path(str(child)).resolve()
        p = Path(str(parent)).resolve()
    except (OSError, ValueError):
        return False
    try:
        c.relative_to(p)
        return True
    except ValueError:
        return False


def derive_hub_from_model_path(model_path: str) -> str:
    """Reverse-derive the hub folder from a legacy ``model_path``.

    The legacy layout is ``<hub>/models--Systran--<name>/``. Walking
    one parent up gives us the hub. We return the directory as a
    string for JSON serialisation; callers that need it as a Path
    can wrap it themselves.

    Returns an empty string when the input doesn't look like a
    model directory (no parent, blank, etc.) so the caller can fall
    back to the default cleanly.
    """
    raw = (model_path or "").strip()
    if not raw:
        return ""
    p = Path(raw)
    if not p.name.startswith("models--"):
        # Looks like a hub already — don't double-strip.
        return str(p)
    parent = p.parent
    if str(parent) in (".", ""):
        return ""
    return str(parent)
