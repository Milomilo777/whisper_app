"""The Tk root — single-screen app.

Layout (top → bottom):

  * Drop zone (drag-and-drop or click-to-browse).
  * Action row: Browse… + Transcribe buttons.
  * Progress bar + status line.
  * Queue Treeview with right-click Cancel.
  * Collapsible console (last log lines).
  * Menu bar: File, Help.

The App spawns ONE worker subprocess on first Transcribe click and
reuses it for the lifetime of the session. Cancel kills the worker;
the next Transcribe click re-spawns it lazily.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import uuid
from queue import Empty, Full, Queue
from tkinter import filedialog, messagebox, ttk
from typing import Any

import sv_ttk

from app.dialogs.about import AboutDialog
from app.dialogs.crash import install_excepthook
from app.dialogs.diagnose import DiagnoseDialog
from app.dialogs.hub_setup import ensure_hub_configured
from app.dialogs.model_download import ModelDownloadDialog
from app.dialogs.model_loading import ModelLoadingDialog
from app.dialogs.show_log import ShowLogDialog
from app.domain.tasks import VideoDownloadTask
from app.services.download_service import (
    FORMAT_LABELS,
    DownloadService,
)
from app.widgets.dropzone import DropZone
from core._timecode import parse_timecode
from core.config import (
    add_recent_file,
    load_config,
    save_config,
)
from core.error_messages import friendly_error
from core.health_check import first_failure, run_all
from core.logging_setup import open_log_folder, setup_logging
from core.model_manager import is_model_on_disk
from core.task import TranscriptionTask
from core.url_kind import url_kind

logger = logging.getLogger(__name__)

RECENT_LIMIT = 5
LOG_PANEL_LINES = 200

# Events whose loss would leave the UI in a stuck state ("running"
# forever, no error dialog, etc). Worker_events.put on these uses an
# unbounded block; high-volume events (``progress``, ``log``,
# ``heartbeat``) drop when the queue is saturated.
_LIFECYCLE_EVENTS: frozenset[str] = frozenset({
    "ready", "startup_error", "done", "error", "worker_exit",
    "download_done", "download_error",
})

# Language picker — (display_label, faster-whisper ISO code or empty
# string for auto-detect). Kept deliberately short: auto-detect works
# on 99 languages out of the box; this list is just for the cases
# where the user wants to *force* a language because auto-detect
# guesses wrong on the first second or two of audio (common with
# music intros).
LANGUAGE_CHOICES: list[tuple[str, str]] = [
    ("Auto-detect", ""),
    ("English", "en"),
    ("Chinese", "zh"),
    ("Vietnamese", "vi"),
]


def _resolve_entry_file() -> str:
    """Path used as the worker's command-line target."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "gui.py",
    )


