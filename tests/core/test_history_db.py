"""Tests for ``core.history.HistoryDB`` — schema + CRUD + maintenance."""
from __future__ import annotations

import sqlite3
import time

import pytest

from core.history import HistoryDB


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "history.db"
    db = HistoryDB(path)
    yield db
    db.close()


def test_schema_creates_two_tables(db, tmp_path):
    conn = sqlite3.connect(str(tmp_path / "history.db"))
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "downloads" in names
    assert "transcriptions" in names
    conn.close()


def test_open_is_idempotent(tmp_path):
    HistoryDB(tmp_path / "h.db").close()
    db2 = HistoryDB(tmp_path / "h.db")
    db2.close()


def test_insert_and_finish_download(db):
    rid = db.insert_download("https://x", title="T", folder="/tmp", format_label="mp4")
    assert rid > 0
    db.finish_download(rid, "finished",
                       output_paths=["/tmp/T.mp4", "/tmp/T.srt"],
                       detected_language="en")
    rows = db.list_downloads()
    assert rows[0]["status"] == "finished"
    assert rows[0]["output_paths"] == ["/tmp/T.mp4", "/tmp/T.srt"]
    assert rows[0]["detected_language"] == "en"


def test_insert_and_finish_transcription(db):
    rid = db.insert_transcription("/tmp/x.wav", model="tiny.en", language="en")
    db.finish_transcription(rid, "finished",
                            output_paths=["/tmp/x.srt"],
                            duration_seconds=12.5,
                            language="en")
    rows = db.list_transcriptions()
    assert rows[0]["status"] == "finished"
    assert rows[0]["duration_seconds"] == 12.5
    assert rows[0]["output_paths"] == ["/tmp/x.srt"]


def test_list_orders_by_id_desc(db):
    a = db.insert_download("https://a")
    b = db.insert_download("https://b")
    rows = db.list_downloads()
    assert rows[0]["id"] == b
    assert rows[1]["id"] == a


def test_list_respects_limit(db):
    for i in range(15):
        db.insert_download(f"https://x{i}")
    rows = db.list_downloads(limit=5)
    assert len(rows) == 5


def test_mark_interrupted_moves_running_rows(db):
    rd = db.insert_download("https://x")
    rt = db.insert_transcription("/tmp/x.wav")
    db.finish_download(rd, "finished")  # this one shouldn't move
    rd2 = db.insert_download("https://y")  # still running
    touched = db.mark_interrupted()
    assert touched == 2
    statuses = {row["id"]: row["status"] for row in db.list_downloads()}
    assert statuses[rd] == "finished"
    assert statuses[rd2] == "interrupted"
    t_status = db.list_transcriptions()[0]["status"]
    assert t_status == "interrupted"


def test_stats_basic_counts(db):
    a = db.insert_download("https://a")
    db.finish_download(a, "finished", output_paths=["/tmp/a.mp4"])
    rt = db.insert_transcription("/tmp/x.wav", language="en")
    db.finish_transcription(rt, "finished", duration_seconds=120.0, language="en")
    rt2 = db.insert_transcription("/tmp/y.wav", language="fa")
    db.finish_transcription(rt2, "finished", duration_seconds=60.0, language="fa")
    s = db.stats()
    assert s["downloads_total"] == 1
    assert s["downloads_finished"] == 1
    assert s["transcriptions_total"] == 2
    assert s["transcriptions_finished"] == 2
    assert s["transcription_minutes"] == 3.0
    langs = dict(s["top_languages"])
    assert langs["en"] == 1
    assert langs["fa"] == 1


def test_finish_download_records_error_string(db):
    rid = db.insert_download("https://x")
    db.finish_download(rid, "error", error="connection reset")
    row = db.list_downloads()[0]
    assert row["status"] == "error"
    assert row["error"] == "connection reset"


def test_started_at_defaults_to_now(db):
    before = int(time.time())
    rid = db.insert_download("https://x")
    after = int(time.time())
    row = db.list_downloads()[0]
    assert before <= row["started_at"] <= after


def test_context_manager_closes_connection(tmp_path):
    with HistoryDB(tmp_path / "h.db") as db:
        rid = db.insert_download("https://x")
        assert rid > 0
    # Re-opening proves the file survives close()
    db2 = HistoryDB(tmp_path / "h.db")
    assert db2.list_downloads()[0]["url"] == "https://x"
    db2.close()
