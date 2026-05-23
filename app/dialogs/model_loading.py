"""Modal "Loading Whisper model…" dialog with an indeterminate bar.

The App keeps a reference to the dialog while the worker spawns and
loads the model; once the worker emits ``ready`` the App calls
:meth:`mark_success_and_close` from the Tk main thread.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ModelLoadingDialog(tk.Toplevel):
    """Modal dialog while the model loads on first Transcribe."""

    def __init__(self, master: "tk.Tk | tk.Toplevel") -> None:
        super().__init__(master)
        self.title("Loading Whisper model")
        self.resizable(False, False)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.cancel)

        self.success: bool = False
        self.cancelled: bool = False

        body = ttk.Frame(self, padding=18)
        body.grid(row=0, column=0, sticky="nsew")

        ttk.Label(
            body,
            text="Loading the Whisper model — this takes a few seconds…",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            body,
            text=(
                "The model loads once per session. "
                "Subsequent transcriptions start instantly."
            ),
            foreground="#666",
        ).grid(row=1, column=0, sticky="w", pady=(4, 10))

        self.pb = ttk.Progressbar(body, length=420, mode="indeterminate")
        self.pb.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        # .start(N) ticks the indeterminate bar every N ms so the
        # user has visual confirmation the app isn't frozen.
        self.pb.start(10)

        self.cancel_btn = ttk.Button(body, text="Cancel", command=self.cancel)
        self.cancel_btn.grid(row=3, column=0, sticky="e")

        body.columnconfigure(0, weight=1)

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

    def cancel(self) -> None:
        """User pressed Cancel (or closed the window).

        We do NOT kill the worker from here — the caller owns the
        worker lifecycle and checks :attr:`cancelled` after
        ``wait_window`` returns.
        """
        self.cancelled = True
        self.success = False
        try:
            self.pb.stop()
        except tk.TclError:
            pass
        try:
            self.cancel_btn.configure(state="disabled")
        except tk.TclError:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass

    def mark_success_and_close(self) -> None:
        """Called from the worker-event poll loop when the spawned
        worker emits ``ready``.
        """
        self.success = True
        try:
            self.pb.stop()
        except tk.TclError:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass
