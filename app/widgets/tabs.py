"""Tab construction extracted from App.

Each ``build_*_tab`` function attaches widgets onto the App and returns
nothing. The App class stays slim while the widget code lives next to its
sibling components.
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from app.domain.languages import SUBTITLE_LANGUAGES

if TYPE_CHECKING:
    from app.app import App
    from app.domain.tasks import TranscriptionTask, VideoDownloadTask


# --- shared UX helpers -----------------------------------------------------


# Glanceable status icons for both Treeviews. Plain Unicode so they
# render without an embedded image set, and so they survive the
# packaging mode that ships no icon assets.
STATUS_ICON = {
    "waiting":   "⋯ ",
    "running":   "▶ ",
    "paused":    "⏸ ",
    "finished":  "✓ ",
    "error":     "✗ ",
    "cancelled": "⊘ ",
}


def _fmt_bytes(n: int) -> str:
    """Compact filesize formatter for the Last Result card."""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.2f} GB"


def status_label(status: str) -> str:
    """Friendly status text for the Treeview's status column."""
    return STATUS_ICON.get(status, "") + status


def build_transcribe_tab(app: "App", parent: ttk.Frame) -> None:
    ttk.Label(parent, text="File").grid(row=0, column=0, padx=10, pady=10, sticky="w")
    app.fv = tk.StringVar()
    ttk.Entry(parent, textvariable=app.fv, width=60).grid(
        row=0, column=1, padx=(0, 6), pady=10, sticky="ew"
    )
    ttk.Button(parent, text="Browse", command=app.browse).grid(row=0, column=2, padx=(0, 10), pady=10)
    ttk.Button(parent, text="Transcribe", command=app.add).grid(
        row=1, column=1, padx=(0, 6), pady=(0, 10), sticky="w"
    )

    # Phase 2a — VAD + word timestamps controls.
    options = ttk.Frame(parent)
    options.grid(row=2, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 10))
    app.vad_enabled_var = tk.BooleanVar(value=bool(app.app_config.get("vad_enabled", True)))
    ttk.Checkbutton(
        options,
        text="Voice Activity Detection",
        variable=app.vad_enabled_var,
        command=app._save_transcribe_prefs,
    ).pack(side="left")
    app.word_timestamps_var = tk.BooleanVar(value=bool(app.app_config.get("word_timestamps", False)))
    ttk.Checkbutton(
        options,
        text="Word timestamps",
        variable=app.word_timestamps_var,
        command=app._save_transcribe_prefs,
    ).pack(side="left", padx=(20, 0))

    # Speaker diarization toggle (sherpa-onnx, on-device). Disabled
    # when the ONNX models or the sherpa-onnx Python package aren't
    # present; the label adapts so the user understands why.
    try:
        from core import diarization as _diar  # type: ignore[import-not-found]
        _diar_available = _diar.is_available()
        _diar_reason = _diar.availability_reason() if not _diar_available else ""
    except Exception:  # noqa: BLE001
        _diar_available = False
        _diar_reason = "sherpa-onnx not present"
    app.diarization_var = tk.BooleanVar(
        value=bool(_diar_available) and bool(app.app_config.get("diarization_enabled", False))
    )
    diar_label = (
        "Identify speakers (diarization)"
        if _diar_available
        else f"Identify speakers (unavailable: {_diar_reason})"
    )
    diar_check = ttk.Checkbutton(
        options,
        text=diar_label,
        variable=app.diarization_var,
        command=app._save_transcribe_prefs,
    )
    if not _diar_available:
        diar_check.state(["disabled"])
    diar_check.pack(side="left", padx=(20, 0))

    ttk.Button(options, text="Advanced...", command=app.open_advanced_dialog).pack(
        side="left", padx=(20, 0)
    )

    ttk.Separator(parent, orient="horizontal").grid(
        row=3, column=0, columnspan=3, sticky="ew", padx=10, pady=(6, 6)
    )
    ttk.Label(parent, text="oTranscribe").grid(row=4, column=0, padx=10, pady=(0, 10), sticky="w")
    ttk.Button(
        parent, text="Import .otr → SRT...", command=app.integrations_service.import_otr_to_srt
    ).grid(row=4, column=1, padx=(0, 6), pady=(0, 10), sticky="w")
    parent.columnconfigure(1, weight=1)

    # --- Last Result card -------------------------------------------------
    # Hidden until the first transcription completes, then populated by
    # App.show_last_result(task). Lives at the bottom of the Transcribe
    # tab so a user who just clicked "Transcribe" and switches back here
    # after the job finishes sees exactly *what* finished and *where*
    # the outputs went, with one-click "Open" buttons. Closes the
    # "did anything happen? where's my SRT?" question the previous UI
    # punted to the Queue tab's right-click menu.
    ttk.Separator(parent, orient="horizontal").grid(
        row=5, column=0, columnspan=3, sticky="ew", padx=10, pady=(6, 6)
    )

    app.last_result_frame = ttk.LabelFrame(parent, text="Last result", padding=8)
    app.last_result_frame.grid(
        row=6, column=0, columnspan=3, sticky="nsew", padx=10, pady=(0, 10)
    )
    parent.rowconfigure(6, weight=1)

    app.last_result_empty_var = tk.StringVar(
        value="No transcription finished yet. Pick a file above and click Transcribe."
    )
    app.last_result_empty_label = ttk.Label(
        app.last_result_frame,
        textvariable=app.last_result_empty_var,
        foreground="#888",
    )
    app.last_result_empty_label.pack(anchor="w")

    # Filled by App.show_last_result; kept as members so that method
    # can clear/repopulate without rebuilding widgets.
    app.last_result_body = ttk.Frame(app.last_result_frame)
    app.last_result_title_var = tk.StringVar(value="")
    app.last_result_files_frame = ttk.Frame(app.last_result_body)


