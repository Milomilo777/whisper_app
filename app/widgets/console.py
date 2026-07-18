"""The Text widget at the bottom of the App (the log feed)."""
from __future__ import annotations

import sys
import tkinter as tk

# Two colour schemes so the log feed matches the app's own Light/Dark
# toggle instead of always being a fixed black/lime terminal regardless
# of theme — sv_ttk restyles every ttk widget automatically, but a plain
# tk.Text is outside its reach and needs its own colours applied here.
_DARK = {"bg": "#0d0d0d", "fg": "#8be08b", "error_fg": "#ff6b6b"}
_LIGHT = {"bg": "#f5f5f5", "fg": "#1a6b1a", "error_fg": "#c62828"}

# Every existing failure-path self.log(...) call in the app already
# reads "Could not ...", "... failed", or "... error" (checked against
# the real call sites, not guessed) — so a plain substring match reliably
# flags the lines a user actually wants to notice, with no per-call-site
# changes needed anywhere else in the codebase.
_ERROR_KEYWORDS = ("could not", "fail", "error")


def _is_error_line(msg: str) -> bool:
    low = msg.lower()
    return any(k in low for k in _ERROR_KEYWORDS)


def build_console(parent: tk.Misc, height: int = 8, theme: str = "dark") -> tk.Text:
    """Create the console Text widget (the user-facing log feed).

    Gets its own right-click menu — Copy (selection), Copy all (the whole
    log in one click), and Clear — so the green output is copyable even
    when the widget is read-only and regardless of keyboard layout. This
    instance binding takes precedence over the app-wide Text menu.
    """
    txt = tk.Text(parent, height=height)
    txt.pack(fill="x")
    apply_console_theme(txt, theme)
    _attach_context_menu(txt)
    return txt


def apply_console_theme(txt: tk.Text, theme_name: str) -> None:
    """Recolour the console to match the app's Light/Dark setting.

    Called once at startup (with the resolved theme) and again from
    App.apply_theme() whenever the user switches Light/Dark/System.
    """
    colours = _LIGHT if theme_name == "light" else _DARK
    try:
        txt.configure(
            bg=colours["bg"], fg=colours["fg"], insertbackground=colours["fg"],
        )
        txt.tag_configure("error", foreground=colours["error_fg"])
    except tk.TclError:
        pass


def insert_log_line(txt: tk.Text, msg: str) -> None:
    """Append msg + a newline, highlighting likely failures in red.

    Scanning every log line for a handful of keywords is the whole
    trick: it needs no cooperation from any of the dozens of existing
    self.log(...) call sites across the app, which just pass plain
    strings and were never going to be rewritten to carry a level.
    """
    tag = ("error",) if _is_error_line(msg) else ()
    txt.insert("end", msg + "\n", tag)
    txt.see("end")


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
