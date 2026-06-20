"""Hermetic tests for the NVIDIA Nemotron 3.5 ASR backend.

NO network, NO riva install, NO API key, NO model. These exercise only the
pure seams: normalize_language_code, results_to_segments, offset_segments
(imported from cloud_stt), classify_riva_error, the key-missing load() path,
and the availability registry.
"""
from __future__ import annotations

import sys
import types

import pytest

from core.backends import get_backend
from core.backends import nvidia_asr as na
from core.backends.cloud_stt import offset_segments


# ---------------------------------------------------------------- language


def test_normalize_none_returns_default():
    assert na.normalize_language_code(None) == "en-US"


def test_normalize_empty_returns_default():
    assert na.normalize_language_code("") == "en-US"
    assert na.normalize_language_code("   ") == "en-US"


def test_normalize_en_promotes_to_en_us():
    assert na.normalize_language_code("en") == "en-US"


def test_normalize_full_bcp47_passes_through():
    assert na.normalize_language_code("es-US") == "es-US"
    assert na.normalize_language_code("fr-FR") == "fr-FR"
    assert na.normalize_language_code("zh-CN") == "zh-CN"


def test_normalize_bare_non_en_passes_through():
    # A bare two-letter code other than "en" is returned as-is rather than
    # guessing a region tag that might be wrong.
    assert na.normalize_language_code("fr") == "fr"


# ---------------------------------------------------------------- results_to_segments


def _make_word(word: str, start_ms: int, end_ms: int, confidence: float = 0.95):
    """Build a SimpleNamespace that looks like a Riva word object."""
    w = types.SimpleNamespace(
        word=word,
        start_time=start_ms,
        end_time=end_ms,
        confidence=confidence,
    )
    return w


def _make_response(transcript: str, words: list, *, is_final: bool = True):
    """Build a SimpleNamespace that looks like a Riva streaming response."""
    alt = types.SimpleNamespace(transcript=transcript, words=words)
    result = types.SimpleNamespace(is_final=is_final, alternatives=[alt])
    return types.SimpleNamespace(results=[result])


def test_results_to_segments_happy_path():
    words = [
        _make_word("hello", 0, 300),
        _make_word("world", 300, 700),
    ]
    response = _make_response("hello world", words)
    segs = na.results_to_segments([response])
    assert len(segs) == 1
    seg = segs[0]
    assert seg["text"] == "hello world"
    # Timestamps convert from ms to seconds.
    assert seg["start"] == pytest.approx(0.0)
    assert seg["end"] == pytest.approx(0.7)
    assert len(seg["words"]) == 2
    assert seg["words"][0] == {
        "start": 0.0,
        "end": 0.3,
        "word": "hello",
        "probability": pytest.approx(0.95),
    }
    assert seg["words"][1]["word"] == "world"
    assert seg["words"][1]["end"] == pytest.approx(0.7)


def test_results_to_segments_ms_to_seconds_conversion():
    words = [_make_word("test", 1500, 2000)]
    response = _make_response("test", words)
    segs = na.results_to_segments([response])
    assert segs[0]["start"] == pytest.approx(1.5)
    assert segs[0]["end"] == pytest.approx(2.0)
    assert segs[0]["words"][0]["start"] == pytest.approx(1.5)
    assert segs[0]["words"][0]["end"] == pytest.approx(2.0)


def test_results_to_segments_empty_transcript_skipped():
    response = _make_response("", [])
    segs = na.results_to_segments([response])
    assert segs == []


def test_results_to_segments_whitespace_only_transcript_skipped():
    response = _make_response("   ", [])
    segs = na.results_to_segments([response])
    assert segs == []


def test_results_to_segments_non_final_skipped():
    words = [_make_word("interim", 0, 500)]
    response = _make_response("interim", words, is_final=False)
    segs = na.results_to_segments([response])
    assert segs == []


def test_results_to_segments_missing_is_final_treated_as_true():
    """is_final absent defaults to True (old / simple mocks are accepted)."""
    alt = types.SimpleNamespace(
        transcript="default final", words=[]
    )
    result = types.SimpleNamespace(alternatives=[alt])
    # is_final attribute deliberately absent.
    response = types.SimpleNamespace(results=[result])
    segs = na.results_to_segments([response])
    assert len(segs) == 1
    assert segs[0]["text"] == "default final"


def test_results_to_segments_multiple_responses():
    r1 = _make_response("first", [_make_word("first", 0, 500)])
    r2 = _make_response("second", [_make_word("second", 600, 1100)])
    segs = na.results_to_segments([r1, r2])
    assert len(segs) == 2
    assert segs[0]["text"] == "first"
    assert segs[1]["text"] == "second"


