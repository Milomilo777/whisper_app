"""ModelDownloadDialog — modal Toplevel that drives ``ensure_model``."""
from __future__ import annotations

import threading
import time
import tkinter as tk
from queue import Empty, Queue
from tkinter import messagebox, ttk
from typing import Any

from core.config import load_config
from core.model_manager import DownloadCancelled, ensure_model


def fmt_bytes(value: float | int | None) -> str:
    v = float(value or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if v < 1024 or unit == "TB":
            return f"{v:.1f} {unit}" if unit != "B" else f"{int(v)} {unit}"
        v /= 1024
    return f"{v:.1f} TB"


def fmt_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "--:--"
    s = max(0, int(seconds))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02}:{m:02}:{sec:02}" if h else f"{m:02}:{sec:02}"


class ModelDownloadDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title("Preparing Whisper model")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.cancel)

        self.events: Queue = Queue()
        self.cancel_event = threading.Event()
        self.done = False
        self.success = False
        self.error: str | None = None
        self.started = time.time()

        self.status_var = tk.StringVar(value="Starting model setup...")
        self.detail_var = tk.StringVar(value="")
        self.elapsed_var = tk.StringVar(value="Elapsed: 00:00")
        self.remaining_var = tk.StringVar(value="Remaining: --:--")
        self.speed_var = tk.StringVar(value="Speed: --")
        self.size_var = tk.StringVar(value="Total: unknown")

        body = ttk.Frame(self, padding=18)
        body.grid(row=0, column=0, sticky="nsew")

        ttk.Label(body, text="Downloading required model", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(body, textvariable=self.status_var).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(10, 4)
        )

        self.pb = ttk.Progressbar(body, length=420, mode="determinate", maximum=100)
        self.pb.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        ttk.Label(body, textvariable=self.detail_var).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Label(body, textvariable=self.elapsed_var).grid(row=4, column=0, sticky="w", pady=(10, 0))
        ttk.Label(body, textvariable=self.remaining_var).grid(row=4, column=1, sticky="e", pady=(10, 0))
        ttk.Label(body, textvariable=self.speed_var).grid(row=5, column=0, sticky="w")
        ttk.Label(body, textvariable=self.size_var).grid(row=5, column=1, sticky="e")

        self.cancel_btn = ttk.Button(body, text="Cancel", command=self.cancel)
        self.cancel_btn.grid(row=6, column=1, sticky="e", pady=(14, 0))

        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

        threading.Thread(target=self._worker, daemon=True).start()
        self.after(100, self._poll)

    def _worker(self) -> None:
        def status(msg: str) -> None:
            self.events.put(("status", msg))

        def progress(payload: dict[str, Any]) -> None:
            self.events.put(("progress", payload))

        try:
            ensure_model(load_config(), status, progress, self.cancel_event)
            self.success = True
        except DownloadCancelled:
            self.success = False
        except Exception as e:  # noqa: BLE001
            self.error = str(e)
            self.success = False
        finally:
            self.done = True
            self.events.put(("done", None))

    def cancel(self) -> None:
        self.cancel_event.set()
        self.status_var.set("Cancelling download...")
        self.cancel_btn.configure(state="disabled")

    def _poll(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except Empty:
                break

            if kind == "status":
                self.status_var.set(payload)
            elif kind == "progress":
                self._apply_progress(payload)
            elif kind == "done":
                if self.success:
                    self.destroy()
                    return
                if self.error:
                    messagebox.showerror("Model setup failed", self.error, parent=self)
                self.destroy()
                return

        elapsed = time.time() - self.started
        self.elapsed_var.set(f"Elapsed: {fmt_duration(elapsed)}")
        self.after(100, self._poll)

    def _apply_progress(self, payload: dict[str, Any]) -> None:
        percent = payload.get("percent")
        if percent is not None:
            self.pb["value"] = percent

        if payload.get("status"):
            self.status_var.set(payload["status"])
        if payload.get("detail"):
            self.detail_var.set(payload["detail"])

        total = payload.get("total")
        downloaded = payload.get("downloaded")
        speed = payload.get("speed")
        remaining = payload.get("remaining")

        if total:
            self.size_var.set(f"Total: {fmt_bytes(total)}")
        if downloaded is not None and total:
            self.size_var.set(f"Total: {fmt_bytes(downloaded)} / {fmt_bytes(total)}")
        if speed:
            self.speed_var.set(f"Speed: {fmt_bytes(speed)}/s")
        if "remaining" in payload:
            self.remaining_var.set(f"Remaining: {fmt_duration(remaining)}")
