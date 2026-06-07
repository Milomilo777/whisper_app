"""Tests for the R3 CUDA usability gate in ``core.hardware``.

``ctranslate2.contains_cuda_device()`` only proves a driver + GPU exist; it
does NOT verify the cuDNN/cuBLAS runtime libraries load. When they don't, a
CUDA model construction hard-fails. ``cuda_load_ok()`` + the probe gating make
the autodetect refuse CUDA in that state. These tests monkeypatch ctranslate2
and the DLL-loadable probe so no real CUDA stack is needed.
"""
from __future__ import annotations

import sys
import types

import pytest

from core import hardware as hw


def _fake_ct2(monkeypatch, *, has_device: bool):
    fake = types.ModuleType("ctranslate2")
    fake.contains_cuda_device = lambda: has_device  # type: ignore[attr-defined]
    fake.get_supported_compute_types = lambda dev: {"float16", "int8_float16"}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ctranslate2", fake)
    return fake


# ---------- cuda_load_ok --------------------------------------------------------


def test_cuda_load_ok_false_when_no_device(monkeypatch):
    _fake_ct2(monkeypatch, has_device=False)
    monkeypatch.setattr(hw, "_cuda_runtime_dlls_loadable", lambda: True)
    assert hw.cuda_load_ok() is False


def test_cuda_load_ok_false_when_runtime_dlls_broken(monkeypatch):
    """Device present but cuDNN/cuBLAS not loadable => not ready."""
    _fake_ct2(monkeypatch, has_device=True)
    monkeypatch.setattr(hw, "_cuda_runtime_dlls_loadable", lambda: False)
    assert hw.cuda_load_ok() is False


def test_cuda_load_ok_true_when_device_and_runtime_ok(monkeypatch):
    _fake_ct2(monkeypatch, has_device=True)
    monkeypatch.setattr(hw, "_cuda_runtime_dlls_loadable", lambda: True)
    assert hw.cuda_load_ok() is True


def test_cuda_load_ok_never_raises_when_ct2_absent(monkeypatch):
    monkeypatch.setitem(sys.modules, "ctranslate2", None)
    # Importing a None module raises ImportError inside the helper; it must be
    # swallowed and reported as not-ok.
    assert hw.cuda_load_ok() is False


# ---------- _probe_cuda gating --------------------------------------------------


def test_probe_cuda_returns_empty_when_runtime_dlls_broken(monkeypatch):
    _fake_ct2(monkeypatch, has_device=True)
    monkeypatch.setattr(hw, "_cuda_runtime_dlls_loadable", lambda: False)
    assert hw._probe_cuda() == []


def test_probe_cuda_returns_tiers_when_runtime_ok(monkeypatch):
    _fake_ct2(monkeypatch, has_device=True)
    monkeypatch.setattr(hw, "_cuda_runtime_dlls_loadable", lambda: True)
    monkeypatch.setattr(hw, "_gpu_name", lambda: "RTX 4090")
    tiers = hw._probe_cuda()
    assert tiers and all(t.device == "cuda" for t in tiers)
    assert tiers[0].slug == "cuda_float16"


def test_probe_tiers_falls_back_to_cpu_on_broken_cuda(monkeypatch):
    """End-to-end: a broken-DLL host yields only the CPU tier."""
    _fake_ct2(monkeypatch, has_device=True)
    monkeypatch.setattr(hw, "_cuda_runtime_dlls_loadable", lambda: False)
    monkeypatch.setattr(hw, "_probe_qnn_npu", lambda: [])
    monkeypatch.setattr(hw, "_probe_openvino", lambda: [])
    monkeypatch.setattr(hw, "_probe_directml", lambda: [])
    tiers = hw.probe_tiers()
    assert [t.slug for t in tiers] == ["cpu_int8"]


# ---------- detect_device_for gating -------------------------------------------


def test_detect_device_for_skips_cuda_when_runtime_broken(monkeypatch):
    _fake_ct2(monkeypatch, has_device=True)
    monkeypatch.setattr(hw, "_cuda_runtime_dlls_loadable", lambda: False)
    monkeypatch.setattr(hw, "device_choice_from_hardware_file", lambda: None)
    # Block the torch legacy fallback so we land on cpu deterministically.
    monkeypatch.setitem(sys.modules, "torch", None)
    dev, ct = hw.detect_device_for({"device": "auto", "compute_type": "int8"})
    assert dev == "cpu"


def test_detect_device_for_uses_cuda_when_runtime_ok(monkeypatch):
    _fake_ct2(monkeypatch, has_device=True)
    monkeypatch.setattr(hw, "_cuda_runtime_dlls_loadable", lambda: True)
    monkeypatch.setattr(hw, "device_choice_from_hardware_file", lambda: None)
    dev, ct = hw.detect_device_for({"device": "auto", "compute_type": "int8"})
    assert dev == "cuda"
    assert ct in ("float16", "int8_float16", "int8")


# ---------- device_choice_from_hardware_file gating ----------------------------


def test_hardware_file_cuda_rejected_when_runtime_broken(monkeypatch):
    _fake_ct2(monkeypatch, has_device=True)
    monkeypatch.setattr(hw, "_cuda_runtime_dlls_loadable", lambda: False)
    monkeypatch.setattr(
        hw, "load_hardware_choice",
        lambda: {"device": "cuda", "compute_type": "float16",
                 "backend": "faster_whisper"},
    )
    assert hw.device_choice_from_hardware_file() is None


def test_hardware_file_cuda_accepted_when_runtime_ok(monkeypatch):
    _fake_ct2(monkeypatch, has_device=True)
    monkeypatch.setattr(hw, "_cuda_runtime_dlls_loadable", lambda: True)
    monkeypatch.setattr(
        hw, "load_hardware_choice",
        lambda: {"device": "cuda", "compute_type": "float16",
                 "backend": "faster_whisper"},
    )
    assert hw.device_choice_from_hardware_file() == ("cuda", "float16")
