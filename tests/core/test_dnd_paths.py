r"""Drag-and-drop path parsing, especially UNC network shares.

A file dragged from a network share ``\\server\share\file.mp4`` used to
be silently ignored: ``Tk.splitlist`` collapses the leading ``\\`` of a
brace-wrapped UNC path down to a single backslash, so the path is no
longer a valid UNC and the later ``os.path.isfile`` gate fails. The pure
``_split_dnd_paths`` helper splits the tkdnd wire format (space-separated
tokens, space-bearing tokens wrapped in ``{...}``) WITHOUT touching the
backslashes, so UNC drops survive. These tests pin that helper and drive
``App._on_drop`` with a stubbed Tk object — no GUI, no tkinterdnd2.
"""
from __future__ import annotations

import types

import pytest

pytest.importorskip("tkinter")

from app.app import App, _split_dnd_paths


# --- the pure splitter -------------------------------------------------

def test_braced_unc_with_space_keeps_double_backslash():
    raw = r"{\\server\share\my file.mp4}"
    assert _split_dnd_paths(raw) == [r"\\server\share\my file.mp4"]


def test_braced_unc_without_space():
    # tkdnd still braces some tokens; a UNC with no space must survive too.
    raw = r"{\\server\share\clip.mp4}"
    assert _split_dnd_paths(raw) == [r"\\server\share\clip.mp4"]


def test_bare_unc_without_space():
    # No braces at all (no space in the path) — passes through verbatim.
    raw = r"\\server\share\clip.mp4"
    assert _split_dnd_paths(raw) == [r"\\server\share\clip.mp4"]


def test_plain_local_path():
    raw = r"C:\path\file.mp4"
    assert _split_dnd_paths(raw) == [r"C:\path\file.mp4"]


def test_local_path_with_space_is_braced():
    raw = r"{C:\my videos\file.mp4}"
    assert _split_dnd_paths(raw) == [r"C:\my videos\file.mp4"]


def test_mapped_drive_path():
    raw = r"Z:\clip.mp4"
    assert _split_dnd_paths(raw) == [r"Z:\clip.mp4"]


def test_multi_file_drop_mixed():
    raw = r"C:\a.mp4 {\\server\share\my file.mp4} Z:\c.mp4"
    assert _split_dnd_paths(raw) == [
        r"C:\a.mp4",
        r"\\server\share\my file.mp4",
        r"Z:\c.mp4",
    ]


def test_empty_and_whitespace():
    assert _split_dnd_paths("") == []
    assert _split_dnd_paths("   ") == []


def test_unbalanced_brace_takes_remainder():
    raw = r"{\\server\share\file.mp4"
    assert _split_dnd_paths(raw) == [r"\\server\share\file.mp4"]


# --- _on_drop end-to-end with a stubbed Tk -----------------------------

class _FakeVar:
    def __init__(self) -> None:
        self.value: str = ""

    def set(self, v: str) -> None:
        self.value = v


class _FakeNotebook:
    def __init__(self) -> None:
        self.selected = None

    def select(self, tab) -> None:  # noqa: ANN001
        self.selected = tab


def _fake_app() -> types.SimpleNamespace:
    """A minimal stand-in exposing only what _on_drop touches."""
    return types.SimpleNamespace(
        fv=_FakeVar(),
        nb=_FakeNotebook(),
        t1="transcribe-tab",
        t3="download-tab",
        enqueued=[],
        logs=[],
        log=lambda msg: None,  # set below to capture
        add=lambda: None,
    )


def _drive(app: types.SimpleNamespace, raw: str) -> None:
    app.log = app.logs.append
    # add() in the multi-file branch enqueues whatever fv currently holds.
    app.add = lambda: app.enqueued.append(app.fv.value)
    event = types.SimpleNamespace(data=raw)
    App._on_drop(app, event)  # type: ignore[arg-type]


def test_on_drop_accepts_unc_file(monkeypatch):
    """A single dragged UNC file lands in the Transcribe field intact."""
    unc = r"\\server\share\my file.mp4"
    monkeypatch.setattr("app.app.os.path.isfile", lambda s: s == unc)
    app = _fake_app()
    _drive(app, r"{\\server\share\my file.mp4}")
    assert app.fv.value == unc
    assert app.nb.selected == app.t1


def test_on_drop_local_file_still_works(monkeypatch):
    local = r"C:\videos\clip.mp4"
    monkeypatch.setattr("app.app.os.path.isfile", lambda s: s == local)
    app = _fake_app()
    _drive(app, local)
    assert app.fv.value == local
    assert app.nb.selected == app.t1


def test_on_drop_multi_file_enqueues_each(monkeypatch):
    files = {r"C:\a.mp4", r"\\server\share\my file.mp4", r"Z:\c.mp4"}
    monkeypatch.setattr("app.app.os.path.isfile", lambda s: s in files)
    app = _fake_app()
    _drive(app, r"C:\a.mp4 {\\server\share\my file.mp4} Z:\c.mp4")
    assert set(app.enqueued) == files


def test_on_drop_url_routes_to_download_tab(monkeypatch):
    monkeypatch.setattr("app.app.os.path.isfile", lambda s: False)
    app = _fake_app()
    app.download_url_var = _FakeVar()
    _drive(app, "https://example.com/video")
    assert app.download_url_var.value == "https://example.com/video"
    assert app.nb.selected == app.t3
