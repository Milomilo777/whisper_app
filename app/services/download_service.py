"""Video download service — yt-dlp subprocess + SMTV in-process streamer.

Posts events back to the App on the shared ``worker_events`` queue
that the transcribe worker already uses, so the Tk side only has a
single event loop to drain.

Event payloads added by this module (the App's ``_handle_event``
branches on ``event`` first, then reads ``task_id`` to find the
right row):

  * ``{"event": "download_progress", "task_id": ..., "percent": ...}``
  * ``{"event": "download_done", "task_id": ..., "saved_path": ...}``
  * ``{"event": "download_error", "task_id": ..., "message": ...,
        "suggestion": ...}``
  * ``{"event": "log", "message": ...}`` — shared with the worker.

The two backends differ in the obvious place:

  * **yt-dlp** spawns ``bin/yt-dlp.exe`` and parses its stdout. The
    Popen handle is kept on the task so Cancel can ``taskkill /T``.
  * **SMTV** streams directly via :func:`core.integrations.smtv.download`
    on a daemon thread. There is no subprocess; Cancel flips the
    task's ``cancelled`` flag and the streamer notices on the next
    chunk boundary.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
from pathlib import Path
from queue import Full, Queue
from typing import Any

from app.domain.tasks import VideoDownloadTask
from app.paths_util import repo_or_install_root
from core._timecode import download_sections_arg
from core.error_messages import friendly_error
from core.integrations import smtv as smtv_mod
from core.url_kind import url_kind

logger = logging.getLogger(__name__)

__all__ = [
    "DownloadService",
    "yt_dlp_path",
    "build_yt_dlp_command",
    "parse_progress_line",
    "parse_destination_line",
]


_PERCENT_RE = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
_DEST_RE = re.compile(
    r"^\[(?:download|Merger|ExtractAudio)\] "
    r"(?:Destination|Merging formats into):\s+(.+)$",
)


# Display labels for the Format combobox. ``output_format`` on the
# task is the lower-case key — kept as a public mapping so the App
# can populate the combobox without re-declaring the list.
FORMAT_LABELS: dict[str, str] = {
    "best": "Best video+audio",
    "mp3": "Audio only (mp3)",
    "m4a": "Audio only (m4a)",
}


# ---------------------------------------------------------- pure helpers --


def yt_dlp_path() -> str:
    """Resolve the bundled ``bin/yt-dlp.exe`` path.

    Always returns a string even when the binary is missing — the
    caller surfaces a friendlier error on Popen failure than a path
    check here would. (Tests can stub this; runtime callers should
    expect a real file at the returned location.)
    """
    return str(repo_or_install_root() / "bin" / "yt-dlp.exe")


def bin_dir() -> str:
    """Folder that holds ``yt-dlp.exe`` + ``ffmpeg.exe`` (passed to
    yt-dlp via ``--ffmpeg-location``)."""
    return str(repo_or_install_root() / "bin")


def build_yt_dlp_command(
    task: VideoDownloadTask,
    *,
    yt_dlp_exe: str,
    bin_path: str,
) -> list[str]:
    """Build the argv list for one yt-dlp invocation.

    Pure function — no I/O, no side effects. Exposed at module level
    so the test suite can pin the argv shape without spinning up a
    subprocess.
    """
    output = os.path.join(task.folder, "%(title)s.%(ext)s")
    cmd = [
        yt_dlp_exe,
        "--ffmpeg-location", bin_path,
        "--newline",
        "-o", output,
    ]

    fmt = task.output_format
    if fmt == "mp3":
        cmd.extend(
            ["-f", "ba/bestaudio", "-x", "--audio-format", "mp3"],
        )
    elif fmt == "m4a":
        cmd.extend(
            ["-f", "ba[ext=m4a]/bestaudio[ext=m4a]/ba/bestaudio",
             "-x", "--audio-format", "m4a"],
        )
    else:
        # "best" = video+audio merged into mp4 when possible.
        cmd.extend(
            [
                "-f",
                "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/best",
                "--merge-output-format", "mp4",
            ],
        )

    sections = download_sections_arg(task.section_start, task.section_end)
    if sections is not None:
        cmd.extend(["--download-sections", sections])

    cmd.append(task.url)
    return cmd


def parse_progress_line(line: str) -> float | None:
    """Pluck a ``percent`` out of one ``[download] N.N%`` line, or None."""
    line = (line or "").strip()
    if not line:
        return None
    m = _PERCENT_RE.search(line)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def parse_destination_line(line: str) -> str | None:
    """Pull the saved-file path out of a yt-dlp ``Destination:`` line."""
    if not line:
        return None
    m = _DEST_RE.match(line.strip())
    return m.group(1).strip() if m else None


# --------------------------------------------------------- the service ---


class DownloadService:
    """Drives downloads on background threads, events to the App."""

    # The App passes its existing ``worker_events`` queue here so this
    # service can stay completely decoupled from Tk. The App's poll
    # loop already drains it on the main thread.
    def __init__(self, events: "Queue[dict[str, Any]]") -> None:
        self._events = events
        # Map id(task) → task so we can look up the in-flight task by
        # its id in events (id() is stable for the task's lifetime).
        self._tasks: dict[int, VideoDownloadTask] = {}

    # ---- enqueue + dispatch ----------------------------------------

    def start(self, task: VideoDownloadTask) -> None:
        """Begin a single download in its own daemon thread."""
        self._tasks[id(task)] = task
        task.status = "running"
        task.progress = 0.0
        import time as _t
        task.start_time = _t.time()
        task.end_time = None

        target = (
            self._run_yt_dlp
            if task.backend == "yt-dlp"
            else self._run_smtv
        )
        threading.Thread(
            target=target, args=(task,),
            name=f"download-{task.backend}",
            daemon=True,
        ).start()

    def cancel(self, task: VideoDownloadTask) -> None:
        """Signal cancellation. yt-dlp gets a hard ``taskkill /T``;
        SMTV's streamer notices the flag on its next chunk."""
        task.cancelled = True
        proc = task.process
        if proc is None:
            return
        # Best-effort hard kill. yt-dlp spawns child ffmpeg processes,
        # so plain Popen.kill() can leave them running. On Windows
        # taskkill /T cleans up the whole tree.
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                proc.kill()
        except Exception:  # noqa: BLE001
            logger.exception("taskkill failed for pid=%s", proc.pid)

    # ---- backends ---------------------------------------------------

    def _run_yt_dlp(self, task: VideoDownloadTask) -> None:
        cmd = build_yt_dlp_command(
            task,
            yt_dlp_exe=yt_dlp_path(),
            bin_path=bin_dir(),
        )
        os.makedirs(task.folder, exist_ok=True)
        self._log(f"[download] {' '.join(cmd)}")

        try:
            kwargs: dict[str, Any] = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
            }
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            proc = subprocess.Popen(cmd, **kwargs)
        except OSError as e:
            self._error(task, f"Could not start yt-dlp: {e}")
            return

        task.process = proc
        saved_path: str | None = None
        try:
            assert proc.stdout is not None
            for raw_line in proc.stdout:
                line = raw_line.rstrip()
                if not line:
                    continue
                percent = parse_progress_line(line)
                if percent is not None:
                    self._progress(task, percent)
                    continue
                dest = parse_destination_line(line)
                if dest:
                    saved_path = dest
                self._log(line)
            rc = proc.wait()
        except Exception as e:  # noqa: BLE001
            self._error(task, f"yt-dlp reader crashed: {e}")
            return
        finally:
            task.process = None

        if task.cancelled:
            self._done(task, saved_path=None, status="cancelled")
            return
        if rc != 0:
            self._error(task, f"yt-dlp exited with code {rc}")
            return
        self._done(task, saved_path=saved_path, status="finished")

    def _run_smtv(self, task: VideoDownloadTask) -> None:
        os.makedirs(task.folder, exist_ok=True)
        self._log(f"[smtv] downloading {task.url}")
        try:
            saved = smtv_mod.download(
                task.url,
                task.folder,
                video_quality="audio",
                progress_cb=lambda pct: self._progress(task, pct),
                cancel_cb=lambda: task.cancelled,
                section_start=task.section_start,
                section_end=task.section_end,
            )
        except smtv_mod.SmtvError as e:
            if task.cancelled:
                self._done(task, saved_path=None, status="cancelled")
                return
            self._error(task, str(e))
            return
        except Exception as e:  # noqa: BLE001
            msg, hint = friendly_error(e)
            self._error(task, msg, suggestion=hint)
            return

        if task.cancelled:
            self._done(task, saved_path=None, status="cancelled")
            return
        self._done(task, saved_path=saved, status="finished")

    # ---- event helpers ---------------------------------------------

    def _emit(self, event: dict[str, Any], *, blocking: bool = False) -> None:
        """Forward an event to the App's worker_events queue.

        ``blocking=True`` is used for lifecycle events (``done`` /
        ``error``) so they're never dropped under saturation;
        progress / log are best-effort.
        """
        try:
            if blocking:
                self._events.put(event)
            else:
                self._events.put_nowait(event)
        except Full:
            logger.warning("download event dropped: %r", event)

    def _progress(self, task: VideoDownloadTask, percent: float) -> None:
        task.progress = max(0.0, min(100.0, percent))
        self._emit(
            {
                "event": "download_progress",
                "task_id": id(task),
                "percent": task.progress,
            },
        )

    def _log(self, message: str) -> None:
        if not message:
            return
        self._emit({"event": "log", "message": message})

    def _done(
        self,
        task: VideoDownloadTask,
        *,
        saved_path: str | None,
        status: str,
    ) -> None:
        task.status = status
        if status == "finished":
            task.progress = 100.0
            task.saved_path = saved_path
        import time as _t
        if task.end_time is None:
            task.end_time = _t.time()
        # Normalise saved_path to absolute so the auto-transcribe
        # hand-off has the same shape regardless of yt-dlp / SMTV.
        abs_saved = None
        if saved_path:
            try:
                abs_saved = str(Path(saved_path).resolve())
            except OSError:
                abs_saved = saved_path
        self._emit(
            {
                "event": "download_done",
                "task_id": id(task),
                "status": status,
                "saved_path": abs_saved,
            },
            blocking=True,
        )

    def _error(
        self,
        task: VideoDownloadTask,
        message: str,
        *,
        suggestion: str = "",
    ) -> None:
        task.status = "error"
        task.error_message = message
        import time as _t
        if task.end_time is None:
            task.end_time = _t.time()
        self._emit(
            {
                "event": "download_error",
                "task_id": id(task),
                "message": message,
                "suggestion": suggestion,
            },
            blocking=True,
        )

    # ---- factory ----------------------------------------------------

    def build_task(
        self,
        url: str,
        folder: str,
        *,
        output_format: str,
        section_start: float | None,
        section_end: float | None,
        auto_transcribe: bool,
    ) -> VideoDownloadTask | None:
        """Build a task for ``url`` after classifying it.

        Returns None when the URL is unsupported (caller should warn
        the user and skip the line).
        """
        kind = url_kind(url)
        if kind == "unsupported":
            return None
        backend: Any = "smtv" if kind == "smtv" else "yt-dlp"
        # SMTV ignores the format selector and always pulls mp3.
        effective_format = "audio" if backend == "smtv" else output_format
        label = FORMAT_LABELS.get(effective_format, effective_format)
        return VideoDownloadTask(
            url=url,
            folder=folder,
            backend=backend,
            format_label=label,
            title=url,
            output_format=effective_format,
            section_start=section_start,
            section_end=section_end,
            auto_transcribe=auto_transcribe,
        )
