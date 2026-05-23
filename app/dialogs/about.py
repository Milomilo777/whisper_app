"""About dialog — small inventory of what this edition does."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

APP_NAME = "Whisper Project — basic"
APP_VERSION = "0.1.0"

ABOUT_BODY = """\
A radically simple offline transcription app.

What it does:
  • Drop / Browse a media file → click Transcribe.
  • Runs faster-whisper large-v3 locally on your machine.
  • Writes .srt, .json, and .txt next to the source file.
  • Picks CUDA when available, otherwise CPU.

What it doesn't do:
  • No video download, diarisation, search, or transcript viewer.
  • No alternative backends.
  • For those, see the full-fat repo.

Built on:
  faster-whisper · ffmpeg · sv-ttk · platformdirs · tkinterdnd2
"""


class AboutDialog(tk.Toplevel):
    def __init__(self, master: "tk.Tk | tk.Toplevel") -> None:
        super().__init__(master)
        self.title(f"About {APP_NAME}")
        self.resizable(False, False)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)

        ttk.Label(
            body, text=APP_NAME, font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            body, text=f"Version {APP_VERSION}", foreground="#666",
        ).pack(anchor="w", pady=(0, 10))
        ttk.Label(
            body, text=ABOUT_BODY, justify="left",
        ).pack(anchor="w")
        ttk.Label(
            body, text="MIT License", foreground="#666",
        ).pack(anchor="w", pady=(8, 12))

        ttk.Button(body, text="Close", command=self.destroy).pack(anchor="e")

        self.update_idletasks()
        try:
            x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
            y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 2
            self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except tk.TclError:
            pass
        try:
            self.grab_set()
        except tk.TclError:
            pass