def build_queue_tab(app: "App", parent: ttk.Frame) -> None:
    ttk.Button(parent, text="Clear completed", command=app.clear_completed).pack(
        anchor="e", padx=10, pady=6
    )

    cols = ("file", "status", "progress", "language", "time")
    app.tree = ttk.Treeview(parent, columns=cols, show="headings")
    headings = {
        "file": "File",
        "status": "Status",
        "progress": "Progress",
        "language": "Language",
        "time": "Elapsed",
    }
    for c in cols:
        app.tree.heading(c, text=headings[c])
    app.tree.column("language", width=140)
    app.tree.column("progress", width=80, anchor="center")
    app.tree.column("time", width=80, anchor="center")
    app.tree.column("status", width=120)
    app.tree.pack(fill="both", expand=True, padx=10)

    # Empty-state hint shown on top of the Treeview when there are no
    # rows yet. App.refresh hides it as soon as a task is enqueued.
    app.queue_empty_var = tk.StringVar(
        value="Queue is empty.  Go to the Transcribe tab and pick a file to add one."
    )
    app.queue_empty_label = ttk.Label(
        parent, textvariable=app.queue_empty_var, foreground="#888", anchor="center"
    )
    app.queue_empty_label.pack(fill="x", pady=(2, 0))

    app.pb = ttk.Progressbar(parent, length=400)
    app.pb.pack(fill="x", padx=10, pady=10)

    ttk.Label(parent, textvariable=app.status_var).pack()
    app.tree.bind("<Button-3>", app.menu_row)
    # Double-click on a finished row -> open the file's containing
    # folder. Discoverable shortcut for the right-click menu entry.
    app.tree.bind("<Double-Button-1>", app.queue_row_double_click)
    app.row_map = {}


