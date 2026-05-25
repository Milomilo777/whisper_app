"""The Tk root. Wires services + dialogs + widgets together."""
from __future__ import annotations

import logging
import os
import sys
import time
import tkinter as tk
from queue import Empty, Full, Queue
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

import sv_ttk

from app.dialogs.advanced import AdvancedDialog
from app.dialogs.model_download import ModelDownloadDialog
from app.dialogs.transcript_viewer import open_viewer as _open_transcript_viewer
from app.domain.tasks import TranscriptionTask, VideoDownloadTask
from app.observability import init_sentry, send_launch_ping_async
from app.services.download_service import DownloadService
from app.services.format_service import FormatService
from app.services.integrations_service import IntegrationsService
from app.services.transcription_service import TranscriptionService
from app.dialogs.statistics import show_statistics as _show_stats
from app.widgets.console import build_console
from app.widgets.platform import open_folder as _open_folder_helper
from app.widgets.tabs import build_download_tab, build_queue_tab, build_transcribe_tab
from app.widgets.tray import TrayController
from core import __version__ as _APP_VERSION
from core.config import load_config, save_config
from core.history import HistoryDB
from core.logging_setup import get_ui_logger, open_log_folder, setup_logging
from core.paths import bin_dir as _resource_bin_dir
from core.watcher import FolderWatcher

logger = logging.getLogger(__name__)


def _resolve_theme(name: str) -> str:
    if name == "system":
        try:
            import darkdetect  # type: ignore[import-not-found]
            return "dark" if (darkdetect.theme() or "").lower() == "dark" else "light"
        except Exception:  # noqa: BLE001
            return "dark"
    return name if name in ("light", "dark") else "dark"


