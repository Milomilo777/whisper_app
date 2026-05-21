"""Tests for cross-transcript search (FTS5 + semantic)."""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import pytest

from core import search as sm


# ---------- availability -------------------------------------------------------


def test_semantic_available_false_when_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    assert sm.semantic_available() is False


# ---------- BLOB pack ----------------------------------------------------------


def test_vector_blob_round_trip():
    vec = [1.0, -2.5, 3.25, 0.0, 1e-3]
    blob = sm._vector_to_blob(vec)
    out = sm._blob_to_vector(blob, len(vec))
    assert len(out) == len(vec)
    for a, b in zip(vec, out):
        assert abs(a - b) < 1e-5


def test_blob_to_vector_returns_empty_on_short_payload():
    assert sm._blob_to_vector(b"", 4) == []
    assert sm._blob_to_vector(b"\x00", 4) == []


# ---------- index_file ---------------------------------------------------------


def _write_transcript(path: Path, segments) -> None:
    path.write_text(json.dumps(segments, ensure_ascii=False), encoding="utf-8")


def _open_db_at(tmp_path: Path):
    conn = sm._open_db(tmp_path / "search.db")
    return conn


def test_index_file_indexes_only_segments_with_text(tmp_path):
    p = tmp_path / "t.json"
    _write_transcript(p, [
        {"start": 0.0, "end": 1.0, "text": "Welcome back."},
        {"start": 1.0, "end": 2.0, "text": ""},
        {"start": 2.0, "end": 3.0, "text": "Second sentence."},
    ])
    conn = _open_db_at(tmp_path)
    try:
        n = sm.index_file(str(p), conn=conn)
        assert n == 2
        rows = conn.execute("SELECT text FROM segments_fts").fetchall()
        texts = sorted(r["text"] for r in rows)
        assert texts == ["Second sentence.", "Welcome back."]
    finally:
        conn.close()


def test_index_file_skips_unchanged_file(tmp_path):
    p = tmp_path / "t.json"
    _write_transcript(p, [{"start": 0.0, "end": 1.0, "text": "hello"}])
    conn = _open_db_at(tmp_path)
    try:
        sm.index_file(str(p), conn=conn)
        # Second call must return 0 (no reindex needed).
        n = sm.index_file(str(p), conn=conn)
        assert n == 0
    finally:
        conn.close()


def test_index_file_reindexes_when_file_changes(tmp_path):
    p = tmp_path / "t.json"
    _write_transcript(p, [{"start": 0.0, "end": 1.0, "text": "old text"}])
    conn = _open_db_at(tmp_path)
    try:
        sm.index_file(str(p), conn=conn)
        # Bump mtime + change content.
        _write_transcript(p, [{"start": 0.0, "end": 1.0, "text": "new text"}])
        import os, time
        new_mtime = p.stat().st_mtime + 10
        os.utime(str(p), (new_mtime, new_mtime))
        n = sm.index_file(str(p), conn=conn)
        assert n == 1
        rows = conn.execute("SELECT text FROM segments_fts").fetchall()
        assert rows[0]["text"] == "new text"
    finally:
        conn.close()


def test_index_file_handles_missing_json(tmp_path):
    conn = _open_db_at(tmp_path)
    try:
        # Should not raise.
        n = sm.index_file(str(tmp_path / "missing.json"), conn=conn)
        assert n == 0
    finally:
        conn.close()


def test_index_file_handles_invalid_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid", encoding="utf-8")
    conn = _open_db_at(tmp_path)
    try:
        n = sm.index_file(str(p), conn=conn)
        assert n == 0
    finally:
        conn.close()


# ---------- FTS5 query ---------------------------------------------------------


def test_search_fts_finds_keyword(tmp_path):
    p = tmp_path / "t.json"
    _write_transcript(p, [
        {"start": 0.0, "end": 1.0, "text": "The cat sat on the mat."},
        {"start": 1.0, "end": 2.0, "text": "The dog ran fast."},
    ])
    conn = _open_db_at(tmp_path)
    try:
        sm.index_file(str(p), conn=conn)
        hits = sm.search("cat", conn=conn)
        assert len(hits) == 1
        assert "cat" in hits[0].text
        assert hits[0].score > 0
        assert hits[0].segment_index == 0
    finally:
        conn.close()


def test_search_empty_query_returns_empty(tmp_path):
    conn = _open_db_at(tmp_path)
    try:
        assert sm.search("", conn=conn) == []
        assert sm.search("   ", conn=conn) == []
    finally:
        conn.close()


def test_search_no_match_returns_empty(tmp_path):
    p = tmp_path / "t.json"
    _write_transcript(p, [{"start": 0.0, "end": 1.0, "text": "hello world"}])
    conn = _open_db_at(tmp_path)
    try:
        sm.index_file(str(p), conn=conn)
        assert sm.search("zebra", conn=conn) == []
    finally:
        conn.close()


def test_search_tolerates_punctuation_in_query(tmp_path):
    """FTS5 panics on raw `:` in MATCH; our wrapper must quote it."""
    p = tmp_path / "t.json"
    _write_transcript(p, [{"start": 0.0, "end": 1.0, "text": "see also: nothing"}])
    conn = _open_db_at(tmp_path)
    try:
        sm.index_file(str(p), conn=conn)
        # No assert on result content — just that the call doesn't raise.
        sm.search("see also:", conn=conn)
    finally:
        conn.close()


# ---------- semantic with mocked embedder --------------------------------------


class _FakeEmbedder:
    """Deterministic 4-d embedder for tests — returns one-hot vectors by keyword."""

    def __init__(self):
        self.calls = 0

    def embed(self, text: str) -> list[float]:
        self.calls += 1
        t = text.lower()
        if "cat" in t:
            return [1.0, 0.0, 0.0, 0.0]
        if "dog" in t:
            return [0.0, 1.0, 0.0, 0.0]
        if "car" in t:
            return [0.0, 0.0, 1.0, 0.0]
        return [0.0, 0.0, 0.0, 1.0]


def test_semantic_search_ranks_by_cosine(tmp_path):
    p = tmp_path / "t.json"
    _write_transcript(p, [
        {"start": 0.0, "end": 1.0, "text": "a cat sat there"},
        {"start": 1.0, "end": 2.0, "text": "the dog ran fast"},
        {"start": 2.0, "end": 3.0, "text": "a car drove past"},
    ])
    conn = _open_db_at(tmp_path)
    embedder = _FakeEmbedder()
    try:
        sm.index_file(str(p), conn=conn, embedder=embedder)
        hits = sm.search("a cat is friendly", conn=conn, embedder=embedder)
        assert len(hits) == 3
        # Top hit must be the "cat" segment (cosine 1.0 with embedder).
        assert "cat" in hits[0].text
        # Score ordering descending.
        scores = [h.score for h in hits]
        assert scores == sorted(scores, reverse=True)
    finally:
        conn.close()


def test_indexed_files_table_tracks_one_row_per_file(tmp_path):
    p = tmp_path / "t.json"
    _write_transcript(p, [{"start": 0.0, "end": 1.0, "text": "x"}])
    conn = _open_db_at(tmp_path)
    try:
        sm.index_file(str(p), conn=conn)
        sm.index_file(str(p), conn=conn)  # idempotent
        rows = conn.execute("SELECT * FROM indexed_files").fetchall()
        assert len(rows) == 1
        assert rows[0]["json_path"] == str(p)
    finally:
        conn.close()
