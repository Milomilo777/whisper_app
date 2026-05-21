"""Task models for the queues."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.task import TranscriptionTask  # re-exported for callers

__all__ = ["TranscriptionTask", "VideoDownloadTask"]


class VideoDownloadTask:
    """A single yt-dlp download job tracked in the Download Videos queue."""

    def __init__(
        self,
        url: str,
        folder: str,
        format_label: str,
        format_info: dict[str, Any],
        title: str = "",
        subtitles_enabled: bool = False,
        subtitle_lang: str = "",
        detected_language: str = "",
    ) -> None:
        self.url = url
        self.folder = folder
        self.format_label = format_label
        self.format_info = format_info
        self.title = title
        self.status = "waiting"
        self.progress: float = 0
        self.start_time: float | None = None
        # Frozen wall-clock for terminal downloads (finished /
        # cancelled / error) — same role as on TranscriptionTask.
        self.end_time: float | None = None
        self.process: Any = None
        self.cancelled = False
        self.subtitles_enabled = subtitles_enabled
        self.subtitle_lang = subtitle_lang
        self.detected_language = detected_language
        # Phase 3a — primary key in core.history.HistoryDB.downloads
        self.history_id: int = 0
