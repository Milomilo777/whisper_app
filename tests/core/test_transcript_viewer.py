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


def test_viewer_dict_root_explains_wrong_file(tmp_path, monkeypatch):
    """A dict-root JSON (e.g. a credentials/config file) must not crash;
    it shows an empty list and surfaces a 'pick the .json' style error
    rather than a raw 'root must be a list' message."""
    from app.dialogs import transcript_viewer

    cfg = tmp_path / "creds.json"
    cfg.write_text(json.dumps({"token": "secret"}), encoding="utf-8")

    captured: dict[str, str] = {}

    def _fake_showerror(title, message, **kw):
        captured["title"] = title
        captured["message"] = message

    monkeypatch.setattr(transcript_viewer.messagebox, "showerror", _fake_showerror)

    root = tk.Tk()
    root.withdraw()
    try:
        viewer = transcript_viewer.TranscriptViewer(root, str(cfg))
        viewer.withdraw()
        try:
            assert viewer.tree.get_children() == ()
            assert "transcript JSON" in captured.get("message", "")
        finally:
            viewer._on_close()
    finally:
        root.destroy()


# --- v0.7.0 enhancements (B1) ------------------------------------------------


def test_strip_fillers_removes_uh_um_er():
    from app.dialogs.transcript_viewer import _strip_fillers, _filler_regex

    pat = _filler_regex()
    assert _strip_fillers("uh hello there", pat) == "hello there"
    assert _strip_fillers("Hello, um, world", pat) == "Hello, world"
    # Doesn't strip a legitimate trailing 'er' as in 'eraser':
    assert "eraser" in _strip_fillers("the eraser", pat)


def test_segment_min_probability_helpers():
    from app.dialogs.transcript_viewer import _segment_min_probability

    seg_with = {"words": [{"probability": 0.9}, {"probability": 0.7}]}
    assert _segment_min_probability(seg_with) == 0.7
    seg_without: dict = {}
    assert _segment_min_probability(seg_without) is None


def test_viewer_rename_speaker_globally(tmp_path):
    """Right-click → Rename speaker rewrites every segment with the
    same label and flags the viewer dirty."""
    from app.dialogs.transcript_viewer import TranscriptViewer

    segs = [
        {"start": 0.0, "end": 1.0, "text": "a", "speaker": "Speaker 00"},
        {"start": 1.0, "end": 2.0, "text": "b", "speaker": "Speaker 01"},
        {"start": 2.0, "end": 3.0, "text": "c", "speaker": "Speaker 00"},
    ]
    p = tmp_path / "rn.json"
    p.write_text(json.dumps(segs), encoding="utf-8")

    root = tk.Tk()
    root.withdraw()
    try:
        viewer = TranscriptViewer(root, str(p))
        viewer.withdraw()
        try:
            from app.dialogs import transcript_viewer as tv_mod
            # simpledialog blocks on a modal — stub the input.
            tv_mod.simpledialog.askstring = lambda *a, **kw: "Alice"  # type: ignore[attr-defined]
            tv_mod.messagebox.showinfo = lambda *a, **kw: None  # type: ignore[attr-defined]
            viewer._rename_speaker("Speaker 00")
            assert viewer.segments[0]["speaker"] == "Alice"
            assert viewer.segments[1]["speaker"] == "Speaker 01"
            assert viewer.segments[2]["speaker"] == "Alice"
            assert viewer._dirty is True
        finally:
            tv_mod.messagebox.askyesno = lambda *a, **kw: True  # type: ignore[attr-defined]
            viewer._on_close()
    finally:
        root.destroy()


def test_viewer_remove_fillers_button(tmp_path):
    from app.dialogs.transcript_viewer import TranscriptViewer

    segs = [
        {"start": 0.0, "end": 1.0, "text": "uh hello there"},
        {"start": 1.0, "end": 2.0, "text": "world, um, hi"},
    ]
    p = tmp_path / "fil.json"
    p.write_text(json.dumps(segs), encoding="utf-8")

    root = tk.Tk()
    root.withdraw()
    try:
        viewer = TranscriptViewer(root, str(p))
        viewer.withdraw()
        try:
            from app.dialogs import transcript_viewer as tv_mod
            tv_mod.messagebox.askyesno = lambda *a, **kw: True  # type: ignore[attr-defined]
            tv_mod.messagebox.showinfo = lambda *a, **kw: None  # type: ignore[attr-defined]
            viewer._remove_fillers()
            assert "uh" not in viewer.segments[0]["text"].lower().split()
            assert "um" not in viewer.segments[1]["text"].lower().split(", ")
            assert viewer._dirty is True
        finally:
            tv_mod.messagebox.askyesno = lambda *a, **kw: True  # type: ignore[attr-defined]
            viewer._on_close()
    finally:
        root.destroy()


