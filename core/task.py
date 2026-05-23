"""``TranscriptionTask`` — a single file's worth of work.

The Tk app keeps a ``list[TranscriptionTask]`` as its in-memory queue
and the worker mirrors the same shape via the JSON IPC.
"""
from __future__ import annotations


class TranscriptionTask:
    """One file = one task. Fields are mutated as the task progresses."""

    def __init__(self, file_path: str) -> None:
        self.file_path: str = file_path
        # Lifecycle: waiting → running → finished / cancelled / error.
        self.status: str = "waiting"
        self.progress: int = 0
        self.start_time: float | None = None
        # Frozen wall-clock for terminal tasks. None until the task
        # leaves the running state, then immutable so the UI's
        # "Elapsed" column stops ticking the moment the worker
        # returns.
        self.end_time: float | None = None
        self.cancelled: bool = False
        # Detected language (faster-whisper info.language) + its
        # probability, surfaced once info is available.
        self.detected_language: str = ""
        self.language_probability: float = 0.0
        # Last error message — set when the worker emits an `error`
        # event for this task; shown in the queue row's tooltip.
        self.error_message: str = ""
