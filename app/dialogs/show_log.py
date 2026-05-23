"""Help → Show recent log dialog.

Renders the tail of ``app.log`` in a read-only Text widget. Refresh
button re-reads from disk so the user can watch a long transcribe
without closing + reopening.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from core.logging_setup import read_recent_log


class ShowLogDialog(tk.Toplevel):
    def __init__(self, master: "tk.Tk | tk.Toplevel", *, lines: int = 200) -> None:
        super().__init__(master)
        self.title("Recent log")
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.minsize(640, 400)
        self._lines = lines

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        ttk.Label(
            body,
            text=f"Last {lines} log lines",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        text_frame = ttk.Frame(body)
        text_frame.pack(fill="both", expand=True, pady=(0, 8))
        self._text = tk.Text(
            text_frame, height=22, width=100, wrap="none",
            font=("Consolas", 9),
        )
        yscroll = ttk.Scrollbar(text_frame, orient="vertical", command=self._text.yview)
        xscroll = ttk.Scrollbar(text_frame, orient="horizontal", command=self._text.xview)
        self._text.configure(
            yscrollcommand=yscroll.set, xscrollcommand=xscroll.set,
        )
        self._text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)

        self._text.configure(state="disabled")

        actions = ttk.Frame(body)
        actions.pack(fill="x")
        ttk.Button(actions, text="Refresh", command=self._refresh).pack(side="left")
        ttk.Button(actions, text="Copy", command=self._copy).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Close", command=self.destroy).pack(side="right")

        self._refresh()

        self.update_idletasks()
        try:
            x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
            y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 2
            self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except tk.TclError:
            pass

    def _refresh(self) -> None:
        body = read_recent_log(self._lines)
        if not body:
            body = "(no log entries yet — try transcribing a file first)\n"
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("1.0", body)
        self._text.see("end")
        self._text.configure(state="disabled")

    def _copy(self) -> None:
        text = self._text.get("1.0", "end-1c")
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update()
        except tk.TclError:
            pass
