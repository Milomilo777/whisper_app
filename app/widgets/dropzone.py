"""The drop-area widget — a big "Drop a file here / or Browse…" box.

If ``tkinterdnd2`` is importable AND the Tk root is a ``TkinterDnD.Tk``,
the widget registers DND_FILES so users can drag from Explorer. When
the root is a plain ``tk.Tk`` (e.g. headless tests, or DnD support
failed to register), the widget falls back to click-to-browse only —
the dependency is required by the basic edition but we don't
hard-crash if registration fails on an odd host.
"""
from __future__ import annotations

import logging
import os
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Callable

logger = logging.getLogger(__name__)

# tkinterdnd2 ships these strings at module scope; we import them
# lazily inside the constructor so this module imports cleanly on
# hosts where tkinterdnd2 isn't installed (we still want pyright /
# pytest to load it).
_DND_FILES = "DND_Files"


class DropZone(ttk.Frame):
    """A ttk frame styled as a dashed drop target.

    Parameters
    ----------
    master:
        Parent widget. Should be a ``TkinterDnD.Tk`` for DnD support.
    on_files:
        Callback ``(list[str]) -> None`` invoked when the user
        drops files OR picks them via the Browse dialog.
    """

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_files: Callable[[list[str]], None],
    ) -> None:
        super().__init__(master, padding=4)
        self._on_files = on_files

        # Visual layer: a deep border around an inner label so the
        # whole zone looks clickable.
        self._inner = tk.Frame(
            self,
            highlightthickness=2,
            highlightbackground="#888",
            highlightcolor="#0078d4",
            bd=0,
        )
        self._inner.pack(fill="both", expand=True, padx=4, pady=4)

        title = ttk.Label(
            self._inner,
            text="Drop a media file here",
            font=("Segoe UI", 14, "bold"),
            anchor="center",
        )
        title.pack(fill="x", pady=(28, 6), padx=24)

        hint = ttk.Label(
            self._inner,
            text="or click anywhere in this box to Browse…",
            anchor="center",
            foreground="#888",
        )
        hint.pack(fill="x", pady=(0, 28), padx=24)

        # Click anywhere → Browse.
        for widget in (self._inner, title, hint):
            widget.bind("<Button-1>", self._on_click_browse)

        # Try to register as a DND target. Failure is silent — the
        # click-to-browse fallback is always available.
        self._try_register_dnd()

    def _try_register_dnd(self) -> None:
        try:
            # On a TkinterDnD.Tk root, every widget inherits the
            # drop_target_register method via the patched Tk class.
            register = getattr(self._inner, "drop_target_register", None)
            bind_drop = getattr(self._inner, "dnd_bind", None)
            if register is None or bind_drop is None:
                logger.info(
                    "Drag-and-drop unavailable (Tk root is not TkinterDnD); "
                    "click-to-browse fallback in use."
                )
                return
            register(_DND_FILES)
            bind_drop("<<Drop>>", self._on_drop)
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to register drop target: %s", e)

    def _on_drop(self, event: object) -> None:
        # tkinterdnd2 packs file paths as a Tcl list inside event.data;
        # tk.splitlist parses curly-brace-quoted entries correctly.
        # ``event`` is a tkinterdnd2.DnDEvent (not a plain tk.Event)
        # so we read .data via getattr to keep the type checker happy.
        raw = getattr(event, "data", "") or ""
        try:
            files = list(self.tk.splitlist(raw))
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not parse DnD payload %r: %s", raw, e)
            return
        files = [f for f in files if f and os.path.exists(f)]
        if files:
            self._on_files(files)

    def _on_click_browse(self, _event: tk.Event) -> None:
        # Open a file picker; multi-select supported. We accept any
        # extension faster-whisper / ffmpeg can read — restricting to
        # a fixed list always misses something users have.
        paths = filedialog.askopenfilenames(
            parent=self.winfo_toplevel(),
            title="Pick media file(s) to transcribe",
            filetypes=[
                ("Media files", "*.mp3 *.mp4 *.wav *.m4a *.mkv *.mov *.flac *.ogg *.webm *.aac *.opus *.wma *.avi"),
                ("All files", "*.*"),
            ],
        )
        if paths:
            self._on_files(list(paths))
