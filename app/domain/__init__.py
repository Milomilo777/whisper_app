"""Domain models shared by the Tk app and the download service.

Pure-Python data containers — no Tk, no I/O, no logging. The
transcription side of the basic edition still uses
:class:`core.task.TranscriptionTask` directly; this package exists
for the download-side :class:`VideoDownloadTask` and any future
non-transcribe model.
"""
from __future__ import annotations
