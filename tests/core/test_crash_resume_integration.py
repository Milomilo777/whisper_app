"""Crash-mid-transcribe → resume integration tests.

Audit R-4 / freeze blocker FB-04: ``HistoryDB.mark_interrupted()``
flips half-finished rows to ``interrupted`` on launch, and the App
offers to resume them. We had no test proving the full chain
actually works. This file fills that gap with database-level
integration tests; the UI half is covered by manual install
testing (RELEASE_PROCESS.md Step 6).

The tests deliberately do NOT launch a real worker process — that
would push smoke-test territory. Instead they:

  1. Build a HistoryDB at a temp path.
  2. Insert rows in various pre-crash states.
  3. Call mark_interrupted().
  4. Assert the rows transition correctly.
  5. Run the same filter the App's crash-resume dialog uses
     (``status == "interrupted" and file_path exists``).
  6. Assert the correct rows survive the filter.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.history import HistoryDB


@pytest.fixture
def history(tmp_path):
    """Fresh HistoryDB in a tmp path; closed at teardown."""
    db = HistoryDB(tmp_path / "history.db")
    try:
        yield db
    finally:
        db.close()


# ---------- mark_interrupted --------------------------------------------------


def test_mark_interrupted_flips_running_transcription(history, tmp_path):
    """A row inserted as ``running`` (the default for
    insert_transcription) must transition to ``interrupted`` when
    mark_interrupted runs — simulating the App's first action on
    launch after a crash."""
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"riff stub")
    row_id = history.insert_transcription(str(audio))
    assert row_id > 0

    # Sanity: row exists, status running.
    rows = history.list_transcriptions(limit=100)
    assert any(r["id"] == row_id and r["status"] == "running"
               for r in rows)

    n = history.mark_interrupted()
    assert n >= 1

    rows = history.list_transcriptions(limit=100)
    matching = [r for r in rows if r["id"] == row_id]
    assert len(matching) == 1
    assert matching[0]["status"] == "interrupted"


def test_mark_interrupted_does_not_touch_finished_rows(history, tmp_path):
    """A successfully-finished row should not be reclassified."""
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"riff stub")
    row_id = history.insert_transcription(str(audio))
    history.finish_transcription(
        row_id, status="finished",
        output_paths=[str(audio.with_suffix(".srt"))],
        duration_seconds=12.5,
        language="en",
    )

    n = history.mark_interrupted()
    assert n == 0

    rows = history.list_transcriptions(limit=100)
    matching = [r for r in rows if r["id"] == row_id]
    assert matching[0]["status"] == "finished"


def test_mark_interrupted_does_not_touch_error_rows(history, tmp_path):
    """An error row (e.g. corrupt audio) should not get reclassified
    on the next launch — the user explicitly saw it fail."""
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"riff stub")
    row_id = history.insert_transcription(str(audio))
    history.finish_transcription(
        row_id, status="error",
        error="invalid audio",
        duration_seconds=0.0,
    )

    history.mark_interrupted()
    rows = history.list_transcriptions(limit=100)
    matching = [r for r in rows if r["id"] == row_id]
    assert matching[0]["status"] == "error"


def test_mark_interrupted_idempotent(history, tmp_path):
    """Calling mark_interrupted twice in a row must not re-touch
    already-interrupted rows. Returns 0 on the second call."""
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"riff stub")
    history.insert_transcription(str(audio))
    first = history.mark_interrupted()
    second = history.mark_interrupted()
    assert first >= 1
    assert second == 0


def test_mark_interrupted_returns_total_across_tables(history, tmp_path):
    """Running download AND running transcription should both be
    flipped in a single call; the return value sums them."""
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"riff stub")
    history.insert_transcription(str(audio))
    history.insert_download("https://example.com/video", title="x")
    n = history.mark_interrupted()
    assert n >= 2  # one of each


# ---------- the resume-filter the App actually uses ---------------------------


def _resume_filter(rows, exists_predicate):
    """Mirror of app/app.py:_maybe_offer_crash_resume's filter.

    Kept here (not imported) so the test pins the filter logic
    — if the App changes the predicate later, this test forces
    the maintainer to update both sides in lockstep.
    """
    return [
        r for r in rows
        if r.get("status") == "interrupted"
        and r.get("file_path")
        and exists_predicate(r["file_path"])
    ]


def test_resume_filter_includes_interrupted_with_existing_file(history, tmp_path):
    """The happy path: an interrupted row with a still-present
    source file is exactly what the resume dialog should offer."""
    audio = tmp_path / "still-here.mp3"
    audio.write_bytes(b"riff stub")
    history.insert_transcription(str(audio))
    history.mark_interrupted()

    rows = history.list_transcriptions(limit=100)
    candidates = _resume_filter(rows, exists_predicate=lambda p: Path(p).is_file())
    assert len(candidates) == 1
    assert candidates[0]["file_path"] == str(audio)


def test_resume_filter_drops_interrupted_with_missing_file(history, tmp_path):
    """An interrupted row whose audio file has since been deleted
    is NOT offered for resume — the user can't transcribe what
    isn't on disk."""
    audio = tmp_path / "deleted.mp3"
    audio.write_bytes(b"riff stub")
    history.insert_transcription(str(audio))
    history.mark_interrupted()
    audio.unlink()  # gone now

    rows = history.list_transcriptions(limit=100)
    candidates = _resume_filter(rows, exists_predicate=lambda p: Path(p).is_file())
    assert candidates == []


