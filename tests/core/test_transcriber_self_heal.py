"""Tests for the R3 self-healing CUDA->CPU model load in ``core.transcriber``.

When ``WhisperModel(device="cuda", ...)`` raises (the classic missing
cuDNN/cuBLAS runtime), the load must NOT hard-fail with a bogus re-download
prompt — it should log the reason, retry with ("cpu","int8"), flip the
downgrade flag, and report the effective device. We stub WhisperModel so no
real model/CUDA stack is needed.
"""
from __future__ import annotations

import sys
import types

import pytest


@pytest.fixture
def transcriber(monkeypatch):
    """Import core.transcriber with WhisperModel stubbed."""
    if "core.transcriber" not in sys.modules:
        fake_fw = types.ModuleType("faster_whisper")
        fake_fw.WhisperModel = object  # type: ignore[attr-defined]
        sys.modules.setdefault("faster_whisper", fake_fw)
    import core.transcriber as t
    return t


class _FakeCt2:
    """Stand-in for the underlying CTranslate2 object exposing device info."""

    def __init__(self, device: str, compute_type: str) -> None:
        self.device = device
        self.compute_type = compute_type


class _FakeWhisperModel:
    """WhisperModel stub: raises on cuda, succeeds on cpu."""

    def __init__(self, model_path, device="cpu", compute_type="int8"):
        if device == "cuda":
            raise RuntimeError(
                "Library cudnn_ops_infer64_8.dll is not found or cannot be loaded"
            )
        self.model = _FakeCt2(device, compute_type)


def test_self_heal_downgrades_to_cpu_on_cuda_failure(transcriber, monkeypatch):
    monkeypatch.setattr(transcriber, "WhisperModel", _FakeWhisperModel)
    msgs: list[str] = []
    model = transcriber._load_whisper_model_self_healing(
        "/fake/model", "cuda", "float16", msgs.append
    )
    assert model is not None
    eff = transcriber.get_effective_device()
    assert eff.downgraded is True
    assert eff.device == "cpu"
    assert eff.compute_type == "int8"
    assert eff.requested_device == "cuda"
    # The status callback should mention the CPU fallback.
    assert any("CPU" in m for m in msgs)


def test_self_heal_no_downgrade_when_cuda_loads(transcriber, monkeypatch):
    class _OkModel:
        def __init__(self, model_path, device="cpu", compute_type="int8"):
            self.model = _FakeCt2(device, compute_type)

    monkeypatch.setattr(transcriber, "WhisperModel", _OkModel)
    model = transcriber._load_whisper_model_self_healing(
        "/fake/model", "cuda", "float16", None
    )
    assert model is not None
    eff = transcriber.get_effective_device()
    assert eff.downgraded is False
    assert eff.device == "cuda"
    assert eff.compute_type == "float16"


def test_cpu_request_failure_still_raises(transcriber, monkeypatch):
    """A CPU load that fails has nothing to fall back to — it must raise."""
    class _BoomModel:
        def __init__(self, model_path, device="cpu", compute_type="int8"):
            raise RuntimeError("cpu load broke")

    monkeypatch.setattr(transcriber, "WhisperModel", _BoomModel)
    with pytest.raises(RuntimeError, match="cpu load broke"):
        transcriber._load_whisper_model_self_healing(
            "/fake/model", "cpu", "int8", None
        )


def test_load_existing_model_self_heals_and_stays_ready(
    transcriber, monkeypatch, tmp_path
):
    """The full load path: requested cuda, falls back to cpu, MODEL_READY."""
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    monkeypatch.setattr(transcriber, "WhisperModel", _FakeWhisperModel)
    monkeypatch.setattr(transcriber, "config", {
        "transcribe_backend": "faster_whisper",
        "model_path": str(model_dir),
    })
    monkeypatch.setattr(transcriber, "device", "cuda")
    monkeypatch.setattr(transcriber, "compute_type", "float16")
    # No batched pipeline wrap on the downgraded CPU model.
    monkeypatch.setattr(transcriber, "BatchedInferencePipeline", None)

    ok = transcriber.load_existing_model(lambda m: None)
    assert ok is True
    assert transcriber.MODEL_READY is True
    eff = transcriber.get_effective_device()
    assert eff.downgraded is True
    assert eff.device == "cpu"
    # The module global `device` must be updated to the effective device so
    # _wrap_for_batched does not try to wrap a CPU model in a CUDA pipeline.
    assert transcriber.device == "cpu"


def test_get_effective_device_capture_is_getattr_guarded(transcriber, monkeypatch):
    """A WhisperModel whose .model lacks device attrs falls back to requested."""
    class _NoAttrModel:
        def __init__(self, model_path, device="cpu", compute_type="int8"):
            self.model = object()  # no .device / .compute_type

    monkeypatch.setattr(transcriber, "WhisperModel", _NoAttrModel)
    transcriber._load_whisper_model_self_healing("/fake", "cpu", "int8", None)
    eff = transcriber.get_effective_device()
    assert eff.device == "cpu"
    assert eff.compute_type == "int8"
