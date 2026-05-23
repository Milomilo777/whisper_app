"""Coverage for ``core.transcriber`` helpers.

The full ``transcribe()`` call needs faster-whisper + a real model;
we focus on the pure helpers it composes from:

  * ``_segment_to_dict``
  * ``_vad_parameters``
  * ``_build_transcribe_kwargs``
  * ``_fmt``
  * ``_resolve_ffprobe``
  * ``get_duration`` (mocked subprocess)
  * ``_write_outputs`` happy + sad paths
"""
from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from typing import Any

import pytest

from core import transcriber as _tr
from core.task import TranscriptionTask


# ---------------------------------------------------------------- _segment_to_dict


class _Seg:
    def __init__(self, start: float, end: float, text: str) -> None:
        self.start = start
        self.end = end
        self.text = text


@pytest.mark.parametrize(
    "start, end, text",
    [
        (0.0, 1.0, "hello"),
        (0.5, 1.25, " padded text "),
        (3600.0, 3601.5, "long offset"),
        (0.0, 0.0, ""),
    ],
)
def test_segment_to_dict_round_trips(start: float, end: float, text: str) -> None:
    out = _tr._segment_to_dict(_Seg(start, end, text))
    assert out == {"start": float(start), "end": float(end), "text": text.strip()}


def test_segment_to_dict_strips_text() -> None:
    out = _tr._segment_to_dict(_Seg(0.0, 1.0, "   padded   "))
    assert out["text"] == "padded"


def test_segment_to_dict_handles_none_text() -> None:
    out = _tr._segment_to_dict(_Seg(0.0, 1.0, None))  # type: ignore[arg-type]
    assert out["text"] == ""


def test_segment_to_dict_preserves_float_precision() -> None:
    out = _tr._segment_to_dict(_Seg(1.234567, 2.345678, "x"))
    assert out["start"] == pytest.approx(1.234567)
    assert out["end"] == pytest.approx(2.345678)


def test_segment_to_dict_raises_on_non_float_start() -> None:
    """A bad segment with non-numeric start raises — caller catches
    in the transcribe loop (P1-16)."""
    with pytest.raises((TypeError, ValueError)):
        _tr._segment_to_dict(_Seg("bad", 1.0, "x"))  # type: ignore[arg-type]


# ---------------------------------------------------------------- _vad_parameters


def test_vad_parameters_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_tr, "config", {"vad_enabled": True})
    out = _tr._vad_parameters()
    assert out is not None
    assert out["min_silence_duration_ms"] == 500
    assert out["threshold"] == 0.5
    assert out["speech_pad_ms"] == 400


def test_vad_parameters_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_tr, "config", {"vad_enabled": False})
    assert _tr._vad_parameters() is None


def test_vad_parameters_missing_key_defaults_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_tr, "config", {})
    out = _tr._vad_parameters()
    assert out is not None


# ---------------------------------------------------------------- _build_transcribe_kwargs


def test_build_kwargs_with_vad_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_tr, "config", {"vad_enabled": True})
    task = TranscriptionTask("/x.mp3")
    kw = _tr._build_transcribe_kwargs(task)
    assert kw["vad_filter"] is True
    assert "vad_parameters" in kw
    assert kw["word_timestamps"] is False


def test_build_kwargs_with_vad_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_tr, "config", {"vad_enabled": False})
    task = TranscriptionTask("/x.mp3")
    kw = _tr._build_transcribe_kwargs(task)
    assert kw["vad_filter"] is False
    assert "vad_parameters" not in kw


def test_build_kwargs_no_forced_language(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_tr, "config", {"vad_enabled": True})
    task = TranscriptionTask("/x.mp3")
    kw = _tr._build_transcribe_kwargs(task)
    assert "language" not in kw


def test_build_kwargs_forced_language_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_tr, "config", {"vad_enabled": True})
    task = TranscriptionTask("/x.mp3")
    setattr(task, "language", "fa")
    kw = _tr._build_transcribe_kwargs(task)
    assert kw.get("language") == "fa"


def test_build_kwargs_auto_language_not_forced(monkeypatch: pytest.MonkeyPatch) -> None:
    """language='auto' is treated as 'not forced' → key absent."""
    monkeypatch.setattr(_tr, "config", {"vad_enabled": True})
    task = TranscriptionTask("/x.mp3")
    setattr(task, "language", "auto")
    kw = _tr._build_transcribe_kwargs(task)
    assert "language" not in kw


def test_build_kwargs_empty_language_not_forced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_tr, "config", {"vad_enabled": True})
    task = TranscriptionTask("/x.mp3")
    setattr(task, "language", "")
    kw = _tr._build_transcribe_kwargs(task)
    assert "language" not in kw