def test_viewer_save_changes_round_trips(tmp_path):
    """Editing a segment then Save Changes must write the new
    segments back through the writer."""
    from app.dialogs.transcript_viewer import TranscriptViewer

    segs = [{"start": 0.0, "end": 1.0, "text": "hello"}]
    p = tmp_path / "rt.json"
    p.write_text(json.dumps(segs), encoding="utf-8")

    root = tk.Tk()
    root.withdraw()
    try:
        viewer = TranscriptViewer(root, str(p))
        viewer.withdraw()
        try:
            from app.dialogs import transcript_viewer as tv_mod
            tv_mod.messagebox.showinfo = lambda *a, **kw: None  # type: ignore[attr-defined]
            viewer.segments[0]["text"] = "goodbye"
            viewer._dirty = True
            viewer._save_changes()
            payload = json.loads(p.read_text(encoding="utf-8"))
            assert payload[0]["text"] == "goodbye"
        finally:
            tv_mod.messagebox.askyesno = lambda *a, **kw: True  # type: ignore[attr-defined]
            viewer._on_close()
    finally:
        root.destroy()


def test_viewer_confidence_tags_applied(tmp_path):
    """Segments with low word confidence get the conf_low tag; high
    confidence gets conf_high."""
    from app.dialogs.transcript_viewer import TranscriptViewer

    segs = [
        {"start": 0.0, "end": 1.0, "text": "low",
         "words": [{"start": 0.0, "end": 1.0, "word": "low", "probability": 0.3}]},
        {"start": 1.0, "end": 2.0, "text": "high",
         "words": [{"start": 1.0, "end": 2.0, "word": "high", "probability": 0.95}]},
        {"start": 2.0, "end": 3.0, "text": "med",
         "words": [{"start": 2.0, "end": 3.0, "word": "med", "probability": 0.7}]},
    ]
    p = tmp_path / "conf.json"
    p.write_text(json.dumps(segs), encoding="utf-8")

    root = tk.Tk()
    root.withdraw()
    try:
        viewer = TranscriptViewer(root, str(p))
        viewer.withdraw()
        try:
            children = viewer.tree.get_children()
            assert "conf_low" in viewer.tree.item(children[0], "tags")
            assert "conf_high" in viewer.tree.item(children[1], "tags")
            assert "conf_med" in viewer.tree.item(children[2], "tags")
        finally:
            viewer._on_close()
    finally:
        root.destroy()


def test_find_replace_replace_all(tmp_path):
    """FindReplaceDialog.replace_all rewrites every match in memory
    and flags the viewer dirty."""
    from app.dialogs.transcript_viewer import TranscriptViewer, FindReplaceDialog

    segs = [
        {"start": 0.0, "end": 1.0, "text": "color of the sky"},
        {"start": 1.0, "end": 2.0, "text": "another color word"},
        {"start": 2.0, "end": 3.0, "text": "different topic"},
    ]
    p = tmp_path / "fr.json"
    p.write_text(json.dumps(segs), encoding="utf-8")

    root = tk.Tk()
    root.withdraw()
    try:
        viewer = TranscriptViewer(root, str(p))
        viewer.withdraw()
        try:
            from app.dialogs import transcript_viewer as tv_mod
            tv_mod.messagebox.showinfo = lambda *a, **kw: None  # type: ignore[attr-defined]
            dlg = FindReplaceDialog(viewer)
            dlg.find_var.set("color")
            dlg.replace_var.set("colour")
            dlg.replace_all()
            assert viewer.segments[0]["text"] == "colour of the sky"
            assert viewer.segments[1]["text"] == "another colour word"
            assert viewer.segments[2]["text"] == "different topic"
            assert viewer._dirty is True
            dlg.destroy()
        finally:
            tv_mod.messagebox.askyesno = lambda *a, **kw: True  # type: ignore[attr-defined]
            viewer._on_close()
    finally:
        root.destroy()


def test_find_replace_backreference_in_replacement_is_literal():
    """Replacement strings that look like regex backreferences
    (e.g. ``\\1``, ``\\g<0>``) must be inserted LITERALLY, not
    interpreted as regex syntax — otherwise the user gets a
    misleading crash or silent garbage in the transcript."""
    from app.dialogs.transcript_viewer import FindReplaceDialog

    out = FindReplaceDialog._safe_replace("Hello world", "world", r"\1", False)
    assert out == r"Hello \1"

    out = FindReplaceDialog._safe_replace("Hello world", "world", r"\g<name>", False)
    assert out == r"Hello \g<name>"

    out = FindReplaceDialog._safe_replace("Hello world", "world", r"\\", False)
    assert out == r"Hello \\"


