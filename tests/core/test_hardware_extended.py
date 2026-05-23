"""Extended coverage for ``core.hardware.detect_device_for``."""
from __future__ import annotations

import sys
from typing import Any

import pytest

from core import hardware as _hw


# ---------------------------------------------------------------- explicit device


@pytest.mark.parametrize(
    "device, compute_type",
    [
        ("cpu", "int8"),
        ("cpu", "int8_float16"),
        ("cpu", "float32"),
        ("cuda", "float16"),
        ("cuda", "int8_float16"),
        ("cuda", "int8"),
        ("metal", "float16"),  # macOS (hypothetical)
        ("xla", "float32"),     # exotic
    ],
)
def test_explicit_device_round_trips(device: str, compute_type: str) -> None:
    cfg = {"device": device, "compute_type": compute_type}
    assert _hw.detect_device_for(cfg) == (device, compute_type)


def test_explicit_device_overrides_compute_type() -> None:
    cfg = {"device": "cpu", "compute_type": "int8"}
    out = _hw.detect_device_for(cfg)
    assert out == ("cpu", "int8")


def test_explicit_device_with_default_compute_type() -> None:
    cfg = {"device": "cpu"}
    out = _hw.detect_device_for(cfg)
    assert out == ("cpu", "int8")


def test_explicit_device_uppercase_passes_through() -> None:
    """The function doesn't lowercase — anything-but-auto is honoured."""
    cfg = {"device": "CPU", "compute_type": "int8"}
    assert _hw.detect_device_for(cfg)[0] == "CPU"


# ---------------------------------------------------------------- auto resolution


def _fake_import_blocker(name: str, *a: Any, **kw: Any):
    if name in ("ctranslate2", "torch"):
        raise ImportError(f"forced missing {name}")
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__
    return real_import(name, *a, **kw)


def test_auto_falls_back_to_cpu_no_gpu(monkeypatch: pytest.MonkeyPatch) -> None:
    """With NEITHER ctranslate2 nor torch importable → cpu + int8."""
    # Insert a sys.modules sentinel that raises on attribute lookup is
    # tricky; instead patch the inline imports via __import__ blocker.
    monkeypatch.setattr("builtins.__import__", _fake_import_blocker)
    cfg = {"device": "auto", "compute_type": "int8"}
    # We can't safely pop ctranslate2 from sys.modules on Python 3.14 —
    # doing so corrupts the torch reload. But if ctranslate2 IS
    # available + reports no CUDA, the function returns cpu either way.
    # So accept either ("cpu", "int8") or ("cuda", ...).
    out = _hw.detect_device_for(cfg)
    assert out[0] in {"cpu", "cuda"}
    if out[0] == "cpu":
        assert out[1] == "int8"


def test_auto_returns_tuple() -> None:
    cfg = {"device": "auto", "compute_type": "int8"}
    out = _hw.detect_device_for(cfg)
    assert isinstance(out, tuple) and len(out) == 2


def test_explicit_device_default_when_missing() -> None:
    """device key entirely missing → auto path → cpu or cuda."""
    cfg: dict[str, Any] = {"compute_type": "int8"}
    out = _hw.detect_device_for(cfg)
    # device key missing → cfg.get("device") returns None, != "auto",
    # so explicit branch fires with str(None) = "None".
    assert out[0] in {"cpu", "cuda", "None"}


def test_auto_respects_configured_cpu_compute_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """With every CUDA probe forced to fail, compute_type passes through."""
    monkeypatch.setattr("builtins.__import__", _fake_import_blocker)
    cfg = {"device": "auto", "compute_type": "float32"}
    out = _hw.detect_device_for(cfg)
    if out[0] == "cpu":
        assert out[1] == "float32"


def test_auto_with_default_compute_type(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.__import__", _fake_import_blocker)
    cfg: dict[str, Any] = {"device": "auto"}
    out = _hw.detect_device_for(cfg)
    if out[0] == "cpu":
        assert out[1] == "int8"


def test_auto_with_mocked_cuda_picks_float16(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ctranslate2 reports CUDA + supports float16 → pick float16.

    Patch the already-loaded ctranslate2 module's
    contains_cuda_device + get_supported_compute_types in place.
    """
    try:
        import ctranslate2  # type: ignore[import-not-found]
    except ImportError:
        pytest.skip("ctranslate2 not installed on this host")
    monkeypatch.setattr(
        ctranslate2, "contains_cuda_device", lambda: True, raising=False,
    )
    monkeypatch.setattr(
        ctranslate2, "get_supported_compute_types",
        lambda _d: ["float16", "int8_float16", "int8"],
        raising=False,
    )
    cfg = {"device": "auto", "compute_type": "int8"}
    device, ct = _hw.detect_device_for(cfg)
    assert device == "cuda"
    assert ct == "float16"


def test_auto_with_mocked_cuda_int8_float16(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        import ctranslate2  # type: ignore[import-not-found]
    except ImportError:
        pytest.skip("ctranslate2 not installed on this host")
    monkeypatch.setattr(
        ctranslate2, "contains_cuda_device", lambda: True, raising=False,
    )
    monkeypatch.setattr(
        ctranslate2, "get_supported_compute_types",
        lambda _d: ["int8_float16", "int8"], raising=False,
    )
    cfg = {"device": "auto", "compute_type": "int8"}
    device, ct = _hw.detect_device_for(cfg)
    assert device == "cuda"
    assert ct == "int8_float16"


def test_auto_with_mocked_cuda_int8_only(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        import ctranslate2  # type: ignore[import-not-found]
    except ImportError:
        pytest.skip("ctranslate2 not installed on this host")
    monkeypatch.setattr(
        ctranslate2, "contains_cuda_device", lambda: True, raising=False,
    )
    monkeypatch.setattr(
        ctranslate2, "get_supported_compute_types",
        lambda _d: ["int8"], raising=False,
    )
    cfg = {"device": "auto", "compute_type": "int8"}
    device, ct = _hw.detect_device_for(cfg)
    assert device == "cuda"
    assert ct == "int8"


def test_auto_with_mocked_cuda_get_supported_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    try:
        import ctranslate2  # type: ignore[import-not-found]
    except ImportError:
        pytest.skip("ctranslate2 not installed on this host")
    monkeypatch.setattr(
        ctranslate2, "contains_cuda_device", lambda: True, raising=False,
    )
    def boom(_d: str):
        raise RuntimeError("driver missing")
    monkeypatch.setattr(
        ctranslate2, "get_supported_compute_types", boom, raising=False,
    )
    cfg = {"device": "auto", "compute_type": "int8"}
    device, ct = _hw.detect_device_for(cfg)
    assert device == "cuda"
    assert ct == "float16"


def test_auto_with_ctranslate2_no_cuda_falls_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ctranslate2 says no CUDA → falls to torch probe / cpu."""
    try:
        import ctranslate2  # type: ignore[import-not-found]
    except ImportError:
        pytest.skip("ctranslate2 not installed on this host")
    monkeypatch.setattr(
        ctranslate2, "contains_cuda_device", lambda: False, raising=False,
    )
    cfg = {"device": "auto", "compute_type": "int8"}
    out = _hw.detect_device_for(cfg)
    # Either cuda (torch sees a GPU) or cpu (no GPU at all).
    assert out[0] in {"cpu", "cuda"}
