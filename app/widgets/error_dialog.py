"""A friendly error dialog: a plain-language sentence up front, with the
raw exception text (if any) tucked behind a collapsible "Details"
disclosure. The detail is still there — copyable, for a bug report — it
just isn't the first (and only) thing a non-technical user has to read,
unlike a bare ``messagebox.showerror(title, str(e))``.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def show_error(
    parent: "tk.Tk | tk.Toplevel", title: str, message: str, detail: str | None = None,
) -> None:
    top = tk.Toplevel(parent)
    top.title(title)
    top.transient(parent)
    top.resizable(False, False)
    top.protocol("WM_DELETE_WINDOW", top.destroy)

    body = ttk.Frame(top, padding=16)
    body.pack(fill="both", expand=True)

    ttk.Label(body, text=message, wraplength=380, justify="left").pack(anchor="w")

    if detail:
        toggle_row = ttk.Frame(body)
        toggle_row.pack(fill="x", pady=(10, 0))

        # A scrollbar in case ``detail`` is ever longer than the 5 visible
        # lines (today every call site passes only str(e) — normally a
        # short one-liner — but nothing here should silently hide part of
        # the text if that ever changes).
        detail_box = ttk.Frame(body)
        text_box = tk.Text(detail_box, height=5, width=54, wrap="word")
        detail_scroll = ttk.Scrollbar(detail_box, orient="vertical", command=text_box.yview)
        text_box.configure(yscrollcommand=detail_scroll.set)
        text_box.insert("1.0", detail)
        text_box.configure(state="disabled")
        text_box.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")
        state = {"shown": False}

        def _copy_detail() -> None:
            try:
                top.clipboard_clear()
                top.clipboard_append(detail or "")
            except tk.TclError:
                pass

        def _toggle() -> None:
            if state["shown"]:
                detail_box.pack_forget()
                toggle_btn.configure(text="Show details ▸")
            else:
                detail_box.pack(fill="both", expand=True, pady=(6, 0))
                toggle_btn.configure(text="Hide details ▾")
            state["shown"] = not state["shown"]

        toggle_btn = ttk.Button(toggle_row, text="Show details ▸", command=_toggle)
        toggle_btn.pack(side="left")
        ttk.Button(toggle_row, text="Copy details", command=_copy_detail).pack(
            side="left", padx=(8, 0)
        )

    ttk.Button(body, text="OK", command=top.destroy).pack(anchor="e", pady=(14, 0))

    top.update_idletasks()
    try:
        x = parent.winfo_rootx() + (parent.winfo_width() - top.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - top.winfo_height()) // 2
        top.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    except tk.TclError:
        pass
    try:
        top.grab_set()
    except tk.TclError:
        pass
