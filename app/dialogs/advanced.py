"""Modal Advanced settings dialog (Phase 2a + 3a).

Exposes the VAD knobs, word-timestamps toggle, output-format checkboxes,
SponsorBlock category checkboxes, and the auto-transcribe-after-download flag.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from core.config import save_config
from core.writers import supported_formats

if TYPE_CHECKING:
    from app.app import App


_SPONSORBLOCK_CATEGORIES = [
    ("sponsor", "Sponsor"),
    ("intro", "Intro"),
    ("outro", "Outro"),
    ("interaction", "Interaction reminder"),
    ("selfpromo", "Self-promo"),
    ("preview", "Preview/recap"),
    ("filler", "Filler tangent"),
]


class AdvancedDialog(tk.Toplevel):
    def __init__(self, app: "App") -> None:
        super().__init__(app)
        self.app = app
        self.title("Advanced settings")
        self.transient(app)
        self.grab_set()
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        cfg = app.app_config
        self._vad_min_silence = tk.IntVar(value=int(cfg.get("vad_min_silence_ms", 500)))
        self._vad_threshold = tk.DoubleVar(value=float(cfg.get("vad_threshold", 0.5)))
        self._vad_speech_pad = tk.IntVar(value=int(cfg.get("vad_speech_pad_ms", 400)))
        self._batch_size = tk.IntVar(value=int(cfg.get("batch_size", 16)))
        self._initial_prompt = tk.StringVar(value=str(cfg.get("initial_prompt", "")))
        self._hotwords = tk.StringVar(value=str(cfg.get("hotwords", "")))
        self._auto_transcribe = tk.BooleanVar(
            value=bool(cfg.get("auto_transcribe_after_download", False))
        )
        existing_formats = set(cfg.get("output_formats") or ["srt", "json"])
        self._format_vars: dict[str, tk.BooleanVar] = {
            f: tk.BooleanVar(value=(f in existing_formats)) for f in supported_formats()
        }
        existing_sb = set(cfg.get("sponsorblock_categories") or [])
        self._sb_vars: dict[str, tk.BooleanVar] = {
            cat: tk.BooleanVar(value=(cat in existing_sb))
            for cat, _label in _SPONSORBLOCK_CATEGORIES
        }

        self._build()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        # VAD parameters
        vad = ttk.LabelFrame(body, text="Voice Activity Detection")
        vad.pack(fill="x", pady=(0, 8))
        self._slider_row(vad, "Min silence (ms)", self._vad_min_silence, 100, 2000, 50, 0)
        self._slider_row(vad, "Threshold", self._vad_threshold, 0.1, 0.9, 0.05, 1, is_float=True)
        self._slider_row(vad, "Speech pad (ms)", self._vad_speech_pad, 0, 1000, 50, 2)

        # Output formats
        outputs = ttk.LabelFrame(body, text="Output formats")
        outputs.pack(fill="x", pady=(0, 8))
        for i, name in enumerate(supported_formats()):
            ttk.Checkbutton(outputs, text=name.upper(), variable=self._format_vars[name]).grid(
                row=i // 3, column=i % 3, sticky="w", padx=8, pady=4
            )

        # Whisper extras
        extras = ttk.LabelFrame(body, text="Whisper extras")
        extras.pack(fill="x", pady=(0, 8))
        ttk.Label(extras, text="Batch size (CUDA only)").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ttk.Spinbox(extras, from_=1, to=64, increment=1, textvariable=self._batch_size, width=6).grid(
            row=0, column=1, sticky="w", padx=8, pady=4
        )
        ttk.Label(extras, text="Initial prompt").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(extras, textvariable=self._initial_prompt, width=42).grid(
            row=1, column=1, sticky="ew", padx=8, pady=4
        )
        ttk.Label(extras, text="Hotwords (comma-separated)").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(extras, textvariable=self._hotwords, width=42).grid(
            row=2, column=1, sticky="ew", padx=8, pady=4
        )
        extras.columnconfigure(1, weight=1)

        # SponsorBlock + auto-transcribe (Phase 3a)
        download = ttk.LabelFrame(body, text="Downloads (yt-dlp)")
        download.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(
            download,
            text="Transcribe after download",
            variable=self._auto_transcribe,
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=4)
        ttk.Label(download, text="SponsorBlock — remove these segments:").grid(
            row=1, column=0, columnspan=3, sticky="w", padx=8, pady=(8, 4)
        )
        for i, (cat, label) in enumerate(_SPONSORBLOCK_CATEGORIES):
            ttk.Checkbutton(download, text=label, variable=self._sb_vars[cat]).grid(
                row=2 + i // 3, column=i % 3, sticky="w", padx=8, pady=2
            )

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Cancel", command=self._on_close).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Save", command=self._save_and_close).pack(side="right")

    def _slider_row(self, parent, label: str, var, lo, hi, _step, row: int, *, is_float: bool = False):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=4)
        scale = ttk.Scale(parent, from_=lo, to=hi, variable=var, orient="horizontal", length=240)
        scale.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        echo_var = tk.StringVar(value=f"{float(var.get()):.2f}" if is_float else str(int(var.get())))

        def _refresh(*_):
            echo_var.set(f"{float(var.get()):.2f}" if is_float else str(int(var.get())))

        var.trace_add("write", _refresh)
        ttk.Label(parent, textvariable=echo_var, width=8).grid(row=row, column=2, padx=8, pady=4)
        parent.columnconfigure(1, weight=1)

    def _save_and_close(self) -> None:
        cfg = self.app.app_config
        cfg["vad_min_silence_ms"] = int(self._vad_min_silence.get())
        cfg["vad_threshold"] = round(float(self._vad_threshold.get()), 2)
        cfg["vad_speech_pad_ms"] = int(self._vad_speech_pad.get())
        cfg["output_formats"] = [name for name, v in self._format_vars.items() if v.get()] or ["srt"]
        cfg["batch_size"] = max(1, int(self._batch_size.get()))
        cfg["initial_prompt"] = self._initial_prompt.get().strip()
        cfg["hotwords"] = self._hotwords.get().strip()
        cfg["auto_transcribe_after_download"] = bool(self._auto_transcribe.get())
        cfg["sponsorblock_categories"] = [c for c, v in self._sb_vars.items() if v.get()]
        try:
            save_config(cfg)
        except Exception as e:  # noqa: BLE001
            self.app.log(f"Failed to save settings: {e}")
        # Sync the on-tab checkboxes to the saved values.
        if hasattr(self.app, "auto_transcribe_var"):
            self.app.auto_transcribe_var.set(cfg["auto_transcribe_after_download"])
        self.destroy()

    def _on_close(self) -> None:
        self.destroy()
