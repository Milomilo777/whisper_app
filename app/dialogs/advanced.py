"""Modal Advanced settings dialog (Phase 2a + 3a).

Exposes the VAD knobs, word-timestamps toggle, output-format checkboxes,
SponsorBlock category checkboxes, and the auto-transcribe-after-download flag.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from core.config import save_config
from core.model_manager import (
    DEFAULT_MODEL_SLUG,
    list_models,
    resolve_model_entry,
)
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
        self._filename_template = tk.StringVar(
            value=str(cfg.get("output_filename_template") or "{base}.{ext}")
        )
        self._transcribe_backend = tk.StringVar(
            value=str(cfg.get("transcribe_backend") or "faster_whisper")
        )
        self._whisper_model = tk.StringVar(
            value=str(cfg.get("whisper_model") or DEFAULT_MODEL_SLUG)
        )
        self._hallucination_detect = tk.BooleanVar(
            value=bool(cfg.get("hallucination_detect_enabled", True))
        )
        self._alignment = tk.StringVar(
            value=str(cfg.get("alignment") or "none")
        )
        self._telemetry_opt_in = tk.BooleanVar(
            value=bool(cfg.get("telemetry_opt_in", False))
        )
        self._minimise_to_tray = tk.BooleanVar(
            value=bool(cfg.get("minimise_to_tray", False))
        )
        self._watched_folder = tk.StringVar(
            value=str(cfg.get("watched_folder") or "")
        )
        self._watched_folder_enabled = tk.BooleanVar(
            value=bool(cfg.get("watched_folder_enabled", False))
        )

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

        # Model picker (v0.8) — slug → MODEL_REGISTRY entry. Changing
        # the picker rewrites cfg["model"] + cfg["model_path"] in
        # _save_and_close so ensure_model downloads the new variant on
        # the next transcription.
        ttk.Label(extras, text="Whisper model").grid(
            row=0, column=0, sticky="w", padx=8, pady=4
        )
        self._model_labels = list_models()
        self._model_slug_to_label = {slug: label for slug, label in self._model_labels}
        self._model_label_to_slug = {label: slug for slug, label in self._model_labels}
        current_label = self._model_slug_to_label.get(
            self._whisper_model.get(), self._model_labels[0][1]
        )
        self._model_display = tk.StringVar(value=current_label)
        ttk.Combobox(
            extras,
            textvariable=self._model_display,
            state="readonly",
            values=[label for _slug, label in self._model_labels],
            width=46,
        ).grid(row=0, column=1, columnspan=2, sticky="ew", padx=8, pady=4)

        ttk.Label(extras, text="Batch size (CUDA only)").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Spinbox(extras, from_=1, to=64, increment=1, textvariable=self._batch_size, width=6).grid(
            row=1, column=1, sticky="w", padx=8, pady=4
        )
        ttk.Label(extras, text="Initial prompt").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(extras, textvariable=self._initial_prompt, width=42).grid(
            row=2, column=1, sticky="ew", padx=8, pady=4
        )
        ttk.Label(extras, text="Hotwords (comma-separated)").grid(row=3, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(extras, textvariable=self._hotwords, width=42).grid(
            row=3, column=1, sticky="ew", padx=8, pady=4
        )
        ttk.Label(extras, text="Backend").grid(row=4, column=0, sticky="w", padx=8, pady=4)
        backend_combo = ttk.Combobox(
            extras,
            textvariable=self._transcribe_backend,
            state="readonly",
            values=("faster_whisper", "whisper_cpp"),
            width=20,
        )
        backend_combo.grid(row=4, column=1, sticky="w", padx=8, pady=4)
        ttk.Button(
            extras, text="Download whisper.cpp model...",
            command=self._download_whisper_cpp_model,
        ).grid(row=4, column=2, sticky="w", padx=8, pady=4)

        ttk.Label(extras, text="Word alignment").grid(row=5, column=0, sticky="w", padx=8, pady=4)
        ttk.Combobox(
            extras,
            textvariable=self._alignment,
            state="readonly",
            values=("none", "stable_ts"),
            width=20,
        ).grid(row=5, column=1, sticky="w", padx=8, pady=4)
        ttk.Label(
            extras,
            text="stable_ts refines word timestamps via DTW (~10-30% slower).",
            foreground="#666",
        ).grid(row=5, column=2, sticky="w", padx=8, pady=4)

        # Hallucination detector toggle (v0.8) + Hardware re-detect.
        ttk.Checkbutton(
            extras,
            text="Flag likely hallucinations (repetition + BoH heuristics)",
            variable=self._hallucination_detect,
        ).grid(row=6, column=0, columnspan=3, sticky="w", padx=8, pady=4)

        ttk.Label(extras, text="Hardware").grid(row=7, column=0, sticky="w", padx=8, pady=4)
        ttk.Button(
            extras, text="Re-detect hardware…",
            command=self._open_hardware_wizard,
        ).grid(row=7, column=1, sticky="w", padx=8, pady=4)
        ttk.Label(
            extras,
            text="Probes CUDA / NPU / DirectML and picks the fastest tier.",
            foreground="#666",
        ).grid(row=7, column=2, sticky="w", padx=8, pady=4)

        ttk.Label(extras, text="Output filename template").grid(row=8, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(extras, textvariable=self._filename_template, width=42).grid(
            row=8, column=1, columnspan=2, sticky="ew", padx=8, pady=4
        )
        ttk.Label(
            extras,
            text="Tokens: {base} {ext} {lang} {date} {speaker_count}",
            foreground="#666",
        ).grid(row=9, column=1, columnspan=2, sticky="w", padx=8, pady=(0, 4))
        extras.columnconfigure(1, weight=1)

        # Watched folder
        watch = ttk.LabelFrame(body, text="Watched folder")
        watch.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(
            watch, text="Auto-transcribe new files dropped here",
            variable=self._watched_folder_enabled,
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=4)
        ttk.Label(watch, text="Folder").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(watch, textvariable=self._watched_folder, width=42).grid(
            row=1, column=1, sticky="ew", padx=8, pady=4
        )
        ttk.Button(
            watch, text="Browse...",
            command=self._browse_watched_folder,
        ).grid(row=1, column=2, sticky="w", padx=8, pady=4)
        watch.columnconfigure(1, weight=1)

        # Tray + telemetry
        misc = ttk.LabelFrame(body, text="App behaviour")
        misc.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(
            misc, text="Minimise to system tray instead of exit",
            variable=self._minimise_to_tray,
        ).pack(anchor="w", padx=8, pady=4)
        ttk.Checkbutton(
            misc, text="Send anonymous crash reports + launch counts (opt-in)",
            variable=self._telemetry_opt_in,
        ).pack(anchor="w", padx=8, pady=4)

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
        tpl = (self._filename_template.get() or "").strip() or "{base}.{ext}"
        cfg["output_filename_template"] = tpl
        cfg["transcribe_backend"] = self._transcribe_backend.get() or "faster_whisper"
        cfg["alignment"] = self._alignment.get() or "none"
        cfg["hallucination_detect_enabled"] = bool(self._hallucination_detect.get())
        # Model picker — convert the displayed label back to the
        # registry slug and rewrite cfg["model"] + cfg["model_path"]
        # when the user picked something different. Setting
        # model_path to "" forces _apply_runtime_fallbacks to point
        # at the right cache folder for the new model.
        chosen_label = self._model_display.get() or ""
        new_slug = self._model_label_to_slug.get(chosen_label, DEFAULT_MODEL_SLUG)
        if new_slug and new_slug != cfg.get("whisper_model"):
            entry = resolve_model_entry(new_slug)
            if entry is not None:
                cfg["whisper_model"] = new_slug
                cfg["model"] = entry
                cfg["model_path"] = ""
                self.app.log(
                    f"Whisper model changed to {new_slug}. The new model "
                    "will download on the next transcription."
                )
            else:
                self.app.log(f"Unknown model slug {new_slug!r}; keeping current model.")
        cfg["telemetry_opt_in"] = bool(self._telemetry_opt_in.get())
        cfg["minimise_to_tray"] = bool(self._minimise_to_tray.get())
        new_watched = (self._watched_folder.get() or "").strip()
        new_watched_enabled = bool(self._watched_folder_enabled.get())
        watched_changed = (
            cfg.get("watched_folder", "") != new_watched
            or bool(cfg.get("watched_folder_enabled", False)) != new_watched_enabled
        )
        cfg["watched_folder"] = new_watched
        cfg["watched_folder_enabled"] = new_watched_enabled
        try:
            save_config(cfg)
        except Exception as e:  # noqa: BLE001
            self.app.log(f"Failed to save settings: {e}")
        # Sync the on-tab checkboxes to the saved values.
        if hasattr(self.app, "auto_transcribe_var"):
            self.app.auto_transcribe_var.set(cfg["auto_transcribe_after_download"])
        # Restart the folder watcher when its settings changed.
        if watched_changed:
            restart = getattr(self.app, "_restart_watched_folder", None)
            if callable(restart):
                try:
                    restart()
                except Exception as e:  # noqa: BLE001
                    self.app.log(f"Watched-folder restart failed: {e}")
        self.destroy()

    def _on_close(self) -> None:
        self.destroy()

    def _browse_watched_folder(self) -> None:
        from tkinter import filedialog
        folder = filedialog.askdirectory(parent=self, title="Choose a folder to watch")
        if folder:
            self._watched_folder.set(folder)

    def _open_hardware_wizard(self) -> None:
        """Launch the hardware autodetect wizard.

        The wizard probes CUDA / NPU / DirectML / CPU, persists the
        winning tier to ``%LOCALAPPDATA%\\WhisperProject\\hardware.json``,
        and ``core.transcriber.detect_device`` reads that file on the
        next model load. The dialog is non-modal so the user can keep
        the Advanced window open while it runs.
        """
        try:
            from app.widgets.hardware_wizard import HardwareWizard
        except Exception as e:  # noqa: BLE001
            self.app.log(f"Hardware wizard unavailable: {e}")
            return
        try:
            HardwareWizard(self, app=self.app)
        except Exception as e:  # noqa: BLE001
            self.app.log(f"Hardware wizard failed to launch: {e}")

    def _download_whisper_cpp_model(self) -> None:
        """Kick off the whisper.cpp model download in a daemon thread.

        The model lives under ``user_cache_dir() / "whisper_cpp" /
        ggml-large-v3-q5_0.bin``. The download is a single HTTPS
        request to the project's HuggingFace mirror (no auth needed).
        We surface progress + final status via the App's log() so the
        user can leave the dialog open while it runs.
        """
        import threading
        try:
            from core.backends import whisper_cpp as _wc
        except Exception as e:  # noqa: BLE001
            self.app.log(f"whisper.cpp backend unavailable: {e}")
            return

        def _worker() -> None:
            try:
                self.app.log("Downloading whisper.cpp model (~1.1 GB)…")
                path = _wc.download_default_model(log=self.app.log)
                self.app.log(f"whisper.cpp model ready at {path}")
            except Exception as e:  # noqa: BLE001
                self.app.log(f"whisper.cpp model download failed: {e}")

        threading.Thread(target=_worker, daemon=True).start()
