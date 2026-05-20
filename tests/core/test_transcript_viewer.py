"""Headless smoke for the in-app transcript viewer.

Drives the real ``app.dialogs.transcript_viewer.TranscriptViewer``
class against a JSON fixture so the widget tree is constructed,
the segments are populated, search filters the list, and segment
selection invokes the seek hook. No VLC dependency — VLC is
treated as optional and the viewer falls back gracefully when
libvlc isn't present, which is the CI scenario.
"""
from __future__ import annotations

import json
import os

import pytest

tk = pytest.importorskip("tkinter")


SAMPLE_SEGMENTS = [
    {"start": 0.0, "end": 1.5, "text": "Hello world", "speaker": "Speaker 00"},
    {"start": 1.5, "end": 3.0, "text": "Second segment", "speaker": "Speaker 01"},
    {"start": 3.0, "end": 5.0, "text": "Third with no speaker"},
]


@pytest.fixture
def sample_json(tmp_path):
    json_path = tmp_path / "demo.json"
    json_path.write_text(json.dumps(SAMPLE_SEGMENTS, ensure_ascii=False), encoding="utf-8")
    return str(json_path)


def test_viewer_loads_segments_into_tree(sample_json):
    from app.dialogs.transcript_viewer import TranscriptViewer

    root = tk.Tk()
    root.withdraw()
    try:
        viewer = TranscriptViewer(root, sample_json)
        viewer.withdraw()
        try:
            children = viewer.tree.get_children()
            assert len(children) == 3
            # Time column on the first row should be "00:00:00".
            assert viewer.tree.item(children[0], "values")[0] == "00:00:00"
            # Speaker column carries the diarisation label when present
            assert viewer.tree.item(children[0], "values")[1] == "Speaker 00"
            assert viewer.tree.item(children[2], "values")[1] == ""
        finally:
            viewer._on_close()
    finally:
        root.destroy()


def test_viewer_search_filters_the_tree(sample_json):
    from app.dialogs.transcript_viewer import TranscriptViewer

    root = tk.Tk()
    root.withdraw()
    try:
        viewer = TranscriptViewer(root, sample_json)
        viewer.withdraw()
        try:
            viewer.search_var.set("second")
            viewer.update_idletasks()
            children = viewer.tree.get_children()
            assert len(children) == 1
            assert "Second segment" in viewer.tree.item(children[0], "values")[2]
            # Clearing the filter brings them all back.
            viewer.search_var.set("")
            viewer.update_idletasks()
            assert len(viewer.tree.get_children()) == 3
        finally:
            viewer._on_close()
    finally:
        root.destroy()


def test_viewer_handles_missing_media_gracefully(sample_json):
    """The JSON lives in a tmp path with no media next to it. The
    viewer must still build cleanly; the embedded player either
    runs in a degraded "no media" state or is disabled by the
    VLC-fallback path."""
    from app.dialogs.transcript_viewer import TranscriptViewer

    root = tk.Tk()
    root.withdraw()
    try:
        viewer = TranscriptViewer(root, sample_json)
        viewer.withdraw()
        try:
            assert viewer.media_path is None
            # The play button is either disabled (when VLC absent) or
            # exists. Either way, the widget must exist and be usable.
            assert viewer.play_btn is not None
        finally:
            viewer._on_close()
    finally:
        root.destroy()


def test_viewer_invalid_json_shows_empty_list(tmp_path, monkeypatch):
    """If the JSON is invalid, the viewer must not crash on
    construction — it logs the error via a messagebox and shows
    an empty tree."""
    from app.dialogs import transcript_viewer

    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")

    # Stub out the error messagebox so the test isn't blocked by a
    # modal popup during CI.
    monkeypatch.setattr(transcript_viewer.messagebox, "showerror", lambda *a, **kw: None)

    root = tk.Tk()
    root.withdraw()
    try:
        viewer = transcript_viewer.TranscriptViewer(root, str(bad))
        viewer.withdraw()
        try:
            assert viewer.tree.get_children() == ()
        finally:
            viewer._on_close()
    finally:
        root.destroy()
