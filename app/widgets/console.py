"""The black/lime Text widget at the bottom of the App."""
from __future__ import annotations

import tkinter as tk


def build_console(parent: tk.Misc, height: int = 8) -> tk.Text:
    """Create the console Text widget (the user-facing log feed)."""
    txt = tk.Text(parent, height=height, bg="black", fg="lime")
    txt.pack(fill="x")
    return txt
