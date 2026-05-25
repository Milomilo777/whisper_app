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


class _AutoScrollbar(ttk.Scrollbar):
    """A scrollbar that hides itself when the whole view already fits.

    Gives the queue lists a vertical scrollbar that appears only when the
    list grows past the visible area. Must be managed by grid — it
    grid_remove()s itself when not needed and grid()s back when it is.
    """

    def set(self, first: float | str, last: float | str) -> None:
        try:
            if float(first) <= 0.0 and float(last) >= 1.0:
                self.grid_remove()
            else:
                self.grid()
        except (ValueError, tk.TclError):
            pass
        super().set(first, last)


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


_PROGRESS_SEGMENTS = 10


def progress_cell(percent: float | int) -> str:
    """Render progress as a text bar + number for a Treeview cell.

    A Treeview cell can't host a real ttk.Progressbar, so we draw a
    fixed-width block bar (█ filled / ░ empty) and append the exact
    percentage — a glanceable graphical trend *and* the number in one
    column.
    """
    try:
        pct = int(round(float(percent)))
    except (TypeError, ValueError):
        pct = 0
    pct = max(0, min(100, pct))
    filled = (pct * _PROGRESS_SEGMENTS + 50) // 100
    bar = "█" * filled + "░" * (_PROGRESS_SEGMENTS - filled)
    return f"{bar} {pct:>3d}%"


