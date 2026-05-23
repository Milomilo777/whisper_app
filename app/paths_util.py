"""Helpers for locating bundled assets at runtime.

Assets (the app icon, anything else committed under ``assets/``)
live next to the source tree in dev, and next to the installed
files in the Setup-Standard layout. This module resolves the
right path in both cases without each caller needing to know
the layout.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _project_root() -> Path:
    """Return the directory that holds ``app/`` + ``core/`` + ``assets/``.

    Two runtime contexts:
      * **dev / source run** — this file lives at
        ``<repo>/app/paths_util.py``; ``parent.parent`` is the
        repo root.
      * **Setup-Standard install** — same shape: this file lives
        at ``<install>/app/paths_util.py``; ``parent.parent`` is
        the install dir (``C:\\Program Files\\WhisperProjectBasic\\``).
    """
    return Path(__file__).resolve().parent.parent


def asset_path(name: str) -> Path | None:
    """Return the path to ``assets/<name>`` if it exists, else None.

    Callers should treat None as "asset missing — use a fallback
    or no-op". The icon is cosmetic, so a missing file should
    never block the launch.
    """
    candidate = _project_root() / "assets" / name
    return candidate if candidate.exists() else None


def repo_or_install_root() -> Path:
    """Public alias for ``_project_root`` for callers that want the
    install/repo dir for non-asset reasons (e.g. computing the
    default hub folder)."""
    # Detect PyInstaller-frozen contexts even though the basic
    # edition doesn't currently ship a frozen exe — kept here so
    # adding one later doesn't break the helper. ``sys.frozen`` is
    # only set by PyInstaller and a handful of other freezers.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return _project_root()
