"""A friendly error dialog: a plain-language sentence up front, with the
raw exception text (if any) tucked behind a collapsible "Details"
disclosure. The detail is still there — copyable, for a bug report — it
just isn't the first (and only) thing a non-technical user has to read,
unlike a bare ``messagebox.showerror(title, str(e))``.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
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

    msg_row = ttk.Frame(body)
    msg_row.pack(fill="x")
    # A messagebox.showerror shows the platform's error icon; keep that
    # at-a-glance "something went wrong" cue here too. A coloured glyph
    # instead of an image keeps this working on every platform/theme.
    icon = ttk.Label(msg_row, text="⚠", foreground="#c62828")
    try:
        icon_font = tkfont.nametofont("TkDefaultFont").copy()
        icon_font.configure(size=16)
        icon.configure(font=icon_font)
        # A tkinter Font deletes its Tcl font when the Python object is
        # garbage-collected; park a reference on the widget to keep it
        # alive as long as the label is.
        setattr(icon, "_font_ref", icon_font)
    except tk.TclError:
        pass
    icon.pack(side="left", anchor="n", padx=(0, 10))
    ttk.Label(msg_row, text=message, wraplength=380, justify="left").pack(
        side="left", anchor="w"
    )

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

    ok_btn = ttk.Button(body, text="OK", command=top.destroy)
    ok_btn.pack(anchor="e", pady=(14, 0))

    # Same keyboard contract as a native messagebox: Enter/Esc dismiss,
    # and focus starts on OK so a plain Enter works immediately.
    top.bind("<Return>", lambda _e: top.destroy())
    top.bind("<Escape>", lambda _e: top.destroy())

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
    ok_btn.focus_set()
    try:
        top.bell()
    except tk.TclError:
        pass
