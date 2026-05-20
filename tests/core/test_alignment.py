"""Tests for the stable-ts alignment post-processor."""
from __future__ import annotations

import sys
import types

import pytest


@pytest.fixture
def alignment_module():
    # Stable-ts is an opt-in dep; mock the import so the module
    # itself can be tested without installing it.
    for mod in [m for m in list(sys.modules) if m.startswith("core.alignment")]:
        del sys.modules[mod]
    import core.alignment as a
    return a


def test_is_available_returns_false_when_module_missing(alignment_module, monkeypatch):
    # Pretend stable_whisper isn't importable.
    monkeypatch.setitem(sys.modules, "stable_whisper", None)
    # Module-level cache could already say True from a previous test
    # run, so call directly.
    assert alignment_module.is_available() is False
    assert "stable-ts" in alignment_module.availability_reason()


def test_refine_raises_when_unavailable(alignment_module, monkeypatch):
    monkeypatch.setattr(alignment_module, "is_available", lambda: False)
    with pytest.raises(RuntimeError, match="stable-ts"):
        alignment_module.refine_word_timestamps_in_place(
            "/tmp/fake.wav",
            [{"start": 0.0, "end": 1.0, "text": "hi"}],
        )


def test_refine_noop_on_empty_segments(alignment_module, monkeypatch):
    monkeypatch.setattr(alignment_module, "is_available", lambda: True)
    monkeypatch.setitem(sys.modules, "stable_whisper", types.ModuleType("stable_whisper"))
    out: list[dict] = []
    alignment_module.refine_word_timestamps_in_place("/tmp/fake.wav", out)
    assert out == []


def test_refine_splices_words_back(alignment_module, monkeypatch):
    """When stable_whisper returns refined word lists, those word
    lists must end up on segments_data."""
    monkeypatch.setattr(alignment_module, "is_available", lambda: True)

    # Build a fake stable_whisper module with an align function.
    class _FakeWord:
        def __init__(self, start, end, word, probability=0.9):
            self.start, self.end, self.word, self.probability = start, end, word, probability

    class _FakeSeg:
        def __init__(self, words):
            self.words = words

    class _FakeResult:
        def __init__(self, segments):
            self.segments = segments

    fake_sw = types.ModuleType("stable_whisper")

    def _load_model(_name):
        return object()

    def _align(_model, _audio, coarse, **_kw):
        return _FakeResult([
            _FakeSeg([_FakeWord(0.0, 0.5, "hello"), _FakeWord(0.5, 1.0, "world")])
            for _ in coarse
        ])

    fake_sw.load_model = _load_model  # type: ignore[attr-defined]
    fake_sw.align = _align  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "stable_whisper", fake_sw)

    segs = [{"start": 0.0, "end": 1.0, "text": "hello world"}]
    alignment_module.refine_word_timestamps_in_place("/tmp/fake.wav", segs)
    assert "words" in segs[0]
    words = segs[0]["words"]
    assert len(words) == 2
    assert words[0]["word"] == "hello"
    assert words[1]["word"] == "world"
    assert words[1]["start"] == 0.5