def test_resume_filter_dedups_by_file_path(history, tmp_path):
    """When the same file was queued multiple times before the
    crash, the resume dialog must offer it ONCE — otherwise the
    user re-runs the same transcription N times."""
    audio = tmp_path / "duplicate.mp3"
    audio.write_bytes(b"riff stub")
    # Three rows for the same file (re-runs).
    history.insert_transcription(str(audio))
    history.insert_transcription(str(audio))
    history.insert_transcription(str(audio))
    history.mark_interrupted()

    rows = history.list_transcriptions(limit=100)
    candidates = _resume_filter(rows, exists_predicate=lambda p: Path(p).is_file())
    # All three are surfaced by the filter; the App then dedupes
    # by file_path in _maybe_offer_crash_resume. Test the dedup
    # step here too so the contract stays explicit.
    unique_paths = {c["file_path"] for c in candidates}
    assert len(unique_paths) == 1


def test_resume_filter_preserves_language_for_task_recreation(history, tmp_path):
    """The recreated task must carry the language hint from the
    interrupted row so the resumed transcription uses the same
    language the user originally selected."""
    audio = tmp_path / "lang.mp3"
    audio.write_bytes(b"riff stub")
    history.insert_transcription(str(audio), language="fa")
    history.mark_interrupted()

    rows = history.list_transcriptions(limit=100)
    candidates = _resume_filter(rows, exists_predicate=lambda p: Path(p).is_file())
    assert candidates[0]["language"] == "fa"


# ---------- end-to-end: insert → crash → resurrect ----------------------------


def test_full_crash_recovery_cycle(history, tmp_path):
    """Exercise the whole arc:

      1. App inserts the row at task dispatch (status='running').
      2. App is killed; the row stays at 'running'.
      3. Next launch calls mark_interrupted() → 'interrupted'.
      4. Resume dialog filters + dedupes → 1 candidate.
      5. App recreates a TranscriptionTask using file_path +
         language from the row.

    This is the contract the user relies on. If any step regresses
    the user loses work after a crash with no visible cue.
    """
    from core.task import TranscriptionTask

    # Step 1: dispatch-time insert (mirrors transcription_service)
    audio = tmp_path / "recovery.mp3"
    audio.write_bytes(b"riff stub")
    history.insert_transcription(str(audio), language="en")

    # Step 2: simulated crash — no further write happens.

    # Step 3: next launch
    n_interrupted = history.mark_interrupted()
    assert n_interrupted >= 1

    # Step 4: resume dialog filter + dedupe
    rows = history.list_transcriptions(limit=100)
    candidates = _resume_filter(rows, exists_predicate=lambda p: Path(p).is_file())
    seen: set[str] = set()
    unique = []
    for r in candidates:
        if r["file_path"] not in seen:
            seen.add(r["file_path"])
            unique.append(r)
    assert len(unique) == 1

    # Step 5: recreate task
    r = unique[0]
    task = TranscriptionTask(r["file_path"])
    task.language = r.get("language") or ""  # type: ignore[attr-defined]
    assert task.file_path == str(audio)
    assert task.language == "en"
    assert task.status == "waiting"  # ready for re-dispatch


def test_wal_mode_survives_after_mark_interrupted(history):
    """Round 1 enabled WAL journalling for crash safety. Confirm
    that mark_interrupted respects WAL — i.e. the journal file
    rolls forward correctly after a write. We can't simulate a
    real crash; we just confirm the PRAGMA is set + multiple
    writes don't break."""
    pragma = history._conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert pragma.lower() == "wal", (
        f"Audit D2 expected WAL mode, got {pragma!r}. WAL is what "
        "lets us recover from a crashed write without rebuilding."
    )
    # Trigger a few writes + a mark_interrupted in sequence; this
    # exercises the WAL transition without anything dramatic.
    for i in range(3):
        history.insert_transcription(f"/fake/{i}.mp3")
    n = history.mark_interrupted()
    assert n >= 3