def test_results_to_segments_empty_results():
    assert na.results_to_segments([]) == []


def test_results_to_segments_bad_input_returns_empty():
    # results_to_segments must not raise on garbage input.
    segs = na.results_to_segments(None)  # type: ignore[arg-type]
    assert segs == []


# ---------------------------------------------------------------- offset reuse


def test_offset_segments_reused_from_cloud_stt():
    """results_to_segments + offset_segments places timestamps globally."""
    words = [
        _make_word("foo", 0, 1000),
        _make_word("bar", 1000, 2000),
    ]
    response = _make_response("foo bar", words)
    chunk_segs = na.results_to_segments([response])

    # Chunk starts at 300 s on the global timeline.
    offset = 300.0
    global_segs = offset_segments(chunk_segs, offset)

    assert len(global_segs) == 1
    assert global_segs[0]["start"] == pytest.approx(300.0)  # 0.0 + 300
    assert global_segs[0]["end"] == pytest.approx(302.0)    # 2.0 + 300
    assert global_segs[0]["words"][0]["start"] == pytest.approx(300.0)
    assert global_segs[0]["words"][1]["end"] == pytest.approx(302.0)
    # Input untouched (pure).
    assert chunk_segs[0]["start"] == pytest.approx(0.0)


# ---------------------------------------------------------------- classify_riva_error


def _fake_rpc_error(code_str: str, details: str = "some detail"):
    """Build a duck-typed fake gRPC RpcError.

    Uses a nested class for the code object so that str(code_obj) calls the
    class-level __str__ (Python does not use __str__ defined on instances of
    SimpleNamespace or other built-in types).
    """
    _code_str = code_str

    class _FakeCode:
        def __str__(self) -> str:
            return _code_str

    code_obj = _FakeCode()

    class _FakeError(Exception):
        def code(self):
            return code_obj

        def details(self):
            return details

        def __str__(self):
            return f"gRPC error: {_code_str}"

    return _FakeError("fake gRPC error")


def test_classify_unauthenticated():
    exc = _fake_rpc_error("StatusCode.UNAUTHENTICATED")
    msg = na.classify_riva_error(exc)
    assert "NVIDIA API key" in msg
    assert "build.nvidia.com" in msg


def test_classify_permission_denied():
    exc = _fake_rpc_error("StatusCode.PERMISSION_DENIED")
    msg = na.classify_riva_error(exc)
    assert "NVIDIA API key" in msg


def test_classify_resource_exhausted():
    exc = _fake_rpc_error("StatusCode.RESOURCE_EXHAUSTED")
    msg = na.classify_riva_error(exc)
    assert "quota" in msg.lower()
    assert "build.nvidia.com" in msg


def test_classify_unavailable():
    exc = _fake_rpc_error("StatusCode.UNAVAILABLE")
    msg = na.classify_riva_error(exc)
    assert "unreachable" in msg.lower() or "servers" in msg.lower()


def test_classify_invalid_argument():
    exc = _fake_rpc_error("StatusCode.INVALID_ARGUMENT")
    msg = na.classify_riva_error(exc)
    assert "audio" in msg.lower() or "configuration" in msg.lower()


def test_classify_generic_no_code():
    """An exception without .code() falls through to the generic message."""

    class _PlainError(Exception):
        pass

    exc = _PlainError("something went wrong")
    msg = na.classify_riva_error(exc)
    assert "NVIDIA ASR error" in msg or "something went wrong" in msg


# ---------------------------------------------------------------- load()


def test_load_without_key_returns_false():
    backend = na.NvidiaAsrBackend(config={"nvidia_asr_api_key": ""})
    statuses: list[str] = []
    ok = backend.load(statuses.append)
    assert ok is False
    assert backend.is_ready() is False
    err = backend.get_error() or ""
    assert err != ""
    assert "build.nvidia.com" in err or "NVIDIA" in err
    assert any("key" in s.lower() or "nvidia" in s.lower() for s in statuses)


def test_load_with_fake_key_is_ready_no_network():
    backend = na.NvidiaAsrBackend(config={"nvidia_asr_api_key": "fake-key-xyz"})
    ok = backend.load()
    assert ok is True
    assert backend.is_ready() is True
    assert backend.get_error() is None


