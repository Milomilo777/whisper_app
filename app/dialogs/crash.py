"""Crash dialog — shown when ``sys.excepthook`` fires.

A standard ``messagebox.showerror`` truncates long tracebacks and
has no Copy button. This Toplevel renders the full traceback in a
scrollable, read-only Text widget with two actions: Copy traceback
and Open log folder.
"""
from __future__ import annotations

import logging
import tkinter as tk
import traceback
from tkinter import ttk
from typing import Callable

from core.logging_setup import open_log_folder

logger = logging.getLogger(__name__)


class CrashDialog(tk.Toplevel):
    def __init__(
        self,
        master: "tk.Tk | tk.Toplevel | None",
        exc_type: "type[BaseException] | None",
        exc_value: BaseException,
        tb: object,
    ) -> None:
        # When the master Tk has already been destroyed (a crash at
        # exit), Toplevel() with master=None creates a fresh root.
        # We still want the dialog visible so the user knows what
        # happened.
        if master is None:
            self._owns_root = True
            root = tk.Tk()
            root.withdraw()
            super().__init__(root)
        else:
            self._owns_root = False
            super().__init__(master)

        self.title("Whisper Project crashed")
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.minsize(640, 400)

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        ttk.Label(
            body, text="Something went wrong.",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", pady=(0, 6))
        ttk.Label(
            body,
            text=(
                "An unexpected error stopped the app. The full traceback is "
                "below. Copy it (and grab the log folder) when you report "
                "the issue."
            ),
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        formatted = "".join(
            traceback.format_exception(exc_type, exc_value, tb)  # type: ignore[arg-type]
        )

        text_frame = ttk.Frame(body)
        text_frame.pack(fill="both", expand=True, pady=(0, 8))
        self._text = tk.Text(
            text_frame, height=18, width=90, wrap="word",
            font=("Consolas", 9),
        )
        yscroll = ttk.Scrollbar(
            text_frame, orient="vertical", command=self._text.yview,
        )
        self._text.configure(yscrollcommand=yscroll.set)
        self._text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)

        self._text.insert("1.0", formatted)
        self._text.configure(state="disabled")

        actions = ttk.Frame(body)
        actions.pack(fill="x")
        ttk.Button(
            actions, text="Copy traceback", command=self._copy,
        ).pack(side="left")
        ttk.Button(
            actions, text="Open log folder",
            command=self._open_log_folder,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            actions, text="Close", command=self._close,
        ).pack(side="right")

        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _copy(self) -> None:
        text = self._text.get("1.0", "end-1c")
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update()
        except tk.TclError:
            pass

    def _open_log_folder(self) -> None:
        try:
            open_log_folder()
        except Exception as e:  # noqa: BLE001
            logger.warning("open_log_folder failed: %s", e)

    def _close(self) -> None:
        try:
            self.destroy()
        except tk.TclError:
            pass
        if self._owns_root:
            try:
                # Destroy the hidden root we created.
                self.master.destroy()  # type: ignore[union-attr]
            except tk.TclError:
                pass


def install_excepthook(
    get_root: "Callable[[], tk.Tk | tk.Toplevel | None] | None" = None,
) -> None:
    """Install a ``sys.excepthook`` that shows a CrashDialog.

    Parameters
    ----------
    get_root:
        Optional zero-arg callable returning the live Tk root (or
        ``None`` if there isn't one yet). The hook calls it lazily
        so the App can install the hook before constructing Tk.
    """
    import sys

    previous = sys.excepthook

    def _hook(
        exc_type: "type[BaseException]",
        exc_value: BaseException,
        tb: object,
    ) -> None:
        try:
            logger.error(
                "UNHANDLED %s: %s", exc_type.__name__, exc_value,
                exc_info=(exc_type, exc_value, tb),  # type: ignore[arg-type]
            )
        except Exception:
            pass
        root: "tk.Tk | tk.Toplevel | None" = None
        if get_root is not None:
            try:
                root = get_root()
            except Exception:
                root = None
        try:
            CrashDialog(root, exc_type, exc_value, tb)
            if root is None:
                # We created a hidden root; spin its mainloop until the
                # dialog is closed. Without this the script exits while
                # the user is still reading the traceback.
                default_root = getattr(tk, "_default_root", None)
                if default_root is not None:
                    default_root.mainloop()
        except Exception:
            # Last-ditch fallback so the user at least gets the
            # traceback in stderr.
            previous(exc_type, exc_value, tb)  # type: ignore[arg-type]

    sys.excepthook = _hook
