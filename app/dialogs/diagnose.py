"""Help → Diagnose dialog.

Re-runs :func:`core.health_check.run_all` on demand and shows the
report in a read-only Text widget with a Copy-to-clipboard button.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from core.health_check import format_report, run_all


class DiagnoseDialog(tk.Toplevel):
    def __init__(self, master: "tk.Tk | tk.Toplevel") -> None:
        super().__init__(master)
        self.title("Diagnose")
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.minsize(560, 360)

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        ttk.Label(
            body, text="System diagnostics",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        self._text = tk.Text(
            body, height=18, width=78, wrap="word",
            font=("Consolas", 9),
        )
        self._text.pack(fill="both", expand=True, pady=(0, 8))
        self._text.configure(state="disabled")

        actions = ttk.Frame(body)
        actions.pack(fill="x")
        ttk.Button(actions, text="Re-run checks", command=self._run).pack(side="left")
        ttk.Button(actions, text="Copy", command=self._copy).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Close", command=self.destroy).pack(side="right")

        # First run on open.
        self._run()

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

    def _run(self) -> None:
        report = format_report(run_all())
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("1.0", report)
        self._text.configure(state="disabled")

    def _copy(self) -> None:
        text = self._text.get("1.0", "end-1c")
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update()  # keep on clipboard after the window closes
        except tk.TclError:
            pass