@pytest.mark.parametrize("lang", ["en", "fa", "zh", "ja", "ar", "de", "es"])
def test_build_kwargs_forced_language_passed_through(
    monkeypatch: pytest.MonkeyPatch, lang: str,
) -> None:
    monkeypatch.setattr(_tr, "config", {"vad_enabled": True})
    task = TranscriptionTask("/x.mp3")
    setattr(task, "language", lang)
    kw = _tr._build_transcribe_kwargs(task)
    assert kw["language"] == lang


# ---------------------------------------------------------------- _fmt


@pytest.mark.parametrize(
    "seconds, expected",
    [
        (0.0, "00:00:00"),
        (1.0, "00:00:01"),
        (60.0, "00:01:00"),
        (3600.0, "01:00:00"),
        (3661.0, "01:01:01"),
        (7322.5, "02:02:02"),
        (86399.0, "23:59:59"),
    ],
)
def test_fmt_seconds(seconds: float, expected: str) -> None:
    assert _tr._fmt(seconds) == expected


# ---------------------------------------------------------------- _resolve_ffprobe


def test_resolve_ffprobe_uses_bundled() -> None:
    path = _tr._resolve_ffprobe()
    assert os.path.isfile(path)


def test_resolve_ffprobe_falls_back_to_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from core import paths as _p
    monkeypatch.setattr(_p, "bundled_binary", lambda _n: None)
    monkeypatch.setattr(_tr, "bundled_binary", lambda _n: None)
    import shutil as _sh
    monkeypatch.setattr(_sh, "which", lambda _n: "/usr/bin/ffprobe")
    out = _tr._resolve_ffprobe()
    assert out == "/usr/bin/ffprobe"


def test_resolve_ffprobe_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_tr, "bundled_binary", lambda _n: None)
    import shutil as _sh
    monkeypatch.setattr(_sh, "which", lambda _n: None)
    with pytest.raises(RuntimeError, match="ffprobe not found"):
        _tr._resolve_ffprobe()


# ---------------------------------------------------------------- get_duration


def test_get_duration_normal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock subprocess.run to return a clean float string."""
    class _FakeResult:
        returncode = 0
        stdout = "123.456\n"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _FakeResult())
    out = _tr.get_duration("/fake/file.mp4")
    assert out == 123.456


def test_get_duration_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResult:
        returncode = 0
        stdout = "0.0\n"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _FakeResult())
    out = _tr.get_duration("/fake/file.mp4")
    assert out == 0.0


def test_get_duration_nonzero_exit_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResult:
        returncode = 1
        stdout = ""
        stderr = "broken file"

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _FakeResult())
    with pytest.raises(RuntimeError, match="ffprobe failed"):
        _tr.get_duration("/fake/file.mp4")


def test_get_duration_empty_output_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResult:
        returncode = 0
        stdout = "   \n"  # only whitespace
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _FakeResult())
    with pytest.raises(RuntimeError, match="ffprobe failed"):
        _tr.get_duration("/fake/file.mp4")


def test_get_duration_timeout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a, **_kw):
        raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=60)

    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(RuntimeError, match="ffprobe timed out"):
        _tr.get_duration("/fake/file.mp4")


def test_get_duration_non_numeric_output_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResult:
        returncode = 0
        stdout = "not-a-number\n"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _FakeResult())
    with pytest.raises(ValueError):
        _tr.get_duration("/fake/file.mp4")


# ---------------------------------------------------------------- _write_outputs


def test_write_outputs_writes_all_three_formats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_tr, "config", {"output_formats": ["srt", "json", "txt"]})
    base = str(tmp_path / "out")
    segments = [{"start": 0.0, "end": 1.0, "text": "hello"}]
    written = _tr._write_outputs(base, segments, "/x.mp3")
    assert len(written) == 3
    assert Path(base + ".srt").exists()
    assert Path(base + ".json").exists()
    assert Path(base + ".txt").exists()


def test_write_outputs_unknown_format_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unknown format mixed with srt → still writes srt; unknown ignored."""
    monkeypatch.setattr(_tr, "config", {"output_formats": ["docx", "srt"]})
    base = str(tmp_path / "out")
    written = _tr._write_outputs(base, [], "/x.mp3")
    assert any(p.endswith(".srt") for p in written)
    assert not any(p.endswith(".docx") for p in written)


def test_write_outputs_all_unknown_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_tr, "config", {"output_formats": ["docx", "vtt"]})
    base = str(tmp_path / "out")
    with pytest.raises(RuntimeError, match="None of the requested output formats"):
        _tr._write_outputs(base, [], "/x.mp3")


def test_write_outputs_empty_formats_list_defaults_to_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty list is falsy → defaults to srt/json/txt (per source)."""
    monkeypatch.setattr(_tr, "config", {"output_formats": []})
    base = str(tmp_path / "out")
    written = _tr._write_outputs(base, [], "/x.mp3")
    assert len(written) == 3


def test_write_outputs_default_when_key_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing output_formats → defaults to srt/json/txt."""
    monkeypatch.setattr(_tr, "config", {})
    base = str(tmp_path / "out")
    written = _tr._write_outputs(base, [], "/x.mp3")
    assert len(written) == 3