def build_transcribe_tab(app: "App", parent: ttk.Frame) -> None:
    """Beginner-friendly Transcribe tab.

    Layout philosophy comes from researching MacWhisper / Aiko / Vibe /
    OpenWhispr / Buzz / WhisperUI in May 2026 (see
    ``docs/V08_FEATURE_RESEARCH.md`` for the citations). The pattern
    every well-loved offline app converges on is:

      1. A *hero drop-zone* takes the visual centre of the tab — it's
         both the empty state and the primary affordance.
      2. *Three* visible controls beneath: language picker, two
         feature toggles (identify speakers + per-word timestamps).
      3. *One* prominent primary CTA — sv_ttk's ``Accent.TButton``
         style + ``ipady`` so it's ~2× the visual weight of Browse.
      4. *Everything else hidden* behind an "Advanced settings…"
         button: VAD knobs, device / compute backend, hotwords,
         output formats, watched folder, telemetry, etc. None of
         these strings (``VAD``, ``compute``, ``device``, ``hotwords``)
         appear on the main canvas — the research's #1 anti-pattern.

    Note for maintainers: every ``*_var`` that lived in the old layout
    is still created here so the config save path + the hermetic test
    suite don't need to know the UI was rebuilt. Vars without a
    matching widget are simply not packed.
    """
    from app.domain.languages import SUBTITLE_LANGUAGES as _LANGS

    # ── all vars created up-front (some have no UI surface; they're
    #     still referenced by config save + test suite + Advanced
    #     dialog, so we initialise them either way) ───────────────────
    app.fv = tk.StringVar()
    app.vad_enabled_var = tk.BooleanVar(
        value=bool(app.app_config.get("vad_enabled", True))
    )
    app.word_timestamps_var = tk.BooleanVar(
        value=bool(app.app_config.get("word_timestamps", False))
    )
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
    # Always start at "Auto" — the language is deliberately NOT restored
    # from config (user request: every launch defaults to auto-detect).
    app.transcribe_lang_var = tk.StringVar(value="Auto")
    app.device_var = tk.StringVar(value=str(app.app_config.get("device", "auto")))
    app.compute_type_var = tk.StringVar(
        value=str(app.app_config.get("compute_type", "int8"))
    )
    app.hotwords_var = tk.StringVar(value=str(app.app_config.get("hotwords", "")))

    # ── Row 0: hero drop zone ─────────────────────────────────────────
    drop_zone = ttk.LabelFrame(parent, text="", padding=24)
    drop_zone.grid(
        row=0, column=0, columnspan=3, sticky="ew",
        padx=15, pady=(15, 6),
    )
    ttk.Label(
        drop_zone,
        text="🎵    Drop an audio or video file here",
        font=("TkDefaultFont", 14, "bold"),
        anchor="center",
        justify="center",
    ).pack(fill="x")
    ttk.Label(
        drop_zone,
        text="or use the Browse button below",
        foreground="#888",
        anchor="center",
        justify="center",
    ).pack(fill="x", pady=(2, 12))
    ttk.Button(drop_zone, text="Browse files...", command=app.browse).pack()

    # ── Row 1: file path display (always visible — shows what's selected) ─
    file_row = ttk.Frame(parent)
    file_row.grid(
        row=1, column=0, columnspan=3, sticky="ew",
        padx=15, pady=(2, 8),
    )
    ttk.Label(file_row, text="Selected file:").pack(side="left")
    ttk.Entry(file_row, textvariable=app.fv).pack(
        side="left", fill="x", expand=True, padx=(8, 0)
    )

    # ── Row 2: three quick options (language + identify speakers +
    #     per-word timestamps) ────────────────────────────────────────
    quick_opts = ttk.Frame(parent)
    quick_opts.grid(
        row=2, column=0, columnspan=3, sticky="ew",
        padx=15, pady=(0, 8),
    )

    ttk.Label(quick_opts, text="Language:").pack(side="left")
    lang_values = ["Auto"] + [name for name, _ in _LANGS]
    lang_combo = ttk.Combobox(
        quick_opts,
        textvariable=app.transcribe_lang_var,
        values=lang_values,
        state="readonly",
        width=14,
    )
    lang_combo.pack(side="left", padx=(6, 24))
    lang_combo.bind("<<ComboboxSelected>>", lambda _e: app._save_transcribe_prefs())

    # Feature toggles — friendly phrasing instead of "diarization" /
    # "Word timestamps". The research's vocabulary mapping: Aiko ships
    # "Produce timestamps" and "Skip silent parts"; speaker-detection
    # is universally framed as "Identify / detect speakers".
    diar_label = (
        "Identify speakers"
        if _diar_available
        else f"Identify speakers (unavailable — {_diar_reason})"
    )
    diar_check = ttk.Checkbutton(
        quick_opts,
        text=diar_label,
        variable=app.diarization_var,
        command=app._save_transcribe_prefs,
    )
    if not _diar_available:
        diar_check.state(["disabled"])
    diar_check.pack(side="left", padx=(0, 24))

    ttk.Checkbutton(
        quick_opts,
        text="Per-word timestamps",
        variable=app.word_timestamps_var,
        command=app._save_transcribe_prefs,
    ).pack(side="left")

    # ── Row 3: the big accent Transcribe CTA + tiny Advanced link ────
    cta_row = ttk.Frame(parent)
    cta_row.grid(
        row=3, column=0, columnspan=3, sticky="ew",
        padx=15, pady=(4, 4),
    )
    transcribe_btn = ttk.Button(
        cta_row,
        text="▶    Transcribe",
        command=app.add,
        style="Accent.TButton",
    )
    # ipady doubles the button height; ipadx widens it. Together they
    # give the primary CTA a clear ~2× visual weight over Browse,
    # matching the hero-CTA pattern across MacWhisper / OpenWhispr /
    # WhisperUI.
    transcribe_btn.pack(side="left", ipadx=24, ipady=8)

    ttk.Button(
        cta_row, text="Advanced settings…",
        command=app.open_advanced_dialog,
    ).pack(side="right")

    parent.columnconfigure(0, weight=1)
    parent.columnconfigure(1, weight=1)
    parent.columnconfigure(2, weight=1)

    # ── Last Result card (hidden until first transcription completes) ─
    ttk.Separator(parent, orient="horizontal").grid(
        row=4, column=0, columnspan=3, sticky="ew",
        padx=15, pady=(8, 6),
    )
    app.last_result_frame = ttk.LabelFrame(parent, text="Last result", padding=10)
    app.last_result_frame.grid(
        row=5, column=0, columnspan=3, sticky="ew",
        padx=15, pady=(0, 12),
    )
    # The card sizes to its content instead of greedily filling the whole
    # lower half of the tab (it previously expanded via rowconfigure
    # weight=1, which dominated the window).
    app.last_result_empty_var = tk.StringVar(
        value="No transcription finished yet. Drop a file above and click Transcribe."
    )
    app.last_result_empty_label = ttk.Label(
        app.last_result_frame,
        textvariable=app.last_result_empty_var,
        foreground="#888",
    )
    app.last_result_empty_label.pack(anchor="w")
    app.last_result_body = ttk.Frame(app.last_result_frame)
    app.last_result_title_var = tk.StringVar(value="")
    app.last_result_files_frame = ttk.Frame(app.last_result_body)


