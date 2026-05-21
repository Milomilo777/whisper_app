"""Backend interface for transcription engines."""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class LanguageInfo:
    """Detected-language metadata returned by every backend.

    Mirrors the relevant ``faster_whisper`` ``info`` fields without
    forcing the rest of the pipeline to import faster_whisper just
    to look at language results.
    """
    language: str = ""
    probability: float = 0.0


class Backend(ABC):
    """Abstract transcription backend.

    Implementations track their own model state (whether the model
    is loaded, what device it's running on, etc.). The transcriber
    dispatcher creates one backend per worker process at module
    import time and keeps it alive for the worker's lifetime.
    """

    name: str = ""

    @abstractmethod
    def load(
        self,
        status_cb: Callable[[str], None] | None = None,
        progress_cb: Callable[[dict[str, Any]], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> bool:
        """Load the model into memory. Returns True on success."""

    @abstractmethod
    def is_ready(self) -> bool:
        """True iff the model is loaded and ready to transcribe."""

    @abstractmethod
    def transcribe_to_segments(
        self,
        audio_path: str,
        *,
        language: str | None = None,
        want_words: bool = False,
        vad_parameters: dict[str, Any] | None = None,
        initial_prompt: str | None = None,
        hotwords: str | None = None,
        batch_size: int = 16,
        progress_cb: Callable[[int], None] | None = None,
        log_cb: Callable[[str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
        paused: Callable[[], bool] | None = None,
        duration: float = 0.0,
    ) -> tuple[list[dict[str, Any]], LanguageInfo]:
        """Transcribe one audio file.

        Returns a tuple of (segments_data, language_info), where each
        segment dict has at minimum ``start``, ``end``, ``text`` and,
        when ``want_words`` is True, a ``words`` list of
        ``{start, end, word, probability}`` dicts.
        """

    def unload(self) -> None:
        """Release the model. Default impl is a no-op for backends
        that rely on Python GC."""
        return None

    def get_error(self) -> str | None:
        """Optional last-error message exposed to the UI."""
        return None