def test_load_with_fake_key_reads_config_values():
    cfg = {
        "nvidia_asr_api_key": "my-key",
        "nvidia_asr_server": "custom.server:443",
        "nvidia_asr_function_id": "custom-function-id",
        "nvidia_asr_chunk_seconds": 120,
        "nvidia_asr_language": "fr-FR",
    }
    backend = na.NvidiaAsrBackend(config=cfg)
    ok = backend.load()
    assert ok is True
    assert backend._server == "custom.server:443"
    assert backend._function_id == "custom-function-id"
    assert backend._chunk_seconds == pytest.approx(120.0)
    assert backend._language == "fr-FR"


# ---------------------------------------------------------------- get_backend factory


def test_get_backend_returns_nvidia_asr():
    b = get_backend("nvidia_asr")
    assert b.name == "nvidia_asr"
    assert isinstance(b, na.NvidiaAsrBackend)


# ---------------------------------------------------------------- availability


def test_availability_without_key_not_ready():
    from core.backends.availability import engine_status

    cfg = {}
    st = engine_status("nvidia_asr", cfg, deep=True)
    assert st.ready is False
    assert st.detail != ""
    assert "NVIDIA" in st.detail or "key" in st.detail.lower()


def test_availability_with_key_ready():
    from core.backends.availability import engine_status

    cfg = {"nvidia_asr_api_key": "some-key"}
    st = engine_status("nvidia_asr", cfg, deep=True)
    assert st.ready is True


def test_availability_shallow_without_key_not_ready():
    from core.backends.availability import engine_status

    st = engine_status("nvidia_asr", {}, deep=False)
    assert st.ready is False


def test_availability_shallow_with_key_ready():
    from core.backends.availability import engine_status

    st = engine_status("nvidia_asr", {"nvidia_asr_api_key": "k"}, deep=False)
    assert st.ready is True


# ---------------------------------------------------------------- registry sync


def test_nvidia_asr_in_known_engines():
    from core.backends.availability import KNOWN_ENGINES

    assert "nvidia_asr" in KNOWN_ENGINES


def test_nvidia_asr_in_advanced_backend_choices():
    """NVIDIA ASR must appear in the Advanced dialog's backend picker.

    Avoids importing Tk by loading app.dialogs.advanced only for its
    _BACKEND_LABEL_TO_VALUE dict — the same technique used by
    test_engine_selector.py to import app.app without a Tk root.
    """
    # Stub tkinter and its sub-modules so the import succeeds headlessly.
    for mod_name in ("tkinter", "tkinter.ttk", "tkinter.filedialog"):
        if mod_name not in sys.modules:
            fake_tk = types.ModuleType(mod_name)
            # Provide the minimal names that advanced.py references at
            # module level (class-body definitions and module constants
            # only; method bodies are not executed at import time).
            for attr in (
                "Toplevel", "Frame", "StringVar", "BooleanVar",
                "IntVar", "DoubleVar", "Canvas", "Label",
            ):
                setattr(fake_tk, attr, object)
            sys.modules[mod_name] = fake_tk

    # Stub heavy app / core imports that advanced.py pulls at the top level.
    for mod_name in (
        "core.config",
        "core.model_manager",
        "core.writers",
    ):
        if mod_name not in sys.modules:
            fake = types.ModuleType(mod_name)
            # Provide the names imported at module level in advanced.py.
            fake.save_config = lambda *a, **kw: None  # type: ignore[attr-defined]
            fake.DEFAULT_MODEL_SLUG = "large-v3"  # type: ignore[attr-defined]
            fake.catalog_entry_info = lambda *a, **kw: None  # type: ignore[attr-defined]
            fake.catalog_models = lambda *a, **kw: []  # type: ignore[attr-defined]
            fake.catalog_resolve_entry = lambda *a, **kw: None  # type: ignore[attr-defined]
            fake.supported_formats = lambda: []  # type: ignore[attr-defined]
            sys.modules[mod_name] = fake

    # Import lazily so the stubs take effect.
    import importlib

    advanced = importlib.import_module("app.dialogs.advanced")

    values = set(advanced._BACKEND_LABEL_TO_VALUE.values())
    assert "nvidia_asr" in values


def test_availability_and_advanced_nvidia_asr_in_sync():
    """ENGINE_CHOICES and _BACKEND_CHOICES must both contain nvidia_asr."""
    from core.backends.availability import KNOWN_ENGINES

    assert "nvidia_asr" in KNOWN_ENGINES

    # Re-use already-imported advanced module (or import if needed).
    import importlib

    advanced = importlib.import_module("app.dialogs.advanced")
    values = set(advanced._BACKEND_LABEL_TO_VALUE.values())
    assert "nvidia_asr" in values
