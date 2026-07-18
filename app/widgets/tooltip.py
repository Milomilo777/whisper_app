"""Shared hover-tooltip helper + a small "(?)" help-icon widget.

Every tab and dialog in the app builds its own ttk widgets; before this
module existed each place that wanted a hover explanation (only the R3
device badge did) re-implemented the same borderless-Toplevel popup from
scratch. This module is the single implementation everyone else should
use, so every section can get a small hover explanation without repeating
the popup plumbing.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Union

TextOrGetter = Union[str, Callable[[], str]]

_BG = "#ffffe0"
_FG = "#000000"
_WRAP = 340
# "question_arrow" is one of Tk's cross-platform standard cursor names
# (X11 cursor font, mapped by Tk on Windows/macOS too); guarded anyway
# since not every Tk build ships every named cursor.
_CURSOR = "question_arrow"


def bind_tooltip(widget: tk.Widget, text: TextOrGetter, *, wraplength: int = _WRAP) -> None:
    """Show a classic yellow tooltip near *widget* on hover.

    *text* may be a plain string or a zero-arg callable returning the
    current text, for tooltips whose content changes at runtime (e.g. a
    status badge). The popup is a borderless Toplevel, destroyed on
    <Leave> or on any click so it never lingers.
    """
    state: dict[str, tk.Toplevel | None] = {"tip": None}

    def _resolve() -> str:
        try:
            return text() if callable(text) else text
        except Exception:  # noqa: BLE001
            return ""

    def _show(_event: Any) -> None:
        if state["tip"] is not None:
            return
        msg = _resolve()
        if not msg:
            return
        try:
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            try:
                tip.wm_attributes("-topmost", True)
            except tk.TclError:
                pass
            x = widget.winfo_rootx() + 12
            y = widget.winfo_rooty() + widget.winfo_height() + 4
            tip.wm_geometry(f"+{x}+{y}")
            tk.Label(
                tip, text=msg, justify="left",
                background=_BG, foreground=_FG,
                relief="solid", borderwidth=1, wraplength=wraplength,
                padx=6, pady=4,
            ).pack()
            state["tip"] = tip
        except Exception:  # noqa: BLE001
            state["tip"] = None

    def _hide(_event: Any) -> None:
        tip = state["tip"]
        state["tip"] = None
        if tip is not None:
            try:
                tip.destroy()
            except Exception:  # noqa: BLE001
                pass

    widget.bind("<Enter>", _show, add="+")
    widget.bind("<Leave>", _hide, add="+")
    widget.bind("<ButtonPress>", _hide, add="+")


def help_icon(parent: tk.Widget, text: TextOrGetter, *, wraplength: int = _WRAP) -> ttk.Label:
    """A small "ⓘ" label that shows *text* as a hover tooltip.

    Pack/grid the returned Label next to a control or a section's title.
    """
    icon = ttk.Label(parent, text=" ⓘ ", foreground="#3a7bd5")
    try:
        icon.configure(cursor=_CURSOR)
    except tk.TclError:
        pass
    bind_tooltip(icon, text, wraplength=wraplength)
    return icon


def add_section_help(frame: tk.Widget, text: str, *, wraplength: int = _WRAP) -> ttk.Label:
    """Pin a small hover-help badge to the top-right corner of *frame*.

    Works with any existing ``ttk.LabelFrame(text=...)`` (or plain Frame)
    without touching its internal grid/pack layout — ``place()`` floats
    independently of the frame's own geometry manager, so this is a
    drop-in one-liner after the frame already exists.
    """
    icon = ttk.Label(frame, text="ⓘ", foreground="#3a7bd5")
    try:
        icon.configure(cursor=_CURSOR)
    except tk.TclError:
        pass
    icon.place(relx=1.0, x=-4, y=1, anchor="ne")
    bind_tooltip(icon, text, wraplength=wraplength)
    return icon
