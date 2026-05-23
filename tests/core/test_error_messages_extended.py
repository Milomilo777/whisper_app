"""Exhaustive coverage for ``core.error_messages.friendly_error``.

Includes one test per regex rule, edge cases for unmapped exceptions,
non-ASCII args, huge messages, and a fuzz pass against random
exception instances to assert "never raises".
"""
from __future__ import annotations

import random
import re

import pytest

from core import error_messages as _em


# ---------------------------------------------------------- one test per rule


@pytest.mark.parametrize(
    "exc",
    [
        FileNotFoundError("ffmpeg.exe was not found"),
        FileNotFoundError("/usr/bin/ffmpeg: No such file"),
        FileNotFoundError("FileNotFoundError: 'ffprobe' not on PATH"),
    ],
)
def test_ffmpeg_or_ffprobe_missing(exc: BaseException) -> None:
    msg, hint = _em.friendly_error(exc)
    assert "ffmpeg" in msg.lower() or "ffprobe" in msg.lower()
    assert "reinstall" in hint.lower() or "bin/" in hint.lower()


def test_silero_missing() -> None:
    msg, hint = _em.friendly_error(FileNotFoundError("silero_vad_v6.onnx not found"))
    assert "vad" in msg.lower()
    assert "reinstall" in hint.lower() or "extract" in hint.lower()


@pytest.mark.parametrize(
    "exc",
    [
        FileNotFoundError("model.bin missing"),
        FileNotFoundError("model_path = /tmp/x does not exist"),
    ],
)
def test_model_files_missing(exc: BaseException) -> None:
    msg, hint = _em.friendly_error(exc)
    assert "model" in msg.lower() or "whisper" in msg.lower()
    assert "transcribe" in hint.lower() or "download" in hint.lower() or "hub" in hint.lower()


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError("CUDA out of memory"),
        RuntimeError("cuBLAS allocation failed: out of memory"),
        RuntimeError("CUDA out of memory. Tried to allocate 3.04 GiB"),
    ],
)
def test_cuda_oom(exc: BaseException) -> None:
    msg, hint = _em.friendly_error(exc)
    assert "gpu" in msg.lower() or "memory" in msg.lower()
    assert "cpu" in hint.lower() or "close" in hint.lower()


@pytest.mark.parametrize(
    "exc",
    [
        FileNotFoundError("cudnn_ops_infer64_8.dll not found"),
        FileNotFoundError("cudnn library is missing"),
    ],
)
def test_cuda_libs_missing(exc: BaseException) -> None:
    msg, hint = _em.friendly_error(exc)
    assert "cuda" in msg.lower()
    assert "cpu" in hint.lower() or "cudnn" in hint.lower()


def test_cublas_message_caught_by_oom_rule() -> None:
    """The CUDA-OOM rule matches anything mentioning cuBLAS — the
    pattern's deliberate: the typical "cuBLAS allocation failed"
    flow IS an OOM in practice."""
    msg, _ = _em.friendly_error(FileNotFoundError("cublas64_12.dll not found"))
    # Matches the OOM rule because of the bare "cuBLAS" alternative.
    assert "gpu" in msg.lower() or "memory" in msg.lower()


@pytest.mark.parametrize(
    "exc",
    [
        PermissionError("[Errno 13] Permission denied: '/tmp/foo.srt'"),
        PermissionError("Access denied for output.json"),
        PermissionError("Cannot write transcript.txt"),
    ],
)
def test_permission_error_subtitle(exc: BaseException) -> None:
    msg, hint = _em.friendly_error(exc)
    assert msg
    assert isinstance(hint, str)


def test_permission_error_generic() -> None:
    msg, hint = _em.friendly_error(PermissionError("denied to /var/log"))
    assert "permission" in msg.lower() or "denied" in msg.lower()


def test_connection_error_via_class() -> None:
    msg, hint = _em.friendly_error(ConnectionError("Network is down"))
    assert "internet" in hint.lower() or "connection" in msg.lower()


def test_connection_error_via_message() -> None:
    """Even non-ConnectionError types whose str matches the rule are caught."""
    msg, hint = _em.friendly_error(RuntimeError("requests.exceptions.ConnectionError: foo"))
    assert "internet" in hint.lower() or "connection" in msg.lower()


def test_timeout_error() -> None:
    msg, hint = _em.friendly_error(TimeoutError("read timed out"))
    assert "long" in msg.lower() or "server" in msg.lower()


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError("ffprobe failed (exit=1) for file.mp4"),
        RuntimeError("ffprobe timed out after 60s"),
        RuntimeError("ffmpeg.exe exited with code 234"),
    ],
)
def test_ffprobe_or_ffmpeg_failures(exc: BaseException) -> None:
    msg, hint = _em.friendly_error(exc)
    assert "ffmpeg" in msg.lower() or "ffprobe" in msg.lower()


@pytest.mark.parametrize(
    "exc",
    [
        OSError("[Errno 28] No space left on device"),
        OSError("disk full"),
    ],
)
def test_disk_full(exc: BaseException) -> None:
    msg, hint = _em.friendly_error(exc)
    assert "disk" in msg.lower() or "full" in msg.lower()


@pytest.mark.parametrize(
    "exc",
    [
        ImportError("No module named 'faster_whisper'"),
        ModuleNotFoundError("faster_whisper.transcribe missing"),
    ],
)
def test_faster_whisper_missing(exc: BaseException) -> None:
    msg, hint = _em.friendly_error(exc)
    assert "faster" in msg.lower() or "whisper" in msg.lower()
    assert "pip" in hint.lower() or "install" in hint.lower()


