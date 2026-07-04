"""oTranscribe ``.otr`` writer.

Delegates the actual serialisation to ``core.integrations.otranscribe``, the
single source of truth for the .otr format (also used by the app's
"Export -> oTranscribe" menu action and the download pipeline's .otr
sidecar export).
"""
from __future__ import annotations

from ..integrations.otranscribe import segments_to_otr


def write(segments: list[dict], audio_path: str = "") -> str:
    return segments_to_otr(segments, media_filename=audio_path)
