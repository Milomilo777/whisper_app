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
    entry_file: str = _resolve_entry_file()

    def __init__(self) -> None:
        super().__init__()
        self.title("Transcription helper")
        self.geometry("900x600")
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

        self.after(100, self._on_start)
        self.after(300, self.loop)

    # Bootstrap ---------------------------------------------------------------
    def _on_start(self) -> None:
        self.transcription_service.start_standby()

    # Menu --------------------------------------------------------------------
    def _build_menu(self) -> None:
        m = tk.Menu(self)
        f = tk.Menu(m, tearoff=0)
        f.add_command(label="Statistics...", command=self.show_statistics)
        f.add_separator()
        f.add_command(label="Exit", command=self.on_exit)
        v = tk.Menu(m, tearoff=0)
        for label, value in (("Light", "light"), ("Dark", "dark"), ("System", "system")):
            v.add_radiobutton(label=label, value=value, variable=self.theme_var, command=self.apply_theme)
        h = tk.Menu(m, tearoff=0)
        h.add_command(label="Open log folder", command=self.open_log_folder)
        h.add_command(label="Open oTranscribe...", command=self.integrations_service.open_otranscribe)
        a = tk.Menu(m, tearoff=0)
        a.add_command(
            label="About",
            command=lambda: messagebox.showinfo("About", "Whisper", parent=self),
        )
        m.add_cascade(label="File", menu=f)
        m.add_cascade(label="View", menu=v)
        m.add_cascade(label="Help", menu=h)
        m.add_cascade(label="About", menu=a)
        self.config(menu=m)

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
        try:
            save_config(self.app_config)
        except Exception:  # noqa: BLE001
            pass

    def open_advanced_dialog(self) -> None:
        AdvancedDialog(self)

    # Generic helpers ---------------------------------------------------------
    def yt_dlp_path(self) -> str:
        exe = "yt-dlp.exe" if os.name == "nt" else "yt-dlp"
        return os.path.join(os.path.dirname(os.path.abspath(self.entry_file)), "bin", exe)

    def bin_path(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(self.entry_file)), "bin")

    def browse(self) -> None:
        f = filedialog.askopenfilename()
        if f:
            self.fv.set(f)

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
            return
        if not self.model_ready:
            if self.model_loading:
                self.log("Request was not queued because the model is still being checked.")
                return
            if not messagebox.askyesno(
                "Model required",
                "The Whisper model must be downloaded before requests can be queued. Download it now?",
                parent=self,
            ):
                self.log("Request was not queued because the required model is not ready.")
                return
            if not self.ensure_model_with_modal():
                self.log("Request was not queued because the required model is not ready.")
                return
        self.queue.append(TranscriptionTask(self.fv.get()))
        self.pb["value"] = 0
        self.nb.select(self.t2)
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
                    t.status,
                    f"{t.progress}%",
                    lang_str,
                    self.fmt_time(t),
                ),
            )
            self.row_map[item_id] = t

    def refresh_download_queue(self) -> None:
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
                    task.status,
                    f"{task.progress}%",
                    self.fmt_time(task),
                ),
            )
            self.download_row_map[item_id] = task

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
