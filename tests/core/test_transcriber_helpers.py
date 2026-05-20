"""Tests for the pure helpers inside ``core.transcriber``.

The transcribe/load_model paths require a real Whisper model and live audio,
so they're covered by the Phase 2a smoke test (``test_transcribe_smoke.py``).
This file exercises only the side-effect-free pieces.
"""
from __future__ import annotations

import logging
import sys

import pytest


@pytest.fixture
def transcriber(monkeypatch):
    """Import core.transcriber with WhisperModel and torch stubbed.

    Importing for real loads faster-whisper and may trigger a model probe; we
    don't want that in unit tests. Stub before first import — but only if not
    already imported, to keep tests cheap when run together.
    """
    if "core.transcriber" not in sys.modules:
        import types as _t
        fake_fw = _t.ModuleType("faster_whisper")
        fake_fw.WhisperModel = object  # type: ignore[attr-defined]
        sys.modules.setdefault("faster_whisper", fake_fw)
    import core.transcriber as t
    return t


def test_fmt_zero(transcriber):
    assert transcriber.fmt(0) == "00:00:00"


def test_fmt_minutes_only(transcriber):
    assert transcriber.fmt(125.7) == "00:02:05"


def test_fmt_includes_hours(transcriber):
    assert transcriber.fmt(3661.999) == "01:01:01"


def test_log_writes_to_callback(transcriber):
    captured = []
    transcriber.log("hello", captured.append)
    assert captured == ["hello"]


def test_log_falls_back_to_logger(transcriber, caplog):
    with caplog.at_level(logging.INFO, logger="core.transcriber"):
        transcriber.log("fallback", None)
    assert any("fallback" in r.message for r in caplog.records)


def test_bundled_binary_returns_name_when_missing(transcriber, tmp_path, monkeypatch):
    import core.paths as paths_mod
    monkeypatch.setattr(paths_mod, "bin_dir", lambda: str(tmp_path / "no-such-dir"))
    assert transcriber.bundled_binary("ffmpeg") == "ffmpeg"


def test_bundled_binary_returns_full_path_when_present(transcriber, tmp_path, monkeypatch):
    import core.paths as paths_mod
    bin_dir_path = tmp_path / "bin"
    bin_dir_path.mkdir()
    import os
    exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    fake = bin_dir_path / exe_name
    fake.write_text("stub")
    monkeypatch.setattr(paths_mod, "bin_dir", lambda: str(bin_dir_path))
    result = transcriber.bundled_binary("ffmpeg")
    assert result == str(fake)


def test_is_model_ready_initially_false(transcriber, monkeypatch):
    monkeypatch.setattr(transcriber, "MODEL_READY", False)
    assert transcriber.is_model_ready() is False


def test_get_model_error_returns_module_state(transcriber, monkeypatch):
    monkeypatch.setattr(transcriber, "MODEL_ERROR", "something broke")
    assert transcriber.get_model_error() == "something broke"


def test_detect_device_respects_explicit_setting(transcriber, monkeypatch):
    monkeypatch.setattr(transcriber, "config", {"device": "cpu", "compute_type": "int8"})
    device, ct = transcriber.detect_device()
    assert device == "cpu"
    assert ct == "int8"


def test_detect_device_auto_falls_back_to_cpu(transcriber, monkeypatch):
    monkeypatch.setattr(transcriber, "config", {"device": "auto", "compute_type": "int8"})
    # Make both ctranslate2 and torch report no CUDA
    import sys as _sys
    fake_ct2 = type(_sys)("ctranslate2")
    fake_ct2.contains_cuda_device = lambda: False  # type: ignore[attr-defined]
    monkeypatch.setitem(_sys.modules, "ctranslate2", fake_ct2)
    fake_torch = type(_sys)("torch")
    class _Cuda:
        @staticmethod
        def is_available():
            return False
    fake_torch.cuda = _Cuda  # type: ignore[attr-defined]
    monkeypatch.setitem(_sys.modules, "torch", fake_torch)
    device, ct = transcriber.detect_device()
    assert device == "cpu"


def test_load_existing_model_missing_path_sets_error(transcriber, monkeypatch, tmp_path):
    monkeypatch.setattr(transcriber, "config", {
        "model_path": str(tmp_path / "no-such-model"),
        "device": "cpu",
        "compute_type": "int8",
    })
    statuses: list[str] = []
    ok = transcriber.load_existing_model(statuses.append)
    assert ok is False
    assert any("missing" in s.lower() for s in statuses)
    assert transcriber.get_model_error()


# ------------------------------------------------------------- atomic write --


def test_write_outputs_is_atomic_on_success(transcriber, tmp_path, monkeypatch):
    """Each output writer runs to <path>.part then os.replace's onto
    the final name. After a clean run only the final file should
    exist; no .part leftovers."""
    monkeypatch.setattr(transcriber, "config", {
        "output_formats": ["srt", "json"],
    })
    seg = [{"start": 0.0, "end": 1.0, "text": "hello"}]
    base = str(tmp_path / "out")
    written = transcriber._write_outputs(base, seg, str(tmp_path / "out.mp4"))

    import os
    assert sorted(os.path.basename(p) for p in written) == ["out.json", "out.srt"]
    for p in written:
        assert os.path.isfile(p)
        assert os.path.getsize(p) > 0
    # No .part files should be left behind.
    leftovers = [f for f in os.listdir(tmp_path) if f.endswith(".part")]
    assert leftovers == [], f"leftover .part files: {leftovers}"


def test_write_outputs_cleans_up_part_on_failure(transcriber, tmp_path, monkeypatch):
    """If the writer raises mid-write, the .part file must be unlinked
    and the final file must not exist or remain at its previous state."""
    monkeypatch.setattr(transcriber, "config", {"output_formats": ["srt"]})

    def _boom(*_a, **_kw):
        raise RuntimeError("writer exploded")

    # Replace the SRT writer with one that always raises.
    monkeypatch.setattr(transcriber, "get_writer", lambda _name: _boom)

    base = str(tmp_path / "out")
    with pytest.raises(RuntimeError, match="writer exploded"):
        transcriber._write_outputs(base, [], str(tmp_path / "out.mp4"))

    import os
    assert not os.path.exists(base + ".srt")
    assert not os.path.exists(base + ".srt.part")
