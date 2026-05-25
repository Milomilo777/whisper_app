"""Transcript outputs get an index instead of overwriting a previous run.

Re-transcribing a file used to overwrite its earlier .srt/.json. Now a
shared index is appended so the previous outputs survive:
name.srt + name.json -> name (1).srt + name (1).json (together).
"""
from __future__ import annotations

import os

import core.transcriber as t


def test_indexed_path():
    assert t._indexed_path("/a/b/video.srt", 0) == "/a/b/video.srt"
    assert t._indexed_path("/a/b/video.srt", 1) == "/a/b/video (1).srt"
    assert t._indexed_path("/a/b/video.srt", 2) == "/a/b/video (2).srt"
    # Only the final extension is split off.
    assert t._indexed_path("/a/b/my.clip.json", 1) == "/a/b/my.clip (1).json"


def test_write_outputs_indexes_instead_of_overwriting(tmp_path, monkeypatch):
    # Stub the writers so no real model / transcription is needed.
    monkeypatch.setattr(t, "supported_formats", lambda: {"srt", "json"})
    monkeypatch.setattr(t, "is_binary", lambda f: False)
    monkeypatch.setattr(t, "get_writer", lambda f: (lambda seg, audio: f"{f}-data"))
    monkeypatch.setitem(t.config, "output_formats", ["srt", "json"])
    monkeypatch.setitem(t.config, "output_filename_template", "{base}.{ext}")

    base = str(tmp_path / "clip")
    first = sorted(os.path.basename(p) for p in
                   t._write_outputs(base, [], "audio.wav", formats=["srt", "json"]))
    second = sorted(os.path.basename(p) for p in
                    t._write_outputs(base, [], "audio.wav", formats=["srt", "json"]))
    third = sorted(os.path.basename(p) for p in
                   t._write_outputs(base, [], "audio.wav", formats=["srt", "json"]))

    assert first == ["clip.json", "clip.srt"]
    assert second == ["clip (1).json", "clip (1).srt"]   # shared index, no overwrite
    assert third == ["clip (2).json", "clip (2).srt"]
    # The original first-run files must still be on disk.
    assert (tmp_path / "clip.srt").exists()
    assert (tmp_path / "clip.json").exists()


def test_write_outputs_shares_one_index_across_formats(tmp_path, monkeypatch):
    # If only ONE of the set exists, both formats jump to the same next
    # index — never a mismatched name (1).srt + name.json pair.
    monkeypatch.setattr(t, "supported_formats", lambda: {"srt", "json"})
    monkeypatch.setattr(t, "is_binary", lambda f: False)
    monkeypatch.setattr(t, "get_writer", lambda f: (lambda seg, audio: f"{f}-data"))
    monkeypatch.setitem(t.config, "output_formats", ["srt", "json"])
    monkeypatch.setitem(t.config, "output_filename_template", "{base}.{ext}")

    base = str(tmp_path / "clip")
    (tmp_path / "clip.srt").write_text("pre-existing", encoding="utf-8")  # only srt exists

    out = sorted(os.path.basename(p) for p in
                 t._write_outputs(base, [], "audio.wav", formats=["srt", "json"]))
    assert out == ["clip (1).json", "clip (1).srt"]
    assert (tmp_path / "clip.srt").read_text(encoding="utf-8") == "pre-existing"