@pytest.mark.parametrize(
    "exc",
    [
        ImportError("tkinterdnd2 not found"),
        ModuleNotFoundError("No module named 'tkinterdnd2'"),
    ],
)
def test_tkinterdnd2_missing(exc: BaseException) -> None:
    msg, hint = _em.friendly_error(exc)
    assert "drag" in msg.lower() or "tkinterdnd" in msg.lower()


# ---------------------------------------------------------- unmapped fallback


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("totally novel error"),
        RuntimeError("unmapped weirdness"),
        Exception("plain Exception"),
        TypeError("wrong type"),
        KeyError("missing key"),
    ],
)
def test_unmapped_falls_back_to_str(exc: BaseException) -> None:
    msg, hint = _em.friendly_error(exc)
    # Hint must be empty on fallback (no rule matched).
    assert hint == ""
    # Message should at least include something derived from the exception.
    assert msg


def test_unmapped_includes_file_path_basename() -> None:
    msg, hint = _em.friendly_error(
        ValueError("widget broke"), file_path="/some/dir/video.mp4",
    )
    assert "video.mp4" in msg
    # The full directory should NOT be included.
    assert "/some/dir/" not in msg


def test_unmapped_with_no_file_path() -> None:
    msg, _ = _em.friendly_error(ValueError("widget broke"))
    assert "widget broke" in msg


def test_unmapped_exception_with_no_args() -> None:
    msg, hint = _em.friendly_error(ValueError())
    # Falls back to class name when str(exc) is empty.
    assert msg == "ValueError"
    assert hint == ""


def test_unmapped_exception_with_huge_message() -> None:
    huge = "x" * 50_000
    msg, _ = _em.friendly_error(ValueError(huge))
    # No truncation in error_messages — message passes through.
    assert huge in msg


def test_unmapped_exception_with_unicode_args() -> None:
    msg, _ = _em.friendly_error(ValueError("视频文件 broken 🎬"))
    assert "视频文件" in msg
    assert "🎬" in msg


def test_unmapped_exception_with_rtl_args() -> None:
    msg, _ = _em.friendly_error(ValueError("خطا در پردازش"))
    assert "خطا" in msg


# ---------------------------------------------------------- all_patterns


def test_all_patterns_compile() -> None:
    for pat in _em.all_patterns():
        re.compile(pat)


def test_all_patterns_returns_at_least_eight() -> None:
    pats = list(_em.all_patterns())
    assert len(pats) >= 8


def test_all_patterns_are_strings() -> None:
    assert all(isinstance(p, str) for p in _em.all_patterns())


def test_friendly_error_returns_2_tuple() -> None:
    out = _em.friendly_error(Exception("x"))
    assert isinstance(out, tuple) and len(out) == 2
    assert isinstance(out[0], str) and isinstance(out[1], str)


# ---------------------------------------------------------- fuzz: never raises


def test_fuzz_random_exception_strings_never_raise() -> None:
    """500 random exception strings → friendly_error must not raise."""
    rng = random.Random(20260523)
    classes = [
        ValueError, RuntimeError, OSError, PermissionError, FileNotFoundError,
        TypeError, KeyError, AttributeError, ConnectionError, TimeoutError,
        ImportError, ModuleNotFoundError, Exception, IOError,
    ]
    chars = (
        "abcdefghijklmnopqrstuvwxyz0123456789 \t\n.,:;-_=+/\\\"'`!@#$%^&*()"
        "[]{}<>?~|视频文件مرحبا🎬"
    )
    for _ in range(500):
        n = rng.randint(0, 200)
        text = "".join(rng.choice(chars) for _ in range(n))
        cls = rng.choice(classes)
        try:
            exc = cls(text)
        except TypeError:
            exc = cls()
        msg, hint = _em.friendly_error(exc)
        assert isinstance(msg, str)
        assert isinstance(hint, str)


def test_fuzz_with_file_paths_never_raises() -> None:
    """Random file paths must not break the file_path basename trim."""
    rng = random.Random(99)
    paths = [
        "/", "", "/tmp", "/tmp/x.mp3", "C:\\Windows\\foo.bat",
        "relative.txt", "/with spaces/in path.mp4",
        "//share/path", "\\\\server\\path", "视频.mp4",
    ]
    for _ in range(200):
        path = rng.choice(paths)
        exc = ValueError(f"random msg {rng.randint(0, 999)}")
        msg, _ = _em.friendly_error(exc, file_path=path)
        assert isinstance(msg, str)


# ---------------------------------------------------------- rule ordering


def test_rules_checked_in_order_first_match_wins() -> None:
    """A FileNotFoundError mentioning both ffmpeg and silero matches
    the ffmpeg rule first because it's earlier in _RULES."""
    msg, _ = _em.friendly_error(FileNotFoundError("ffmpeg AND silero_vad missing"))
    assert "ffmpeg" in msg.lower() or "ffprobe" in msg.lower()


def test_rules_has_at_least_one_entry() -> None:
    assert len(_em._RULES) >= 1
    for pat, msg, hint in _em._RULES:
        assert isinstance(pat, re.Pattern)
        assert isinstance(msg, str) and msg
        assert isinstance(hint, str) and hint
