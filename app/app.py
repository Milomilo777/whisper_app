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
from app.widgets.dropzone import DropZone
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

logger = logging.getLogger(__name__)

RECENT_LIMIT = 5
LOG_PANEL_LINES = 200

# Events whose loss would leave the UI in a stuck state ("running"
# forever, no error dialog, etc). Worker_events.put on these uses an
# unbounded block; high-volume events (``progress``, ``log``,
# ``heartbeat``) drop when the queue is saturated.
_LIFECYCLE_EVENTS: frozenset[str] = frozenset({
    "ready", "startup_error", "done", "error", "worker_exit",
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
        self.root.geometry("720x560")
        self.root.minsize(560, 460)
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)
        self._install_icon()

        self.config_dict: dict[str, Any] = load_config()
        setup_logging(self.config_dict.get("log_level", "INFO"))
        logger.info("App startup")

        sv_ttk.set_theme("dark")

        # In-memory queue + worker bookkeeping.
        self.queue: list[TranscriptionTask] = []
        self.worker: dict[str, Any] | None = None
        # Bound so a runaway producer can't OOM the parent.
        self.worker_events: Queue = Queue(maxsize=2000)
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

        # Progress bar.
        self.pb = ttk.Progressbar(
            outer, length=600, mode="determinate", maximum=100,
        )
        self.pb.pack(fill="x", pady=(6, 4))

        # Queue label + Treeview.
        ttk.Label(outer, text="Queue:").pack(anchor="w", pady=(8, 2))

        tree_frame = ttk.Frame(outer)
        tree_frame.pack(fill="both", expand=True)

        cols = ("status", "progress", "language")
        self.tree = ttk.Treeview(
            tree_frame, columns=cols, show="tree headings", height=6,
        )
        self.tree.heading("#0", text="File")
        self.tree.heading("status", text="Status")
        self.tree.heading("progress", text="Progress")
        self.tree.heading("language", text="Language")
        self.tree.column("#0", width=300, anchor="w")
        self.tree.column("status", width=100, anchor="w")
        self.tree.column("progress", width=80, anchor="e")
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
        self.row_map: dict[str, TranscriptionTask] = {}

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
            try:
                save_config(self.config_dict)
            except Exception as e:  # noqa: BLE001
                logger.warning("save_config (recent files) failed: %s", e)
            self._rebuild_recent_menu()
            self.status_var.set(
                f"Added {added} file(s). Click Transcribe to begin."
            )

    def _add_tree_row(self, task: TranscriptionTask) -> str:
        return self.tree.insert(
            "", "end",
            text=os.path.basename(task.file_path),
            values=(task.status, f"{task.progress}%", ""),
        )

    def _iid_for(self, task: TranscriptionTask) -> str | None:
        for iid, t in self.row_map.items():
            if t is task:
                return iid
        return None

    def _update_tree_row(self, task: TranscriptionTask) -> None:
        iid = self._iid_for(task)
        if iid is None:
            return
        self.tree.item(
            iid,
            values=(
                task.status,
                f"{task.progress}%",
                task.detected_language or "",
            ),
        )

    # ------------------------------------------------------------ transcribe

    def _on_transcribe_click(self) -> None:
        # Build a list of waiting tasks; refuse if there's nothing.
        waiting = [t for t in self.queue if t.status == "waiting"]
        if not waiting:
            self.status_var.set("Add a file first.")
            return

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

    def _append_console(self, message: str) -> None:
        self.console.configure(state="normal")
        self.console.insert("end", message + "\n")
        # Trim to a few thousand lines so the widget stays responsive
        # on multi-hour transcribes.
        line_count = int(self.console.index("end-1c").split(".")[0])
        if line_count > 4000:
            self.console.delete("1.0", f"{line_count - 2000}.0")
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
            menu.add_command(label="Cancel", command=self._cancel_running)
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

    def _remove_task(self, iid: str, task: TranscriptionTask) -> None:
        if task in self.queue:
            self.queue.remove(task)
        try:
            self.tree.delete(iid)
        except tk.TclError:
            pass
        self.row_map.pop(iid, None)

    def _stop_worker(self) -> None:
        """Structured shutdown — shutdown msg → terminate → kill."""
        worker = self.worker
        if worker is None:
            return
        proc = worker.get("process")
        if proc is None or proc.poll() is not None:
            self.worker = None
            return

        # 1. Send {"action":"shutdown"} via stdin in a daemon thread so
        #    a full pipe never blocks the Tk main thread.
        def _async_shutdown() -> None:
            try:
                if proc.stdin:
                    proc.stdin.write(json.dumps({"action": "shutdown"}) + "\n")
                    proc.stdin.flush()
            except Exception:
                logger.debug("stop_worker stdin shutdown failed", exc_info=True)
        threading.Thread(
            target=_async_shutdown, name="worker-shutdown", daemon=True,
        ).start()

        # 2. Wait briefly.
        try:
            proc.wait(timeout=3.0)
            self.worker = None
            return
        except subprocess.TimeoutExpired:
            logger.info("Worker ignored shutdown; terminating")
        # 3. terminate.
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
        # 4. kill.
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
        if running:
            ok = messagebox.askyesno(
                "Quit Whisper Project?",
                "A transcription is in progress. Quit and cancel it?",
                parent=self.root,
            )
            if not ok:
                return
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
