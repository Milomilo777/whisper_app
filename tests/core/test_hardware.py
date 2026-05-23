"""Tests for ``core.hardware.detect_device_for``."""
from __future__ import annotations

from core import hardware as _hw


def test_explicit_cpu_setting_wins() -> None:
    cfg = {"device": "cpu", "compute_type": "int8"}
    assert _hw.detect_device_for(cfg) == ("cpu", "int8")


def test_explicit_cuda_setting_wins() -> None:
    cfg = {"device": "cuda", "compute_type": "float16"}
    assert _hw.detect_device_for(cfg) == ("cuda", "float16")


def test_auto_falls_back_to_cpu_when_no_gpu(monkeypatch) -> None:
    # Make every CUDA probe raise so the fall-through to cpu fires.
    import sys
    # Remove any cached ctranslate2 / torch so the inline imports fail.
    for mod in list(sys.modules):
        if mod.startswith("ctranslate2") or mod.startswith("torch"):
            sys.modules.pop(mod)
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, *args, **kwargs):
        if name in ("ctranslate2", "torch"):
            raise ImportError(f"forced missing {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    cfg = {"device": "auto", "compute_type": "int8"}
    device, ct = _hw.detect_device_for(cfg)
    assert device == "cpu"
    assert ct == "int8"
