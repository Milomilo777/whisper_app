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

from app.dialogs.model_download import ModelDownloadDialog
from app.domain.languages import SUBTITLE_LANGUAGES
from app.domain.tasks import TranscriptionTask, VideoDownloadTask
from app.observability import init_sentry
from app.services.download_service import DownloadService
from app.services.format_service import FormatService
from app.services.integrations_service import IntegrationsService
from app.services.transcription_service import TranscriptionService
from app.widgets.console import build_console
from core.config import load_config, save_config
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
        f.add_command(label="Exit", command=self.on_exit)
        v = tk.Menu(m, tearoff=0)
        for label, value in (("Light", "light"), ("Dark", "dark"), ("System", "system")):
            v.add_radiobutton(label=label, value=value, variable=self.theme_var, command=self.apply_theme)
        h = tk.Menu(m, tearoff=0)
        h.add_command(label="Open log folder", command=self.open_log_folder)
        h.add_command(label="Open oTranscribe...", command=self.integrations_service.open_otranscribe)
        a = tk.Menu(m, tearoff=0)
        a.add_command(label="About", command=lambda: messagebox.showinfo("About", "Whisper"))
        m.add_cascade(label="File", menu=f)
        m.add_cascade(label="View", menu=v)
        m.add_cascade(label="Help", menu=h)
        m.add_cascade(label="About", menu=a)
        self.config(menu=m)

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

        ttk.Label(self.t1, text="File").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.fv = tk.StringVar()
        ttk.Entry(self.t1, textvariable=self.fv, width=60).grid(row=0, column=1, padx=(0, 6), pady=10, sticky="ew")
        ttk.Button(self.t1, text="Browse", command=self.browse).grid(row=0, column=2, padx=(0, 10), pady=10)
        ttk.Button(self.t1, text="Transcribe", command=self.add).grid(row=1, column=1, padx=(0, 6), pady=(0, 10), sticky="w")
        ttk.Separator(self.t1, orient="horizontal").grid(row=2, column=0, columnspan=3, sticky="ew", padx=10, pady=(6, 6))
        ttk.Label(self.t1, text="oTranscribe").grid(row=3, column=0, padx=10, pady=(0, 10), sticky="w")
        ttk.Button(
            self.t1, text="Import .otr → SRT...", command=self.integrations_service.import_otr_to_srt
        ).grid(row=3, column=1, padx=(0, 6), pady=(0, 10), sticky="w")
        self.t1.columnconfigure(1, weight=1)
        ttk.Button(self.t2, text="Clear completed", command=self.clear_completed).pack(anchor="e", padx=10, pady=6)

        cols = ("file", "status", "progress", "language", "time")
        self.tree = ttk.Treeview(self.t2, columns=cols, show="headings")
        for c in cols:
            self.tree.heading(c, text=c)
        self.tree.column("language", width=140)
        self.tree.pack(fill="both", expand=True)

        self.pb = ttk.Progressbar(self.t2, length=400)
        self.pb.pack(fill="x", padx=10, pady=10)

        ttk.Label(self.t2, textvariable=self.status_var).pack()

        self.tree.bind("<Button-3>", self.menu_row)
        self.row_map: dict[str, TranscriptionTask] = {}

        self._build_download_tab()

    def _build_download_tab(self) -> None:
        top = ttk.Frame(self.t3, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="URL").grid(row=0, column=0, sticky="w")
        self.download_url_var = tk.StringVar()
        self.download_url_var.trace_add("write", lambda *_: self.format_service.schedule_lookup())
        ttk.Entry(top, textvariable=self.download_url_var, width=80).grid(
            row=0, column=1, columnspan=2, sticky="ew", padx=(6, 0)
        )

        ttk.Label(top, text="Folder").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.download_folder_var = tk.StringVar(value=self.app_config.get("download_folder", ""))
        ttk.Entry(top, textvariable=self.download_folder_var, width=70).grid(
            row=1, column=1, sticky="ew", padx=(6, 0), pady=(8, 0)
        )
        ttk.Button(top, text="Browse", command=self.browse_download_folder).grid(
            row=1, column=2, sticky="ew", padx=(6, 0), pady=(8, 0)
        )

        ttk.Label(top, text="Mode").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.download_mode_var = tk.StringVar(value="Audio and video")
        self.download_mode_combo = ttk.Combobox(
            top,
            textvariable=self.download_mode_var,
            state="readonly",
            values=("Audio and video", "Audio"),
            width=24,
        )
        self.download_mode_combo.grid(row=2, column=1, sticky="w", padx=(6, 0), pady=(8, 0))
        self.download_mode_combo.bind("<<ComboboxSelected>>", lambda _e: self.update_download_mode())

        ttk.Label(top, text="Audio").grid(row=3, column=0, sticky="w", pady=(8, 0))
        self.audio_format_var = tk.StringVar()
        self.audio_format_combo = ttk.Combobox(
            top, textvariable=self.audio_format_var, state="readonly", width=76
        )
        self.audio_format_combo.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(6, 0), pady=(8, 0))

        ttk.Label(top, text="Video").grid(row=4, column=0, sticky="w", pady=(8, 0))
        self.video_format_var = tk.StringVar()
        self.video_format_combo = ttk.Combobox(
            top, textvariable=self.video_format_var, state="readonly", width=76
        )
        self.video_format_combo.grid(row=4, column=1, columnspan=2, sticky="ew", padx=(6, 0), pady=(8, 0))

        ttk.Label(top, text="Output").grid(row=5, column=0, sticky="w", pady=(8, 0))
        self.output_format_var = tk.StringVar(value="mp4")
        self.output_format_combo = ttk.Combobox(
            top, textvariable=self.output_format_var, state="readonly", width=20
        )
        self.output_format_combo.grid(row=5, column=1, sticky="w", padx=(6, 0), pady=(8, 0))

        ttk.Label(top, text="Subtitles").grid(row=6, column=0, sticky="w", pady=(8, 0))
        sub_frame = ttk.Frame(top)
        sub_frame.grid(row=6, column=1, columnspan=2, sticky="ew", padx=(6, 0), pady=(8, 0))
        saved_sub_enabled = bool(self.app_config.get("download_subtitles_enabled", False))
        self.download_subtitles_var = tk.BooleanVar(value=saved_sub_enabled)
        ttk.Checkbutton(
            sub_frame,
            text="Download subtitles (auto + manual when present)",
            variable=self.download_subtitles_var,
            command=self.update_subtitle_state,
        ).pack(side="left")
        saved_sub_lang = self.app_config.get("download_subtitle_lang") or SUBTITLE_LANGUAGES[0][0]
        if saved_sub_lang not in [name for name, _ in SUBTITLE_LANGUAGES]:
            saved_sub_lang = SUBTITLE_LANGUAGES[0][0]
        self.subtitle_lang_var = tk.StringVar(value=saved_sub_lang)
        self.subtitle_lang_combo = ttk.Combobox(
            sub_frame,
            textvariable=self.subtitle_lang_var,
            state="disabled",
            values=[name for name, _ in SUBTITLE_LANGUAGES],
            width=24,
        )
        self.subtitle_lang_combo.pack(side="left", padx=(10, 0))
        self.subtitle_status_var = tk.StringVar(value="")
        ttk.Label(sub_frame, textvariable=self.subtitle_status_var, foreground="#666").pack(
            side="left", padx=(10, 0)
        )

        # Auto-transcribe checkbox (Phase 3a)
        self.auto_transcribe_var = tk.BooleanVar(
            value=bool(self.app_config.get("auto_transcribe_after_download", False))
        )
        ttk.Checkbutton(
            top,
            text="Transcribe after download",
            variable=self.auto_transcribe_var,
            command=self._save_auto_transcribe_pref,
        ).grid(row=7, column=1, columnspan=2, sticky="w", padx=(6, 0), pady=(4, 0))

        self.format_status_var = tk.StringVar(value="Enter a URL to load available formats")
        ttk.Label(top, textvariable=self.format_status_var).grid(
            row=8, column=1, columnspan=2, sticky="w", padx=(6, 0), pady=(4, 0)
        )
        ttk.Button(top, text="Download", command=self.add_download).grid(
            row=9, column=2, sticky="e", pady=(10, 0)
        )

        top.columnconfigure(1, weight=1)

        bottom = ttk.Frame(self.t3, padding=(10, 0, 10, 10))
        bottom.pack(fill="both", expand=True)

        cols = ("name", "url", "format", "status", "progress", "time")
        self.download_tree = ttk.Treeview(bottom, columns=cols, show="headings", height=8)
        for c in cols:
            self.download_tree.heading(c, text=c)
        self.download_tree.column("name", width=220)
        self.download_tree.column("url", width=420)
        self.download_tree.column("format", width=180)
        self.download_tree.column("status", width=100)
        self.download_tree.column("progress", width=80)
        self.download_tree.column("time", width=80)
        self.download_tree.pack(fill="both", expand=True)
        self.download_tree.bind("<Button-3>", self.download_menu_row)
        self.download_row_map: dict[str, VideoDownloadTask] = {}

        self.update_download_mode()
        self.update_subtitle_state()
        self.after(200, self.format_service.poll)
        self.after(300, self.download_service.poll)

    def _save_auto_transcribe_pref(self) -> None:
        self.app_config["auto_transcribe_after_download"] = bool(self.auto_transcribe_var.get())
        try:
            save_config(self.app_config)
        except Exception:  # noqa: BLE001
            pass

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

    # Service-driven shims (kept for tests + tk callbacks) -------------------
    def start_standby_worker(self) -> None:
        self.transcription_service.start_standby()

    def start_worker(self, worker: dict[str, Any] | None = None, temporary: bool = False) -> None:
        self.transcription_service.start_worker(worker=worker, temporary=temporary)

    def stop_worker(self, worker: dict[str, Any]) -> None:
        self.transcription_service.stop_worker(worker)

    def stop_workers(self) -> None:
        self.transcription_service.stop_all()

    def restart_worker(self, worker: dict[str, Any]) -> None:
        self.transcription_service.restart_worker(worker)

    def retire_worker(self, worker: dict[str, Any]) -> None:
        self.transcription_service.retire_worker(worker)

    def active_workers(self) -> list[dict[str, Any]]:
        return self.transcription_service.active_workers()

    def ready_workers(self) -> list[dict[str, Any]]:
        return self.transcription_service.ready_workers()

    def idle_workers(self) -> list[dict[str, Any]]:
        return self.transcription_service.idle_workers()

    def update_model_state(self) -> None:
        self.transcription_service.update_model_state()

    def poll_worker_events(self) -> None:
        self.transcription_service.poll()

    def poll_format_events(self) -> None:
        self.format_service.poll()

    def poll_download_events(self) -> None:
        self.download_service.poll()

    def schedule_format_lookup(self) -> None:
        self.format_service.schedule_lookup()

    def lookup_formats(self) -> None:
        self.format_service.lookup_formats()

    def process_download_queue(self) -> None:
        self.download_service.process_queue()

    def maybe_update_yt_dlp(self, task: VideoDownloadTask) -> None:
        self.download_service.maybe_update_yt_dlp(task)

    def build_subtitle_command(self, task: VideoDownloadTask, lang: str) -> list[str]:
        return self.download_service.build_subtitle_command(task, lang)

    def build_download_command(self, task: VideoDownloadTask) -> list[str]:
        return self.download_service.build_download_command(task)

    def resolve_subtitle_lang(self, task: VideoDownloadTask) -> str:
        return self.download_service.resolve_subtitle_lang(task)

    def subtitle_lang_args(self, lang: str) -> str:
        from app.domain.languages import subtitle_lang_args as _f
        return _f(lang)

    def export_task_to_otr(self, task: TranscriptionTask) -> None:
        self.integrations_service.export_task_to_otr(task)

    def import_otr_to_srt(self) -> None:
        self.integrations_service.import_otr_to_srt()

    def open_otranscribe(self) -> None:
        self.integrations_service.open_otranscribe()

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
        url = self.download_url_var.get().strip()
        folder = self.download_folder_var.get().strip()
        mode = self.download_mode_var.get()
        audio_label = self.audio_format_var.get()
        video_label = self.video_format_var.get()
        output = self.output_format_var.get()
        if not url:
            messagebox.showwarning("Missing URL", "Enter a URL first.", parent=self)
            return
        if not folder:
            messagebox.showwarning("Missing folder", "Select a download folder first.", parent=self)
            return
        if not audio_label or audio_label not in self.audio_format_map:
            messagebox.showwarning(
                "Missing audio format",
                "Wait for formats to load, then select an audio format.",
                parent=self,
            )
            return
        if mode == "Audio and video" and (
            not video_label or video_label not in self.video_format_map
        ):
            messagebox.showwarning(
                "Missing video format",
                "Wait for formats to load, then select a video format.",
                parent=self,
            )
            return
        if not output:
            messagebox.showwarning("Missing output", "Select an output format.", parent=self)
            return

        os.makedirs(folder, exist_ok=True)
        self.app_config["download_folder"] = folder
        title = self.current_video_title or url
        subtitles_enabled = self.download_subtitles_var.get()
        sub_lang_name = self.subtitle_lang_var.get()
        sub_lang_code = next(
            (code for name, code in SUBTITLE_LANGUAGES if name == sub_lang_name), ""
        )
        self.app_config["download_subtitles_enabled"] = subtitles_enabled
        self.app_config["download_subtitle_lang"] = sub_lang_name
        save_config(self.app_config)
        label_extra = ""
        if subtitles_enabled:
            label_extra = f" + subs ({sub_lang_name})"
        format_label = f"{mode} -> {output}{label_extra}"
        format_info = {
            "mode": mode,
            "audio": self.audio_format_map[audio_label],
            "video": self.video_format_map.get(video_label),
            "output": output,
        }
        self.download_queue.append(
            VideoDownloadTask(
                url,
                folder,
                format_label,
                format_info,
                title,
                subtitles_enabled=subtitles_enabled,
                subtitle_lang=sub_lang_code,
                detected_language=self.current_video_language,
            )
        )
        self.refresh_download_queue()
        self.download_service.process_queue()

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
                    command=lambda: self.export_task_to_otr(task),
                )
                m.add_separator()
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
            m.add_command(label="Remove", command=lambda: self.remove_download(task))
        m.tk_popup(e.x_root, e.y_root)

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
    def process(self) -> None:
        if not self.queue:
            return
        waiting = [task for task in self.queue if task.status == "waiting"]
        if not waiting:
            return
        active_count = len(self.transcription_service.active_workers())
        idle_count = len(self.transcription_service.idle_workers())
        needed = min(len(waiting), self.parallel_workers) - idle_count
        for _ in range(max(0, needed)):
            if active_count >= self.parallel_workers:
                break
            self.transcription_service.start_worker(temporary=True)
            active_count += 1
        idle = self.transcription_service.idle_workers()
        if not idle:
            return
        for worker, t in zip(idle, waiting):
            worker["task"] = t
            t.status = "running"
            t.progress = 0
            t.start_time = time.time()
            self.update_overall_progress()
            try:
                command = {
                    "action": "transcribe",
                    "file_path": t.file_path,
                    "language": getattr(t, "language", None),
                }
                import json as _json
                worker["process"].stdin.write(_json.dumps(command) + "\n")
                worker["process"].stdin.flush()
            except Exception as e:  # noqa: BLE001
                t.status = "error"
                worker["task"] = None
                self.log(f"Failed to start transcription: {e}")
                self.transcription_service.restart_worker(worker)

    def finish_worker_task(self, worker: dict[str, Any], keep_status: bool = False) -> None:
        self.transcription_service.finish_task(worker, keep_status=keep_status)

    def update_overall_progress(self) -> None:
        running = [t for t in self.queue if t.status == "running"]
        if not running:
            self.pb["value"] = 0
            return
        self.pb["value"] = sum(t.progress for t in running) / len(running)

    def loop(self) -> None:
        self.refresh()
        self.process()
        self.download_service.process_queue()
        self.after(500, self.loop)