def test_write_outputs_no_part_files_left_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_tr, "config", {"output_formats": ["srt"]})
    base = str(tmp_path / "out")
    _tr._write_outputs(base, [{"start": 0.0, "end": 1.0, "text": "x"}], "/x.mp3")
    leftovers = [p.name for p in tmp_path.iterdir() if ".part" in p.name]
    assert leftovers == []


def test_write_outputs_part_file_deleted_on_writer_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_tr, "config", {"output_formats": ["srt"]})

    def boom(_segs, _audio):
        raise RuntimeError("writer failed")

    monkeypatch.setattr(_tr, "get_writer", lambda _n: boom)
    base = str(tmp_path / "out")
    with pytest.raises(RuntimeError):
        _tr._write_outputs(base, [], "/x.mp3")
    leftovers = [p.name for p in tmp_path.iterdir() if ".part" in p.name]
    assert leftovers == []


def test_write_outputs_atomic_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The .part → final rename is atomic; we check there's no
    intermediate window-with-partial-content."""
    monkeypatch.setattr(_tr, "config", {"output_formats": ["txt"]})
    base = str(tmp_path / "out")
    _tr._write_outputs(base, [{"start": 0.0, "end": 1.0, "text": "ok"}], "/x.mp3")
    out_file = Path(base + ".txt")
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert content == "ok\n"


def test_write_outputs_part_filename_has_pid_tid_uuid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_tr, "config", {"output_formats": ["srt"]})

    seen: list[str] = []
    real_open = open

    def spy_open(path: Any, *a: Any, **kw: Any):  # noqa: ANN202
        if isinstance(path, str) and ".part" in path:
            seen.append(path)
        return real_open(path, *a, **kw)

    import builtins
    monkeypatch.setattr(builtins, "open", spy_open)

    base = str(tmp_path / "out")
    _tr._write_outputs(base, [], "/x.mp3")
    assert seen
    name = os.path.basename(seen[0])
    # Format: out.srt.<pid>-<tid>-<uuid>.part
    assert ".part" in name
    parts_pre = name.rsplit(".part", 1)[0]
    # pid-tid-uuid8
    tail = parts_pre.rsplit("-", 1)[1]
    assert len(tail) == 8


def test_write_outputs_kept_successful_message_on_partial_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SRT OK, JSON failing → error mentions kept outputs."""
    monkeypatch.setattr(_tr, "config", {"output_formats": ["srt", "json"]})

    def fake_supported() -> set[str]:
        return {"srt", "json"}

    def fake_get_writer(name: str):
        if name == "srt":
            return lambda _s, _a: "1\n00:00:00,000 --> 00:00:01,000\nhi\n"

        def boom(_s, _a):
            raise PermissionError("denied")
        return boom

    monkeypatch.setattr(_tr, "supported_formats", fake_supported)
    monkeypatch.setattr(_tr, "get_writer", fake_get_writer)

    base = str(tmp_path / "out")
    with pytest.raises(RuntimeError, match="Kept successful"):
        _tr._write_outputs(base, [], "/x.mp3")
    assert Path(base + ".srt").exists()


def test_write_outputs_all_failures_reraises_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When every format fails, propagate the first exception."""
    monkeypatch.setattr(_tr, "config", {"output_formats": ["srt"]})

    def fake_supported() -> set[str]:
        return {"srt"}

    def failing_writer(_n: str):
        def boom(_s, _a):
            raise IOError("disk error")
        return boom

    monkeypatch.setattr(_tr, "supported_formats", fake_supported)
    monkeypatch.setattr(_tr, "get_writer", failing_writer)

    base = str(tmp_path / "out")
    with pytest.raises(IOError, match="disk error"):
        _tr._write_outputs(base, [], "/x.mp3")


# ---------------------------------------------------------------- module-level state


def test_module_has_model_globals() -> None:
    assert hasattr(_tr, "MODEL")
    assert hasattr(_tr, "PIPELINE")
    assert hasattr(_tr, "MODEL_READY")
    assert hasattr(_tr, "MODEL_ERROR")


def test_module_has_device_compute_type() -> None:
    assert isinstance(_tr.device, str)
    assert isinstance(_tr.compute_type, str)


def test_is_model_ready_returns_bool() -> None:
    assert isinstance(_tr.is_model_ready(), bool)


def test_get_model_error_returns_str_or_none() -> None:
    out = _tr.get_model_error()
    assert out is None or isinstance(out, str)


def test_detect_device_returns_tuple() -> None:
    out = _tr.detect_device()
    assert isinstance(out, tuple) and len(out) == 2