def test_find_replace_rejects_whitespace_only_needle(tmp_path):
    """Find with whitespace-only needle must noop instead of
    destructively replacing every space in every segment."""
    from app.dialogs.transcript_viewer import TranscriptViewer, FindReplaceDialog

    segs = [{"start": 0.0, "end": 1.0, "text": "hello world"}]
    p = tmp_path / "ws.json"
    p.write_text(json.dumps(segs), encoding="utf-8")
    root = tk.Tk()
    root.withdraw()
    try:
        viewer = TranscriptViewer(root, str(p))
        viewer.withdraw()
        try:
            from app.dialogs import transcript_viewer as tv_mod
            tv_mod.messagebox.showinfo = lambda *a, **kw: None  # type: ignore[attr-defined]
            dlg = FindReplaceDialog(viewer)
            dlg.find_var.set("  ")
            dlg.replace_var.set("X")
            dlg.replace_all()
            assert viewer.segments[0]["text"] == "hello world"
            assert viewer._dirty is False
            dlg.destroy()
        finally:
            tv_mod.messagebox.askyesno = lambda *a, **kw: True  # type: ignore[attr-defined]
            viewer._on_close()
    finally:
        root.destroy()


def test_speaker_rename_rejects_empty_input(tmp_path):
    """Renaming a speaker to empty / whitespace-only must noop,
    otherwise every matching label gets silently erased."""
    from app.dialogs.transcript_viewer import TranscriptViewer

    segs = [
        {"start": 0.0, "end": 1.0, "text": "a", "speaker": "Speaker 00"},
    ]
    p = tmp_path / "rn2.json"
    p.write_text(json.dumps(segs), encoding="utf-8")

    root = tk.Tk()
    root.withdraw()
    try:
        viewer = TranscriptViewer(root, str(p))
        viewer.withdraw()
        try:
            from app.dialogs import transcript_viewer as tv_mod
            # askstring returns " " (whitespace) — viewer must noop.
            tv_mod.simpledialog.askstring = lambda *a, **kw: "   "  # type: ignore[attr-defined]
            viewer._rename_speaker("Speaker 00")
            assert viewer.segments[0]["speaker"] == "Speaker 00"
            assert viewer._dirty is False
        finally:
            tv_mod.messagebox.askyesno = lambda *a, **kw: True  # type: ignore[attr-defined]
            viewer._on_close()
    finally:
        root.destroy()


def test_viewer_suspect_segments_get_red_background(tmp_path):
    """A segment carrying ``suspect=True`` must be rendered with the
    ``suspect`` row tag so the viewer highlights it in red. Tag layers
    UNDER the karaoke ``active`` tag and OVER the confidence colour."""
    from app.dialogs.transcript_viewer import TranscriptViewer

    segs = [
        {"start": 0.0, "end": 1.0, "text": "real speech"},
        {
            "start": 1.0, "end": 2.0,
            "text": "Thanks for watching!",
            "suspect": True,
            "suspect_reason": "bag-of-hallucinations",
        },
        {
            "start": 2.0, "end": 3.0,
            "text": "low confidence and suspect",
            "suspect": True,
            "suspect_reason": "repetition",
            "words": [
                {"start": 2.0, "end": 3.0, "word": "x", "probability": 0.2}
            ],
        },
    ]
    p = tmp_path / "sus.json"
    p.write_text(json.dumps(segs), encoding="utf-8")

    root = tk.Tk()
    root.withdraw()
    try:
        viewer = TranscriptViewer(root, str(p))
        viewer.withdraw()
        try:
            children = viewer.tree.get_children()
            tags0 = viewer.tree.item(children[0], "tags")
            tags1 = viewer.tree.item(children[1], "tags")
            tags2 = viewer.tree.item(children[2], "tags")
            assert "suspect" not in tags0
            assert "suspect" in tags1
            # Suspect + low confidence must coexist.
            assert "suspect" in tags2
            assert "conf_low" in tags2
        finally:
            viewer._on_close()
    finally:
        root.destroy()


def test_strip_fillers_collapses_space_before_punctuation():
    """When an inline filler is removed, any space-before-punctuation
    artefact left behind must be tidied. The terminal-punctuation
    case ("Hello um!") collapses the filler word AND its trailing
    "!" because the regex treats them as one unit — this is the
    documented behaviour. The interesting case is the inline one."""
    from app.dialogs.transcript_viewer import _strip_fillers, _filler_regex

    pat = _filler_regex()
    # Inline filler — punctuation that wasn't part of the filler
    # group survives the cleanup.
    assert _strip_fillers("Are you um sure?", pat) == "Are you sure?"
