"""Modal Advanced settings dialog (Phase 2a + 3a).

Exposes the VAD knobs, word-timestamps toggle, output-format checkboxes,
SponsorBlock category checkboxes, and the auto-transcribe-after-download flag.
"""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from core.config import save_config
from core.model_manager import (
    DEFAULT_MODEL_SLUG,
    catalog_models,
    catalog_resolve_entry,
)
from core.writers import supported_formats

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.app import App


# Output-format checkbox labels. Defaults to NAME.upper(); override
# here when the registry key isn't a clean display string. ``smtv_docx``
# is the transcription team's templated Word export.
_FORMAT_LABELS: dict[str, str] = {
    "smtv_docx": "SMTV transcription",
}


_SPONSORBLOCK_CATEGORIES = [
    ("sponsor", "Sponsor"),
    ("intro", "Intro"),
    ("outro", "Outro"),
    ("interaction", "Interaction reminder"),
    ("selfpromo", "Self-promo"),
    ("preview", "Preview/recap"),
    ("filler", "Filler tangent"),
]


# Backend picker — human-readable labels mapped to the stored config value.
# Offline engines stay first (faster_whisper is the default); the two cloud
# options spell out their auth model so a non-technical user can tell them
# apart (a pasted key vs. a downloaded service-account file).
_BACKEND_CHOICES: list[tuple[str, str]] = [
    ("Faster-Whisper — offline, default", "faster_whisper"),
    ("whisper.cpp — offline, low-end CPUs", "whisper_cpp"),
    ("Parakeet — offline, NVIDIA", "parakeet"),
    ("Gemini cloud — simple API key", "cloud_stt"),
    (
        "Google Cloud Speech-to-Text — service account (60 min/mo free)",
        "google_cloud_stt",
    ),
]
_BACKEND_LABEL_TO_VALUE = {label: value for label, value in _BACKEND_CHOICES}
_BACKEND_VALUE_TO_LABEL = {value: label for label, value in _BACKEND_CHOICES}

# Step-by-step help for getting a Google Cloud service-account JSON. Each
# entry is (numbered text, optional clickable URL). The URLs open the exact
# console pages; screenshots are not embedded.
_GCLOUD_HELP_STEPS: list[tuple[str, str]] = [
    (
        "1. Create or pick a Google Cloud project.",
        "https://console.cloud.google.com/projectcreate",
    ),
    (
        "2. Enable the Speech-to-Text API for that project.",
        "https://console.cloud.google.com/apis/library/speech.googleapis.com",
    ),
    (
        "3. (Optional but recommended) Make sure billing is on to unlock "
        "the 60 free min/month + $300 credit.",
        "https://console.cloud.google.com/billing",
    ),
    (
        "4. Create a service account, then give it the role "
        "'Cloud Speech-to-Text User' (for Batch mode also "
        "'Storage Object Admin' on your bucket).",
        "https://console.cloud.google.com/iam-admin/serviceaccounts",
    ),
    (
        "5. On that service account: Keys > Add key > Create new key > "
        "JSON > Download. Keep this file private.",
        "",
    ),
    (
        "6. Back here, click 'Browse...' and pick that downloaded .json "
        "file. Then click 'Test connection'.",
        "",
    ),
]
_GCLOUD_OFFICIAL_GUIDE = (
    "https://cloud.google.com/speech-to-text/docs/before-you-begin"
)
_GCLOUD_USAGE_CONSOLE = "https://console.cloud.google.com/billing"


