"""Headless smoke for the transcript search dialog.

Mirrors tests/core/test_transcript_viewer.py's pattern: a real,
withdrawn tk.Tk() root plus the actual SearchDialog class, no VLC/
model dependency. Background work (reindex, search) is monkeypatched
out at the core.search boundary so these stay hermetic and fast.
"""
from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")


def test_dialog_builds_and_starts_indexing(monkeypatch):
    import app.dialogs.search_dialog as sd

    # __init__ kicks off a REAL background thread (core._threads.safe_thread)
    # that would otherwise touch the actual machine's history.db / search.db.
    # Stub the one call it makes into core.search so this stays hermetic —
    # patching at that boundary (not "safe_thread", which search_dialog only
    # ever imports inside the worker closure, never as a module attribute).
    monkeypatch.setattr("core.search.reindex_all_history", lambda: 0)

    root = tk.Tk()
    root.withdraw()
    try:
        dialog = sd.SearchDialog(root)
        dialog.withdraw()
        try:
            # Checked immediately after construction, before the background
            # thread's post_to_main callback could possibly have run (nothing
            # pumps the Tk event loop in this headless test) — so this is the
            # real, deterministic "just opened" state regardless of what the
            # stubbed reindex does.
            assert dialog.status_var.get() == "Indexing…"
            assert dialog.tree.get_children() == ()
        finally:
            dialog._on_close()
    finally:
        root.destroy()


def test_finish_search_populates_tree_rows():
    import app.dialogs.search_dialog as sd
    from core.search import SearchHit

    root = tk.Tk()
    root.withdraw()
    try:
        dialog = sd.SearchDialog.__new__(sd.SearchDialog)  # skip __init__'s reindex kickoff
        tk.Toplevel.__init__(dialog, root)
        dialog._build_widgets()
        dialog._closing = False
        dialog.withdraw()
        try:
            hits = [
                SearchHit(json_path="C:/x/demo.json", segment_index=0,
                          text="hello world", score=0.9, start_seconds=12.0),
                SearchHit(json_path="C:/x/other.json", segment_index=3,
                          text="second hit", score=0.5, start_seconds=75.0),
            ]
            dialog._finish_search(hits, None)
            rows = dialog.tree.get_children()
            assert len(rows) == 2
            assert dialog.tree.item(rows[0], "values") == ("demo.json", "00:00:12", "hello world")
            assert dialog.tree.item(rows[1], "values") == ("other.json", "00:01:15", "second hit")
            assert dialog.status_var.get() == "2 result(s)"
        finally:
            dialog._on_close()
    finally:
        root.destroy()


def test_finish_search_reports_error():
    import app.dialogs.search_dialog as sd

    root = tk.Tk()
    root.withdraw()
    try:
        dialog = sd.SearchDialog.__new__(sd.SearchDialog)
        tk.Toplevel.__init__(dialog, root)
        dialog._build_widgets()
        dialog._closing = False
        dialog.withdraw()
        try:
            dialog._finish_search([], "search.db is locked")
            assert "search.db is locked" in dialog.status_var.get()
        finally:
            dialog._on_close()
    finally:
        root.destroy()


def test_open_selected_opens_viewer_at_result_time(monkeypatch, tmp_path):
    import app.dialogs.search_dialog as sd
    from core.search import SearchHit

    json_path = tmp_path / "demo.json"
    json_path.write_text("[]", encoding="utf-8")

    opened: dict = {}

    def fake_open_viewer(master, path, initial_seek_seconds=None):
        opened["master"] = master
        opened["path"] = path
        opened["seek"] = initial_seek_seconds

    monkeypatch.setattr(
        "app.dialogs.transcript_viewer.open_viewer", fake_open_viewer,
    )

    root = tk.Tk()
    root.withdraw()
    try:
        dialog = sd.SearchDialog.__new__(sd.SearchDialog)
        tk.Toplevel.__init__(dialog, root)
        dialog._master_window = root
        dialog._build_widgets()
        dialog._closing = False
        dialog.withdraw()
        try:
            hit = SearchHit(
                json_path=str(json_path), segment_index=0,
                text="hello", score=1.0, start_seconds=42.0,
            )
            dialog._finish_search([hit], None)
            dialog.tree.selection_set("0")
            dialog.tree.focus("0")
            dialog._open_selected()
            assert opened["path"] == str(json_path)
            assert opened["seek"] == 42.0
        finally:
            dialog._on_close()
    finally:
        root.destroy()


def test_open_selected_with_no_selection_is_a_noop():
    import app.dialogs.search_dialog as sd

    root = tk.Tk()
    root.withdraw()
    try:
        dialog = sd.SearchDialog.__new__(sd.SearchDialog)
        tk.Toplevel.__init__(dialog, root)
        dialog._master_window = root
        dialog._build_widgets()
        dialog._closing = False
        dialog.withdraw()
        try:
            dialog._open_selected()  # must not raise
        finally:
            dialog._on_close()
    finally:
        root.destroy()
