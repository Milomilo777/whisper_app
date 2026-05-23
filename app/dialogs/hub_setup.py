"""First-run Model Hub Folder picker.

Pops on the very first launch (and any launch where ``hub_folder``
is unset). Modeled after the full-fat repo's dialog but with the
"explain why" copy trimmed.

UX:

  +-------------------------------------------------+
  |  Choose Model Hub Folder                         |
  +-------------------------------------------------+
  |  Where should Whisper Project keep its model     |
  |  files (~3 GB)?                                  |
  |                                                  |
  |  Hub folder:                                     |
  |  [ <app_dir>/hub                  ] [Browse…]    |
  |                                                  |
  |       [ Use default ]  [ OK ]  [ Cancel ]        |
  +-------------------------------------------------+
"""
from __future__ import annotations

import logging
import os
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Callable, Optional

from core import hub as _hub
from core.config import save_config

logger = logging.getLogger(__name__)


class HubSetupDialog(tk.Toplevel):
    """Modal dialog that asks the user to pick / confirm the hub folder."""

    def __init__(
        self,
        master: "tk.Tk | tk.Toplevel",
        config: dict,
        *,
        save: Callable[[dict], None] | None = None,
        on_done: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.title("Choose Model Hub Folder")
        self.transient(master)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self._config = config
        self._save = save if save is not None else save_config
        self._on_done = on_done
        self._chosen_path: Optional[str] = None
        self._saved: bool = False

        initial = (config.get("hub_folder") or "").strip()
        if not initial:
            initial = str(_hub.default_hub_folder())
        self._path_var = tk.StringVar(value=initial)

        self._build()

        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self._center_on(master)

    def _build(self) -> None:
        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)

        ttk.Label(
            body,
            text="Where should Whisper Project keep its model files?",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        ttk.Label(
            body,
            text=(
                "The model is ~3 GB. The default sits next to the app so\n"
                "uninstalling removes everything. Pick a different folder\n"
                "(e.g. an external drive) if you prefer."
            ),
            foreground="#666",
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        row = ttk.Frame(body)
        row.pack(fill="x", pady=(0, 6))
        ttk.Label(row, text="Hub folder:").pack(side="left")
        self._entry = ttk.Entry(row, textvariable=self._path_var, width=58)
        self._entry.pack(side="left", padx=(8, 4), fill="x", expand=True)
        ttk.Button(row, text="Browse…", command=self._browse).pack(side="left")

        ttk.Label(
            body,
            text=f"Default if you accept: {_hub.default_hub_folder()}",
            foreground="#666",
        ).pack(anchor="w", pady=(0, 10))

        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(4, 0))
        ttk.Button(actions, text="Cancel", command=self._on_cancel).pack(
            side="right", padx=(8, 0),
        )
        ttk.Button(
            actions, text="OK", command=self._on_ok, style="Accent.TButton",
        ).pack(side="right")
        ttk.Button(
            actions, text="Use default", command=self._on_use_default,
        ).pack(side="right", padx=(0, 8))

    def _center_on(self, master: "tk.Misc") -> None:
        try:
            master.update_idletasks()
            mx = master.winfo_rootx()
            my = master.winfo_rooty()
            mw = master.winfo_width() or 800
            mh = master.winfo_height() or 600
            w = self.winfo_width() or 540
            h = self.winfo_height() or 220
            x = mx + max(0, (mw - w) // 2)
            y = my + max(0, (mh - h) // 2)
            self.geometry(f"+{x}+{y}")
        except (tk.TclError, AttributeError):
            pass

    def _browse(self) -> None:
        initial = (self._path_var.get() or "").strip()
        if initial and not os.path.isdir(initial):
            parent = os.path.dirname(initial)
            initial = parent if parent and os.path.isdir(parent) else ""
        folder = filedialog.askdirectory(
            parent=self,
            title="Pick the model hub folder",
            initialdir=initial or None,
            mustexist=False,
        )
        if folder:
            self._path_var.set(_hub.normalise_hub_path(folder))

    def _on_use_default(self) -> None:
        self._path_var.set(str(_hub.default_hub_folder()))
        self._on_ok()

    def _on_ok(self) -> None:
        path = _hub.normalise_hub_path(self._path_var.get())
        self._chosen_path = path
        self._config["hub_folder"] = path
        # Clear model_path so the runtime fallback re-derives it from
        # the new hub on the next load_config call.
        self._config["model_path"] = ""
        try:
            self._save(self._config)
            self._saved = True
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to persist hub_folder: %s", e)
        self._close(path)

    def _on_cancel(self) -> None:
        # Cancel still returns a usable default for the current session.
        path = str(_hub.default_hub_folder())
        self._chosen_path = path
        self._close(path)

    def _close(self, path: str) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        if self._on_done is not None:
            try:
                self._on_done(path)
            except Exception as e:  # noqa: BLE001
                logger.warning("hub_setup on_done callback raised: %s", e)
        try:
            self.destroy()
        except tk.TclError:
            pass

    @property
    def chosen_path(self) -> Optional[str]:
        return self._chosen_path

    @property
    def saved(self) -> bool:
        return self._saved


def ensure_hub_configured(
    master: "tk.Tk | tk.Toplevel",
    config: dict,
    *,
    save: Callable[[dict], None] | None = None,
    on_done: Callable[[str], None] | None = None,
) -> str:
    """Show the dialog when needed; return the path to use for now."""
    if _hub.is_hub_configured(config):
        return (config.get("hub_folder") or "").strip()
    HubSetupDialog(master, config, save=save, on_done=on_done)
    return str(_hub.default_hub_folder())
