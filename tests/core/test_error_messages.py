"""Tests for ``core.error_messages.friendly_error``."""
from __future__ import annotations

import pytest

from core import error_messages as _em


def test_unknown_falls_back_to_str() -> None:
    msg, hint = _em.friendly_error(ValueError("totally unique mystery"))
    assert "totally unique mystery" in msg
    assert hint == ""


def test_ffmpeg_missing_mapped() -> None:
    err = FileNotFoundError("ffmpeg.exe was not found anywhere")
    msg, hint = _em.friendly_error(err)
    assert "ffmpeg" in msg.lower() or "ffprobe" in msg.lower()
    assert "bin/" in hint or "reinstall" in hint.lower()


def test_silero_vad_missing_mapped() -> None:
    err = FileNotFoundError("silero_vad_v6.onnx not found")
    msg, hint = _em.friendly_error(err)
    assert "vad" in msg.lower()
    assert hint != ""


def test_cuda_oom_mapped() -> None:
    err = RuntimeError("CUDA out of memory. Tried to allocate 3.04 GiB")
    msg, hint = _em.friendly_error(err)
    assert "gpu" in msg.lower() or "memory" in msg.lower()
    assert "cpu" in hint.lower() or "close" in hint.lower()


def test_permission_error_srt_mapped() -> None:
    err = PermissionError("[Errno 13] Permission denied: 'foo.srt'")
    msg, hint = _em.friendly_error(err)
    assert "open" in msg.lower() or "permission" in msg.lower()


def test_connection_error_mapped() -> None:
    class CE(Exception):
        pass
    err = CE("ConnectionError: Max retries exceeded")
    # The pattern matches the exception class name OR the message text;
    # exception isn't requests.ConnectionError so use the message form.
    err = ConnectionError("network unreachable")
    msg, hint = _em.friendly_error(err)
    assert "internet" in hint.lower() or "connection" in msg.lower()


def test_ffprobe_failed_mapped() -> None:
    err = RuntimeError("ffprobe failed (exit=1) for file.mp4: bad header")
    msg, hint = _em.friendly_error(err)
    assert "ffmpeg" in msg.lower() or "ffprobe" in msg.lower()


def test_file_path_appended_to_fallback() -> None:
    err = ValueError("widget broke")
    msg, _hint = _em.friendly_error(err, file_path="/tmp/something.mp4")
    assert "something.mp4" in msg


def test_all_patterns_nonempty() -> None:
    pats = list(_em.all_patterns())
    assert len(pats) > 5
    assert all(isinstance(p, str) and p for p in pats)
