from __future__ import annotations

from typing import Any


class TranscriptionTask:
    def __init__(self, file_path: str) -> None:
        self.file_path: str = file_path
        self.status: str = "waiting"
        self.progress: int = 0
        self.start_time: float | None = None
        # Frozen wall-clock for a terminal task. Set once by the
        # service / app cancel path when the task transitions to
        # finished / cancelled / error. Without this the Elapsed
        # column in the Queue tab kept ticking after the worker
        # had already returned, so the user never saw "this file
        # took 1m 22s" — they only saw a number that kept growing
        # while their attention had moved on.
        self.end_time: float | None = None
        self.paused: bool = False
        self.cancelled: bool = False
        # Phase 2a additions
        self.detected_language: str = ""
        self.language_probability: float = 0.0
        self.language: str | None = None
        # Phase 3a — primary key in core.history.HistoryDB.transcriptions
        self.history_id: int = 0
        # Resume-from-cancellation: when True the worker dispatches
        # ``resume_transcription`` instead of ``transcribe`` so the
        # partial checkpoint on disk is reused. Falls back to a fresh
        # transcribe automatically if the partial is stale (different
        # source mtime, changed model/config, etc.).
        self.resume: bool = False
        # Set by the app when this task was auto-spawned from a finished
        # download. Holds the originating VideoDownloadTask so the
        # Download row can mirror "transcribing" + progress and flip back
        # to "finished" when this task ends. Typed Any to keep core free
        # of an app-layer import.
        self.source_download: Any = None
        # Optional transcription time-slice (Transcribe-tab time range).
        # Wall-clock seconds into the source; both None = the whole file.
        # Fed to faster-whisper as clip_timestamps so only this span is
        # processed; segment timestamps stay on the original timeline.
        self.clip_start: float | None = None
        self.clip_end: float | None = None
