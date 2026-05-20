"""The Tk root. Wires services + dialogs + widgets together."""
from __future__ import annotations

import logging
import os
import sys
import time
import tkinter as tk
from queue import Queue
from tkinter import filedialog, messagebox, ttk
from typing import Any

import sv_ttk

from app.dialogs.advanced import AdvancedDialog
from app.dialogs.model_download import ModelDownloadDialog
from app.dialogs.transcript_viewer import open_viewer as _open_transcript_viewer
from app.domain.tasks import TranscriptionTask, VideoDownloadTask
from app.observability import init_sentry
from app.services.download_service import DownloadService
from app.services.format_service import FormatService
from app.services.integrations_service import IntegrationsService
from app.services.transcription_service import TranscriptionService
from app.dialogs.statistics import show_statistics as _show_stats
from app.widgets.console import build_console
from app.widgets.platform import open_folder as _open_folder_helper
from app.widgets.tabs import build_download_tab, build_queue_tab, build_transcribe_tab
from core.config import load_config, save_config
from core.history import HistoryDB
from core.logging_setup import get_ui_logger, open_log_folder, setup_logging
from core.paths import bin_dir as _resource_bin_dir

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

    def __init__(self) -> None:
        super().__init__()
        self.title("Whisper Project")
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
        self.worker_events: Queue = Queue()
        self.worker_ready = False
        self.app_config = load_config()
        setup_logging(self.app_config.get("log_level", "INFO"))
        init_sentry()
        self._ui_logger = get_ui_logger()
        logger.info("App startup; theme=%s", self.app_config.get("theme", "dark"))
        self.theme_var = tk.StringVar(value=self.app_config.get("theme", "dark"))
        sv_ttk.set_theme(_resolve_theme(self.theme_var.get()))
        self.parallel_workers = max(1, int(self.app_config.get("parallel_workers", 2)))
        self.next_worker_id = 1
        self.format_events: Queue = Queue()
        self.download_events: Queue = Queue()
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
        self.bind("<Control-q>", lambda _e: self.on_exit())
        self.bind("<Control-Q>", lambda _e: self.on_exit())

        # Opt-in drag-and-drop on the main window. tkinterdnd2 is in
        # requirements.txt but the desktop app stays usable even if
        # the import fails — we just log and skip.
        self._install_drag_drop()

        self.after(100, self._on_start)
        self.after(300, self.loop)

    # Bootstrap ---------------------------------------------------------------
    def _on_start(self) -> None:
        self.transcription_service.start_standby()

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
        f.add_command(label="Exit                                  Ctrl+Q", command=self.on_exit)

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
        h.add_command(label="Open log folder", command=self.open_log_folder)
        h.add_command(label="Open oTranscribe...", command=self.integrations_service.open_otranscribe)
        a = tk.Menu(m, tearoff=0)
        a.add_command(label="About", command=self._show_about)

        m.add_cascade(label="File", menu=f)
        m.add_cascade(label="View", menu=v)
        m.add_cascade(label="Help", menu=h)
        m.add_cascade(label="About", menu=a)
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
        except Exception:  # noqa: BLE001
            pass

    def _show_about(self) -> None:
        """A more informative About dialog than the previous one-word "Whisper".

        Shows the project version, the GitHub URL, and a one-line
        description of what the app does. ``parent=self`` so the
        Toplevel centers on the app window (Session 9 audit fix).
        """
        body = (
            "Whisper Project v0.7.0\n\n"
            "Offline transcription + video downloader for Windows.\n"
            "Built on faster-whisper and yt-dlp.\n\n"
            "https://github.com/Milomilo777/whisper_project_direct_download_v2"
        )
        messagebox.showinfo("About Whisper Project", body, parent=self)

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

    def on_exit(self) -> None:
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
        except Exception:  # noqa: BLE001
            pass

    def _save_transcribe_prefs(self) -> None:
        self.app_config["vad_enabled"] = bool(self.vad_enabled_var.get())
        self.app_config["word_timestamps"] = bool(self.word_timestamps_var.get())
        if getattr(self, "diarization_var", None) is not None:
            self.app_config["diarization_enabled"] = bool(self.diarization_var.get())
        try:
            save_config(self.app_config)
        except Exception:  # noqa: BLE001
            pass

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
            self.log("Model downloaded. Starting standby worker.")
            self.transcription_service.start_standby()
            return True
        self.model_ready = False
        self.status_var.set("Model is required")
        if mandatory:
            self.log("Model setup was cancelled or failed.")
        return False

    # Adding tasks ------------------------------------------------------------
    def add(self) -> None:
        if not self.fv.get():
            self.log("Pick a file first — use the Browse button on the Transcribe tab.")
            return
        if not self.model_ready:
            if self.model_loading:
                self.log("Model is still loading — please wait a moment, then try again.")
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
        self.queue.append(TranscriptionTask(self.fv.get()))
        self.pb["value"] = 0
        self.nb.select(self.t2)
        self.log(f"Queued: {os.path.basename(self.fv.get())}")
        self.refresh()

    def enqueue_transcription_from_download(self, file_path: str, language: str) -> None:
        """Auto-transcribe-after-download wiring: push a task without the modal."""
        task = TranscriptionTask(file_path)
        if hasattr(task, "language"):
            setattr(task, "language", language)
        self.queue.append(task)
        self.refresh()

    def add_download(self) -> None:
        self.download_service.enqueue_from_form()

    # Right-click context menus -----------------------------------------------
    def menu_row(self, e: tk.Event) -> None:
        item = self.tree.identify_row(e.y)
        if not item:
            return
        self.tree.selection_set(item)
        task = self.row_map.get(item)
        if not task:
            return
        m = tk.Menu(self, tearoff=0)
        if task.status == "waiting":
            m.add_command(label="Cancel", command=lambda: self.cancel(task))
        elif task.status == "running":
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
                    label="Open output folder",
                    command=lambda: self._open_folder(os.path.dirname(task.file_path)),
                )
                m.add_separator()
            m.add_command(label="Re-run", command=lambda: self._rerun_task(task))
            m.add_command(label="Remove", command=lambda: self.remove_task(task))
        m.tk_popup(e.x_root, e.y_root)

    def download_menu_row(self, e: tk.Event) -> None:
        item = self.download_tree.identify_row(e.y)
        if not item:
            return
        task = self.download_row_map.get(item)
        if not task:
            return
        m = tk.Menu(self, tearoff=0)
        if task.status in ("waiting", "running"):
            m.add_command(label="Cancel", command=lambda: self.cancel_download(task))
        elif task.status in ("finished", "cancelled", "error"):
            m.add_command(
                label="Open download folder",
                command=lambda: self._open_folder(task.folder),
            )
            m.add_command(label="Re-run", command=lambda: self._rerun_download(task))
            m.add_command(label="Remove", command=lambda: self.remove_download(task))
        m.tk_popup(e.x_root, e.y_root)

    def _open_folder(self, folder: str) -> None:
        _open_folder_helper(folder, parent=self)

    def _rerun_task(self, task: TranscriptionTask) -> None:
        new_task = TranscriptionTask(task.file_path)
        if getattr(task, "language", None):
            new_task.language = task.language
        self.queue.append(new_task)
        self.refresh()

    def _rerun_download(self, task: VideoDownloadTask) -> None:
        from app.domain.tasks import VideoDownloadTask as VDT
        copy = VDT(
            task.url, task.folder, task.format_label, task.format_info, task.title,
            subtitles_enabled=task.subtitles_enabled,
            subtitle_lang=task.subtitle_lang,
            detected_language=task.detected_language,
        )
        self.download_queue.append(copy)
        self.refresh_download_queue()
        self.download_service.process_queue()

    def cancel_download(self, task: VideoDownloadTask) -> None:
        task.cancelled = True
        task.status = "cancelled"
        if task.process and task.process.poll() is None:
            task.process.terminate()
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
        s = time.time() - t.start_time
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        sec = int(s % 60)
        return f"{h:02}:{m:02}:{sec:02}"

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
                    f"{t.progress}%",
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

    def refresh_download_queue(self) -> None:
        from app.widgets.tabs import status_label

        self.download_tree.delete(*self.download_tree.get_children())
        self.download_row_map = {}
        for task in self.download_queue:
            item_id = self.download_tree.insert(
                "",
                "end",
                values=(
                    task.title,
                    task.url,
                    task.format_label,
                    status_label(task.status),
                    f"{task.progress}%",
                    self.fmt_time(task),
                ),
            )
            self.download_row_map[item_id] = task
        self._refresh_window_title()

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
        if not running and not running_dl:
            self.title("Whisper Project")
            return
        if running and not running_dl and len(running) == 1:
            t = running[0]
            self.title(
                f"Whisper Project — {t.progress}% transcribing "
                f"{os.path.basename(t.file_path)}"
            )
            return
        if running_dl and not running and len(running_dl) == 1:
            d = running_dl[0]
            self.title(
                f"Whisper Project — {d.progress}% downloading "
                f"{d.title[:40] if d.title else d.url[:40]}"
            )
            return
        total = len(running) + len(running_dl)
        all_p = [t.progress for t in running] + [d.progress for d in running_dl]
        avg = sum(all_p) // len(all_p) if all_p else 0
        self.title(f"Whisper Project — {total} tasks (avg {avg}%)")

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
        self.log(
            f"Done: {os.path.basename(task.file_path)} → "
            f"{len(existing)} file(s) in {folder}"
        )

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

    def _install_drag_drop(self) -> None:
        """Wire tkinterdnd2 if available, no-op otherwise."""
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore[import-not-found]
        except ImportError:
            logger.info("tkinterdnd2 not present; drag-and-drop disabled")
            return
        # tkinterdnd2 monkey-patches the Tk root with drop_target_register;
        # we have to apply that to ourselves.
        try:
            TkinterDnD._require(self)
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