class AdvancedDialog(tk.Toplevel):
    def __init__(self, app: "App") -> None:
        super().__init__(app)
        self.app = app
        self.title("Advanced settings")
        self.transient(app)
        self.grab_set()
        self.resizable(True, True)
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
        self._cookies_browser = tk.StringVar(
            value=(cfg.get("cookies_from_browser") or "").strip() or "(off)"
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
        self._whisper_model = tk.StringVar(
            value=str(cfg.get("whisper_model") or DEFAULT_MODEL_SLUG)
        )
        # Cloud Speech-to-Text (Google Gemini API) — opt-in, uploads audio.
        self._cloud_api_key = tk.StringVar(
            value=str(cfg.get("cloud_stt_api_key") or "")
        )
        self._cloud_model = tk.StringVar(
            value=str(cfg.get("cloud_stt_model") or "gemini-3.5-flash")
        )
        self._cloud_test_result = tk.StringVar(value="")
        # Google Cloud Speech-to-Text (service-account JSON) — separate from
        # the Gemini "paste a key" backend above. Uploads audio too.
        self._gcloud_credentials = tk.StringVar(
            value=str(cfg.get("gcloud_stt_credentials_json") or "")
        )
        self._gcloud_batch_mode = tk.BooleanVar(
            value=bool(cfg.get("gcloud_stt_batch_mode", False))
        )
        self._gcloud_bucket = tk.StringVar(
            value=str(cfg.get("gcloud_stt_bucket") or "")
        )
        self._gcloud_diarization = tk.BooleanVar(
            value=bool(cfg.get("gcloud_stt_diarization", False))
        )
        self._gcloud_test_result = tk.StringVar(value="")
        self._gcloud_usage_text = tk.StringVar(value="")
        # Backend picker uses a human label internally; map back on save.
        self._backend_display = tk.StringVar(
            value=_BACKEND_VALUE_TO_LABEL.get(
                str(cfg.get("transcribe_backend") or "faster_whisper"),
                _BACKEND_CHOICES[0][0],
            )
        )
        self._hallucination_detect = tk.BooleanVar(
            value=bool(cfg.get("hallucination_detect_enabled", True))
        )
        # v0.8 Phase 2 + 3 toggles
        self._demucs_enabled = tk.BooleanVar(
            value=bool(cfg.get("demucs_enabled", False))
        )
        self._ai_enabled = tk.BooleanVar(
            value=bool(cfg.get("ai_enabled", False))
        )
        self._auto_chapters_enabled = tk.BooleanVar(
            value=bool(cfg.get("auto_chapters_enabled", True))
        )
        self._voiceprint_enabled = tk.BooleanVar(
            value=bool(cfg.get("voiceprint_enabled", True))
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

        self.update_idletasks()

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        # Use most of the screen while leaving margins
        width = int(screen_w * 0.75)
        height = int(screen_h * 0.85)

        # Minimum sensible size
        width = max(width, 1100)
        height = max(height, 800)

        # Never exceed screen bounds
        width = min(width, screen_w - 80)
        height = min(height, screen_h - 80)

        x = (screen_w - width) // 2
        y = (screen_h - height) // 2

        self.geometry(f"{width}x{height}+{x}+{y}")

    def _build(self) -> None:
        main = ttk.Frame(self)
        main.pack(fill="both", expand=True)

        # Scrollable content area
        content_container = ttk.Frame(main)
        content_container.pack(fill="both", expand=True)

        canvas = tk.Canvas(content_container, highlightthickness=0)
        # Keep a handle so _teardown_mousewheel can drop the global
        # bind_all on close (the <Leave> unbind only fires while the dialog
        # stays open — closing with the pointer over the canvas would
        # otherwise leave a bind_all pointing at a destroyed widget).
        self._scroll_canvas = canvas
        scrollbar = ttk.Scrollbar(
            content_container,
            orient="vertical",
            command=canvas.yview,
        )

        body = ttk.Frame(canvas, padding=12)

        body.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=body, anchor="nw")

        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        def _on_mousewheel(event):
            if canvas.winfo_exists():
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_mousewheel(_event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
            canvas.bind_all(
                "<Button-4>",
                lambda e: canvas.yview_scroll(-1, "units")
            )
            canvas.bind_all(
                "<Button-5>",
                lambda e: canvas.yview_scroll(1, "units")
            )

        def _unbind_mousewheel(_event):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", _bind_mousewheel)
        canvas.bind("<Leave>", _unbind_mousewheel)

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
            ttk.Checkbutton(
                outputs,
                text=_FORMAT_LABELS.get(name, name.upper()),
                variable=self._format_vars[name],
            ).grid(row=i // 3, column=i % 3, sticky="w", padx=8, pady=4)

        # Whisper extras
        extras = ttk.LabelFrame(body, text="Whisper extras")
        extras.pack(fill="x", pady=(0, 8))

        # Model picker (v0.8) — slug → catalog entry. The catalog is the
        # MERGED config catalog (built-in MODEL_REGISTRY + any models the
        # online/local config adds under ``model_catalog``), so a new model
        # can ship without an app update. Changing the picker rewrites
        # cfg["model"] + cfg["model_path"] in _save_and_close so ensure_model
        # downloads the new variant on the next transcription.
        ttk.Label(extras, text="Whisper model").grid(
            row=0, column=0, sticky="w", padx=8, pady=4
        )
        # Augment each model's label with its on-disk status so the user
        # can see which models are already downloaded vs. which will
        # download (the ~size is already in the label) on first use.
        labeled = [
            (slug, f"{base}   "
                   f"[{'OK - downloaded' if self._model_downloaded(slug) else 'needs download'}]")
            for slug, base in catalog_models(self.app.app_config)
        ]
        self._model_slug_to_label = {slug: lbl for slug, lbl in labeled}
        self._model_label_to_slug = {lbl: slug for slug, lbl in labeled}
        current_label = self._model_slug_to_label.get(
            self._whisper_model.get(), labeled[0][1]
        )
        self._model_display = tk.StringVar(value=current_label)
        ttk.Combobox(
            extras,
            textvariable=self._model_display,
            state="readonly",
            values=[lbl for _slug, lbl in labeled],
            width=56,
        ).grid(row=0, column=1, columnspan=2, sticky="ew", padx=8, pady=4)
        ttk.Button(
            extras, text="Download now", command=self._download_selected_model,
        ).grid(row=0, column=3, sticky="w", padx=(0, 8), pady=4)

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
            textvariable=self._backend_display,
            state="readonly",
            values=[label for label, _value in _BACKEND_CHOICES],
            width=56,
        )
        backend_combo.grid(row=4, column=1, sticky="ew", padx=8, pady=4)
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

        # AI Layer (v0.8 Phase 2 + 3) — opt-in heavy features.
        ai = ttk.LabelFrame(body, text="AI Layer (Phase 2 + 3)")
        ai.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(
            ai, text="Enable local LLM (download Qwen2.5-1.5B ~1 GB on first use)",
            variable=self._ai_enabled,
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=4)
        ttk.Button(
            ai, text="Install AI model…",
            command=self._install_ai_model,
        ).grid(row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Label(
            ai, text="Powers summary / Q&A / chapter titles when enabled.",
            foreground="#666",
        ).grid(row=1, column=1, columnspan=2, sticky="w", padx=8, pady=4)
        ttk.Checkbutton(
            ai, text="Pre-process noisy audio with Demucs vocals separation",
            variable=self._demucs_enabled,
        ).grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=4)
        ttk.Checkbutton(
            ai, text="Generate auto-chapter markers (writes <name>.chapters.json)",
            variable=self._auto_chapters_enabled,
        ).grid(row=3, column=0, columnspan=3, sticky="w", padx=8, pady=4)
        ttk.Checkbutton(
            ai, text="Cross-file voice fingerprint (relabel SPEAKER_NN with enrolled names)",
            variable=self._voiceprint_enabled,
        ).grid(row=4, column=0, columnspan=3, sticky="w", padx=8, pady=4)

        # Cloud Speech-to-Text (Google) — OPTIONAL, uploads audio.
        cloud = ttk.LabelFrame(
            body, text="Cloud Speech-to-Text (Google) — optional, uploads audio"
        )
        cloud.pack(fill="x", pady=(0, 8))
        ttk.Label(
            cloud,
            text=(
                "PRIVACY: selecting the 'cloud_stt' backend UPLOADS your "
                "audio to Google for transcription. This BREAKS the offline "
                "guarantee — only use it for content you may send to a cloud "
                "service. The default engines stay fully offline."
            ),
            foreground="#b00020",
            wraplength=820,
            justify="left",
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(4, 8))
        ttk.Label(cloud, text="Google API key").grid(
            row=1, column=0, sticky="w", padx=8, pady=4
        )
        ttk.Entry(
            cloud, textvariable=self._cloud_api_key, show="*", width=52,
        ).grid(row=1, column=1, sticky="ew", padx=8, pady=4)
        ttk.Button(
            cloud, text="Test key", command=self._test_cloud_key,
        ).grid(row=1, column=2, sticky="w", padx=8, pady=4)
        ttk.Label(
            cloud,
            textvariable=self._cloud_test_result,
            foreground="#666",
            wraplength=820,
            justify="left",
        ).grid(row=2, column=1, columnspan=2, sticky="w", padx=8, pady=(0, 4))
        ttk.Label(
            cloud,
            text="Get a free key at aistudio.google.com (paste it above).",
            foreground="#666",
        ).grid(row=3, column=1, columnspan=2, sticky="w", padx=8, pady=(0, 4))
        ttk.Label(cloud, text="Model").grid(
            row=4, column=0, sticky="w", padx=8, pady=4
        )
        ttk.Entry(
            cloud, textvariable=self._cloud_model, width=32,
        ).grid(row=4, column=1, sticky="w", padx=8, pady=4)
        ttk.Label(
            cloud,
            text="Default: gemini-3.5-flash (a current Gemini audio model).",
            foreground="#666",
        ).grid(row=4, column=2, sticky="w", padx=8, pady=4)
        _cloud_cfg = self.app.app_config
        used = float(_cloud_cfg.get("cloud_stt_minutes_used") or 0.0)
        cap = int(_cloud_cfg.get("cloud_stt_free_minutes_cap") or 60)
        ttk.Label(
            cloud,
            text=(
                f"Cloud minutes used: {used:.1f} (free tier ~{cap} min/month, "
                "tracked LOCALLY). The dollar credit balance is NOT readable "
                "from an API key — check your usage in Google's billing "
                "console:"
            ),
            wraplength=820,
            justify="left",
        ).grid(row=5, column=0, columnspan=3, sticky="w", padx=8, pady=(8, 0))
        link = ttk.Label(
            cloud,
            text="https://console.cloud.google.com/billing",
            foreground="#1a73e8",
            cursor="hand2",
        )
        link.grid(row=6, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 4))
        link.bind("<Button-1>", lambda _e: self._open_billing_console())
        cloud.columnconfigure(1, weight=1)

        self._build_gcloud_frame(body)

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
        ttk.Label(
            download,
            text=("Cookies from browser (for login-walled sites — Facebook /"
                  " Instagram / TikTok stories, some YouTube Shorts):"),
        ).grid(row=6, column=0, columnspan=3, sticky="w", padx=8, pady=(8, 2))
        ttk.Combobox(
            download, textvariable=self._cookies_browser, state="readonly",
            width=14,
            values=["(off)", "chrome", "edge", "firefox", "brave",
                    "chromium", "opera", "vivaldi"],
        ).grid(row=7, column=0, sticky="w", padx=8, pady=(0, 4))

        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Cancel", command=self._on_close).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Save", command=self._save_and_close).pack(side="right")

    def _build_gcloud_frame(self, body) -> None:
        """Build the Google Cloud Speech-to-Text (service-account) frame.

        Kept separate from the Gemini "paste a key" frame above because the
        two cloud paths authenticate differently (an API key vs. a
        downloaded service-account JSON file) and a non-technical user must
        not confuse them.
        """
        gc = ttk.LabelFrame(
            body,
            text=(
                "Google Cloud Speech-to-Text (service account) "
                "— optional, uploads audio"
            ),
        )
        gc.pack(fill="x", pady=(0, 8))

        ttk.Label(
            gc,
            text=(
                "This is the FULL Google Cloud Speech-to-Text service. It "
                "signs in with a service-account JSON file you download from "
                "the Google Cloud console (NOT the simple API key used by the "
                "Gemini option above). New Google Cloud customers get 60 free "
                "minutes every month plus a $300 / 90-day credit."
            ),
            wraplength=820,
            justify="left",
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(4, 8))

        # -- service-account JSON file row --------------------------------
        ttk.Label(gc, text="Service-account JSON file:").grid(
            row=1, column=0, sticky="w", padx=8, pady=4
        )
        self._gcloud_path_label = ttk.Label(
            gc,
            text=self._gcloud_path_display(),
            foreground="#666",
            wraplength=560,
            justify="left",
        )
        self._gcloud_path_label.grid(row=1, column=1, sticky="ew", padx=8, pady=4)
        ttk.Button(
            gc, text="Browse...", command=self._browse_gcloud_credentials,
        ).grid(row=1, column=2, sticky="w", padx=8, pady=4)

        btns = ttk.Frame(gc)
        btns.grid(row=2, column=1, columnspan=2, sticky="w", padx=8, pady=(0, 4))
        ttk.Button(
            btns, text="How do I get this file?",
            command=self._show_gcloud_help,
        ).pack(side="left")
        ttk.Button(
            btns, text="Test connection",
            command=self._test_gcloud_connection,
        ).pack(side="left", padx=(8, 0))
        ttk.Label(
            gc,
            textvariable=self._gcloud_test_result,
            foreground="#666",
            wraplength=820,
            justify="left",
        ).grid(row=3, column=1, columnspan=2, sticky="w", padx=8, pady=(0, 4))

        # -- batch mode + bucket ------------------------------------------
        ttk.Checkbutton(
            gc,
            text="Batch mode (cheaper, slower)",
            variable=self._gcloud_batch_mode,
            command=self._refresh_gcloud_dynamic,
        ).grid(row=4, column=0, columnspan=3, sticky="w", padx=8, pady=(8, 0))
        ttk.Label(
            gc,
            text=(
                "Batch is ~75% cheaper (~$0.004/min vs ~$0.016/min) but can "
                "take up to ~24 hours and needs a Google Cloud Storage bucket "
                "you own."
            ),
            foreground="#666",
            wraplength=820,
            justify="left",
        ).grid(row=5, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 4))
        ttk.Label(gc, text="Cloud Storage bucket:").grid(
            row=6, column=0, sticky="w", padx=8, pady=4
        )
        self._gcloud_bucket_entry = ttk.Entry(
            gc, textvariable=self._gcloud_bucket, width=42,
        )
        self._gcloud_bucket_entry.grid(row=6, column=1, sticky="ew", padx=8, pady=4)

        # -- diarization ---------------------------------------------------
        ttk.Checkbutton(
            gc,
            text="Detect speakers (diarization)",
            variable=self._gcloud_diarization,
        ).grid(row=7, column=0, columnspan=3, sticky="w", padx=8, pady=4)

        # -- live usage / cost estimate -----------------------------------
        ttk.Label(
            gc,
            textvariable=self._gcloud_usage_text,
            wraplength=820,
            justify="left",
        ).grid(row=8, column=0, columnspan=3, sticky="w", padx=8, pady=(8, 0))
        ttk.Label(
            gc,
            text="(local estimate — see Google Cloud Console for the real figure)",
            foreground="#666",
        ).grid(row=9, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 2))
        usage_link = ttk.Label(
            gc,
            text="Open billing/usage console",
            foreground="#1a73e8",
            cursor="hand2",
        )
        usage_link.grid(row=10, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 4))
        usage_link.bind(
            "<Button-1>", lambda _e: self._open_url(_GCLOUD_USAGE_CONSOLE)
        )

        # -- privacy note --------------------------------------------------
        ttk.Label(
            gc,
            text="Cloud transcription uploads your audio to Google (it is not offline).",
            foreground="#b00020",
            wraplength=820,
            justify="left",
        ).grid(row=11, column=0, columnspan=3, sticky="w", padx=8, pady=(4, 4))

        gc.columnconfigure(1, weight=1)

        # Initialise the dynamic bits (bucket enable/disable + usage label).
        self._refresh_gcloud_dynamic()
        self._refresh_gcloud_usage()

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

    def _model_downloaded(self, slug: str) -> bool:
        """True when the model's weights are already on disk under the
        configured hub folder, so the dropdown can mark it downloaded."""
        entry = catalog_resolve_entry(self.app.app_config, slug)
        if not entry:
            return False
        try:
            from core import hub as _hub
            cfg = self.app.app_config
            hub_folder = (cfg.get("hub_folder") or "").strip() or str(
                _hub.default_hub_folder()
            )
            folder = _hub.model_folder_for(hub_folder, entry["name"])
            return (folder / "model.bin").exists()
        except Exception:  # noqa: BLE001
            return False

    def _download_selected_model(self) -> None:
        """Download / install the model chosen in the picker, on demand —
        instead of waiting for the first transcription to trigger it."""
        slug = self._model_label_to_slug.get(
            self._model_display.get() or "", DEFAULT_MODEL_SLUG
        )
        entry = catalog_resolve_entry(self.app.app_config, slug)
        if entry is None:
            return
        if self._model_downloaded(slug):
            self.app.log("That model is already downloaded.")
            return
        cfg = self.app.app_config
        cfg["whisper_model"] = slug
        cfg["model"] = entry
        cfg["model_path"] = ""  # let ensure_model fetch it into the hub
        try:
            save_config(cfg)
        except Exception as e:  # noqa: BLE001
            self.app.log(f"Could not save model choice: {e}")
            return
        # Close Advanced first, then open the download modal on the app so
        # two modal grabs don't stack.
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        # Use download_model_now (not ensure_model_with_modal): the latter
        # early-returns on the app-global model_ready flag, so once ANY model
        # was loaded "Download now" did nothing. We already confirmed THIS
        # slug's bytes are absent via _model_downloaded above; force the modal.
        self.app.after(0, lambda: self.app.download_model_now())

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
        _cb = self._cookies_browser.get().strip()
        cfg["cookies_from_browser"] = "" if _cb in ("", "(off)") else _cb
        tpl = (self._filename_template.get() or "").strip() or "{base}.{ext}"
        cfg["output_filename_template"] = tpl
        cfg["transcribe_backend"] = _BACKEND_LABEL_TO_VALUE.get(
            self._backend_display.get() or "", "faster_whisper"
        )
        cfg["cloud_stt_api_key"] = self._cloud_api_key.get().strip()
        cfg["cloud_stt_model"] = (
            self._cloud_model.get().strip() or "gemini-3.5-flash"
        )
        # Google Cloud Speech-to-Text (service-account) settings.
        cfg["gcloud_stt_credentials_json"] = (
            self._gcloud_credentials.get() or ""
        ).strip()
        cfg["gcloud_stt_batch_mode"] = bool(self._gcloud_batch_mode.get())
        cfg["gcloud_stt_bucket"] = (self._gcloud_bucket.get() or "").strip()
        cfg["gcloud_stt_diarization"] = bool(self._gcloud_diarization.get())
        cfg["alignment"] = self._alignment.get() or "none"
        cfg["hallucination_detect_enabled"] = bool(self._hallucination_detect.get())
        cfg["demucs_enabled"] = bool(self._demucs_enabled.get())
        cfg["ai_enabled"] = bool(self._ai_enabled.get())
        cfg["auto_chapters_enabled"] = bool(self._auto_chapters_enabled.get())
        cfg["voiceprint_enabled"] = bool(self._voiceprint_enabled.get())
        # Model picker — convert the displayed label back to the
        # registry slug and rewrite cfg["model"] + cfg["model_path"]
        # when the user picked something different. Setting
        # model_path to "" forces _apply_runtime_fallbacks to point
        # at the right cache folder for the new model.
        chosen_label = self._model_display.get() or ""
        new_slug = self._model_label_to_slug.get(chosen_label, DEFAULT_MODEL_SLUG)
        if new_slug and new_slug != cfg.get("whisper_model"):
            entry = catalog_resolve_entry(cfg, new_slug)
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
        self._teardown_mousewheel()
        self.destroy()

    def _teardown_mousewheel(self) -> None:
        """Drop the global mousewheel binds before the dialog is destroyed.

        _bind_mousewheel uses canvas.bind_all (a GLOBAL bind) on <Enter> and
        only releases it on <Leave>. If the dialog is closed while the pointer
        is still over the canvas, <Leave> never fires and the global bind keeps
        pointing at the now-destroyed canvas — a stray callback on every
        subsequent scroll. Both close paths call this first."""
        canvas = getattr(self, "_scroll_canvas", None)
        if canvas is None:
            return
        try:
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")
        except Exception:  # noqa: BLE001
            pass

    def _on_close(self) -> None:
        self._teardown_mousewheel()
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

    def _install_ai_model(self) -> None:
        """Download the local LLM model in a background thread.

        ~1 GB Qwen2.5-1.5B-Instruct Q4_K_M; the wizard logs progress
        to ``self.app.log`` so the user can leave the dialog open
        while it runs.
        """
        import threading
        try:
            from core import llm as _llm
        except Exception as e:  # noqa: BLE001
            self.app.log(f"LLM module unavailable: {e}")
            return
        if not _llm.runtime_available():
            self.app.log(_llm.runtime_availability_reason())
            return

        def _worker() -> None:
            try:
                self.app.log_threadsafe("Downloading Qwen2.5-1.5B LLM model (~1 GB)…")
                path = _llm.download_default_model(log=self.app.log_threadsafe)
                self.app.log_threadsafe(f"LLM model ready at {path}")
            except Exception as e:  # noqa: BLE001
                logger.exception("LLM model download failed")
                self.app.log_threadsafe(f"LLM model download failed: {e}")

        from core._threads import safe_thread
        safe_thread(_worker, name="llm-model-download")

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
                self.app.log_threadsafe("Downloading whisper.cpp model (~1.1 GB)…")
                path = _wc.download_default_model(log=self.app.log_threadsafe)
                self.app.log_threadsafe(f"whisper.cpp model ready at {path}")
            except Exception as e:  # noqa: BLE001
                logger.exception("whisper.cpp model download failed")
                self.app.log_threadsafe(f"whisper.cpp model download failed: {e}")

        from core._threads import safe_thread
        safe_thread(_worker, name="whispercpp-model-download")

    def _test_cloud_key(self) -> None:
        """Validate the pasted Google API key on a DAEMON thread.

        The check is a tiny ``models.list`` HTTPS request — it must
        never block the UI thread, and its result is posted back to the
        Tk main thread via ``app.post_to_main`` before touching the
        result StringVar (off-thread widget writes raise on 3.14).
        """
        key = self._cloud_api_key.get().strip()
        model = self._cloud_model.get().strip() or "gemini-3.5-flash"
        if not key:
            self._cloud_test_result.set("Paste an API key first.")
            return
        self._cloud_test_result.set("Testing key…")

        def _set_result(msg: str) -> None:
            try:
                self._cloud_test_result.set(msg)
            except Exception:  # noqa: BLE001
                pass

        def _worker() -> None:
            try:
                from core.backends.cloud_stt import CloudSttBackend
                backend = CloudSttBackend(
                    config={"cloud_stt_api_key": key, "cloud_stt_model": model}
                )
                backend.load()
                ok, msg = backend.ping_key()
            except Exception as e:  # noqa: BLE001
                ok, msg = False, f"Key check failed: {e}"
            text = ("OK — " if ok else "FAILED — ") + msg
            self.app.post_to_main(lambda: _set_result(text))
            self.app.log_threadsafe(f"Cloud STT key test: {text}")

        from core._threads import safe_thread
        safe_thread(_worker, name="cloud-stt-key-test")

    def _open_billing_console(self) -> None:
        """Open Google's billing console in the default browser."""
        self._open_url("https://console.cloud.google.com/billing")

    def _open_url(self, url: str) -> None:
        """Open ``url`` in the default browser; never raises."""
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception as e:  # noqa: BLE001
            self.app.log(f"Could not open link: {e}")

    # -- Google Cloud Speech-to-Text (service-account) handlers -----------

    def _gcloud_path_display(self) -> str:
        """The path text shown next to 'Browse...' ('(none selected)' empty)."""
        path = (self._gcloud_credentials.get() or "").strip()
        return path or "(none selected)"

    def _browse_gcloud_credentials(self) -> None:
        """Pick the downloaded service-account JSON file."""
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            parent=self,
            title="Pick your Google Cloud service-account JSON key file",
            filetypes=[("JSON key file", "*.json"), ("All files", "*.*")],
        )
        if path:
            self._gcloud_credentials.set(path)
            self._gcloud_path_label.config(text=self._gcloud_path_display())

    def _refresh_gcloud_dynamic(self) -> None:
        """Enable/disable the bucket entry based on the batch-mode checkbox."""
        try:
            state = "normal" if self._gcloud_batch_mode.get() else "disabled"
            self._gcloud_bucket_entry.config(state=state)
        except tk.TclError:
            pass

    def _refresh_gcloud_usage(self) -> None:
        """Recompute the live 'minutes used / estimated cost' label.

        Reads the LOCAL monthly counter from config and asks the pure
        formatter (in the backend module) for the display string. The
        formatter resets the shown minutes to 0 when the stored month is
        not the current month (the free tier resets monthly).
        """
        try:
            from core.backends import google_cloud_stt as _g
        except Exception as e:  # noqa: BLE001
            self._gcloud_usage_text.set(f"Usage unavailable: {e}")
            return
        cfg = self.app.app_config
        used = float(cfg.get("gcloud_stt_minutes_used") or 0.0)
        month_stored = str(cfg.get("gcloud_stt_minutes_month") or "")
        cap = int(cfg.get("gcloud_stt_free_minutes_cap") or 60)
        batch = bool(self._gcloud_batch_mode.get())
        text = _g.format_usage(
            used, month_stored, _g.month_marker(), cap, batch
        )
        self._gcloud_usage_text.set(text)

    def _show_gcloud_help(self) -> None:
        """Open a step-by-step help dialog with clickable console links."""
        top = tk.Toplevel(self)
        top.title("How to get a Google Cloud service-account JSON file")
        top.transient(self)
        top.resizable(True, True)
        frame = ttk.Frame(top, padding=14)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text=(
                "Follow these steps once. The links open the exact Google "
                "Cloud console pages (screenshots are not embedded)."
            ),
            wraplength=620,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        for text, url in _GCLOUD_HELP_STEPS:
            row = ttk.Frame(frame)
            row.pack(fill="x", anchor="w", pady=2)
            ttk.Label(
                row, text=text, wraplength=620, justify="left",
            ).pack(anchor="w")
            if url:
                link = ttk.Label(
                    row, text=url, foreground="#1a73e8", cursor="hand2",
                    wraplength=620, justify="left",
                )
                link.pack(anchor="w", padx=(16, 0))
                link.bind("<Button-1>", lambda _e, u=url: self._open_url(u))

        guide = ttk.Label(
            frame,
            text=f"Official guide: {_GCLOUD_OFFICIAL_GUIDE}",
            foreground="#1a73e8",
            cursor="hand2",
            wraplength=620,
            justify="left",
        )
        guide.pack(anchor="w", pady=(12, 0))
        guide.bind(
            "<Button-1>", lambda _e: self._open_url(_GCLOUD_OFFICIAL_GUIDE)
        )

        ttk.Button(frame, text="Close", command=top.destroy).pack(
            anchor="e", pady=(14, 0)
        )
        top.update_idletasks()
        try:
            top.grab_set()
        except tk.TclError:
            pass

    def _test_gcloud_connection(self) -> None:
        """Validate the service account on a DAEMON thread (never blocks UI).

        Steps, all off the Tk thread:
          1. Ensure the google libraries are installed (install on demand
             via core.optional_deps if missing, surfacing an "installing..."
             status).
          2. Build the backend, call load() (validates the JSON + project),
             then build the v2 SpeechClient (proves auth + the credentials
             parse). A clean client build is enough to confirm the account
             without spending a recognise call.

        The result is marshalled back to the Tk main thread via
        ``app.post_to_main`` before touching the result StringVar — never
        touch Tk from the worker thread.
        """
        path = (self._gcloud_credentials.get() or "").strip()
        batch = bool(self._gcloud_batch_mode.get())
        bucket = (self._gcloud_bucket.get() or "").strip()
        if not path:
            self._gcloud_test_result.set(
                "Pick your service-account JSON file first (Browse...)."
            )
            return
        self._gcloud_test_result.set("Testing connection...")

        def _set_result(msg: str) -> None:
            try:
                self._gcloud_test_result.set(msg)
            except Exception:  # noqa: BLE001
                pass

        def _status(msg: str) -> None:
            self.app.post_to_main(lambda: _set_result(msg))

        def _worker() -> None:
            try:
                from core import optional_deps
                from core.backends import google_cloud_stt as _g
                if not _g.runtime_available():
                    _status("Installing Google Cloud libraries (one-time)...")
                    ok_install = optional_deps.install(
                        "google_cloud_stt", log_cb=self.app.log_threadsafe
                    )
                    if not ok_install or not _g.runtime_available():
                        _status(
                            "FAILED — could not install the Google Cloud "
                            "libraries. Check your internet connection and "
                            "retry."
                        )
                        return
                config = {
                    "gcloud_stt_credentials_json": path,
                    "gcloud_stt_batch_mode": batch,
                    "gcloud_stt_bucket": bucket,
                    "gcloud_stt_model": (
                        self.app.app_config.get("gcloud_stt_model") or "chirp_2"
                    ),
                    "gcloud_stt_location": (
                        self.app.app_config.get("gcloud_stt_location")
                        or "us-central1"
                    ),
                }
                backend = _g.GoogleCloudSttBackend(config=config)
                if not backend.load():
                    _status("FAILED — " + (backend.get_error() or "unknown error"))
                    return
                # Building the client proves the JSON authenticates and the
                # Speech-to-Text client can initialise (no audio spent).
                try:
                    backend._build_client()  # noqa: SLF001 — intentional probe
                except Exception as e:  # noqa: BLE001
                    _status("FAILED — " + str(e))
                    return
                _status(
                    "OK — service account accepted and the Speech-to-Text "
                    "client initialised. You can transcribe with this backend."
                )
            except Exception as e:  # noqa: BLE001
                logger.exception("Google Cloud STT connection test failed")
                _status(f"FAILED — connection test error: {e}")

        from core._threads import safe_thread
        safe_thread(_worker, name="gcloud-stt-connection-test")
