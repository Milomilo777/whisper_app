from __future__ import annotations


class TranscriptionTask:
    def __init__(self, file_path: str) -> None:
        self.file_path: str = file_path
        self.status: str = "waiting"
        self.progress: int = 0
        self.start_time: float | None = None
        self.paused: bool = False
        self.cancelled: bool = False
        # Phase 2a additions
        self.detected_language: str = ""
        self.language_probability: float = 0.0
        self.language: str | None = None
        # Phase 3a — primary key in core.history.HistoryDB.transcriptions
        self.history_id: int = 0
