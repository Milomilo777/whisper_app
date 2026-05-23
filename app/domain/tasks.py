"""Task models for the queues.

The basic edition's existing transcription task
(:class:`core.task.TranscriptionTask`) is unchanged and re-exported
here for symmetry. :class:`VideoDownloadTask` is the new model used
by the Download Videos section.

Both task types live in the same Treeview row map on the App, told
apart by their ``kind`` attribute.
"""
from __future__ import annotations

from typing import Any, Literal

from core.task import TranscriptionTask  # re-exported for callers

__all__ = ["TranscriptionTask", "VideoDownloadTask"]


TaskKind = Literal["transcribe", "download"]


class VideoDownloadTask:
    """A single download job tracked in the Download Videos queue.

    Two flavours, distinguished by ``backend``:

      * ``"yt-dlp"`` — drives ``bin/yt-dlp.exe`` in a subprocess
      * ``"smtv"``   — drives :mod:`core.integrations.smtv`
                       (no subprocess; the download streams in a
                       worker thread inside the parent Python
                       interpreter)

    Either way the lifecycle matches :class:`core.task.TranscriptionTask`:
    ``waiting → running → finished / cancelled / error``.
    """

    # Single-row marker so the App's Treeview can branch on this
    # without isinstance() against an import the worker process can't
    # see. Always ``"download"`` for instances of this class.
    kind: TaskKind = "download"

    def __init__(
        self,
        url: str,
        folder: str,
        *,
        backend: Literal["yt-dlp", "smtv"],
        format_label: str = "",
        title: str = "",
        output_format: str = "best",
        section_start: float | None = None,
        section_end: float | None = None,
        auto_transcribe: bool = False,
    ) -> None:
        self.url = url
        self.folder = folder
        self.backend: Literal["yt-dlp", "smtv"] = backend
        self.format_label = format_label
        self.title = title or url
        # ``best`` (= "Best video+audio"), ``mp3``, ``m4a`` — only
        # meaningful for the yt-dlp backend. SMTV always pulls the
        # mp3 audio track in this edition.
        self.output_format = output_format
        # Lifecycle.
        self.status: str = "waiting"
        self.progress: float = 0.0
        self.start_time: float | None = None
        # Frozen wall-clock for terminal downloads (finished /
        # cancelled / error) — same role as on TranscriptionTask.
        self.end_time: float | None = None
        # The Popen handle for yt-dlp tasks. None for SMTV (which
        # runs in-process) and before/after the subprocess is alive.
        # ``Any`` keeps pyright happy without dragging subprocess
        # into the type surface.
        self.process: Any = None
        self.cancelled = False
        # Optional time-range slice. yt-dlp honours these via
        # ``--download-sections``; SMTV does not (a WARN is logged
        # and the full file downloads).
        self.section_start: float | None = section_start
        self.section_end: float | None = section_end
        # Set by the download service on success — kept so the App
        # can hand the path to the transcribe pipeline when
        # ``auto_transcribe`` is True.
        self.saved_path: str | None = None
        # Toggled per-task from the global "Auto-transcribe after
        # download" checkbox at enqueue time. We snapshot on the
        # task itself so unchecking the box between enqueue and
        # completion doesn't surprise a user mid-flight.
        self.auto_transcribe = auto_transcribe
        # Last error message — surfaced to the user via the standard
        # messagebox + the Treeview tooltip.
        self.error_message: str = ""

    # Friendly fall-through name for display purposes. The Treeview
    # already shows ``title`` in the File column.
    def __repr__(self) -> str:  # pragma: no cover - debug only
        return (
            f"VideoDownloadTask({self.backend!r}, {self.url!r}, "
            f"status={self.status!r})"
        )

    def time_range_label(self) -> str | None:
        """Short ``MM:SS -> MM:SS`` badge for the Queue row, or None."""
        if self.section_start is None and self.section_end is None:
            return None

        def _fmt(seconds: float | None, *, fallback: str) -> str:
            if seconds is None:
                return fallback
            total = int(seconds)
            hours, rem = divmod(total, 3600)
            minutes, secs = divmod(rem, 60)
            if hours:
                return f"{hours}:{minutes:02d}:{secs:02d}"
            return f"{minutes}:{secs:02d}"

        return (
            f"{_fmt(self.section_start, fallback='start')} -> "
            f"{_fmt(self.section_end, fallback='end')}"
        )
