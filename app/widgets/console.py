"""The black/lime Text widget at the bottom of the App (the log feed)."""
from __future__ import annotations

import sys
import tkinter as tk


def build_console(parent: tk.Misc, height: int = 8) -> tk.Text:
    """Create the console Text widget (the user-facing log feed).

    Gets its own right-click menu — Copy (selection), Copy all (the whole
    log in one click), and Clear — so the green output is copyable even
    when the widget is read-only and regardless of keyboard layout. This
    instance binding takes precedence over the app-wide Text menu.
    """
    txt = tk.Text(parent, height=height, bg="black", fg="lime")
    txt.pack(fill="x")
    _attach_context_menu(txt)
    return txt


def _attach_context_menu(txt: tk.Text) -> None:
    def _copy_selection() -> None:
        try:
            txt.event_generate("<<Copy>>")
        except tk.TclError:
            pass

    def _copy_all() -> None:
        try:
            data = txt.get("1.0", "end-1c")
            if data:
                txt.clipboard_clear()
                txt.clipboard_append(data)
        except tk.TclError:
            pass

    def _clear() -> None:
        # The log is toggled state="disabled" between writes; flip to
        # normal to clear, then restore whatever state it was in.
        try:
            state = str(txt.cget("state"))
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            txt.configure(state=state)  # type: ignore[arg-type]
        except tk.TclError:
            pass

    def _popup(event: tk.Event) -> str:
        menu = tk.Menu(txt, tearoff=0)
        menu.add_command(label="Copy", command=_copy_selection)
        menu.add_command(label="Copy all", command=_copy_all)
        menu.add_separator()
        menu.add_command(label="Clear", command=_clear)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    txt.bind("<Button-3>", _popup)
    if sys.platform == "darwin":
        # macOS Tk reports right-click as Button-2 (Button-3 is the
        # middle/third button there, which mac mice/trackpads rarely
        # generate). Bind both so the context menu opens either way.
        txt.bind("<Button-2>", _popup)
