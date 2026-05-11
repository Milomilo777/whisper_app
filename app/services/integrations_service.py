"""oTranscribe (and future integrations) wiring."""
from __future__ import annotations

import logging
import os
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING

from core.integrations.otranscribe import otr_to_srt, srt_to_otr

if TYPE_CHECKING:
    from app.app import App
    from core.task import TranscriptionTask

logger = logging.getLogger(__name__)


class IntegrationsService:
    def __init__(self, app: "App") -> None:
        self.app = app

    def open_otranscribe(self) -> None:
        webbrowser.open("https://otranscribe.com/")
        self.app.log(
            "Opened https://otranscribe.com/ in your browser. "
            "Drag the audio and the .otr file into the page."
        )

    def export_task_to_otr(self, task: "TranscriptionTask") -> None:
        base, _ = os.path.splitext(task.file_path)
        srt_path = base + ".srt"
        if not os.path.exists(srt_path):
            messagebox.showwarning(
                "Cannot export",
                "No SRT file found next to the source — has the transcription completed?",
                parent=self.app,
            )
            return
        otr_path = base + ".otr"
        try:
            payload = srt_to_otr(srt_path, os.path.basename(task.file_path))
            with open(otr_path, "w", encoding="utf-8") as f:
                f.write(payload)
        except Exception as e:  # noqa: BLE001
            logger.exception("Export to .otr failed")
            messagebox.showerror("Export failed", str(e), parent=self.app)
            return
        self.app.log(f"Saved {otr_path}")
        self.app.status_var.set(f"Saved {os.path.basename(otr_path)}")

    def import_otr_to_srt(self) -> None:
        otr_path = filedialog.askopenfilename(
            title="Choose an .otr file",
            filetypes=[("oTranscribe files", "*.otr"), ("All files", "*.*")],
            parent=self.app,
        )
        if not otr_path:
            return
        suggested = Path(otr_path).with_suffix(".srt").name
        srt_path = filedialog.asksaveasfilename(
            title="Save SRT as...",
            defaultextension=".srt",
            initialfile=suggested,
            filetypes=[("SubRip subtitle", "*.srt"), ("All files", "*.*")],
            parent=self.app,
        )
        if not srt_path:
            return
        try:
            text = otr_to_srt(otr_path)
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:  # noqa: BLE001
            logger.exception("Import .otr → SRT failed")
            messagebox.showerror("Import failed", str(e), parent=self.app)
            return
        self.app.log(f"Wrote {srt_path}")
        self.app.status_var.set(f"Saved {os.path.basename(srt_path)}")
