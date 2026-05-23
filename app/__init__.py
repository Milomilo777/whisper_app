"""Whisper Project (basic) — Tk app package.

``app`` owns Tk and depends on ``core``; ``core`` never depends on
``app``. The entry point is :func:`app.app.main`, re-exported here
as :func:`run` so ``python -m app`` (and the PyInstaller spec) can
target it.
"""
from __future__ import annotations


def run() -> int:
    from .app import main
    return main()
