"""Fixpack sweep — transcript viewer list-of-non-dicts hardening.

Regression for the defect: ``TranscriptViewer._load_segments`` accepted any
JSON whose root was a list, including a list of NON-dict elements such as
``[1, 2, 3]`` or ``["a", "b"]`` (e.g. an unrelated JSON array). It stored that
straight into ``self.segments``; the very next step (``_populate_listbox``)
calls ``seg.get("text")`` on each element, raising an unhandled
``AttributeError`` because ``int``/``str`` have no ``.get`` — crashing viewer
construction instead of guiding the user to the right file.

The fix keeps only the dict entries after confirming the root is a list, and
when none qualify it surfaces the same "pick the .json" guidance via the error
messagebox (so ``self.segments`` ends up ``[]``) rather than crashing.

These tests drive the PURE ``_load_segments`` seam: the viewer object is built
via ``TranscriptViewer.__new__`` with only the attributes the method touches
stubbed, and the module ``messagebox`` is monkeypatched so no modal pops. No
Tk root, no VLC, no network, no model — hermetic on every platform.
"""
from __future__ import annotations

import json

import pytest

from app.dialogs import transcript_viewer as tv_mod
from app.dialogs.transcript_viewer import TranscriptViewer


def _make_viewer(json_path: str) -> TranscriptViewer:
    """Build a bare viewer for the ``_load_segments`` seam only.

    ``__new__`` skips ``__init__`` (which would build the whole Tk widget
    tree), so we attach just the attributes ``_load_segments`` reads/writes:
    the JSON path and a ``segments`` list.
    """
    viewer = TranscriptViewer.__new__(TranscriptViewer)
    viewer.json_path = json_path
    viewer.segments = []
    return viewer


def _capture_showerror(monkeypatch) -> dict[str, str]:
    captured: dict[str, str] = {}

    def _fake_showerror(title, message, **kw):
        captured["title"] = title
        captured["message"] = message

    monkeypatch.setattr(tv_mod.messagebox, "showerror", _fake_showerror)
    return captured


@pytest.mark.parametrize("payload", [[1, 2, 3], ["a", "b"], [True, None, 4.5]])
def test_load_segments_list_of_non_dicts_does_not_crash(tmp_path, monkeypatch, payload):
    """A list of non-dict elements must not crash; it yields an empty
    segment list and surfaces the 'pick the .json' guidance.

    Pre-fix this stored the raw list into ``self.segments`` without error;
    the crash (AttributeError) only surfaced later in ``_populate_listbox``.
    To prove the regression directly at the seam we also assert the segment
    list is dict-only here — pre-fix ``segments`` would equal ``payload``,
    which contains non-dicts, so this assertion FAILS on the old code.
    """
    captured = _capture_showerror(monkeypatch)

    p = tmp_path / "weird.json"
    p.write_text(json.dumps(payload), encoding="utf-8")

    viewer = _make_viewer(str(p))
    viewer._load_segments()  # must not raise

    assert viewer.segments == []
    assert all(isinstance(s, dict) for s in viewer.segments)
    assert "transcript" in captured.get("message", "").lower()


def test_load_segments_mixed_list_keeps_only_dicts(tmp_path, monkeypatch):
    """A list mixing dict segments with junk elements keeps the dicts and
    silently drops the non-dicts — no crash, no error popup."""
    captured = _capture_showerror(monkeypatch)

    payload = [
        {"start": 0.0, "end": 1.0, "text": "real one"},
        7,
        "garbage",
        {"start": 1.0, "end": 2.0, "text": "real two"},
    ]
    p = tmp_path / "mixed.json"
    p.write_text(json.dumps(payload), encoding="utf-8")

    viewer = _make_viewer(str(p))
    viewer._load_segments()

    assert len(viewer.segments) == 2
    assert all(isinstance(s, dict) for s in viewer.segments)
    assert [s["text"] for s in viewer.segments] == ["real one", "real two"]
    # The salvage path is not an error — no messagebox fired.
    assert captured == {}


def test_load_segments_valid_list_unchanged(tmp_path, monkeypatch):
    """A normal list of segment dicts loads verbatim — the fix must not
    change the happy path."""
    captured = _capture_showerror(monkeypatch)

    payload = [
        {"start": 0.0, "end": 1.0, "text": "hello"},
        {"start": 1.0, "end": 2.0, "text": "world"},
    ]
    p = tmp_path / "good.json"
    p.write_text(json.dumps(payload), encoding="utf-8")

    viewer = _make_viewer(str(p))
    viewer._load_segments()

    assert viewer.segments == payload
    assert captured == {}


def test_load_segments_empty_list_is_ok(tmp_path, monkeypatch):
    """An empty list is a valid (empty) transcript — no error, no crash."""
    captured = _capture_showerror(monkeypatch)

    p = tmp_path / "empty.json"
    p.write_text(json.dumps([]), encoding="utf-8")

    viewer = _make_viewer(str(p))
    viewer._load_segments()

    assert viewer.segments == []
    assert captured == {}