class App:
    """Top-level controller — owns the Tk root, queue, and worker."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Whisper Project — basic")
        # Taller default so the new Download Videos section fits
        # without scrolling on first paint. Width unchanged.
        self.root.geometry("760x820")
        self.root.minsize(620, 700)
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)
        self._install_icon()

        self.config_dict: dict[str, Any] = load_config()
        setup_logging(self.config_dict.get("log_level", "INFO"))
        logger.info("App startup")

        sv_ttk.set_theme("dark")

        # In-memory queue + worker bookkeeping.
        self.queue: list[TranscriptionTask] = []
        # Download queue lives alongside the transcribe queue. Each
        # download is its own VideoDownloadTask. Both queues share
        # the same Treeview (distinguished by the ``kind`` column)
        # and the same worker_events queue (distinguished by event
        # name in ``_handle_event``).
        self.download_queue: list[VideoDownloadTask] = []
        self.download_current: VideoDownloadTask | None = None
        self.worker: dict[str, Any] | None = None
        # Bound so a runaway producer can't OOM the parent.
        self.worker_events: Queue = Queue(maxsize=2000)
        self.download_service = DownloadService(self.worker_events)
        self.model_loading: bool = False
        self.model_loading_dialog: ModelLoadingDialog | None = None
        # Tk StringVar for the status line + recent-files submenu rebuild.
        self.status_var = tk.StringVar(value="Ready")
        self._recent_menu: tk.Menu | None = None

        self._build_ui()
        self._build_menu()

        # Crash dialog hook — must come AFTER the Tk root exists so it
        # can locate it.
        install_excepthook(get_root=lambda: self.root)

        # Startup health check + first-run hub picker, deferred so
        # the main window has had a chance to paint.
        self.root.after(50, self._run_startup_checks)
        # Poll the worker-event queue on the Tk main thread.
        self.root.after(100, self._poll_worker_events)

    # ------------------------------------------------------------ UI build

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)

        # Drop zone — top half.
        self.dropzone = DropZone(outer, on_files=self._on_files_added)
        self.dropzone.pack(fill="both", expand=False, ipady=20)

        # Action row.
        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(10, 6))
        ttk.Button(
            actions, text="Browse…", command=self._browse,
        ).pack(side="left")
        # Language picker — small dropdown so the user can force a
        # language when auto-detect picks wrong. Kept intentionally
        # short (the four the collaborator actually transcribes);
        # everything else falls back to auto-detect, which works on
        # 99 languages.
        ttk.Label(actions, text="Language:").pack(side="left", padx=(14, 4))
        self.language_var = tk.StringVar(value=LANGUAGE_CHOICES[0][0])
        self.language_combo = ttk.Combobox(
            actions,
            textvariable=self.language_var,
            values=[label for label, _code in LANGUAGE_CHOICES],
            state="readonly",
            width=18,
        )
        self.language_combo.pack(side="left")
        self.transcribe_btn = ttk.Button(
            actions, text="Transcribe", command=self._on_transcribe_click,
            style="Accent.TButton",
        )
        self.transcribe_btn.pack(side="left", padx=(8, 0))
        # Hint label next to the buttons.
        ttk.Label(
            actions, textvariable=self.status_var, foreground="#888",
        ).pack(side="left", padx=(14, 0))

        # Download Videos section — same single screen, just below
        # the transcribe controls. Builds the per-section state
        # variables on self so the rest of the App can read them.
        self._build_download_section(outer)

        # Progress bar.
        self.pb = ttk.Progressbar(
            outer, length=600, mode="determinate", maximum=100,
        )
        self.pb.pack(fill="x", pady=(6, 4))

        # Queue label + Treeview.
        ttk.Label(outer, text="Queue:").pack(anchor="w", pady=(8, 2))

        tree_frame = ttk.Frame(outer)
        tree_frame.pack(fill="both", expand=True)

        cols = ("kind", "status", "progress", "language")
        self.tree = ttk.Treeview(
            tree_frame, columns=cols, show="tree headings", height=6,
        )
        self.tree.heading("#0", text="File")
        self.tree.heading("kind", text="Kind")
        self.tree.heading("status", text="Status")
        self.tree.heading("progress", text="Progress")
        self.tree.heading("language", text="Language")
        self.tree.column("#0", width=300, anchor="w")
        self.tree.column("kind", width=78, anchor="w")
        self.tree.column("status", width=90, anchor="w")
        self.tree.column("progress", width=70, anchor="e")
        self.tree.column("language", width=80, anchor="w")
        yscroll = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.tree.yview,
        )
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        # Esc → cancel running task.
        self.root.bind("<Escape>", lambda _e: self._cancel_running())
        # Right-click → context menu.
        self.tree.bind("<Button-3>", self._on_tree_right_click)

        # Map iid → task for fast lookups during event handling.
        # Values are either TranscriptionTask or VideoDownloadTask;
        # the App distinguishes them with isinstance() at use sites.
        self.row_map: dict[str, TranscriptionTask | VideoDownloadTask] = {}

        # Collapsible console — start collapsed.
        self.console_visible = tk.BooleanVar(value=False)
        toggle_row = ttk.Frame(outer)
        toggle_row.pack(fill="x", pady=(6, 0))
        ttk.Checkbutton(
            toggle_row, text="Show log",
            variable=self.console_visible,
            command=self._toggle_console,
        ).pack(side="left")

        self.console = tk.Text(
            outer, height=8, wrap="none", font=("Consolas", 9),
        )
        self.console.configure(state="disabled")
        # Not packed initially.

    # Default Format / Folder / Auto-transcribe persisted under
    # these keys in config.json. Centralised so config readers and
    # writers always agree.
    _CFG_DOWNLOAD_FOLDER = "download_folder"
    _CFG_DOWNLOAD_FORMAT = "download_format"
    _CFG_AUTO_TRANSCRIBE = "auto_transcribe_after_download"

    def _build_download_section(self, outer: ttk.Frame) -> None:
        """Add the Download Videos LabelFrame to ``outer``.

        Compact ~6-row block. All state is on self so the download
        service and event handlers can read it without poking at
        widget IDs.
        """
        frame = ttk.LabelFrame(
            outer, text="Download Videos (optional)", padding=8,
        )
        frame.pack(fill="x", pady=(8, 0))

        # Row 1: URL header.
        ttk.Label(
            frame,
            text="URLs (one per line):",
            foreground="#888",
        ).grid(row=0, column=0, columnspan=4, sticky="w")

        # Row 2: URL text box.
        self.download_urls = tk.Text(
            frame, height=3, wrap="none", font=("Segoe UI", 9),
        )
        self.download_urls.grid(
            row=1, column=0, columnspan=4, sticky="ew", pady=(2, 6),
        )

        # Row 3: Folder.
        ttk.Label(frame, text="Folder:").grid(row=2, column=0, sticky="w")
        # Default folder: user's Downloads folder, persisted to config.
        default_folder = self.config_dict.get(
            self._CFG_DOWNLOAD_FOLDER,
        ) or self._default_download_folder()
        self.download_folder_var = tk.StringVar(value=default_folder)
        ttk.Entry(
            frame, textvariable=self.download_folder_var,
        ).grid(row=2, column=1, columnspan=2, sticky="ew", padx=(4, 4))
        ttk.Button(
            frame, text="…", width=3,
            command=self._on_pick_download_folder,
        ).grid(row=2, column=3, sticky="w")

        # Row 4: Format combobox.
        ttk.Label(frame, text="Format:").grid(
            row=3, column=0, sticky="w", pady=(6, 0),
        )
        labels = list(FORMAT_LABELS.values())
        saved_format = self.config_dict.get(
            self._CFG_DOWNLOAD_FORMAT, "best",
        )
        # Convert saved key to label; fall back to "Best video+audio".
        initial_label = FORMAT_LABELS.get(
            saved_format if isinstance(saved_format, str) else "best",
            labels[0],
        )
        self.download_format_var = tk.StringVar(value=initial_label)
        ttk.Combobox(
            frame, textvariable=self.download_format_var,
            values=labels, state="readonly", width=22,
        ).grid(row=3, column=1, sticky="w", padx=(4, 0), pady=(6, 0))

        # Row 5: Time range (optional).
        ttk.Label(frame, text="Time range (optional):").grid(
            row=4, column=0, sticky="w", pady=(6, 0),
        )
        time_frame = ttk.Frame(frame)
        time_frame.grid(
            row=4, column=1, columnspan=3, sticky="w",
            padx=(4, 0), pady=(6, 0),
        )
        ttk.Label(time_frame, text="Start").pack(side="left")
        self.download_start_var = tk.StringVar()
        ttk.Entry(
            time_frame, textvariable=self.download_start_var, width=10,
        ).pack(side="left", padx=(4, 12))
        ttk.Label(time_frame, text="End").pack(side="left")
        self.download_end_var = tk.StringVar()
        ttk.Entry(
            time_frame, textvariable=self.download_end_var, width=10,
        ).pack(side="left", padx=(4, 0))

        # Row 6: Auto-transcribe checkbox + Download button.
        bottom = ttk.Frame(frame)
        bottom.grid(
            row=5, column=0, columnspan=4, sticky="ew", pady=(8, 0),
        )
        self.auto_transcribe_var = tk.BooleanVar(
            value=bool(self.config_dict.get(self._CFG_AUTO_TRANSCRIBE, False)),
        )
        ttk.Checkbutton(
            bottom, text="Auto-transcribe after download",
            variable=self.auto_transcribe_var,
        ).pack(side="left")
        ttk.Button(
            bottom, text="Download",
            command=self._on_download_click,
            style="Accent.TButton",
        ).pack(side="right")

        # Column weights so the Entry widgets grow with the window.
        for col, weight in ((0, 0), (1, 1), (2, 1), (3, 0)):
            frame.columnconfigure(col, weight=weight)

    def _default_download_folder(self) -> str:
        """User's Downloads folder, with a CWD fallback for headless tests."""
        home = os.path.expanduser("~")
        candidate = os.path.join(home, "Downloads")
        if os.path.isdir(candidate):
            return candidate
        return home or os.getcwd()

    def _on_pick_download_folder(self) -> None:
        chosen = filedialog.askdirectory(
            parent=self.root,
            title="Pick a download folder",
            initialdir=self.download_folder_var.get() or os.path.expanduser("~"),
        )
        if chosen:
            self.download_folder_var.set(chosen)

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        self.root.configure(menu=menubar)

        # File
        filem = tk.Menu(menubar, tearoff=False)
        filem.add_command(label="Open…", accelerator="Ctrl+O",
                          command=self._browse)
        self._recent_menu = tk.Menu(filem, tearoff=False)
        filem.add_cascade(label="Open recent", menu=self._recent_menu)
        filem.add_separator()
        filem.add_command(label="Exit", accelerator="Ctrl+Q",
                          command=self.on_exit)
        menubar.add_cascade(label="File", menu=filem)

        # Help
        helpm = tk.Menu(menubar, tearoff=False)
        helpm.add_command(label="About", command=lambda: AboutDialog(self.root))
        helpm.add_separator()
        helpm.add_command(label="Show recent log",
                          command=lambda: ShowLogDialog(
                              self.root, lines=LOG_PANEL_LINES))
        helpm.add_command(label="Diagnose",
                          command=lambda: DiagnoseDialog(self.root))
        helpm.add_command(label="Open log folder",
                          command=self._open_log_folder)
        menubar.add_cascade(label="Help", menu=helpm)

        # Accelerators.
        self.root.bind("<Control-o>", lambda _e: self._browse())
        self.root.bind("<Control-q>", lambda _e: self.on_exit())

        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self) -> None:
        menu = self._recent_menu
        if menu is None:
            return
        menu.delete(0, "end")
        recent = self.config_dict.get("recent_files") or []
        if not recent:
            menu.add_command(label="(no recent files)", state="disabled")
            return
        for path in recent:
            if not isinstance(path, str):
                continue
            label = os.path.basename(path) or path
            # Capture path in a default-arg to avoid late-binding.
            menu.add_command(
                label=f"{label}  —  {path}",
                command=lambda p=path: self._open_recent(p),
            )

    def _open_recent(self, path: str) -> None:
        if not os.path.exists(path):
            messagebox.showwarning(
                "File missing",
                f"The file no longer exists:\n{path}",
                parent=self.root,
            )
            return
        self._on_files_added([path])

    # ------------------------------------------------------------ startup

    def _run_startup_checks(self) -> None:
        results = run_all()
        failure = first_failure(results)
        if failure is not None:
            messagebox.showerror(
                "Startup issue",
                f"Issue: {failure.detail}\n\nTry: {failure.suggestion}",
                parent=self.root,
            )
        # First-run hub picker.
        ensure_hub_configured(
            self.root, self.config_dict,
            on_done=self._on_hub_chosen,
        )

    def _on_hub_chosen(self, path: str) -> None:
        # The dialog already wrote hub_folder + cleared model_path.
        # Reload config so the next ensure_model() uses the fresh
        # values without us having to mirror them by hand.
        self.config_dict = load_config()
        logger.info("Hub chosen: %s", path)

    # ------------------------------------------------------------ window chrome

    def _install_icon(self) -> None:
        """Set the window-title-bar and taskbar icon.

        Looks for ``assets/whisper.ico`` next to the source tree
        (dev / Setup-Standard install) — silently no-ops if the
        icon is missing, since the icon is cosmetic and a missing
        file should not prevent the app from launching.
        """
        from .paths_util import asset_path  # local import keeps top tidy
        ico = asset_path("whisper.ico")
        if not ico:
            return
        try:
            self.root.iconbitmap(default=str(ico))
        except tk.TclError as exc:
            logger.warning("Could not set window icon (%s): %s", ico, exc)

    # ------------------------------------------------------------ file intake

    def _browse(self) -> None:
        paths = filedialog.askopenfilenames(
            parent=self.root,
            title="Pick media file(s) to transcribe",
            filetypes=[
                ("Media files", "*.mp3 *.mp4 *.wav *.m4a *.mkv *.mov *.flac *.ogg *.webm *.aac *.opus *.wma *.avi"),
                ("All files", "*.*"),
            ],
        )
        if paths:
            self._on_files_added(list(paths))

    # Debounce window for save_config after a burst of file-added
    # callbacks. 250 ms is short enough that a power cut between
    # add and save won't surprise anyone, and long enough that a
    # rapid 100-file drop collapses to a single save (audit P1-9).
    _SAVE_DEBOUNCE_MS = 250

    def _on_files_added(self, files: list[str]) -> None:
        added = 0
        for f in files:
            if not os.path.isfile(f):
                continue
            task = TranscriptionTask(os.path.abspath(f))
            self.queue.append(task)
            iid = self._add_tree_row(task)
            self.row_map[iid] = task
            added += 1
            # Update recent list.
            add_recent_file(self.config_dict, task.file_path, limit=RECENT_LIMIT)
        if added:
            self._rebuild_recent_menu()
            self.status_var.set(
                f"Added {added} file(s). Click Transcribe to begin."
            )
            self._schedule_save_config()

    def _schedule_save_config(self) -> None:
        """Coalesce a burst of save requests into one disk write."""
        existing = getattr(self, "_save_timer_id", None)
        if existing is not None:
            try:
                self.root.after_cancel(existing)
            except tk.TclError:
                pass
        self._save_timer_id = self.root.after(
            self._SAVE_DEBOUNCE_MS, self._flush_save_config,
        )

    def _flush_save_config(self) -> None:
        self._save_timer_id = None
        try:
            save_config(self.config_dict)
        except Exception as e:  # noqa: BLE001
            logger.warning("save_config (debounced) failed: %s", e)

    def _add_tree_row(
        self, task: TranscriptionTask | VideoDownloadTask,
    ) -> str:
        if isinstance(task, VideoDownloadTask):
            display = task.title or task.url
            progress_text = f"{int(task.progress)}%"
            return self.tree.insert(
                "", "end",
                text=display,
                values=("download", task.status, progress_text, ""),
            )
        return self.tree.insert(
            "", "end",
            text=os.path.basename(task.file_path),
            values=("transcribe", task.status, f"{task.progress}%", ""),
        )

    def _iid_for(
        self, task: TranscriptionTask | VideoDownloadTask,
    ) -> str | None:
        for iid, t in self.row_map.items():
            if t is task:
                return iid
        return None

    def _update_tree_row(
        self, task: TranscriptionTask | VideoDownloadTask,
    ) -> None:
        iid = self._iid_for(task)
        if iid is None:
            return
        if isinstance(task, VideoDownloadTask):
            self.tree.item(
                iid,
                values=(
                    "download",
                    task.status,
                    f"{int(task.progress)}%",
                    "",
                ),
            )
            return
        self.tree.item(
            iid,
            values=(
                "transcribe",
                task.status,
                f"{task.progress}%",
                task.detected_language or "",
            ),
        )

    # ------------------------------------------------------------ download

    def _on_download_click(self) -> None:
        """Parse the URL Text widget; enqueue one task per non-blank line."""
        raw = self.download_urls.get("1.0", "end").strip()
        if not raw:
            self.status_var.set("Paste at least one URL.")
            return
        folder = self.download_folder_var.get().strip()
        if not folder:
            messagebox.showwarning(
                "Pick a folder",
                "Choose a download folder first.",
                parent=self.root,
            )
            return

        # Resolve combobox label → format key once.
        label_to_key = {v: k for k, v in FORMAT_LABELS.items()}
        fmt_key = label_to_key.get(self.download_format_var.get(), "best")

        start_sec = parse_timecode(self.download_start_var.get())
        end_sec = parse_timecode(self.download_end_var.get())
        # If both fields were filled but only one parsed, warn the
        # user — silently dropping their input is worse than refusing.
        for label, raw_text, parsed in (
            ("Start", self.download_start_var.get(), start_sec),
            ("End", self.download_end_var.get(), end_sec),
        ):
            if raw_text.strip() and parsed is None:
                messagebox.showwarning(
                    "Bad time-range",
                    f"Couldn't parse {label!r} time {raw_text!r}.\n"
                    "Use H:MM:SS, MM:SS, or seconds.",
                    parent=self.root,
                )
                return

        auto = bool(self.auto_transcribe_var.get())

        urls = [line.strip() for line in raw.splitlines() if line.strip()]
        added = 0
        skipped: list[str] = []
        for url in urls:
            task = self.download_service.build_task(
                url, folder,
                output_format=fmt_key,
                section_start=start_sec,
                section_end=end_sec,
                auto_transcribe=auto,
            )
            if task is None:
                skipped.append(url)
                continue
            self.download_queue.append(task)
            iid = self._add_tree_row(task)
            self.row_map[iid] = task
            added += 1

        if skipped:
            messagebox.showwarning(
                "Some URLs were skipped",
                "Couldn't classify these URLs:\n\n"
                + "\n".join(skipped[:5])
                + ("\n…" if len(skipped) > 5 else ""),
                parent=self.root,
            )

        if added == 0:
            return

        # Persist user-friendly knobs.
        self.config_dict[self._CFG_DOWNLOAD_FOLDER] = folder
        self.config_dict[self._CFG_DOWNLOAD_FORMAT] = fmt_key
        self.config_dict[self._CFG_AUTO_TRANSCRIBE] = auto
        self._schedule_save_config()

        # Clear the text area + time fields so the next paste starts fresh.
        self.download_urls.delete("1.0", "end")
        self.download_start_var.set("")
        self.download_end_var.set("")

        self.status_var.set(f"Queued {added} download(s).")
        self._dispatch_next_download()

    def _dispatch_next_download(self) -> None:
        """Start the next waiting download if nothing is already running."""
        if self.download_current is not None:
            return
        for task in self.download_queue:
            if task.status == "waiting" and not task.cancelled:
                self.download_current = task
                self._update_tree_row(task)
                self.download_service.start(task)
                self.status_var.set(
                    f"Downloading {task.title or task.url}…",
                )
                return

    def _task_by_id(
        self, task_id: int,
    ) -> VideoDownloadTask | None:
        for t in self.download_queue:
            if id(t) == task_id:
                return t
        return None

    def _on_download_progress(self, event: dict[str, Any]) -> None:
        task = self._task_by_id(int(event.get("task_id", 0)))
        if task is None:
            return
        task.progress = max(0.0, min(100.0, float(event.get("percent", 0))))
        self._update_tree_row(task)
        # The shared progress bar reflects whichever job is currently
        # foreground. A transcribe job's progress trumps the download
        # bar so the transcribe doesn't appear stuck.
        if self.worker is None or self.worker.get("task") is None:
            self.pb["value"] = task.progress

    def _on_download_done(self, event: dict[str, Any]) -> None:
        task = self._task_by_id(int(event.get("task_id", 0)))
        if task is None:
            return
        status = event.get("status", "finished")
        task.status = status
        saved_path = event.get("saved_path")
        if isinstance(saved_path, str) and saved_path:
            task.saved_path = saved_path
        if status == "finished":
            task.progress = 100.0
        self._update_tree_row(task)
        if self.download_current is task:
            self.download_current = None
        if status == "finished" and saved_path:
            self.status_var.set(
                f"Saved {os.path.basename(saved_path)}",
            )
            # Auto-transcribe handoff: feed the saved file into the
            # transcribe pipeline. The lazy-model-load gate runs the
            # first time the user clicks Transcribe — we trigger a
            # click programmatically so the model dialog appears
            # exactly once for the whole batch.
            if task.auto_transcribe and os.path.isfile(saved_path):
                self._on_files_added([saved_path])
                self._on_transcribe_click()
        elif status == "cancelled":
            self.status_var.set("Download cancelled")
        # Pick up the next download regardless of how this one ended.
        self._dispatch_next_download()

    def _on_download_error(self, event: dict[str, Any]) -> None:
        task = self._task_by_id(int(event.get("task_id", 0)))
        if task is None:
            return
        message = event.get("message") or "Unknown download error"
        suggestion = event.get("suggestion") or ""
        task.status = "error"
        task.error_message = message
        self._update_tree_row(task)
        if self.download_current is task:
            self.download_current = None
        full = f"Download failed for {task.title or task.url}:\n{message}"
        if suggestion:
            full += f"\n\nTry: {suggestion}"
        logger.error("Download error: %s", message)
        messagebox.showerror("Download failed", full, parent=self.root)
        self.status_var.set("Download failed.")
        self._dispatch_next_download()

    # ------------------------------------------------------------ transcribe

    def _on_transcribe_click(self) -> None:
        # Build a list of waiting tasks; refuse if there's nothing.
        waiting = [t for t in self.queue if t.status == "waiting"]
        if not waiting:
            self.status_var.set("Add a file first.")
            return

        # Re-entrancy guard. ``wait_window`` on the download / loading
        # dialogs processes Tk events on the main thread, so a fast
        # double-click on Transcribe would otherwise run two
        # _dispatch_next paths concurrently and mis-attribute the
        # first task's progress / done events to the second one
        # (audit P0-5).
        if getattr(self, "_transcribe_in_progress", False):
            return
        self._transcribe_in_progress = True
        try:
            self.transcribe_btn.configure(state="disabled")
        except tk.TclError:
            pass

        try:
            # Lazy: download model if missing → spawn worker → transcribe.
            cfg = load_config()
            if not is_model_on_disk(cfg):
                dialog = ModelDownloadDialog(self.root)
                self.root.wait_window(dialog)
                if not dialog.success:
                    self.status_var.set("Model download did not complete.")
                    return
                # Refresh config snapshot in case model_path was redirected.
                self.config_dict = load_config()

            if self.worker is None or not self._worker_alive():
                ok = self._spawn_worker_blocking()
                if not ok:
                    return

            # Dispatch the next waiting task. The worker handles one at
            # a time; we re-dispatch on the `done`/`error` events.
            self._dispatch_next()
        finally:
            self._transcribe_in_progress = False
            try:
                self.transcribe_btn.configure(state="normal")
            except tk.TclError:
                pass

    def _worker_alive(self) -> bool:
        if self.worker is None:
            return False
        proc = self.worker.get("process")
        return proc is not None and proc.poll() is None

    def _spawn_worker_blocking(self) -> bool:
        """Spawn the worker subprocess and wait for its ``ready`` event.

        Shows a modal ModelLoadingDialog during the wait. Returns
        True on success, False if the user cancelled or the worker
        died on startup.
        """
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--worker"]
        else:
            cmd = [sys.executable, "-u", "-m", "core.worker"]
        token = uuid.uuid4().hex
        env = os.environ.copy()
        env["WHISPER_WORKER_TOKEN"] = token
        kwargs: dict[str, Any] = {
            "cwd": os.path.dirname(os.path.abspath(_resolve_entry_file())),
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "env": env,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        try:
            process = subprocess.Popen(cmd, **kwargs)
        except OSError as e:
            messagebox.showerror(
                "Could not start worker",
                f"Failed to spawn worker subprocess:\n{e}",
                parent=self.root,
            )
            return False

        self.worker = {
            "process": process, "ready": False, "task": None, "token": token,
        }

        # Background reader thread → worker_events queue.
        def reader() -> None:
            try:
                for line in process.stdout:  # type: ignore[union-attr]
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        event = {"event": "log", "message": line}
                    self._enqueue_worker_event(event)
                rc = process.wait()
                # Lifecycle event — block until the parent drains
                # space rather than risk losing it to a Full queue.
                self._enqueue_worker_event(
                    {"event": "worker_exit", "return_code": rc, "_token": token},
                )
            except Exception:
                logger.exception("worker reader thread crashed")

        threading.Thread(
            target=reader, name="worker-reader", daemon=True,
        ).start()

        # Show the modal loading dialog and wait for the worker to
        # signal ``ready`` (handled by the poll loop).
        dialog = ModelLoadingDialog(self.root)
        self.model_loading_dialog = dialog
        self.root.wait_window(dialog)
        self.model_loading_dialog = None

        if not dialog.success:
            # User cancelled OR ``ready`` never came → kill worker.
            self._stop_worker()
            return False
        return True

    def _dispatch_next(self) -> None:
        if self.worker is None or not self._worker_alive():
            return
        if self.worker.get("task") is not None:
            return
        for task in self.queue:
            if task.status == "waiting" and not task.cancelled:
                self._send_transcribe(task)
                return
        # Nothing left to do.
        self.status_var.set("All tasks complete.")
        self.pb["value"] = 0

    def _send_transcribe(self, task: TranscriptionTask) -> None:
        assert self.worker is not None
        proc = self.worker["process"]
        if proc is None or proc.stdin is None or proc.poll() is not None:
            self._on_task_error(task, "Worker is not running.")
            return
        task.status = "running"
        task.start_time = time.time()
        self.worker["task"] = task
        self._update_tree_row(task)
        self.status_var.set(f"Transcribing {os.path.basename(task.file_path)}…")
        self.pb["value"] = 0
        # Resolve the language picker selection to a faster-whisper
        # code; empty string means "auto-detect", which the worker
        # treats as no language override.
        lang_label = self.language_var.get()
        lang_code = next(
            (code for label, code in LANGUAGE_CHOICES if label == lang_label),
            "",
        )
        cmd: dict[str, Any] = {
            "action": "transcribe", "file_path": task.file_path,
        }
        if lang_code:
            cmd["language"] = lang_code
        try:
            proc.stdin.write(json.dumps(cmd) + "\n")
            proc.stdin.flush()
        except (OSError, BrokenPipeError) as e:
            self._on_task_error(task, f"Failed to send command to worker: {e}")

    # ------------------------------------------------------------ events

    def _enqueue_worker_event(self, event: dict[str, Any]) -> None:
        """Put one event onto the worker_events queue.

        Lifecycle events (``done``, ``error``, ``worker_exit``,
        ``startup_error``, ``ready``) MUST NOT be dropped — they
        drive UI state machines. For those we block until the Tk
        poll loop drains the queue. High-volume events
        (``progress``, ``log``, ``heartbeat``) are best-effort:
        attempt a non-blocking put and log on overflow.
        """
        name = event.get("event")
        if name in _LIFECYCLE_EVENTS:
            # No timeout — the Tk poll loop runs every 100 ms and
            # drains the queue in bulk, so blocking is bounded.
            self.worker_events.put(event)
            return
        try:
            self.worker_events.put_nowait(event)
        except Full:
            logger.warning("worker_events.put_nowait dropped event %r", event)

    def _poll_worker_events(self) -> None:
        try:
            while True:
                event = self.worker_events.get_nowait()
                self._handle_event(event)
        except Empty:
            pass
        self.root.after(100, self._poll_worker_events)

    def _handle_event(self, event: dict[str, Any]) -> None:
        name = event.get("event")
        if name == "ready":
            if self.worker is not None:
                self.worker["ready"] = True
            if self.model_loading_dialog is not None:
                self.model_loading_dialog.mark_success_and_close()
            return
        if name == "startup_error":
            msg = event.get("message", "Model failed to load.")
            logger.error("Worker startup_error: %s", msg)
            if self.model_loading_dialog is not None:
                self.model_loading_dialog.cancel()
            messagebox.showerror(
                "Model load failed",
                f"The Whisper model could not load:\n{msg}",
                parent=self.root,
            )
            self._stop_worker()
            return
        if name == "log":
            self._append_console(event.get("message", ""))
            return
        if name == "progress":
            self._on_progress(float(event.get("percent", 0)))
            return
        if name == "language_detected":
            self._on_language(
                event.get("file_path", ""),
                str(event.get("language", "")),
                float(event.get("probability", 0.0)),
            )
            return
        if name == "started":
            return
        if name == "done":
            self._on_task_done(event.get("file_path", ""))
            return
        if name == "error":
            self._on_worker_error(event)
            return
        if name == "heartbeat":
            return
        if name == "download_progress":
            self._on_download_progress(event)
            return
        if name == "download_done":
            self._on_download_done(event)
            return
        if name == "download_error":
            self._on_download_error(event)
            return
        if name == "worker_exit":
            rc = event.get("return_code")
            had_task = bool(self.worker and self.worker.get("task") is not None)
            logger.info("Worker exited (rc=%s, had_task=%s)", rc, had_task)
            # If the current task was still running, mark it errored.
            if had_task:
                assert self.worker is not None
                t = self.worker["task"]
                self._on_task_error(t, f"Worker exited unexpectedly (rc={rc}).")
            else:
                # No task was running — usually a clean shutdown. But
                # if there are waiting tasks the worker silently
                # vanished (parent stdin closed by an OS hook, AV,
                # etc), and the queue would otherwise sit at
                # "waiting" forever. Surface that as a status hint
                # so the next Transcribe click respawns and picks
                # them up.
                waiting = [
                    t for t in self.queue
                    if t.status == "waiting" and not t.cancelled
                ]
                if waiting and rc not in (0, None):
                    self.status_var.set(
                        f"Worker exited unexpectedly (rc={rc}). "
                        "Click Transcribe to resume."
                    )
            self.worker = None
            return

    def _on_progress(self, percent: float) -> None:
        self.pb["value"] = max(0, min(100, percent))
        if self.worker and self.worker.get("task") is not None:
            t = self.worker["task"]
            t.progress = int(percent)
            self._update_tree_row(t)

    def _on_language(self, file_path: str, lang: str, prob: float) -> None:
        for task in self.queue:
            if task.file_path == file_path:
                task.detected_language = lang
                task.language_probability = prob
                self._update_tree_row(task)
                break

    def _on_task_done(self, file_path: str) -> None:
        for task in self.queue:
            if task.file_path == file_path:
                task.status = "finished"
                task.progress = 100
                task.end_time = time.time()
                self._update_tree_row(task)
                break
        if self.worker is not None:
            self.worker["task"] = None
        self.status_var.set(
            f"Done: {os.path.basename(file_path)}"
        )
        # Pick up the next waiting task.
        self._dispatch_next()

    def _on_worker_error(self, event: dict[str, Any]) -> None:
        file_path = event.get("file_path") or ""
        msg = event.get("message") or "Unknown error"
        suggestion = event.get("suggestion") or ""
        task: TranscriptionTask | None = None
        for t in self.queue:
            if t.file_path == file_path:
                task = t
                break
        if task is not None:
            self._on_task_error(task, msg, suggestion=suggestion)
        else:
            messagebox.showerror(
                "Worker error", msg, parent=self.root,
            )
        if self.worker is not None:
            self.worker["task"] = None
        self._dispatch_next()

    def _on_task_error(
        self,
        task: TranscriptionTask,
        msg: str,
        *,
        suggestion: str = "",
    ) -> None:
        task.status = "error"
        task.error_message = msg
        task.end_time = time.time()
        self._update_tree_row(task)
        full = f"Couldn't transcribe {os.path.basename(task.file_path)}:\n{msg}"
        if suggestion:
            full += f"\n\nTry: {suggestion}"
        logger.error("Task error for %s: %s", task.file_path, msg)
        messagebox.showerror("Transcription failed", full, parent=self.root)
        self.status_var.set(f"Error: {os.path.basename(task.file_path)}")

    # Hard cap for the console Text widget. Trimmed AGGRESSIVELY
    # (down to half the cap) so the trim doesn't fire on every line
    # once the cap is reached (audit P1-8).
    CONSOLE_LINE_CAP = 5000

    def _append_console(self, message: str) -> None:
        self.console.configure(state="normal")
        self.console.insert("end", message + "\n")
        line_count = int(self.console.index("end-1c").split(".")[0])
        if line_count > self.CONSOLE_LINE_CAP:
            keep = self.CONSOLE_LINE_CAP // 2
            self.console.delete("1.0", f"{line_count - keep}.0")
        self.console.see("end")
        self.console.configure(state="disabled")

    def _toggle_console(self) -> None:
        if self.console_visible.get():
            self.console.pack(fill="both", expand=False, pady=(4, 0))
        else:
            self.console.pack_forget()

    # ------------------------------------------------------------ cancel / exit

    def _cancel_running(self) -> None:
        if self.worker is None or self.worker.get("task") is None:
            return
        task: TranscriptionTask = self.worker["task"]
        task.cancelled = True
        task.status = "cancelled"
        task.end_time = time.time()
        self._update_tree_row(task)
        # The transcriber's loop polls task.cancelled but it only
        # runs in the worker process. Quickest way to stop a long
        # running transcribe is to kill the worker; we re-spawn
        # lazily on the next Transcribe click.
        self.status_var.set(f"Cancelled {os.path.basename(task.file_path)}")
        self._stop_worker()

    def _on_tree_right_click(self, event: tk.Event) -> None:
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self.tree.selection_set(iid)
        task = self.row_map.get(iid)
        if task is None:
            return
        menu = tk.Menu(self.root, tearoff=False)
        if task.status == "running":
            if isinstance(task, VideoDownloadTask):
                menu.add_command(
                    label="Cancel",
                    command=lambda: self._cancel_download(task),
                )
            else:
                menu.add_command(
                    label="Cancel", command=self._cancel_running,
                )
        elif task.status == "waiting":
            menu.add_command(
                label="Remove from queue",
                command=lambda: self._remove_task(iid, task),
            )
        else:
            menu.add_command(
                label="Remove from list",
                command=lambda: self._remove_task(iid, task),
            )
        menu.tk_popup(event.x_root, event.y_root)

    def _cancel_download(self, task: VideoDownloadTask) -> None:
        """Right-click → Cancel on a running download row."""
        self.download_service.cancel(task)
        # Visual feedback now — the worker thread will follow up
        # with a download_done(status="cancelled") event once the
        # subprocess actually exits.
        task.status = "cancelled"
        self._update_tree_row(task)
        self.status_var.set(
            f"Cancelling {task.title or task.url}…",
        )

    def _remove_task(
        self, iid: str, task: TranscriptionTask | VideoDownloadTask,
    ) -> None:
        if isinstance(task, VideoDownloadTask):
            if task in self.download_queue:
                self.download_queue.remove(task)
        else:
            if task in self.queue:
                self.queue.remove(task)
        try:
            self.tree.delete(iid)
        except tk.TclError:
            pass
        self.row_map.pop(iid, None)

    def _stop_worker(self) -> None:
        """Structured shutdown — shutdown msg → terminate → kill.

        The shutdown JSON is best-effort: when the worker has
        already closed its end of stdin (or the pipe is broken for
        any reason), the write raises and we fall through to
        ``proc.wait()`` → ``terminate()`` → ``kill()`` without
        leaking a daemon thread (audit P1-13).
        """
        worker = self.worker
        if worker is None:
            return
        proc = worker.get("process")
        if proc is None or proc.poll() is not None:
            self.worker = None
            return

        # 1. Try the shutdown command synchronously, but tolerate a
        #    closed pipe. The write is microseconds when it works
        #    and OSError-immediate when it doesn't; there's no
        #    realistic scenario where blocking the Tk thread for
        #    "long enough to matter" comes from this single small
        #    JSON write. The previous fire-and-forget daemon thread
        #    leaked one thread per cancel/transcribe cycle when the
        #    worker had stdin closed.
        try:
            if proc.stdin:
                proc.stdin.write(json.dumps({"action": "shutdown"}) + "\n")
                proc.stdin.flush()
        except (OSError, BrokenPipeError, ValueError):
            # Worker's stdin already closed (graceful or otherwise).
            # Fall through to proc.wait — the worker is already
            # winding down, the wait below will reap it shortly.
            logger.debug("stop_worker stdin shutdown failed", exc_info=True)

        # 2. Always close our end of stdin too — sending EOF makes
        #    the worker's ``_read_command_line`` return None on the
        #    very next iteration, which is its alternate graceful
        #    shutdown path.
        try:
            if proc.stdin:
                proc.stdin.close()
        except (OSError, ValueError):
            pass

        # 3. Wait briefly.
        try:
            proc.wait(timeout=3.0)
            self.worker = None
            return
        except subprocess.TimeoutExpired:
            logger.info("Worker ignored shutdown; terminating")
        # 4. terminate.
        try:
            proc.terminate()
        except Exception:
            logger.exception("worker terminate() raised")
        try:
            proc.wait(timeout=2.0)
            self.worker = None
            return
        except subprocess.TimeoutExpired:
            logger.warning("Worker ignored terminate; killing")
        # 5. kill.
        try:
            proc.kill()
        except Exception:
            logger.exception("worker kill() raised")
        self.worker = None

    def _open_log_folder(self) -> None:
        try:
            open_log_folder()
        except Exception as e:  # noqa: BLE001
            logger.warning("open_log_folder failed: %s", e)
            messagebox.showwarning(
                "Couldn't open log folder", str(e), parent=self.root,
            )

    def on_exit(self) -> None:
        running = any(t.status == "running" for t in self.queue)
        downloading = any(
            t.status == "running" for t in self.download_queue
        )
        if running or downloading:
            msg = (
                "A transcription is in progress. Quit and cancel it?"
                if running
                else "A download is in progress. Quit and cancel it?"
            )
            ok = messagebox.askyesno(
                "Quit Whisper Project?", msg, parent=self.root,
            )
            if not ok:
                return
        # Cancel any running download cleanly before tearing down the
        # worker_events queue.
        for t in self.download_queue:
            if t.status == "running":
                try:
                    self.download_service.cancel(t)
                except Exception:  # noqa: BLE001
                    logger.exception("download cancel during exit failed")
        self._stop_worker()
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def main() -> int:
    """Entry point — construct the Tk root + the App."""
    # Try TkinterDnD root first for drag-and-drop support.
    try:
        from tkinterdnd2 import TkinterDnD  # type: ignore[import-not-found]
        root: tk.Tk = TkinterDnD.Tk()
    except Exception as e:  # noqa: BLE001
        # Fall back to a plain Tk root. Without tkinterdnd2 the
        # DropZone falls back to click-to-browse only.
        try:
            # Best-effort surface to the log so a debugger can find
            # the reason DnD didn't register.
            from core.logging_setup import setup_logging as _setup
            _setup()
            logging.getLogger(__name__).warning(
                "tkinterdnd2 unavailable (%s); DnD disabled", e,
            )
        except Exception:
            pass
        root = tk.Tk()

    App(root)
    root.mainloop()
    return 0
