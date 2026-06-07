"""Pure-seam tests for the LAN server's per-job options + clip parsing.

No socket, no model, no Tk. Locks the contract that ``normalize_options`` /
``normalize_language`` / ``parse_clip`` whitelist + coerce raw client data the
same way the existing ``normalize_formats`` seam does — a mis-coerced option is
exactly how a hard-to-spot server bug ships (e.g. ``"yes"`` silently becoming
``True``).
"""
from __future__ import annotations

from core.config import DEFAULT_CONFIG, _validate_overrides
from core.server.httpd import (
    WEB_LANGUAGE_CODES,
    normalize_language,
    normalize_options,
    parse_clip,
)


# --- normalize_options: valid -------------------------------------------------

def test_options_valid_bools_and_numbers():
    out = normalize_options({
        "vad_enabled": True,
        "word_timestamps": False,
        "vad_threshold": 0.4,
        "vad_min_silence_ms": 300,
        "diarization_enabled": True,
        "diarization_num_speakers": 3,
        "demucs_enabled": False,
        "hallucination_detect_enabled": True,
        "auto_chapters_enabled": False,
    })
    assert out == {
        "vad_enabled": True,
        "word_timestamps": False,
        "vad_threshold": 0.4,
        "vad_min_silence_ms": 300,
        "diarization_enabled": True,
        "diarization_num_speakers": 3,
        "demucs_enabled": False,
        "hallucination_detect_enabled": True,
        "auto_chapters_enabled": False,
    }


def test_options_string_coercion_from_multipart():
    # Multipart form fields arrive as strings; they must coerce.
    out = normalize_options({
        "vad_enabled": "true",
        "word_timestamps": "0",
        "vad_threshold": "0.7",
        "vad_min_silence_ms": "250",
        "diarization_enabled": "yes",
    })
    assert out["vad_enabled"] is True
    assert out["word_timestamps"] is False
    assert out["vad_threshold"] == 0.7
    assert out["vad_min_silence_ms"] == 250
    assert out["diarization_enabled"] is True


# --- normalize_options: invalid / clamped ------------------------------------

def test_options_threshold_clamped_to_unit_interval():
    assert normalize_options({"vad_threshold": 5.0})["vad_threshold"] == 1.0
    assert normalize_options({"vad_threshold": -2})["vad_threshold"] == 0.0


def test_options_negative_min_silence_clamped_to_zero():
    assert normalize_options({"vad_min_silence_ms": -100})["vad_min_silence_ms"] == 0


def test_options_num_speakers_below_one_becomes_auto_sentinel():
    # 0 / negative / blank -> -1 (the engine's auto-cluster sentinel).
    assert normalize_options({"diarization_num_speakers": 0})["diarization_num_speakers"] == -1
    assert normalize_options({"diarization_num_speakers": -5})["diarization_num_speakers"] == -1
    assert normalize_options({"diarization_num_speakers": 2})["diarization_num_speakers"] == 2


def test_options_uncoercible_values_dropped():
    out = normalize_options({
        "vad_threshold": "not-a-number",
        "vad_min_silence_ms": "abc",
        "vad_enabled": "maybe",
    })
    assert out == {}


# --- normalize_options: unknown dropped --------------------------------------

def test_options_unknown_keys_dropped():
    out = normalize_options({
        "vad_enabled": True,
        "transcribe_backend": "cloud_stt",   # NOT per-job switchable
        "model_path": "C:/evil",             # not a per-job option
        "bogus": 1,
    })
    assert out == {"vad_enabled": True}
    assert "transcribe_backend" not in out
    assert "model_path" not in out


def test_options_non_dict_returns_empty():
    assert normalize_options(None) == {}
    assert normalize_options("vad_enabled=1") == {}
    assert normalize_options([("vad_enabled", True)]) == {}


# --- the validated options must survive _validate_overrides ------------------

def test_normalized_options_pass_config_validation():
    """Every normalized option key/type must overlay DEFAULT_CONFIG cleanly.

    This is the load-bearing contract: the handler writes these into a per-job
    ``.whisperproject.json`` and the engine runs them through
    ``core.config._validate_overrides``. If a normalized value were the wrong
    type for its DEFAULT_CONFIG key it would be silently dropped there.
    """
    import pathlib
    opts = normalize_options({
        "vad_enabled": False,
        "vad_threshold": 0.3,
        "vad_min_silence_ms": 200,
        "word_timestamps": True,
        "diarization_enabled": True,
        "diarization_num_speakers": 2,
        "demucs_enabled": True,
        "hallucination_detect_enabled": False,
        "auto_chapters_enabled": False,
    })
    # All keys must be real config keys.
    for k in opts:
        assert k in DEFAULT_CONFIG, f"{k!r} is not a DEFAULT_CONFIG key"
    cleaned = _validate_overrides(dict(opts), pathlib.Path("x"))
    # Nothing dropped -> the validator accepted every type.
    assert cleaned == opts


# --- normalize_language -------------------------------------------------------

def test_language_whitelist_and_autodetect():
    assert normalize_language("en") == "en"
    assert normalize_language("FA") == "fa"
    assert normalize_language("") == ""
    assert normalize_language(None) == ""


def test_language_strips_bcp47_suffix():
    assert normalize_language("en-US") == "en"
    assert normalize_language("pt-BR") == "pt"
    assert normalize_language("zh-Hans") == "zh"
    assert normalize_language("en_US") == "en"


def test_language_unknown_falls_back_to_autodetect():
    assert normalize_language("klingon") == ""
    assert normalize_language("xx") == ""


def test_language_whitelist_size_matches_desktop():
    # ~26 destination languages + en + auto-detect "".
    assert "" in WEB_LANGUAGE_CODES
    assert "en" in WEB_LANGUAGE_CODES and "fa" in WEB_LANGUAGE_CODES
    assert len(WEB_LANGUAGE_CODES) >= 26


# --- parse_clip ---------------------------------------------------------------

def test_clip_basic_window():
    assert parse_clip(10, 30) == (10.0, 30.0)
    assert parse_clip("5", "12.5") == (5.0, 12.5)


def test_clip_drops_nonpositive_and_inverted():
    assert parse_clip(0, 0) == (None, None)
    assert parse_clip(-3, 10) == (None, 10.0)
    assert parse_clip(20, 10) == (20.0, None)   # end <= start dropped
    assert parse_clip(None, None) == (None, None)


def test_clip_ignores_uncoercible():
    assert parse_clip("abc", "def") == (None, None)
