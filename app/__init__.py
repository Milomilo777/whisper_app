"""Whisper Project — Tk desktop app.

Layout:
    app.app                 — the App class (Tk root, wires services)
    app.dialogs             — Toplevel dialogs (model download, etc.)
    app.domain              — task models and enumerations
    app.services            — background work (downloads, transcription, formats)
    app.widgets             — small custom widgets

Public entry point: ``app.run()``.
"""
from __future__ import annotations

__all__ = ["run", "App"]


def run() -> None:
    """Launch the Tk app. Used by ``gui.py`` and the frozen exe entry point."""
    from .app import App
    App().mainloop()


def __getattr__(name: str):
    if name == "App":
        from .app import App as _App
        return _App
    raise AttributeError(name)
