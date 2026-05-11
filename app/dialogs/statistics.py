"""Statistics dialog (Phase 3a).

A read-only summary of the SQLite history. Opened from File → Statistics....
"""
from __future__ import annotations

from tkinter import messagebox
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.app import App


def show_statistics(app: "App") -> None:
    if not app.history:
        messagebox.showinfo("Statistics", "history.db is unavailable.", parent=app)
        return
    s = app.history.stats()
    langs = ", ".join(f"{lang} ({c})" for lang, c in s["top_languages"]) or "none"
    body = (
        f"Downloads: {s['downloads_finished']} / {s['downloads_total']} finished\n"
        f"Transcriptions: {s['transcriptions_finished']} / {s['transcriptions_total']} finished\n"
        f"Total transcription time: {s['transcription_minutes']} minute(s)\n"
        f"Top languages: {langs}"
    )
    messagebox.showinfo("Statistics", body, parent=app)