def build_queue_tab(app: "App", parent: ttk.Frame) -> None:
    ttk.Button(parent, text="Clear completed", command=app.clear_completed).pack(
        anchor="e", padx=10, pady=6
    )

    cols = ("file", "status", "progress", "language", "time")
    tree_frame = ttk.Frame(parent)
    tree_frame.pack(fill="both", expand=True, padx=10)
    tree_frame.rowconfigure(0, weight=1)
    tree_frame.columnconfigure(0, weight=1)
    app.tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
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
    app.tree.column("progress", width=150, anchor="w")
    app.tree.column("time", width=80, anchor="center")
    app.tree.column("status", width=120)
    _vsb = _AutoScrollbar(tree_frame, orient="vertical", command=app.tree.yview)
    app.tree.configure(yscrollcommand=_vsb.set)
    app.tree.grid(row=0, column=0, sticky="nsew")
    _vsb.grid(row=0, column=1, sticky="ns")

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

    # --- Optional time-range slice (v1.0.3) -------------------------------
    # Two short Entry widgets inside a LabelFrame, plus a tiny hint
    # label below. Both vars are per-job (no config persistence) and
    # the DownloadService clears them after the task is queued.
    app.download_start_time_var = tk.StringVar(value="")
    app.download_end_time_var = tk.StringVar(value="")
    trim_frame = ttk.LabelFrame(top, text="Time range (optional)", padding=(8, 4))
    trim_frame.grid(
        row=5, column=2, sticky="ew", padx=(12, 0), pady=(8, 0)
    )
    ttk.Label(trim_frame, text="Start").grid(row=0, column=0, sticky="w")
    start_entry = ttk.Entry(
        trim_frame, textvariable=app.download_start_time_var, width=12
    )
    start_entry.grid(row=0, column=1, sticky="w", padx=(4, 8))
    ttk.Label(trim_frame, text="0:00:00", foreground="#888").grid(
        row=0, column=2, sticky="w"
    )
    ttk.Label(trim_frame, text="End").grid(row=1, column=0, sticky="w", pady=(2, 0))
    end_entry = ttk.Entry(
        trim_frame, textvariable=app.download_end_time_var, width=12
    )
    end_entry.grid(row=1, column=1, sticky="w", padx=(4, 8), pady=(2, 0))
    ttk.Label(trim_frame, text="0:00:00", foreground="#888").grid(
        row=1, column=2, sticky="w", pady=(2, 0)
    )
    ttk.Label(
        trim_frame,
        text="e.g. 0:00:51 to 0:01:25 - leave blank for full video",
        foreground="#888",
    ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

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

    # Primary CTA for the Download tab — same Accent style + larger
    # ipadx/ipady as the Transcribe button on the other tab, so the
    # user has a single visual rule for "this is the main action".
    # Spans the full row (columnspan=3) and sits at the bottom of the
    # form so it's the natural last step after filling URL + format.
    download_btn = ttk.Button(
        top, text="⬇    Download",
        command=app.add_download,
        style="Accent.TButton",
    )
    download_btn.grid(
        row=10, column=0, columnspan=3, sticky="e",
        padx=(0, 0), pady=(12, 0), ipadx=24, ipady=8,
    )

    top.columnconfigure(1, weight=1)

    bottom = ttk.Frame(parent, padding=(10, 0, 10, 10))
    bottom.pack(fill="both", expand=True)

    cols = ("name", "url", "format", "status", "progress", "time")
    bottom.rowconfigure(0, weight=1)
    bottom.columnconfigure(0, weight=1)
    app.download_tree = ttk.Treeview(bottom, columns=cols, show="headings", height=8)
    for c in cols:
        app.download_tree.heading(c, text=c)
    app.download_tree.column("name", width=220)
    app.download_tree.column("url", width=420)
    app.download_tree.column("format", width=180)
    app.download_tree.column("status", width=100)
    app.download_tree.column("progress", width=150, anchor="w")
    app.download_tree.column("time", width=80)
    _dvsb = _AutoScrollbar(bottom, orient="vertical", command=app.download_tree.yview)
    app.download_tree.configure(yscrollcommand=_dvsb.set)
    app.download_tree.grid(row=0, column=0, sticky="nsew")
    _dvsb.grid(row=0, column=1, sticky="ns")
    app.download_tree.bind("<Button-3>", app.download_menu_row)
    # See `app.row_map` above — annotation belongs on the class.
    app.download_row_map = {}

    app.update_download_mode()
    app.update_subtitle_state()
    app.after(200, app.format_service.poll)
    app.after(300, app.download_service.poll)