def build_download_tab(app: "App", parent: ttk.Frame) -> None:
    top = ttk.Frame(parent, padding=10)
    top.pack(fill="x")

    ttk.Label(top, text="URL").grid(row=0, column=0, sticky="w")
    app.download_url_var = tk.StringVar()
    app.download_url_var.trace_add("write", lambda *_: app.format_service.schedule_lookup())
    ttk.Entry(top, textvariable=app.download_url_var, width=80).grid(
        row=0, column=1, columnspan=2, sticky="ew", padx=(6, 0)
    )

    ttk.Label(top, text="Folder").grid(row=1, column=0, sticky="w", pady=(8, 0))
    app.download_folder_var = tk.StringVar(value=app.app_config.get("download_folder", ""))
    ttk.Entry(top, textvariable=app.download_folder_var, width=70).grid(
        row=1, column=1, sticky="ew", padx=(6, 0), pady=(8, 0)
    )
    ttk.Button(top, text="Browse", command=app.browse_download_folder).grid(
        row=1, column=2, sticky="ew", padx=(6, 0), pady=(8, 0)
    )

    ttk.Label(top, text="Mode").grid(row=2, column=0, sticky="w", pady=(8, 0))
    app.download_mode_var = tk.StringVar(value="Audio and video")
    app.download_mode_combo = ttk.Combobox(
        top,
        textvariable=app.download_mode_var,
        state="readonly",
        values=("Audio and video", "Audio"),
        width=24,
    )
    app.download_mode_combo.grid(row=2, column=1, sticky="w", padx=(6, 0), pady=(8, 0))
    app.download_mode_combo.bind("<<ComboboxSelected>>", lambda _e: app.update_download_mode())

    ttk.Label(top, text="Audio").grid(row=3, column=0, sticky="w", pady=(8, 0))
    app.audio_format_var = tk.StringVar()
    app.audio_format_combo = ttk.Combobox(
        top, textvariable=app.audio_format_var, state="readonly", width=76
    )
    app.audio_format_combo.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(6, 0), pady=(8, 0))

    ttk.Label(top, text="Video").grid(row=4, column=0, sticky="w", pady=(8, 0))
    app.video_format_var = tk.StringVar()
    app.video_format_combo = ttk.Combobox(
        top, textvariable=app.video_format_var, state="readonly", width=76
    )
    app.video_format_combo.grid(row=4, column=1, columnspan=2, sticky="ew", padx=(6, 0), pady=(8, 0))

    ttk.Label(top, text="Output").grid(row=5, column=0, sticky="w", pady=(8, 0))
    app.output_format_var = tk.StringVar(value="mp4")
    app.output_format_combo = ttk.Combobox(
        top, textvariable=app.output_format_var, state="readonly", width=20
    )
    app.output_format_combo.grid(row=5, column=1, sticky="w", padx=(6, 0), pady=(8, 0))

    ttk.Label(top, text="Subtitles").grid(row=6, column=0, sticky="w", pady=(8, 0))
    sub_frame = ttk.Frame(top)
    sub_frame.grid(row=6, column=1, columnspan=2, sticky="ew", padx=(6, 0), pady=(8, 0))
    saved_sub_enabled = bool(app.app_config.get("download_subtitles_enabled", False))
    app.download_subtitles_var = tk.BooleanVar(value=saved_sub_enabled)
    ttk.Checkbutton(
        sub_frame,
        text="Download subtitles (auto + manual when present)",
        variable=app.download_subtitles_var,
        command=app.update_subtitle_state,
    ).pack(side="left")
    saved_sub_lang = app.app_config.get("download_subtitle_lang") or SUBTITLE_LANGUAGES[0][0]
    if saved_sub_lang not in [name for name, _ in SUBTITLE_LANGUAGES]:
        saved_sub_lang = SUBTITLE_LANGUAGES[0][0]
    app.subtitle_lang_var = tk.StringVar(value=saved_sub_lang)
    app.subtitle_lang_combo = ttk.Combobox(
        sub_frame,
        textvariable=app.subtitle_lang_var,
        state="disabled",
        values=[name for name, _ in SUBTITLE_LANGUAGES],
        width=24,
    )
    app.subtitle_lang_combo.pack(side="left", padx=(10, 0))
    app.subtitle_status_var = tk.StringVar(value="")
    ttk.Label(sub_frame, textvariable=app.subtitle_status_var, foreground="#666").pack(
        side="left", padx=(10, 0)
    )

    app.auto_transcribe_var = tk.BooleanVar(
        value=bool(app.app_config.get("auto_transcribe_after_download", False))
    )
    ttk.Checkbutton(
        top,
        text="Transcribe after download",
        variable=app.auto_transcribe_var,
        command=app._save_auto_transcribe_pref,
    ).grid(row=7, column=1, columnspan=2, sticky="w", padx=(6, 0), pady=(4, 0))

    # SMTV "all parts" toggle. Built always, shown only when an SMTV
    # episode with >=1 sibling parts is detected. format_service sets
    # visibility via app._smtv_series_toggle().
    app.smtv_download_all_parts_var = tk.BooleanVar(value=True)
    smtv_frame = ttk.Frame(top)
    smtv_check = ttk.Checkbutton(
        smtv_frame,
        text="Download all parts of this series (SMTV)",
        variable=app.smtv_download_all_parts_var,
    )
    smtv_check.pack(side="left")

    def _toggle(*, visible: bool) -> None:
        if visible:
            smtv_frame.grid(row=8, column=1, columnspan=2, sticky="w",
                            padx=(6, 0), pady=(4, 0))
        else:
            smtv_frame.grid_remove()

    _toggle(visible=False)
    app._smtv_series_toggle = _toggle  # type: ignore[attr-defined]

    app.format_status_var = tk.StringVar(value="Enter a URL to load available formats")
    ttk.Label(top, textvariable=app.format_status_var).grid(
        row=9, column=1, columnspan=2, sticky="w", padx=(6, 0), pady=(4, 0)
    )
    ttk.Button(top, text="Download", command=app.add_download).grid(
        row=10, column=2, sticky="e", pady=(10, 0)
    )

    top.columnconfigure(1, weight=1)

    bottom = ttk.Frame(parent, padding=(10, 0, 10, 10))
    bottom.pack(fill="both", expand=True)

    cols = ("name", "url", "format", "status", "progress", "time")
    app.download_tree = ttk.Treeview(bottom, columns=cols, show="headings", height=8)
    for c in cols:
        app.download_tree.heading(c, text=c)
    app.download_tree.column("name", width=220)
    app.download_tree.column("url", width=420)
    app.download_tree.column("format", width=180)
    app.download_tree.column("status", width=100)
    app.download_tree.column("progress", width=80)
    app.download_tree.column("time", width=80)
    app.download_tree.pack(fill="both", expand=True)
    app.download_tree.bind("<Button-3>", app.download_menu_row)
    # See `app.row_map` above — annotation belongs on the class.
    app.download_row_map = {}

    app.update_download_mode()
    app.update_subtitle_state()
    app.after(200, app.format_service.poll)
    app.after(300, app.download_service.poll)
