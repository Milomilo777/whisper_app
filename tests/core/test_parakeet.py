"""Tests for the Parakeet sherpa-onnx backend adapter."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from core.backends import parakeet as pk
from core.backends import get_backend


# ---------- availability -------------------------------------------------------


def test_runtime_available_false_when_module_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "sherpa_onnx", None)
    assert pk.runtime_available() is False


def test_is_model_present_false_with_no_files(tmp_path):
    assert pk.is_model_present(tmp_path) is False


def test_is_model_present_true_when_all_four_files_exist(tmp_path):
    for name in pk.REQUIRED_FILES:
        (tmp_path / name).write_bytes(b"x")
    assert pk.is_model_present(tmp_path) is True


def test_is_model_present_false_when_one_file_missing(tmp_path):
    for name in pk.REQUIRED_FILES[:-1]:
        (tmp_path / name).write_bytes(b"x")
    # tokens.txt absent
    assert pk.is_model_present(tmp_path) is False


def test_availability_reason_lists_missing_files(tmp_path, monkeypatch):
    monkeypatch.setattr(pk, "runtime_available", lambda: True)
    monkeypatch.setattr(pk, "model_dir", lambda: tmp_path)
    # Only one file present.
    (tmp_path / "encoder.onnx").write_bytes(b"x")
    msg = pk.availability_reason()
    assert "decoder.onnx" in msg
    assert "joiner.onnx" in msg
    assert "tokens.txt" in msg


# ---------- dispatcher ---------------------------------------------------------


def test_get_backend_parakeet_returns_parakeet_instance():
    # Re-import inside the test so we use the same module instance the
    # dispatcher is currently holding. The test_backends fixture
    # nukes core.backends.* from sys.modules, so a module-level
    # `from core.backends import parakeet as pk` may bind to a stale
    # class object that fails isinstance against the dispatcher's
    # freshly-imported one.
    from core.backends import get_backend as _get
    from core.backends.parakeet import ParakeetBackend as _PB
    inst = _get("parakeet")
    assert isinstance(inst, _PB)
    assert inst.name == "parakeet"


def test_get_backend_unknown_name_still_falls_back():
    from core.backends import get_backend as _get
    inst = _get("does-not-exist")
    # Unknown names fall through to faster_whisper per dispatcher contract.
    assert inst.__class__.__name__ != "ParakeetBackend"


# ---------- load failure paths -------------------------------------------------


def test_backend_load_fails_cleanly_when_runtime_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(pk, "runtime_available", lambda: False)
    backend = pk.ParakeetBackend()
    ok = backend.load()
    assert ok is False
    assert backend.is_ready() is False
    err = backend.get_error()
    assert err is not None and "sherpa" in err.lower()


def test_backend_load_fails_when_model_files_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(pk, "runtime_available", lambda: True)
    monkeypatch.setattr(pk, "model_dir", lambda: tmp_path)
    backend = pk.ParakeetBackend()
    ok = backend.load()
    assert ok is False
    err = backend.get_error()
    assert err is not None and "model" in err.lower()


# ---------- token → segment grouping ------------------------------------------


def test_tokens_to_segments_handles_empty_text():
    assert pk._tokens_to_segments("", [], [], duration=10.0) == []


def test_tokens_to_segments_falls_back_to_single_segment_with_no_timestamps():
    out = pk._tokens_to_segments("hello world", [], [], duration=5.0)
    assert len(out) == 1
    assert out[0]["text"] == "hello world"
    assert out[0]["start"] == 0.0
    assert out[0]["end"] == 5.0


def test_tokens_to_segments_groups_by_gap():
    tokens = ["a", "b", "c", "d"]
    # Two clusters: first at t=0-0.5, second at t=5.0-5.5
    timestamps = [0.0, 0.2, 5.0, 5.2]
    out = pk._tokens_to_segments("abcd", tokens, timestamps, duration=10.0,
                                  max_gap_seconds=0.8)
    assert len(out) == 2
    assert out[0]["text"] == "ab"
    assert out[1]["text"] == "cd"
    assert out[0]["start"] == 0.0
    assert out[0]["end"] == pytest.approx(0.2)
    assert out[1]["start"] == 5.0
    assert out[1]["end"] == pytest.approx(5.2)


def test_tokens_to_segments_keeps_single_cluster_together():
    tokens = ["w", "x", "y", "z"]
    timestamps = [0.0, 0.3, 0.6, 0.9]  # no gap > 0.8
    out = pk._tokens_to_segments("wxyz", tokens, timestamps, duration=5.0,
                                  max_gap_seconds=0.8)
    assert len(out) == 1
    assert out[0]["text"] == "wxyz"
