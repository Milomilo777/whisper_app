"""Cross-platform UI helpers."""
from __future__ import annotations

import os
import sys
from tkinter import messagebox
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk


def open_folder(folder: str, parent: "tk.Misc | None" = None) -> None:
    if not folder or not os.path.isdir(folder):
        messagebox.showwarning("Folder missing",
                               f"Could not open: {folder or '(empty)'}", parent=parent)
        return
    try:
        if os.name == "nt":
            os.startfile(folder)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            import subprocess
            subprocess.run(["open", folder], check=False)
        else:
            import subprocess
            subprocess.run(["xdg-open", folder], check=False)
    except Exception as e:  # noqa: BLE001
        messagebox.showerror("Open folder failed", str(e), parent=parent)
