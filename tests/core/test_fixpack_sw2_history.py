"""Regression test for ``HistoryDB.stats()`` top_languages status gating.

The documented contract for ``stats()`` is that cancelled / non-finished
rows are not counted (every other aggregate gates on ``status='finished'``).
Before the fix the ``top_languages`` query counted ALL transcriptions
regardless of status, so a cancelled row's language leaked into the
breakdown. This test pins the gating.
"""
from __future__ import annotations

import pytest

from core.history import HistoryDB


@pytest.fixture
def db(tmp_path):
    db = HistoryDB(tmp_path / "history.db")
    yield db
    db.close()


def test_top_languages_excludes_non_finished(db):
    # A finished transcription in English...
    fin = db.insert_transcription("/tmp/fin.wav", language="en")
    db.finish_transcription(fin, "finished", duration_seconds=10.0,
                            language="en")
    # ...and a cancelled transcription in a *different* language.
    cancelled = db.insert_transcription("/tmp/cancel.wav", language="fr")
    db.finish_transcription(cancelled, "cancelled", language="fr")

    langs = dict(db.stats()["top_languages"])

    # Only the finished language is counted; the cancelled one is gone.
    assert langs == {"en": 1}
    assert "fr" not in langs