def _resolve_entry_file() -> str:
    """Where does ``bin/`` live? Frozen exe sits beside it; source uses gui.py."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "gui.py",
    )


class App(tk.Tk):
    """The Tk root.

    Many attributes are populated *after* construction by the tab-
    builder functions in :mod:`app.widgets.tabs` (``fv``, ``pb``,
    every ``*_var`` and ``*_combo``, etc.). They live as forward-
    declared annotations on the class so pyright sees them and so
    refactoring tools follow them; the actual assignment still
    happens in the tab builder.
    """

    entry_file: str = _resolve_entry_file()

    # --- forward declarations of attributes assigned after init -----------
    # Transcribe tab
    fv: tk.StringVar
    vad_enabled_var: tk.BooleanVar
    word_timestamps_var: tk.BooleanVar
    # Queue tab
    tree: "ttk.Treeview"
    pb: "ttk.Progressbar"
    row_map: dict[str, Any]
    # Download tab
    download_url_var: tk.StringVar
    download_folder_var: tk.StringVar
    # v1.0.3 — optional time-range slice on the Download tab. Both
    # vars are created by tabs.build_download_tab and are per-job
    # (DownloadService clears them after enqueue, no config save).
    download_start_time_var: tk.StringVar
    download_end_time_var: tk.StringVar
    download_mode_var: tk.StringVar
    download_mode_combo: "ttk.Combobox"
    audio_format_var: tk.StringVar
    audio_format_combo: "ttk.Combobox"
    video_format_var: tk.StringVar
    video_format_combo: "ttk.Combobox"
    output_format_var: tk.StringVar
    output_format_combo: "ttk.Combobox"
    download_subtitles_var: tk.BooleanVar
    subtitle_lang_var: tk.StringVar
    subtitle_lang_combo: "ttk.Combobox"
    subtitle_status_var: tk.StringVar
    auto_transcribe_var: tk.BooleanVar
    smtv_download_all_parts_var: tk.BooleanVar
    # Diarization toggle (Transcribe tab)
    diarization_var: tk.BooleanVar
    # Quick-options row on the Transcribe tab
    transcribe_lang_var: tk.StringVar
    device_var: tk.StringVar
    compute_type_var: tk.StringVar
    hotwords_var: tk.StringVar
    format_status_var: tk.StringVar
    download_tree: "ttk.Treeview"
    download_row_map: dict[str, Any]
    # Set by format_service.lookup_formats / _apply_smtv_formats
    _smtv_episode: Any | None
    # Set by tabs.build_download_tab — toggles the series checkbox.
    # Signature: (visible: bool) -> None
    _smtv_series_toggle: Any
    # Console widget (built by app.widgets.console.build_console)
    txt: "tk.Text"
    # Optional history DB; None when SQLite init fails
    history: "HistoryDB | None"
    # Last-result card on the Transcribe tab
    last_result_frame: "ttk.LabelFrame"
    last_result_empty_var: tk.StringVar
    last_result_empty_label: "ttk.Label"
    last_result_body: "ttk.Frame"
    last_result_title_var: tk.StringVar
    last_result_files_frame: "ttk.Frame"
    # Queue-tab empty-state placeholder
    queue_empty_var: tk.StringVar
    queue_empty_label: "ttk.Label"
    # Whether to chime the system bell when a job finishes (View menu)
    chime_on_complete_var: tk.BooleanVar
    # Recent-files submenu rebuilt every time it opens
    _recent_menu: tk.Menu
    # System tray + watched-folder controllers (created lazily)
    tray: "TrayController | None"
    _folder_watcher: "FolderWatcher | None"
    # When True, on_exit treats Tk close as a true exit even when
    # minimise_to_tray is on (set by TrayController._exit_app).
    _exit_from_tray: bool

    def __init__(self) -> None:
        super().__init__()
        # Window-title base carries the version so the user can always see
        # which build is running (title bar / taskbar / Alt-Tab).
        self._base_title = f"Whisper Project v{_APP_VERSION}"
        self.title(self._base_title)
        self._install_icon()
        # High-DPI scaling: pick up the system DPI so fonts and
        # paddings don't shrink to dollhouse size on 150 % displays.
        self._apply_hidpi_scaling()
        # Restore the user's saved window geometry if any; falls back
        # to a sensible default. _save_window_geometry persists it on
        # the WM_DELETE_WINDOW exit path.
        saved_geom = load_config().get("window_geometry") or ""
        if isinstance(saved_geom, str) and saved_geom.count("x") == 1:
            try:
                self.geometry(saved_geom)
            except Exception:  # noqa: BLE001
                self.geometry("960x640")
        else:
            self.geometry("960x640")
        self.protocol("WM_DELETE_WINDOW", self.on_exit)

        # Per-instance queues (no more module-globals — AUDIT B3 fix).
        self.queue: list[TranscriptionTask] = []
        self.download_queue: list[VideoDownloadTask] = []
        self.download_current: VideoDownloadTask | None = None

        self.status_var = tk.StringVar(value="Initializing...")
        self.model_ready = False
        self.model_loading = False
        self.model_setup_running = False
        self.workers: list[dict[str, Any]] = []
        # Audit A13: bound the inter-thread event queues. 2000 is
        # well above normal traffic (~1-5 events/s per worker) but
        # caps memory in catastrophic cases (Tk frozen, thousands
        # of files dropped into the watcher at once). Producers
        # block on Full rather than OOM the process — easier to
        # diagnose.
        self.worker_events: Queue = Queue(maxsize=2000)
        self.worker_ready = False
        self.app_config = load_config()
        setup_logging(self.app_config.get("log_level", "INFO"))
        init_sentry()
        send_launch_ping_async()
        self._ui_logger = get_ui_logger()
        logger.info("App startup; theme=%s", self.app_config.get("theme", "dark"))
        self.theme_var = tk.StringVar(value=self.app_config.get("theme", "dark"))
        sv_ttk.set_theme(_resolve_theme(self.theme_var.get()))
        self.parallel_workers = max(1, int(self.app_config.get("parallel_workers", 2)))
        self.next_worker_id = 1
        self.format_events: Queue = Queue(maxsize=2000)
        self.download_events: Queue = Queue(maxsize=2000)
        self.audio_format_map: dict[str, dict[str, Any]] = {}
        self.video_format_map: dict[str, dict[str, Any]] = {}
        self.current_video_title = ""
        self.current_video_language = ""
        self.format_lookup_after: str | None = None

        # Services
        self.format_service = FormatService(self)
        self.download_service = DownloadService(self)
        self.transcription_service = TranscriptionService(self)
        self.integrations_service = IntegrationsService(self)

        # SQLite history (Phase 3a). Mark any pre-crash row as interrupted on launch.
        try:
            self.history = HistoryDB()
            interrupted = self.history.mark_interrupted()
            if interrupted:
                logger.info("Marked %d running rows as interrupted on launch", interrupted)
        except Exception as e:  # noqa: BLE001
            logger.warning("history.db unavailable: %s", e)
            self.history = None

        self._build_menu()
        self._build_tabs()
        self.txt = build_console(self)

        # Wire global keyboard shortcuts now that the widgets exist:
        #   Ctrl+O          → Browse for a file to transcribe
        #   Ctrl+Enter      → Start transcribing whatever is in the
        #                     file picker
        #   Esc             → Cancel the currently-running task
        #   Ctrl+Q          → Quit (same as File → Exit)
        self.bind("<Control-o>", lambda _e: self.browse())
        self.bind("<Control-O>", lambda _e: self.browse())
        self.bind("<Control-Return>", lambda _e: self.add())
        self.bind("<Escape>", lambda _e: self._cancel_running())
        # Ctrl+Q always exits — same convention as File→Exit.
        self.bind("<Control-q>", lambda _e: self._force_exit())
        self.bind("<Control-Q>", lambda _e: self._force_exit())

        # Opt-in drag-and-drop on the main window. tkinterdnd2 is in
        # requirements.txt but the desktop app stays usable even if
        # the import fails — we just log and skip.
        self._install_drag_drop()

        # System tray + watched folder. Both are best-effort: missing
        # dependencies (pystray / Pillow / watchdog) silently disable
        # the feature rather than blocking app startup.
        self.tray = None
        self._folder_watcher = None
        self._exit_from_tray = False
        # Flag flipped to True at the top of on_exit so watcher
        # callbacks / stability-check ticks short-circuit before
        # touching destroyed widgets. Keep watched_after_ids so
        # each path only schedules ONE stability-check ladder.
        self._closing = False
        self._watched_after_ids: dict[str, str] = {}
        # Thread-safe queue drained on the Tk main thread by
        # _drain_watched_paths. watchdog fires callbacks from a
        # background thread; on Python 3.14 calling self.after()
        # from a non-main thread raises RuntimeError. Routing
        # through this queue lets us bounce safely.
        #
        # Sibling queue: _main_thread_calls (below) — same idea, but
        # for arbitrary callables coming from ANY background thread
        # (burn-subs worker, hardware-wizard benchmark, tray clicks).
        # _watched_path_queue is filesystem-watcher → main thread;
        # _main_thread_calls is any-thread → main thread.
        self._watched_path_queue: Queue = Queue(maxsize=2000)
        # Background threads (burn-subs worker, hardware-wizard benchmark,
        # tray clicks, …) can't call self.after() directly on Python 3.14
        # (RuntimeError; undefined on earlier 3.x). They push callables
        # here; _drain_main_calls() runs them on the Tk main thread.
        self._main_thread_calls: Queue = Queue(maxsize=2000)
        self._install_tray()
        self._install_clipboard_keys()
        self._install_text_context_menu()
        self._restart_watched_folder()
        self.after(250, self._drain_watched_paths)
        self.after(50, self._drain_main_calls)

        # Auto-resume after crash: history.mark_interrupted() above
        # flipped rows from running → interrupted. If any of those
        # files still exist on disk, offer to re-enqueue them.
        self.after(700, self._maybe_offer_crash_resume)

        self.after(100, self._on_start)
        self.after(300, self.loop)

    # Bootstrap ---------------------------------------------------------------
    def _on_start(self) -> None:
        # First-run Hub Folder picker.
        #
        # v1.0.3 — lazy model load.
        # We used to call ``transcription_service.start_standby()`` here
        # (and in the hub-setup callbacks) so the Whisper model was
        # already in RAM when the user clicked Transcribe. That cost
        # ~1.5 GB of idle memory + a CPU spike on EVERY launch, even
        # for sessions where the user never transcribed (e.g. opened
        # the app just to browse history or download a video).
        #
        # The worker now spawns on the first transcribe request via
        # ``TranscriptionService.ensure_worker_ready``, which shows a
        # short modal "Loading Whisper model…" dialog. Do NOT re-add
        # the standby calls here — the trade-off is intentional.
        #
        # The hub-setup dialog still fires on first launch so the user
        # picks where models live; we just don't preload the model.
        from core import hub as _hub

        if _hub.is_hub_configured(self.app_config):
            return

        try:
            from app.dialogs.hub_setup import ensure_hub_configured

            def _hub_picked(path: str) -> None:
                self.log(f"Model hub folder set to: {path}")
                try:
                    self.app_config = load_config()
                except Exception:  # noqa: BLE001
                    pass

            ensure_hub_configured(
                self, self.app_config,
                on_done=_hub_picked,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Hub setup dialog failed: %s", e)

    # Menu --------------------------------------------------------------------
    def _build_menu(self) -> None:
        m = tk.Menu(self)
        f = tk.Menu(m, tearoff=0)
        f.add_command(label="Browse...                          Ctrl+O", command=self.browse)
        # Recent files submenu — populated from history.db at menu-open
        # time so it always reflects the latest run. Skips when history
        # is None (SQLite init failed) and shows a single disabled
        # "(no recent files)" placeholder.
        self._recent_menu = tk.Menu(f, tearoff=0, postcommand=self._populate_recent_menu)
        f.add_cascade(label="Recent files", menu=self._recent_menu)
        f.add_separator()
        f.add_command(label="Statistics...", command=self.show_statistics)
        f.add_separator()
        # File→Exit bypasses the minimise-to-tray redirect. When the
        # user explicitly clicks Exit they mean exit; the redirect is
        # only for the window-close (X) button.
        f.add_command(label="Exit                                  Ctrl+Q",
                      command=self._force_exit)

        v = tk.Menu(m, tearoff=0)
        for label, value in (("Light", "light"), ("Dark", "dark"), ("System", "system")):
            v.add_radiobutton(label=label, value=value, variable=self.theme_var, command=self.apply_theme)
        v.add_separator()
        # Audible-cue toggle. Stored in app_config so the user's choice
        # survives a restart. Default ON — first-time users want to
        # know when a long job completes.
        self.chime_on_complete_var = tk.BooleanVar(
            value=bool(self.app_config.get("chime_on_complete", True))
        )
        v.add_checkbutton(
            label="Chime on completion",
            variable=self.chime_on_complete_var,
            command=self._save_chime_pref,
        )

        h = tk.Menu(m, tearoff=0)
        h.add_command(label="Open transcript viewer...", command=self._open_transcript_viewer_picker)
        h.add_separator()
        # oTranscribe round-trip — used to be a button on the Transcribe
        # tab; moved here in the UI simplification pass because it's a
        # secondary workflow (most users never touch it), and consumer
        # transcription apps (MacWhisper, Buzz, Aiko) keep
        # secondary imports under a menu.
        h.add_command(
            label="Import oTranscribe (.otr) → SRT...",
            command=self.integrations_service.import_otr_to_srt,
        )
        h.add_command(label="Open oTranscribe website...",
                      command=self.integrations_service.open_otranscribe)
        h.add_separator()
        h.add_command(label="Open log folder", command=self.open_log_folder)
        m.add_cascade(label="File", menu=f)
        m.add_cascade(label="View", menu=v)
        m.add_cascade(label="Help", menu=h)
        # Direct menubar command — clicking "About" opens the dialog in
        # one click. (It used to be a cascade whose only item was
        # another "About", so the user had to click About twice.)
        m.add_command(label="About", command=self._show_about)
        self.config(menu=m)

    def _populate_recent_menu(self) -> None:
        """Re-populate the File > Recent files submenu from history.db.

        Called automatically by Tk every time the user opens the
        submenu (via the ``postcommand`` hook), so the list is always
        current. We list the last 10 file_paths from the history.db
        transcriptions table; an "Open file" click sets fv + selects
        the Transcribe tab without auto-enqueueing.
        """
        menu = self._recent_menu
        menu.delete(0, "end")
        history = getattr(self, "history", None)
        rows: list[dict[str, Any]] = []
        if history is not None:
            try:
                rows = history.list_transcriptions(limit=10) or []
            except Exception:  # noqa: BLE001
                rows = []
        if not rows:
            menu.add_command(label="(no recent files)", state="disabled")
            return
        seen: set[str] = set()
        added = 0
        for row in rows:
            path = row.get("file_path") if isinstance(row, dict) else None
            if not path or path in seen:
                continue
            seen.add(path)
            label = f"{os.path.basename(path)}  —  {os.path.dirname(path)[:48]}"
            menu.add_command(
                label=label,
                command=lambda p=path: self._open_recent(p),
            )
            added += 1
            if added >= 10:
                break
        menu.add_separator()
        menu.add_command(label="Clear list", command=self._clear_recent)

    def _burn_subs_for(self, task: TranscriptionTask) -> None:
        """Burn the SRT next to the task's source media into a new MP4.

        Runs ffmpeg in a daemon thread so the UI stays responsive
        on long videos. On completion, surfaces a log line + chimes
        + opens the output folder. Failure logs via messagebox.
        """
        import threading
        from core import burn_subs

        base, _ = os.path.splitext(task.file_path)
        srt_path = base + ".srt"
        if not os.path.isfile(srt_path):
            messagebox.showwarning(
                "No SRT found",
                f"Expected SRT not found next to source:\n{srt_path}",
                parent=self,
            )
            return
        # Suggest "<base>-subbed.mp4" so the source is never clobbered.
        suggested = base + "-subbed.mp4"
        out_path = filedialog.asksaveasfilename(
            parent=self,
            title="Save burned-in video as...",
            initialfile=os.path.basename(suggested),
            defaultextension=".mp4",
            filetypes=[("MP4 video", "*.mp4"), ("All files", "*.*")],
        )
        if not out_path:
            return

        self.log(f"Burning subtitles into {os.path.basename(out_path)}...")

        def worker() -> None:
            try:
                burn_subs.burn(task.file_path, srt_path, out_path)
                # Tk methods touched from a thread → route via the
                # main-thread queue (self.after(0, ...) from a worker
                # raises RuntimeError on Python 3.14).
                self.post_to_main(lambda: self._burn_subs_done(out_path))
            except Exception as e:  # noqa: BLE001
                # Audit B3: log the stack trace before the lossy
                # UI string-conversion so postmortem diagnosis is
                # possible from logs alone.
                logger.exception(
                    "burn_subs.burn failed: file=%s out=%s",
                    task.file_path, out_path,
                )
                msg = str(e)
                self.post_to_main(lambda: self._burn_subs_failed(msg))

        from core._threads import safe_thread
        safe_thread(worker, name="burn-subs")

    def _burn_subs_done(self, out_path: str) -> None:
        self.log(f"✓ Burned subtitles → {out_path}")
        if getattr(self, "chime_on_complete_var", None) is not None:
            try:
                if self.chime_on_complete_var.get():
                    self.bell()
            except Exception:  # noqa: BLE001
                pass
        self._open_folder(os.path.dirname(out_path) or ".")

    def _burn_subs_failed(self, msg: str) -> None:
        self.log(f"Burn-subs failed: {msg}")
        messagebox.showerror("Burn subtitles failed", msg, parent=self)

    def _open_transcript_viewer_picker(self) -> None:
        """Open the transcript viewer with a file picker."""
        _open_transcript_viewer(self, None)

    def open_transcript_viewer_for(self, file_path: str) -> None:
        """Open the viewer for a transcript JSON found next to file_path.

        Used by the Last Result card's "View transcript" button so a
        user one click away from the just-finished output. If the
        JSON isn't on disk for any reason, we fall back to the file
        picker.
        """
        base, _ = os.path.splitext(file_path)
        json_path = base + ".json"
        if os.path.isfile(json_path):
            _open_transcript_viewer(self, json_path)
        else:
            _open_transcript_viewer(self, None)

    def _open_recent(self, path: str) -> None:
        if not os.path.isfile(path):
            messagebox.showwarning(
                "File missing",
                f"That file is no longer at:\n{path}",
                parent=self,
            )
            return
        self.fv.set(path)
        self.nb.select(self.t1)

    def _clear_recent(self) -> None:
        """Best-effort clear — only present in history if the DB exposes it."""
        history = getattr(self, "history", None)
        if history is None:
            return
        clearer = getattr(history, "clear_recent", None) or getattr(
            history, "delete_old_transcriptions", None
        )
        if callable(clearer):
            try:
                clearer()
            except Exception:  # noqa: BLE001
                pass

    def _save_chime_pref(self) -> None:
        self.app_config["chime_on_complete"] = bool(self.chime_on_complete_var.get())
        try:
            save_config(self.app_config)
        except Exception as e:
            logger.exception("Failed to save chime preference")
            self.log(f"Could not save preference: {e}")

    def _show_about(self) -> None:
        """A full feature inventory in a scrollable Toplevel.

        Many capabilities ship enabled-by-default but live behind
        the Advanced dialog or have no surface in the main UI; this
        dialog is the canonical "what does this app actually do"
        reference and is intentionally exhaustive.
        """
        dlg = tk.Toplevel(self)
        dlg.title("About Whisper Project")
        dlg.transient(self)
        dlg.geometry("680x620")
        dlg.minsize(560, 480)

        header = ttk.Frame(dlg, padding=(16, 14, 16, 8))
        header.pack(fill="x")
        from core import __version__ as _app_ver
        ttk.Label(
            header,
            text=f"Whisper Project — v{_app_ver}",
            font=("TkDefaultFont", 13, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            header,
            text=(
                "A local, offline Windows desktop app that turns audio "
                "and video into subtitles. Powered by OpenAI Whisper "
                "via faster-whisper. No cloud, no API key, no upload."
            ),
            wraplength=640,
            justify="left",
            foreground="#666",
        ).pack(anchor="w", pady=(4, 0))

        body_frame = ttk.Frame(dlg, padding=(16, 4, 16, 8))
        body_frame.pack(fill="both", expand=True)
        text = tk.Text(
            body_frame, wrap="word", borderwidth=0, highlightthickness=0,
            font=("TkDefaultFont", 9), padx=4, pady=4,
        )
        scroll = ttk.Scrollbar(body_frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        text.tag_configure(
            "section", font=("TkDefaultFont", 10, "bold"),
            spacing1=8, spacing3=2,
        )
        text.tag_configure(
            "subsection", font=("TkDefaultFont", 9, "bold"),
            lmargin1=14, lmargin2=14, spacing1=4,
        )
        text.tag_configure(
            "bullet", lmargin1=28, lmargin2=42, spacing1=1, spacing3=1,
        )

        sections: list[tuple[str, list[tuple[str, list[str]]]]] = [
            ("Transcription engine", [
                ("Input", [
                    "Any audio or video file ffmpeg can read",
                    "Drag-and-drop one or many files onto the window",
                    "Browse… (Ctrl+O) for single or multi-select",
                    "Recent-files submenu (last 10 from history)",
                ]),
                ("Models", [
                    "Whisper Large v3 (default, ~3 GB)",
                    "Whisper Large v3 Turbo (~5× faster, ~1.6 GB)",
                    "Distil Large v3.5 (fastest English-only, ~1.5 GB)",
                    "Picker lives in the Advanced dialog",
                ]),
                ("Backends (pluggable)", [
                    "faster-whisper (CTranslate2, default)",
                    "whisper.cpp via pywhispercpp (quantised ggml)",
                    "Parakeet TDT v3 via sherpa-onnx",
                    "Switch in the Advanced dialog",
                ]),
                ("Hardware", [
                    "Autodetect at first launch (CUDA / NPU / DirectML / CPU)",
                    "Choice persisted in hardware.json",
                    "Manual override in the Advanced dialog",
                ]),
                ("Quality controls", [
                    "Voice Activity Detection (Silero VAD), tunable",
                    "Word-level timestamps (opt-in)",
                    "Optional stable-ts word-alignment refinement",
                    "Optional Demucs vocal-separation pre-processing",
                ]),
            ]),
            ("Output formats", [
                ("Files written next to your source", [
                    "SubRip — .srt",
                    "WebVTT — .vtt",
                    "Whisper JSON — .json (segments + word-level data)",
                    "Plain text — .txt",
                    "Tab-separated — .tsv",
                    "LRC lyrics — .lrc",
                    "Markdown — .md",
                    "Microsoft Word — .docx",
                    "PDF — via reportlab",
                ]),
                ("Round-trip", [
                    "oTranscribe import (.otr → .srt)",
                    "oTranscribe export (.srt → .otr) for manual editing",
                ]),
                ("Templating", [
                    "output_filename_template config key with tokens "
                    "{base} {ext} {lang} {date} {speaker_count}",
                    "Sibling subdirectories created on the fly",
                ]),
            ]),
            ("Post-processing", [
                ("Per-file extras", [
                    "Speaker diarisation (sherpa-onnx, no HF token)",
                    "Cross-file speaker voiceprint matching",
                    "Auto-chapter markers (long-silence heuristic)",
                    "Hallucination detector — flags suspect segments "
                    "in the viewer (red rows)",
                ]),
                ("Optional local LLM", [
                    "Qwen2.5-1.5B-Instruct, download-on-first-use",
                    "Summaries, Q&A, AI-generated chapter titles",
                    "Off by default; opt in from the Advanced dialog",
                ]),
            ]),
            ("Video download", [
                ("Sources", [
                    "Any URL yt-dlp supports (YouTube, Vimeo, …)",
                    "Supreme Master TV episode pages "
                    "(multi-quality + article text + series parts)",
                ]),
                ("Pipeline options", [
                    "Format/quality picker per URL",
                    "Audio-only mode (MP3 / m4a / opus)",
                    "Subtitle download + burn-in to video",
                    "SponsorBlock category skipping",
                    "Auto-transcribe after download",
                    "Cookies from browser — download login-walled / "
                    "age-gated content (Facebook / Instagram / TikTok, "
                    "some YouTube Shorts)",
                ]),
            ]),
            ("Transcript viewer", [
                ("Open via", [
                    "Help → Open transcript viewer…",
                    "Last-Result card → View transcript",
                ]),
                ("Editing", [
                    "Find / replace (Ctrl+F), case-insensitive default",
                    "Speaker rename — rewrites every same-labelled segment",
                    "Remove fillers — strips uh/um/er… with whole-word regex",
                    "Atomic save (Ctrl+S)",
                ]),
                ("Playback", [
                    "Embedded VLC when python-vlc + libvlc are installed",
                    "Click-to-seek on any segment",
                    "Karaoke — active word wrapped in [brackets] as VLC plays",
                ]),
                ("Display", [
                    "Word-confidence colour coding "
                    "(green ≥ 0.85, amber ≥ 0.6, red below)",
                    "Type-as-you-search filter",
                ]),
            ]),
            ("Workflow + system integration", [
                ("Queue", [
                    "Multi-file batch with per-file progress",
                    "Parallel workers (configurable, default 2)",
                    "Cancel a running job (Esc)",
                ]),
                ("Automation", [
                    "Watched folder — auto-enqueue files dropped in",
                    "Windows Explorer right-click "
                    "\"Transcribe with Whisper Project\" (optional install task)",
                    "Per-folder .whisperproject.json overrides",
                ]),
                ("Desktop", [
                    "System tray + minimise-to-tray (opt-in)",
                    "Native Windows toast on completion + chime",
                    "High-DPI scaling",
                    "Light / dark / system theme",
                ]),
                ("Reliability", [
                    "Crash-auto-resume — re-enqueues interrupted files",
                    "Worker subprocess with 5 s heartbeat + 30 s watchdog",
                    "history.db opens in WAL mode + integrity check",
                    "--safe-mode CLI flag backs up config and re-runs first-run",
                ]),
            ]),
            ("Search + statistics", [
                ("History", [
                    "Every finished job recorded in SQLite history.db",
                    "File → Recent files (last 10)",
                    "File → Statistics… — total minutes transcribed, etc.",
                ]),
                ("Search", [
                    "Semantic + FTS5 full-text search across saved transcripts",
                ]),
            ]),
            ("Keyboard shortcuts", [
                ("Global", [
                    "Ctrl+O — Browse for files",
                    "Ctrl+Enter — Transcribe selected",
                    "Esc — Cancel running job",
                    "Ctrl+Q — Exit (bypasses minimise-to-tray)",
                ]),
                ("Viewer", [
                    "Ctrl+F — Find / replace",
                    "Ctrl+S — Save edits",
                ]),
            ]),
            ("Privacy", [
                ("Default", [
                    "Everything runs locally; no network call without your action",
                ]),
                ("Opt-in telemetry", [
                    "Anonymous launch ping (config: telemetry_opt_in)",
                    "Sentry crash reporting (env: SENTRY_DSN + opt-in)",
                ]),
            ]),
        ]

        for section_title, subsections in sections:
            text.insert("end", section_title + "\n", "section")
            for sub_title, bullets in subsections:
                text.insert("end", sub_title + "\n", "subsection")
                for line in bullets:
                    text.insert("end", "• " + line + "\n", "bullet")

        text.configure(state="disabled")

        footer = ttk.Frame(dlg, padding=(16, 4, 16, 14))
        footer.pack(fill="x")
        ttk.Button(footer, text="OK", command=dlg.destroy).pack(side="right")

        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        dlg.update_idletasks()
        try:
            dlg.grab_set()
        except tk.TclError:
            pass

    def show_statistics(self) -> None:
        _show_stats(self)

    def open_log_folder(self) -> None:
        path = open_log_folder()
        logger.info("Opened log folder: %s", path)

    def apply_theme(self) -> None:
        name = self.theme_var.get()
        sv_ttk.set_theme(_resolve_theme(name))
        self.app_config["theme"] = name
        save_config(self.app_config)

    def _force_exit(self) -> None:
        """Bypass the minimise-to-tray redirect and exit immediately.

        Called by File → Exit, Ctrl+Q, and the tray menu's Exit item.
        The window's X button (WM_DELETE_WINDOW) continues to honour
        the minimise-to-tray preference.
        """
        self._exit_from_tray = True
        self.on_exit()

    def on_exit(self) -> None:
        # Optional minimise-to-tray: when the user has enabled tray
        # support in the Advanced dialog and the tray icon is running,
        # the window's close (X) button hides the window instead of
        # tearing down. File → Exit / Ctrl+Q route through
        # _force_exit() which sets _exit_from_tray=True so they
        # always exit regardless of the preference.
        if (
            not self._exit_from_tray
            and bool(self.app_config.get("minimise_to_tray", False))
            and self.tray is not None
            and self.tray.is_supported()
        ):
            try:
                self.withdraw()
                self.log("Window minimised to tray. Right-click the tray icon to exit.")
            except Exception:  # noqa: BLE001
                pass
            return

        # Flip the closing flag so watcher events / stability-checks
        # in flight short-circuit before touching destroyed widgets.
        self._closing = True

        active = [t for t in self.queue if t.status not in ("finished", "cancelled", "error")]
        active_downloads = [
            t for t in self.download_queue if t.status not in ("finished", "cancelled", "error")
        ]
        if active or active_downloads:
            if not messagebox.askyesno(
                "Exit with queued tasks",
                "There are queued or running tasks. Exit anyway?",
                parent=self,
            ):
                return
        # Persist window size + position so the next launch reopens at
        # the same shape. Runs *before* terminating subprocesses so it
        # never sees a broken state.
        self._save_window_geometry()
        if self._folder_watcher is not None:
            try:
                self._folder_watcher.stop()
            except Exception:  # noqa: BLE001
                pass
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:  # noqa: BLE001
                pass
        for task in self.download_queue:
            if task.process and task.process.poll() is None:
                task.process.terminate()
        self.transcription_service.stop_all()
        self.destroy()

    def destroy(self) -> None:  # type: ignore[override]
        # Cancel every pending after() callback before tearing down the
        # Tcl interpreter. Otherwise the service poll loops fire one last
        # time after destroy() and spam the console with
        #   invalid command name "<id>poll"
        # because their bound-method Tcl command no longer exists.
        #
        # tk.call("after", "info") returns a tuple of IDs when >=1 callback
        # is pending and an empty string when none are. The earlier
        # str(pending).split() path produced garbage tokens like
        # "('after#0',)" for the tuple case, which after_cancel silently
        # accepts without actually cancelling — so the fix was a no-op.
        try:
            pending = self.tk.call("after", "info")
            if isinstance(pending, (tuple, list)):
                ids = list(pending)
            else:
                text = str(pending).strip()
                ids = text.split() if text else []
            for cb_id in ids:
                try:
                    self.after_cancel(cb_id)
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
        super().destroy()

    # Tabs --------------------------------------------------------------------
    def _build_tabs(self) -> None:
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        self.t1 = ttk.Frame(self.nb)
        self.t2 = ttk.Frame(self.nb)
        self.t3 = ttk.Frame(self.nb)
        self.nb.add(self.t1, text="Transcribe")
        self.nb.add(self.t2, text="Transcription Queue")
        self.nb.add(self.t3, text="Download Videos")
        build_transcribe_tab(self, self.t1)
        build_queue_tab(self, self.t2)
        build_download_tab(self, self.t3)

    def _save_auto_transcribe_pref(self) -> None:
        self.app_config["auto_transcribe_after_download"] = bool(self.auto_transcribe_var.get())
        try:
            save_config(self.app_config)
        except Exception as e:
            # Audit B1 / FB-01: config-save failures must NOT be
            # silent. The user has just toggled a preference; if
            # the disk write fails (permission denied, antivirus
            # lock), they need to know — otherwise their choice
            # silently reverts on the next launch.
            logger.exception("Failed to save auto-transcribe preference")
            self.log(f"Could not save preference: {e}")

    def _save_transcribe_prefs(self) -> None:
        self.app_config["vad_enabled"] = bool(self.vad_enabled_var.get())
        self.app_config["word_timestamps"] = bool(self.word_timestamps_var.get())
        if getattr(self, "diarization_var", None) is not None:
            self.app_config["diarization_enabled"] = bool(self.diarization_var.get())
        # transcribe_language is intentionally NOT persisted: the picker
        # resets to "Auto" every launch (user request). The choice still
        # lives in transcribe_lang_var for the rest of the session.
        if getattr(self, "device_var", None) is not None:
            self.app_config["device"] = self.device_var.get()
        if getattr(self, "compute_type_var", None) is not None:
            self.app_config["compute_type"] = self.compute_type_var.get()
        if getattr(self, "hotwords_var", None) is not None:
            self.app_config["hotwords"] = self.hotwords_var.get().strip()
        try:
            save_config(self.app_config)
        except Exception as e:
            logger.exception("Failed to save transcribe preferences")
            self.log(f"Could not save preferences: {e}")

    def open_advanced_dialog(self) -> None:
        AdvancedDialog(self)

    # Generic helpers ---------------------------------------------------------
    def yt_dlp_path(self) -> str:
        exe = "yt-dlp.exe" if os.name == "nt" else "yt-dlp"
        return os.path.join(_resource_bin_dir(), exe)

    def bin_path(self) -> str:
        return _resource_bin_dir()

    def browse(self) -> None:
        """Pick one or more files.

        The dialog supports multi-select; if the user picks several
        files we enqueue each. Single-file selection still just
        populates the file-picker entry without auto-enqueueing —
        keeps the muscle-memory of "Browse → Transcribe" intact.
        """
        chosen = filedialog.askopenfilenames(parent=self)
        if not chosen:
            return
        if len(chosen) == 1:
            self.fv.set(chosen[0])
            return
        count = 0
        for path in chosen:
            self.fv.set(path)
            self.add()
            count += 1
        self.log(f"Enqueued {count} files via Browse...")

    def browse_download_folder(self) -> None:
        folder = filedialog.askdirectory()
        if folder:
            self.download_folder_var.set(folder)
            self.app_config["download_folder"] = folder
            save_config(self.app_config)

    def update_download_mode(self) -> None:
        audio_only = self.download_mode_var.get() == "Audio"
        if audio_only:
            self.video_format_combo.configure(state="disabled")
            outputs = ("mp3", "m4a", "aac", "opus", "flac", "wav")
            if self.output_format_var.get() not in outputs:
                self.output_format_var.set("mp3")
        else:
            self.video_format_combo.configure(state="readonly")
            outputs = ("mp4", "mkv", "webm")
            if self.output_format_var.get() not in outputs:
                self.output_format_var.set("mp4")
        self.output_format_combo["values"] = outputs

    def update_subtitle_state(self) -> None:
        if self.download_subtitles_var.get():
            self.subtitle_lang_combo.configure(state="readonly")
        else:
            self.subtitle_lang_combo.configure(state="disabled")
            self.subtitle_status_var.set("")

    def model_status(self, msg: str) -> None:
        self.status_var.set(msg)
        self.log(msg)
        if "Model loaded" in msg:
            self.model_ready = True

    # Modal model setup -------------------------------------------------------
    def ensure_model_with_modal(self, mandatory: bool = False) -> bool:
        if self.model_ready:
            self.status_var.set("Model loaded")
            return True
        if self.model_setup_running:
            return False
        self.model_setup_running = True
        dialog = ModelDownloadDialog(self)
        self.wait_window(dialog)
        self.model_setup_running = False
        if dialog.success:
            # v1.0.3 — lazy model load.
            # Used to call ``transcription_service.start_standby()``
            # here to spawn a worker the moment the model bytes
            # finished downloading. We no longer preload — the worker
            # spawns on the first transcribe via
            # ``ensure_worker_ready``, which puts up its own modal.
            # Just log that the bytes are ready.
            self.log("Model downloaded.")
            return True
        self.model_ready = False
        self.status_var.set("Model is required")
        if mandatory:
            self.log("Model setup was cancelled or failed.")
        return False

    # Adding tasks ------------------------------------------------------------
    def add(self) -> None:
        text = self.fv.get().strip()
        if not text:
            self.log("Pick a file first — use the Browse button on the Transcribe tab.")
            return
        # YouTube / yt-dlp URL detection — if the user pastes a URL
        # into the Transcribe file field, route it through the
        # Download tab with auto-transcribe-after-download on. The
        # download flow is the established way to fetch network
        # media; we just connect the dots.
        if text.startswith(("http://", "https://")):
            try:
                self.download_url_var.set(text)
                if hasattr(self, "auto_transcribe_var"):
                    self.auto_transcribe_var.set(True)
                self.nb.select(self.t3)
                self.log(
                    f"URL detected — pasted into the Download tab with "
                    f"auto-transcribe ON: {text[:60]}"
                )
            except Exception as e:  # noqa: BLE001
                self.log(f"URL handoff failed: {e}")
            return
        # Local-path sanity: a deleted / mistyped path would otherwise
        # enqueue a task that only fails deep in the worker with a cryptic
        # error. Catch it here where we can give a clear message.
        if not os.path.isfile(text):
            self.log(f"File not found — pick an existing file: {text}")
            return
        # First-transcribe gating:
        #   1. If the model bytes are not on disk → download dialog.
        #   2. Then call ensure_worker_ready to lazy-load the model
        #      into a worker subprocess. v1.0.3: was previously
        #      preloaded at startup; deferring it here saves ~1.5 GB
        #      of idle RAM in sessions where the user never clicks
        #      Transcribe.
        if not self._model_bytes_present():
            if self.model_setup_running:
                self.log("Model download already in progress — please wait.")
                return
            if not messagebox.askyesno(
                "Whisper model required",
                "The Whisper model must be downloaded before the first transcription. "
                "Download it now? (about 3 GB, one time only)",
                parent=self,
            ):
                self.log("Transcription cancelled: the Whisper model is required.")
                return
            if not self.ensure_model_with_modal():
                self.log("Transcription cancelled: the Whisper model is not ready.")
                return
        if not self.transcription_service.ensure_worker_ready(self):
            self.log("Transcription cancelled: model load was cancelled")
            return
        # Per-task language override. The picker shows "Auto" for the
        # default Whisper auto-detect; any other value is a language
        # name that maps to a known code via app.domain.languages.
        task = TranscriptionTask(self.fv.get())
        lang_choice = getattr(self, "transcribe_lang_var", None)
        if lang_choice is not None:
            choice = lang_choice.get().strip()
            if choice and choice.lower() != "auto":
                from app.domain.languages import SUBTITLE_LANGUAGES
                code = next(
                    (c for name, c in SUBTITLE_LANGUAGES if name == choice),
                    "",
                )
                if code:
                    task.language = code
        self.queue.append(task)
        self.pb["value"] = 0
        self.nb.select(self.t2)
        self.log(f"Queued: {os.path.basename(self.fv.get())}")
        self.refresh()

    def _model_bytes_present(self) -> bool:
        """True when the Whisper model files are already on disk.

        Cheap probe used by the lazy-load enqueue gate to decide
        whether to surface the ~3 GB download dialog. Just checks
        that the configured ``model_path`` exists; the worker's
        load step will surface any deeper corruption via a
        ``startup_error`` event.
        """
        try:
            from pathlib import Path
            mp = self.app_config.get("model_path") or ""
            return bool(mp) and Path(mp).exists()
        except Exception:  # noqa: BLE001
            return False

    def enqueue_transcription_from_download(
        self, file_path: str, language: str, source_download: "Any" = None
    ) -> None:
        """Auto-transcribe-after-download wiring: push a task without freezing.

        Runs on the Tk main thread (the download-complete handler). A
        cold Whisper-model load takes 10–60 s, and the old code waited
        for the worker's ``ready`` event synchronously here — which
        froze the whole UI after every download with the checkbox on
        (the "Transcribe after download freezes the app" bug).

        Instead we spawn a worker if none is alive yet and poll for
        readiness with ``after()`` so the event loop keeps running; the
        task is enqueued the moment a worker reports ready. If the load
        never completes we drop the task rather than queue one that can
        never run.
        """
        base = os.path.basename(file_path)

        def _enqueue() -> None:
            task = TranscriptionTask(file_path)
            if hasattr(task, "language"):
                setattr(task, "language", language)
            # Link the originating download row to this transcription so
            # the Download tab shows "transcribing" + live progress, then
            # flips back to "finished" when the transcription ends.
            if source_download is not None:
                task.source_download = source_download
                source_download.transcription_task = task
                source_download.status = "transcribing"
                self.refresh_download_queue()
            self.queue.append(task)
            self.refresh()

        def _on_timeout() -> None:
            self.log(f"Auto-transcribe skipped: model load timed out for {base}")
            if source_download is not None:
                source_download.status = "finished"
                source_download.transcription_task = None
                self.refresh_download_queue()

        self._when_worker_ready(
            _enqueue,
            on_timeout=_on_timeout,
            loading_label=f"will transcribe {base} when ready.",
        )

    def _when_worker_ready(
        self,
        on_ready: Callable[[], None],
        *,
        on_timeout: Callable[[], None] | None = None,
        loading_label: str = "",
    ) -> None:
        """Run ``on_ready`` on the Tk main thread once a transcription
        worker is loaded, without blocking the event loop.

        Every main-thread enqueue path (auto-transcribe-after-download,
        crash-resume, watched-folder) used to call
        ``ensure_worker_ready(headless=True)``, which blocks on a
        ``threading.Event.wait`` for up to the model-load timeout. Those
        handlers run on the Tk main thread, so a cold model load froze
        the whole UI. This spawns a worker if none is alive and polls
        for readiness with ``after()`` instead; ``on_timeout`` (if
        given) runs when the load doesn't finish within the timeout.
        """
        from app.services.transcription_service import HEADLESS_READY_TIMEOUT_S
        svc = self.transcription_service
        if svc.ready_workers():
            on_ready()
            return
        # Spawn a worker if none is alive yet — but don't spawn a second
        # if one is already loading (a parallel path may have started it).
        if not svc.active_workers():
            svc.start_worker(temporary=False)
            if loading_label:
                self.log(f"Loading Whisper model — {loading_label}")
        deadline = time.monotonic() + HEADLESS_READY_TIMEOUT_S

        def _await_ready() -> None:
            if svc.ready_workers():
                on_ready()
                return
            if time.monotonic() >= deadline:
                if on_timeout is not None:
                    on_timeout()
                return
            self.after(400, _await_ready)

        self.after(400, _await_ready)

    def add_download(self) -> None:
        self.download_service.enqueue_from_form()

    # Right-click context menus -----------------------------------------------
    def menu_row(self, e: tk.Event) -> None:
        item = self.tree.identify_row(e.y)
        if not item:
            return
        sel = self.tree.selection()
        # If the right-clicked row is part of a multi-row selection, act
        # on the whole selection (bulk) rather than resetting to one row.
        if item in sel and len(sel) > 1:
            tasks = [t for t in (self.row_map.get(i) for i in sel) if t]
            if tasks:
                self._bulk_task_menu(tasks, e)
            return
        self.tree.selection_set(item)
        task = self.row_map.get(item)
        if not task:
            return
        m = tk.Menu(self, tearoff=0)
        if task.status == "waiting":
            m.add_command(label="Cancel", command=lambda: self.cancel(task))
        elif task.status == "running":
            m.add_command(label="Pause", command=lambda: self.pause(task))
            m.add_command(label="Cancel", command=lambda: self.cancel(task))
        elif task.status == "paused":
            m.add_command(label="Resume", command=lambda: self.resume(task))
            m.add_command(label="Cancel", command=lambda: self.cancel(task))
        elif task.status in ("finished", "cancelled", "error"):
            if task.status == "finished":
                m.add_command(
                    label="Export → oTranscribe (.otr)",
                    command=lambda: self.integrations_service.export_task_to_otr(task),
                )
                m.add_command(
                    label="Burn subtitles into video...",
                    command=lambda: self._burn_subs_for(task),
                )
                m.add_command(
                    label="View transcript",
                    command=lambda: self.open_transcript_viewer_for(task.file_path),
                )
                m.add_command(
                    label="Open output folder",
                    command=lambda: self._open_folder(os.path.dirname(task.file_path)),
                )
                m.add_separator()
            # Resume-from-cancellation: if a partial checkpoint
            # exists for this cancelled task, surface a "Resume"
            # entry above "Re-run". Only the cancelled path is wired
            # — for "error" and "finished" we don't want to invite
            # the user to resume from a stale partial that may have
            # been produced by a different config.
            if task.status == "cancelled":
                try:
                    from core.transcriber import has_resumable_checkpoint
                    if has_resumable_checkpoint(task.file_path):
                        m.add_command(
                            label="Resume",
                            command=lambda: self.resume_task(task),
                        )
                except Exception:  # noqa: BLE001
                    # Checkpoint probe must never block the menu.
                    pass
            m.add_command(label="Re-run", command=lambda: self._rerun_task(task))
            m.add_command(label="Remove", command=lambda: self.remove_task(task))
        m.tk_popup(e.x_root, e.y_root)

    def download_menu_row(self, e: tk.Event) -> None:
        item = self.download_tree.identify_row(e.y)
        if not item:
            return
        sel = self.download_tree.selection()
        if item in sel and len(sel) > 1:
            tasks = [t for t in (self.download_row_map.get(i) for i in sel) if t]
            if tasks:
                self._bulk_download_menu(tasks, e)
            return
        task = self.download_row_map.get(item)
        if not task:
            return
        m = tk.Menu(self, tearoff=0)
        if task.status in ("waiting", "running"):
            m.add_command(label="Cancel", command=lambda: self.cancel_download(task))
        elif task.status in ("finished", "cancelled", "error"):
            saved = getattr(task, "saved_path", None)
            if task.status == "finished" and saved and os.path.isfile(saved):
                m.add_command(
                    label="Open file",
                    command=lambda p=saved: self._open_file(p),
                )
            m.add_command(
                label="Open download folder",
                command=lambda: self._open_folder(task.folder),
            )
            m.add_command(label="Re-run", command=lambda: self._rerun_download(task))
            m.add_command(label="Remove", command=lambda: self.remove_download(task))
        m.tk_popup(e.x_root, e.y_root)

    # --- bulk (multi-select) queue actions -----------------------------------
    def _bulk_apply(self, tasks: list[Any], fn: Callable[[Any], Any]) -> None:
        for t in list(tasks):
            try:
                fn(t)
            except Exception:  # noqa: BLE001
                pass

    def _resumable_tasks(self, tasks: list[Any]) -> list[Any]:
        try:
            from core.transcriber import has_resumable_checkpoint
        except Exception:  # noqa: BLE001
            return []
        out: list[Any] = []
        for t in tasks:
            if getattr(t, "status", "") == "cancelled":
                try:
                    if has_resumable_checkpoint(t.file_path):
                        out.append(t)
                except Exception:  # noqa: BLE001
                    pass
        return out

    def _bulk_rerun(self, tasks: list[Any]) -> None:
        if not self.transcription_service.ensure_worker_ready(self):
            self.log("Re-run cancelled: model load was cancelled")
            return
        for t in tasks:
            nt = TranscriptionTask(t.file_path)
            if getattr(t, "language", None):
                nt.language = t.language
            self.queue.append(nt)
        self.refresh()

    def _bulk_resume(self, tasks: list[Any]) -> None:
        if not self.transcription_service.ensure_worker_ready(self):
            self.log("Resume cancelled: model load was cancelled")
            return
        for t in tasks:
            nt = TranscriptionTask(t.file_path)
            if getattr(t, "language", None):
                nt.language = t.language
            nt.resume = True
            nt.cancelled = False
            self.queue.append(nt)
        self.refresh()

    def _bulk_task_menu(self, tasks: list[Any], e: tk.Event) -> None:
        active = [t for t in tasks if t.status in ("waiting", "running", "paused")]
        terminal = [t for t in tasks if t.status in ("finished", "cancelled", "error")]
        if not active and not terminal:
            return
        m = tk.Menu(self, tearoff=0)
        if active:
            m.add_command(label=f"Cancel selected ({len(active)})",
                          command=lambda ts=active: self._bulk_apply(ts, self.cancel))
        if terminal:
            m.add_command(label=f"Re-run selected ({len(terminal)})",
                          command=lambda ts=terminal: self._bulk_rerun(ts))
            resumable = self._resumable_tasks(terminal)
            if resumable:
                m.add_command(label=f"Resume selected ({len(resumable)})",
                              command=lambda ts=resumable: self._bulk_resume(ts))
            m.add_command(label=f"Remove selected ({len(terminal)})",
                          command=lambda ts=terminal: self._bulk_apply(ts, self.remove_task))
        m.tk_popup(e.x_root, e.y_root)

    def _bulk_download_menu(self, tasks: list[Any], e: tk.Event) -> None:
        active = [t for t in tasks if t.status in ("waiting", "running")]
        terminal = [t for t in tasks if t.status in ("finished", "cancelled", "error")]
        if not active and not terminal:
            return
        m = tk.Menu(self, tearoff=0)
        if active:
            m.add_command(label=f"Cancel selected ({len(active)})",
                          command=lambda ts=active: self._bulk_apply(ts, self.cancel_download))
        if terminal:
            m.add_command(label=f"Re-run selected ({len(terminal)})",
                          command=lambda ts=terminal: self._bulk_apply(ts, self._rerun_download))
            m.add_command(label=f"Remove selected ({len(terminal)})",
                          command=lambda ts=terminal: self._bulk_apply(ts, self.remove_download))
        m.tk_popup(e.x_root, e.y_root)

    def _open_folder(self, folder: str) -> None:
        _open_folder_helper(folder, parent=self)

    def _rerun_task(self, task: TranscriptionTask) -> None:
        # Right-click re-run is an interactive action: show the
        # lazy-load modal if no worker is alive yet.
        if not self.transcription_service.ensure_worker_ready(self):
            self.log("Re-run cancelled: model load was cancelled")
            return
        new_task = TranscriptionTask(task.file_path)
        if getattr(task, "language", None):
            new_task.language = task.language
        self.queue.append(new_task)
        self.refresh()

    def resume_task(self, task: TranscriptionTask) -> None:
        """Re-enqueue a cancelled task to resume from its checkpoint.

        We don't try to revive the original task object in place: the
        cancel path tore down its worker and the row is in a terminal
        state. A fresh TranscriptionTask carrying ``resume=True`` is
        clearer for the user (a new Queue row appears) and matches
        the existing ``_rerun_task`` pattern.

        The worker side falls back to a full re-run if the checkpoint
        turns out to be stale at validation time, so the user always
        gets an output.
        """
        # Interactive — surface the lazy-load modal if needed.
        if not self.transcription_service.ensure_worker_ready(self):
            self.log("Resume cancelled: model load was cancelled")
            return
        new_task = TranscriptionTask(task.file_path)
        if getattr(task, "language", None):
            new_task.language = task.language
        new_task.resume = True
        new_task.cancelled = False
        self.queue.append(new_task)
        self.refresh()

    def _rerun_download(self, task: VideoDownloadTask) -> None:
        from app.domain.tasks import VideoDownloadTask as VDT
        copy = VDT(
            task.url, task.folder, task.format_label, task.format_info, task.title,
            subtitles_enabled=task.subtitles_enabled,
            subtitle_lang=task.subtitle_lang,
            detected_language=task.detected_language,
            # Preserve the time-range slice — without this a re-run silently
            # fetched the full video instead of the slice the user picked.
            section_start=task.section_start,
            section_end=task.section_end,
        )
        self.download_queue.append(copy)
        self.refresh_download_queue()
        self.download_service.process_queue()

    def cancel_download(self, task: VideoDownloadTask) -> None:
        task.cancelled = True
        task.status = "cancelled"
        # Freeze the Elapsed column at the cancel moment.
        if task.end_time is None:
            task.end_time = time.time()
        if task.process and task.process.poll() is None:
            task.process.terminate()
        # If the download had already handed off to auto-transcribe, stop
        # that too and unlink it — otherwise the transcription keeps running
        # and finish_task would later overwrite this "cancelled" status.
        tr = getattr(task, "transcription_task", None)
        if tr is not None:
            task.transcription_task = None
            try:
                tr.source_download = None
                self.cancel(tr)
            except Exception:  # noqa: BLE001
                pass
        self.refresh_download_queue()

    def remove_download(self, task: VideoDownloadTask) -> None:
        if task in self.download_queue:
            self.download_queue.remove(task)
        self.refresh_download_queue()

    def pause(self, t: TranscriptionTask) -> None:
        t.paused = True
        t.status = "paused"
        self.refresh()

    def resume(self, t: TranscriptionTask) -> None:
        t.paused = False
        t.status = "running"
        self.refresh()

    def cancel(self, t: TranscriptionTask) -> None:
        t.cancelled = True
        t.status = "cancelled"
        # Freeze the Elapsed column at the cancel moment so the user
        # sees how long the task actually ran before they killed it.
        if getattr(t, "end_time", None) is None:
            t.end_time = time.time()
        for worker in self.workers:
            if worker["task"] == t:
                self.log("Cancelling running task and restarting its worker...")
                worker["task"] = None
                if worker.get("temporary") and not any(task.status == "waiting" for task in self.queue):
                    self.transcription_service.retire_worker(worker)
                else:
                    self.transcription_service.restart_worker(worker)
                break
        self.refresh()

    def remove_task(self, t: TranscriptionTask) -> None:
        if t in self.queue:
            self.queue.remove(t)
        self.refresh()

    def clear_completed(self) -> None:
        self.queue[:] = [t for t in self.queue if t.status not in ("finished", "cancelled", "error")]
        self.refresh()

    # Rendering ---------------------------------------------------------------
    def fmt_time(self, t: Any) -> str:
        if not getattr(t, "start_time", None):
            return ""
        # Freeze at end_time once the task is in a terminal state
        # (finished / cancelled / error). Before this, the Elapsed
        # column kept incrementing forever — the user never saw
        # "this file took 1m 22s", just a number that grew while
        # they were doing something else.
        end = getattr(t, "end_time", None)
        if end is not None:
            s = end - t.start_time
        else:
            s = time.time() - t.start_time
        s = max(0.0, s)
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        sec = int(s % 60)
        return f"{h:02}:{m:02}:{sec:02}"

    def _download_row_progress(self, task: Any) -> float:
        # While an auto-transcribe runs, the download row mirrors the
        # linked transcription's live progress (else it sits at 100%).
        tr = getattr(task, "transcription_task", None)
        if task.status == "transcribing" and tr is not None:
            return tr.progress
        return task.progress

    def _row_progress_text(self, status: str, progress: float) -> str:
        """Progress text for a queue row: the real bar, or an indeterminate
        marquee while the row is working but has no percentage yet (e.g.
        during the model load before the first segment)."""
        from app.widgets.tabs import marquee_cell, progress_cell

        if status in ("running", "transcribing") and (progress or 0) <= 0:
            return marquee_cell(getattr(self, "_anim_frame", 0))
        return progress_cell(progress)

    def _ensure_animation(self) -> None:
        """Start the marquee loop if any row is working without a real %."""
        if getattr(self, "_anim_running", False):
            return
        needs = any(
            t.status == "running" and (t.progress or 0) <= 0 for t in self.queue
        ) or any(
            d.status in ("running", "transcribing")
            and (self._download_row_progress(d) or 0) <= 0
            for d in self.download_queue
        )
        if needs:
            self._anim_running = True
            self._animate_tick()

    def _animate_tick(self) -> None:
        from app.widgets.tabs import marquee_cell

        self._anim_frame = getattr(self, "_anim_frame", 0) + 1
        bar = marquee_cell(self._anim_frame)
        active = False
        for item_id, t in list(getattr(self, "row_map", {}).items()):
            if t.status == "running" and (t.progress or 0) <= 0:
                active = True
                try:
                    self.tree.set(item_id, "progress", bar)
                except tk.TclError:
                    pass
        for item_id, d in list(getattr(self, "download_row_map", {}).items()):
            if d.status in ("running", "transcribing") and (self._download_row_progress(d) or 0) <= 0:
                active = True
                try:
                    self.download_tree.set(item_id, "progress", bar)
                except tk.TclError:
                    pass
        if active:
            self.after(250, self._animate_tick)
        else:
            self._anim_running = False

    def refresh(self) -> None:
        from app.widgets.tabs import status_label

        self.tree.delete(*self.tree.get_children())
        self.row_map = {}
        for t in self.queue:
            lang = getattr(t, "detected_language", "") or ""
            prob = getattr(t, "language_probability", None)
            lang_str = f"{lang} ({prob * 100:.0f}%)" if (lang and isinstance(prob, (int, float))) else lang
            item_id = self.tree.insert(
                "",
                "end",
                values=(
                    os.path.basename(t.file_path),
                    status_label(t.status),
                    self._row_progress_text(t.status, t.progress),
                    lang_str,
                    self.fmt_time(t),
                ),
            )
            self.row_map[item_id] = t
        # Empty-state hint visibility — show when the queue is empty,
        # hide once there is at least one task. Kept here (rather than
        # in tabs.py) because refresh is the choke point for queue
        # changes, so the placeholder can't drift out of sync.
        if hasattr(self, "queue_empty_label"):
            if self.queue:
                self.queue_empty_label.pack_forget()
            else:
                self.queue_empty_label.pack(fill="x", pady=(2, 0))
        # Reflect work-in-progress in the window title so users with
        # the app minimised see "Whisper — 34% transcribing foo.mp4"
        # in their taskbar / Alt-Tab.
        self._refresh_window_title()
        self._ensure_animation()

    def refresh_download_queue(self) -> None:
        from app.widgets.tabs import status_label

        self.download_tree.delete(*self.download_tree.get_children())
        self.download_row_map = {}
        for task in self.download_queue:
            # While auto-transcribe runs, mirror the linked transcription's
            # live progress on the download row (otherwise a finished
            # download would sit at 100% and look idle while it transcribes).
            prog = self._download_row_progress(task)
            item_id = self.download_tree.insert(
                "",
                "end",
                values=(
                    task.title,
                    task.url,
                    task.format_label,
                    status_label(task.status),
                    self._row_progress_text(task.status, prog),
                    self.fmt_time(task),
                ),
            )
            self.download_row_map[item_id] = task
        self._refresh_window_title()
        self._ensure_animation()

    # -- UX helpers (Phase v0.7.1 — user-friendly result surfacing) ----------

    def _refresh_window_title(self) -> None:
        """Update the Tk window title so the taskbar / Alt-Tab reflects state.

        Idle: "Whisper Project".
        One running task: "Whisper Project — 34% transcribing foo.mp4".
        Multiple running: "Whisper Project — 2 tasks (avg 41%)".
        """
        running = [t for t in self.queue if t.status == "running"]
        running_dl = [
            d for d in self.download_queue if d.status == "running"
        ]
        # Sync the tray icon colour to current activity.
        if self.tray is not None:
            try:
                self.tray.set_active(bool(running or running_dl))
            except Exception:  # noqa: BLE001
                pass
        if not running and not running_dl:
            self.title(self._base_title)
            return
        if running and not running_dl and len(running) == 1:
            t = running[0]
            self.title(
                f"{self._base_title} — {t.progress}% transcribing "
                f"{os.path.basename(t.file_path)}"
            )
            return
        if running_dl and not running and len(running_dl) == 1:
            d = running_dl[0]
            self.title(
                f"{self._base_title} — {d.progress}% downloading "
                f"{d.title[:40] if d.title else d.url[:40]}"
            )
            return
        total = len(running) + len(running_dl)
        all_p = [t.progress for t in running] + [d.progress for d in running_dl]
        avg = sum(all_p) // len(all_p) if all_p else 0
        self.title(f"{self._base_title} — {total} tasks (avg {avg}%)")

    def show_last_result(self, task: "TranscriptionTask") -> None:
        """Populate the Transcribe-tab Last Result card.

        Called by TranscriptionService.finish_task when a job
        completes successfully. Lists every output file that
        actually exists on disk next to the input, with sizes and
        one-click "Open" buttons. Also offers a single "Open folder"
        button as a shortcut.
        """
        from app.widgets.tabs import _fmt_bytes

        if not hasattr(self, "last_result_frame"):
            return

        try:
            self.last_result_empty_label.pack_forget()
        except Exception:  # noqa: BLE001
            pass

        # Wipe any previous result card body and rebuild from scratch
        # — simpler than diff-updating a handful of widgets.
        for child in list(self.last_result_body.winfo_children()):
            child.destroy()
        try:
            self.last_result_body.pack_forget()
        except Exception:  # noqa: BLE001
            pass

        base, _ = os.path.splitext(task.file_path)
        folder = os.path.dirname(task.file_path) or "."
        candidates = [
            f"{base}.srt",
            f"{base}.json",
            f"{base}.vtt",
            f"{base}.tsv",
            f"{base}.txt",
            f"{base}.lrc",
        ]
        existing = [p for p in candidates if os.path.isfile(p)]

        ttk.Label(
            self.last_result_body,
            text=f"✓ {os.path.basename(task.file_path)}",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w")
        if existing:
            ttk.Label(
                self.last_result_body,
                text=f"Saved {len(existing)} output file"
                     f"{'' if len(existing) == 1 else 's'} in {folder}",
                foreground="#666",
            ).pack(anchor="w", pady=(2, 6))

            files_frame = ttk.Frame(self.last_result_body)
            files_frame.pack(fill="x")
            for path in existing:
                row = ttk.Frame(files_frame)
                row.pack(fill="x", pady=1)
                size = _fmt_bytes(os.path.getsize(path))
                ttk.Label(
                    row, text=f"• {os.path.basename(path)}  ({size})"
                ).pack(side="left")
                ttk.Button(
                    row, text="Open",
                    command=lambda p=path: self._open_file(p),
                ).pack(side="right")
        else:
            ttk.Label(
                self.last_result_body,
                text="(no output files were found on disk — re-run the task?)",
                foreground="#a00",
            ).pack(anchor="w")

        button_row = ttk.Frame(self.last_result_body)
        button_row.pack(anchor="w", pady=(8, 0))
        ttk.Button(
            button_row, text="Open folder",
            command=lambda: self._open_folder(folder),
        ).pack(side="left")
        # "View transcript" launches the in-app viewer with the JSON
        # next to the source media (or the file picker if no JSON
        # found). Discoverable single click into the new viewer.
        if any(p.endswith(".json") for p in existing):
            ttk.Button(
                button_row, text="View transcript",
                command=lambda: self.open_transcript_viewer_for(task.file_path),
            ).pack(side="left", padx=(8, 0))

        self.last_result_body.pack(fill="both", expand=True)
        # Chime + log so the user notices even if they're on another
        # tab. The bell is one short cross-platform beep; suppressed
        # when the View > Chime on completion toggle is off.
        if getattr(self, "chime_on_complete_var", None) is not None:
            try:
                if self.chime_on_complete_var.get():
                    self.bell()
            except Exception:  # noqa: BLE001
                pass
        # Native toast via the tray controller — visible even when the
        # window is minimised. Falls through silently if pystray /
        # Pillow aren't installed (tray controller is None) or the
        # user disabled tray support.
        if self.tray is not None:
            body = (
                f"Wrote {len(existing)} output file"
                f"{'' if len(existing) == 1 else 's'} for "
                f"{os.path.basename(task.file_path)}"
            )
            try:
                self.tray.notify("Whisper Project — transcription done", body)
            except Exception:  # noqa: BLE001
                pass
        self.log(
            f"Done: {os.path.basename(task.file_path)} → "
            f"{len(existing)} file(s) in {folder}"
        )
        # Auto-switch back to the Transcribe tab when a job finishes
        # so the user lands on the Last Result card (file paths +
        # Open buttons) instead of having to manually switch from the
        # Queue tab. Mirrors the auto-switch to Queue when a
        # transcription starts.
        try:
            self.nb.select(self.t1)
        except Exception:  # noqa: BLE001
            pass

    def _open_file(self, path: str) -> None:
        """Open a single file with the OS default handler."""
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                import subprocess
                subprocess.run(["open", path], check=False)
            else:
                import subprocess
                subprocess.run(["xdg-open", path], check=False)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Open failed", str(e), parent=self)

    def _install_tray(self) -> None:
        """Bring up the system-tray icon if pystray + Pillow are present.

        The icon's right-click menu offers Show/Hide/Exit; the icon
        colour mirrors active/idle state. Failing imports silently
        leave ``self.tray = None`` so the rest of the app still
        boots in environments without tray support.
        """
        try:
            tray = TrayController(self)
            if not tray.is_supported():
                logger.info("Tray icon unavailable: pystray or Pillow missing")
                self.tray = None
                return
            tray.start()
            self.tray = tray
            logger.info("Tray icon installed")
        except Exception as e:  # noqa: BLE001
            logger.warning("Tray icon failed to install: %s", e)
            self.tray = None

    def _restart_watched_folder(self) -> None:
        """(Re)start the watched-folder watcher from current config.

        The watcher class lives in ``core.watcher``; if the
        ``watchdog`` Python package isn't installed the call no-ops.
        Files dropped into the watched folder are auto-enqueued onto
        the transcription queue via a Tk-safe ``after()`` hop.
        """
        # Tear down any previous watcher so we don't leak observer
        # threads when the user picks a new folder in Advanced.
        if self._folder_watcher is not None:
            try:
                self._folder_watcher.stop()
            except Exception:  # noqa: BLE001
                pass
            self._folder_watcher = None

        if not bool(self.app_config.get("watched_folder_enabled", False)):
            return
        folder = str(self.app_config.get("watched_folder") or "").strip()
        if not folder or not os.path.isdir(folder):
            self.log(
                f"Watched folder ignored — not a directory: {folder!r}"
            )
            return

        def _on_new_file(path: str) -> None:
            # watchdog calls back from its own thread — DON'T touch Tk
            # from here. Calling self.after() off-thread raises
            # RuntimeError on Python 3.14 (and is undefined behaviour
            # on earlier 3.x). Instead push the path into a
            # thread-safe queue that the Tk main loop drains via
            # _drain_watched_paths.
            if self._closing:
                return
            try:
                self._watched_path_queue.put_nowait(path)
            except Exception:  # noqa: BLE001
                pass

        try:
            watcher = FolderWatcher(folder, _on_new_file)
            watcher.start()
        except Exception as e:  # noqa: BLE001
            self.log(f"Could not start folder watcher: {e}")
            return
        self._folder_watcher = watcher
        self.log(f"Watching folder for new media: {folder}")

    def _drain_watched_paths(self) -> None:
        """Drain the cross-thread queue of watched-folder paths.

        Runs on the Tk main thread (scheduled via after()). watchdog
        callbacks push into ``_watched_path_queue`` from their worker
        thread; this method dequeues + hands each path to
        ``_enqueue_watched_file`` (which is now safe because we're
        on the Tk thread). Re-arms itself every 250 ms while the
        app is alive.
        """
        if self._closing:
            return
        try:
            while True:
                path = self._watched_path_queue.get_nowait()
                self._enqueue_watched_file(path)
        except Exception:  # noqa: BLE001 — Empty + anything else, just stop draining
            pass
        if not self._closing:
            try:
                self.after(250, self._drain_watched_paths)
            except Exception:  # noqa: BLE001
                pass

    def _drain_main_calls(self) -> None:
        """Drain the cross-thread queue of main-thread callables.

        Runs on the Tk main thread (scheduled via after()). Any
        background thread that needs to touch widgets pushes a
        zero-arg callable into ``_main_thread_calls`` via
        :meth:`post_to_main`; this method dequeues and runs each on
        the Tk thread. Bounded to 64 calls per tick so a flood from
        a misbehaving thread can't stall the Tk loop.
        """
        if self._closing:
            return
        drained = 0
        while drained < 64:  # bound to keep the Tk loop responsive
            try:
                fn = self._main_thread_calls.get_nowait()
            except Empty:
                break
            try:
                fn()
            except Exception:  # noqa: BLE001
                logger.exception("Main-thread call raised")
            drained += 1
        if not self._closing:
            try:
                self.after(50, self._drain_main_calls)
            except Exception:  # noqa: BLE001
                pass

    def post_to_main(self, fn: Callable[[], None]) -> None:
        """Schedule ``fn`` on the Tk main thread from any thread.

        Safe to call from worker / background threads where
        ``self.after(0, fn)`` would either raise (Python 3.14) or
        silently no-op (older 3.x with off-thread Tk calls). The
        callable is drained by :meth:`_drain_main_calls` on the
        next Tk tick (≤ 50 ms).
        """
        try:
            self._main_thread_calls.put_nowait(fn)
        except Full:
            logger.warning("Main-thread call queue full; dropping callback")

    def _enqueue_watched_file(self, path: str) -> None:
        """Auto-enqueue a media file dropped into the watched folder.

        Mirrors the bookkeeping of App.add(): builds a
        TranscriptionTask, appends to the queue, refreshes the
        Treeview. Skips when the file is still being written (size
        keeps growing for a few seconds after the first detect on
        Windows).

        Deduplicated by path: Windows fires both ``on_created`` and
        ``on_modified`` for the same file (sometimes several of the
        latter as the writer flushes). Each invocation cancels any
        in-flight stability-check ladder for the same path before
        scheduling a fresh one, so we never enqueue the same file
        twice.
        """
        if self._closing:
            return
        if not os.path.isfile(path):
            return
        try:
            size1 = os.path.getsize(path)
        except OSError:
            return

        norm = os.path.normcase(os.path.abspath(path))
        # Cancel any prior stability-check ladder for this path so
        # we don't double-enqueue under rapid event bursts.
        prior = self._watched_after_ids.pop(norm, None)
        if prior is not None:
            try:
                self.after_cancel(prior)
            except Exception:  # noqa: BLE001
                pass

        def _check_stable_then_enqueue(prev_size: int) -> None:
            self._watched_after_ids.pop(norm, None)
            if self._closing:
                return
            try:
                size_now = os.path.getsize(path)
            except OSError:
                return
            if size_now != prev_size:
                # File still growing — re-schedule. Track the new id
                # so a later event can cancel us cleanly.
                try:
                    aid = self.after(1200, lambda: _check_stable_then_enqueue(size_now))
                    self._watched_after_ids[norm] = aid
                except Exception:  # noqa: BLE001
                    pass
                return
            # Don't re-enqueue a file we've already finished. Cheap
            # dedup: skip if any queue entry references the same
            # normalised path AND is not in a terminal state.
            for existing in self.queue:
                try:
                    if (os.path.normcase(os.path.abspath(existing.file_path)) == norm
                            and existing.status not in ("finished", "cancelled", "error")):
                        return
                except Exception:  # noqa: BLE001
                    continue
            # Lazy model load without freezing the UI. The watched-folder
            # tick runs on the Tk main thread, so a synchronous wait for
            # the model would freeze the app; spawn + await the worker via
            # after()-polling instead and enqueue once it's ready.
            base = os.path.basename(path)

            def _do_enqueue() -> None:
                task = TranscriptionTask(path)
                self.queue.append(task)
                self.refresh()
                self.log(f"Watched: enqueued {base}")

            self._when_worker_ready(
                _do_enqueue,
                on_timeout=lambda: self.log(
                    f"Watched: skipped {base} — model load timed out"
                ),
                loading_label=f"will transcribe {base} when ready.",
            )

        try:
            aid = self.after(1200, lambda: _check_stable_then_enqueue(size1))
            self._watched_after_ids[norm] = aid
        except Exception:  # noqa: BLE001
            pass

    def _maybe_offer_crash_resume(self) -> None:
        """If history.db flagged any rows interrupted on launch, offer
        to re-enqueue the still-existing files."""
        history = getattr(self, "history", None)
        if history is None:
            return
        try:
            rows = history.list_transcriptions(limit=200) or []
        except Exception:  # noqa: BLE001
            return
        interrupted = [
            r for r in rows
            if r.get("status") == "interrupted"
            and r.get("file_path")
            and os.path.isfile(r["file_path"])
        ]
        if not interrupted:
            return
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for r in interrupted:
            p = r["file_path"]
            if p not in seen:
                seen.add(p)
                unique.append(r)
        n = len(unique)
        # Pluralise verb + noun together so the message reads
        # correctly for both n=1 and n>1.
        noun = "transcription" if n == 1 else "transcriptions"
        verb = "was" if n == 1 else "were"
        pronoun = "it" if n == 1 else "them"
        if not messagebox.askyesno(
            "Resume interrupted transcriptions?",
            f"We found {n} {noun} that {verb} interrupted by a "
            f"previous crash. Resume {pronoun} now?",
            parent=self,
        ):
            # User declined — clear the interrupted flag on the rows we
            # offered so this prompt doesn't reappear on every launch.
            try:
                history.dismiss_interrupted_transcriptions(
                    [r["id"] for r in unique]
                )
            except Exception:  # noqa: BLE001
                logger.debug("Failed to dismiss interrupted rows", exc_info=True)
            return
        # Crash-resume: if a partial checkpoint exists for any of
        # these interrupted files, flag the new task as a resume so
        # the worker reuses the on-disk segments instead of starting
        # over. Worker validation will fall back to a fresh
        # transcribe if the checkpoint is stale (different model,
        # mtime drift, etc.) so this is always safe to set when the
        # partial is present.
        try:
            from core.transcriber import has_resumable_checkpoint
        except Exception:  # noqa: BLE001
            has_resumable_checkpoint = lambda _p: False  # type: ignore[assignment]
        # Lazy model load without freezing the UI. This fires from a
        # startup after(), i.e. on the Tk main thread, so we spawn and
        # await the worker via after()-polling instead of a synchronous
        # wait (which froze the app while the model loaded). On timeout
        # the rows stay flagged interrupted for a later attempt.
        def _do_resume() -> None:
            resumed = 0
            for r in unique:
                task = TranscriptionTask(r["file_path"])
                lang = r.get("language") or ""
                if lang and hasattr(task, "language"):
                    task.language = lang  # type: ignore[attr-defined]
                try:
                    if has_resumable_checkpoint(r["file_path"]):
                        task.resume = True
                        resumed += 1
                except Exception:  # noqa: BLE001
                    pass
                self.queue.append(task)
            self.refresh()
            if resumed:
                self.log(
                    f"Re-enqueued {n} interrupted transcription(s) "
                    f"({resumed} will resume from checkpoint)"
                )
            else:
                self.log(f"Re-enqueued {n} interrupted transcription(s)")

        self._when_worker_ready(
            _do_resume,
            on_timeout=lambda: self.log(
                f"Crash-resume skipped: model load timed out "
                f"({n} task(s) not re-enqueued)"
            ),
            loading_label=f"resuming {n} interrupted transcription(s) when ready.",
        )

    _CLIPBOARD_VK = {86: "paste", 67: "copy", 88: "cut", 65: "selectall"}

    @staticmethod
    def _clipboard_action(keysym: str, keycode: int) -> str | None:
        """Map a Ctrl+key press to a clipboard action, layout-independently.

        Returns None when Tk's own Latin-keysym binding already handles
        the key (English layout) — so we don't act twice — or when it
        isn't a clipboard key. Otherwise it dispatches by the physical
        key's keycode, which is identical whatever the active keyboard
        layout. This fixes paste / copy / cut / select-all under a
        non-Latin layout (Persian, Arabic, Russian, …), where Tk's
        built-in ``<Control-v>`` keysym binding never fires because the
        layout doesn't produce the Latin 'v' keysym.
        """
        if (keysym or "").lower() in ("a", "c", "v", "x"):
            return None
        return App._CLIPBOARD_VK.get(keycode)

    def _install_clipboard_keys(self) -> None:
        virt = {"paste": "<<Paste>>", "copy": "<<Copy>>", "cut": "<<Cut>>"}

        def _on_ctrl_key(event: tk.Event) -> str | None:
            action = self._clipboard_action(
                event.keysym or "", getattr(event, "keycode", -1)
            )
            if action is None:
                return None
            w = event.widget
            if action == "selectall":
                try:
                    w.select_range(0, "end")  # type: ignore[attr-defined]
                    w.icursor("end")  # type: ignore[attr-defined]
                    return "break"
                except (tk.TclError, AttributeError):
                    pass
                try:
                    w.tag_add("sel", "1.0", "end-1c")  # type: ignore[attr-defined]
                    return "break"
                except (tk.TclError, AttributeError):
                    pass
                return None
            try:
                w.event_generate(virt[action])
                return "break"
            except tk.TclError:
                return None

        self.bind_all("<Control-KeyPress>", _on_ctrl_key, add="+")

    def _install_text_context_menu(self) -> None:
        """Right-click Copy / Cut / Paste / Select all on every text field.

        A mouse-driven, keyboard-layout-independent way to use the
        clipboard. The keyboard shortcuts also work (see
        _install_clipboard_keys), but a right-click menu is what a
        non-technical user reaches for and it never depends on the active
        layout — e.g. selecting + copying the download-folder path. Bound
        on the Entry / Text widget classes so it covers every field; the
        Treeview queue menus use a different class and are unaffected.
        """
        def _popup(event: tk.Event) -> str:
            w = event.widget

            def _select_all() -> None:
                try:
                    w.select_range(0, "end")  # type: ignore[attr-defined]
                    w.icursor("end")  # type: ignore[attr-defined]
                except (tk.TclError, AttributeError):
                    try:
                        w.tag_add("sel", "1.0", "end-1c")  # type: ignore[attr-defined]
                    except (tk.TclError, AttributeError):
                        pass

            menu = tk.Menu(w, tearoff=0)
            menu.add_command(label="Cut", command=lambda: w.event_generate("<<Cut>>"))
            menu.add_command(label="Copy", command=lambda: w.event_generate("<<Copy>>"))
            menu.add_command(label="Paste", command=lambda: w.event_generate("<<Paste>>"))
            menu.add_separator()
            menu.add_command(label="Select all", command=_select_all)
            try:
                w.focus_set()
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
            return "break"

        for cls in ("TEntry", "Entry", "Text"):
            self.bind_class(cls, "<Button-3>", _popup, add="+")

    def _install_icon(self) -> None:
        """Set the window-title-bar + taskbar icon from ``assets/whisper.ico``.

        Cosmetic — silently no-ops when the file is missing so a
        damaged install never blocks launch.
        """
        if getattr(sys, "frozen", False):
            ico = os.path.join(
                os.path.dirname(os.path.abspath(sys.executable)),
                "assets", "whisper.ico",
            )
        else:
            ico = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "assets", "whisper.ico",
            )
        if not os.path.isfile(ico):
            return
        try:
            self.iconbitmap(default=ico)
        except tk.TclError as exc:
            logger.warning("Could not set window icon (%s): %s", ico, exc)

    def _apply_hidpi_scaling(self) -> None:
        """Bump Tk's pt→px scaling on high-DPI displays.

        Tk default is 72 dpi (1.0). Most modern Windows machines
        report 96 dpi (1.33). Computing from ``self.winfo_fpixels``
        gives the right factor on 125 % / 150 % Windows scaling, so
        the app's fonts and widget paddings keep their physical
        size rather than shrinking to the size of a 1 cm icon.
        """
        try:
            dpi = float(self.winfo_fpixels("1i"))
            if dpi <= 0:
                return
            scale = max(1.0, dpi / 72.0)
            self.tk.call("tk", "scaling", scale)
            logger.info("Tk scaling set to %.2f (%.0f dpi)", scale, dpi)
        except Exception as e:  # noqa: BLE001
            logger.info("Could not apply HiDPI scaling: %s", e)

    def _install_drag_drop(self) -> None:
        """Wire tkinterdnd2 if available, no-op otherwise.

        ``TkinterDnD._require(self)`` loads the Tcl ``tkdnd`` package
        into the interpreter but DOES NOT add the
        ``drop_target_register`` / ``dnd_bind`` methods to a plain
        ``tk.Tk`` instance — those live on ``TkinterDnD.DnDWrapper``.
        Mix the wrapper into our App's class so the methods become
        bound. Without this graft, drag-and-drop silently never
        registered in v0.7.1.
        """
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore[import-not-found]
        except ImportError:
            logger.info("tkinterdnd2 not present; drag-and-drop disabled")
            return
        try:
            TkinterDnD._require(self)
            # Graft DnDWrapper's methods onto our class so this
            # instance gains drop_target_register / dnd_bind.
            wrapper = getattr(TkinterDnD, "DnDWrapper", None)
            if wrapper is not None and wrapper not in self.__class__.__mro__:
                self.__class__ = type(
                    self.__class__.__name__,
                    (self.__class__, wrapper),
                    {},
                )
            if not hasattr(self, "drop_target_register"):
                logger.warning(
                    "tkinterdnd2 imported but drop_target_register "
                    "is still missing; drag-and-drop disabled"
                )
                return
            self.drop_target_register(DND_FILES)  # type: ignore[attr-defined]
            self.dnd_bind("<<Drop>>", self._on_drop)  # type: ignore[attr-defined]
            logger.info("Drag-and-drop enabled (tkinterdnd2)")
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not initialise drag-and-drop: %s", e)

    def _on_drop(self, event: tk.Event) -> None:
        """Handle a drag-and-drop onto the window.

        tkinterdnd2 packs all dropped paths into a single string with
        space-or-brace separation. The simplest robust parser is
        ``self.tk.splitlist`` — Tcl knows the encoding rules.
        Behaviour:
          - one file dropped → populate the Transcribe tab's file
            field
          - multiple files   → enqueue each as a Transcription task
            without further prompts
          - URL dropped      → if it's a known download URL, paste
            into the Download tab's URL field
        """
        raw = getattr(event, "data", "") or ""
        try:
            items = list(self.tk.splitlist(raw))
        except Exception:  # noqa: BLE001
            items = [raw]
        paths: list[str] = []
        urls: list[str] = []
        for item in items:
            s = item.strip()
            if not s:
                continue
            if s.startswith(("http://", "https://")):
                urls.append(s)
            elif os.path.isfile(s):
                paths.append(s)

        if urls and hasattr(self, "download_url_var"):
            self.download_url_var.set(urls[0])
            self.nb.select(self.t3)
            self.log(f"Pasted URL into Download tab: {urls[0]}")
        if paths:
            if len(paths) == 1:
                self.fv.set(paths[0])
                self.nb.select(self.t1)
                self.log(f"Picked: {os.path.basename(paths[0])} (drag-and-drop)")
            else:
                count = 0
                for p in paths:
                    self.fv.set(p)
                    self.add()
                    count += 1
                self.log(f"Enqueued {count} files via drag-and-drop")

    def _cancel_running(self) -> None:
        """Esc handler — cancel whichever single running task is most relevant."""
        for t in self.queue:
            if t.status == "running":
                self.cancel(t)
                return
        for d in self.download_queue:
            if d.status == "running":
                self.cancel_download(d)
                return

    def _save_window_geometry(self) -> None:
        """Persist the window's current size + position in config.json."""
        try:
            geom = self.geometry()
        except Exception:  # noqa: BLE001
            return
        if not geom:
            return
        try:
            self.app_config["window_geometry"] = geom
            save_config(self.app_config)
        except Exception:  # noqa: BLE001
            pass

    def queue_row_double_click(self, event: tk.Event) -> None:
        """Double-click on a finished Queue row opens its folder.

        For waiting/running/error/cancelled rows the action is a
        no-op (no useful destination yet).
        """
        item = self.tree.identify_row(event.y)
        if not item:
            return
        task = self.row_map.get(item)
        if not task or task.status != "finished":
            return
        self._open_folder(os.path.dirname(task.file_path) or ".")

    def log(self, msg: str) -> None:
        self._ui_logger.info(msg)
        if hasattr(self, "txt") and self.txt is not None:
            self.txt.insert("end", msg + "\n")
            self.txt.see("end")

    # Driver loops ------------------------------------------------------------
    def update_overall_progress(self) -> None:
        running = [t for t in self.queue if t.status == "running"]
        if not running:
            self.pb["value"] = 0
            return
        self.pb["value"] = sum(t.progress for t in running) / len(running)

    def loop(self) -> None:
        self.refresh()
        self.transcription_service.dispatch_waiting()
        self.download_service.process_queue()
        self.after(500, self.loop)
