"""SQLite history of downloads + transcriptions.

Schema is created on first open and is idempotent. Database lives at
``user_data_dir() / "history.db"``. Calls are cheap (one connection per
HistoryDB instance) and use ``with conn`` blocks to commit-or-rollback.

The Tk app does not call this from the main thread for long queries — but
small writes (insert / mark_finished / mark_interrupted) are fast enough.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

from .config import user_data_dir

logger = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    title TEXT,
    folder TEXT,
    format_label TEXT,
    status TEXT NOT NULL,
    started_at INTEGER,
    finished_at INTEGER,
    output_paths TEXT,
    detected_language TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS transcriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    model TEXT,
    status TEXT NOT NULL,
    started_at INTEGER,
    finished_at INTEGER,
    duration_seconds REAL,
    language TEXT,
    output_paths TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status);
CREATE INDEX IF NOT EXISTS idx_transcriptions_status ON transcriptions(status);
"""


def default_db_path() -> Path:
    return user_data_dir() / "history.db"


class HistoryDB:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path: Path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False — the transcription / download
        # services dispatch from worker threads, not the Tk main
        # thread. Without this flag every cross-thread insert
        # raises sqlite3.ProgrammingError (silently swallowed by
        # the callers' broad `except Exception`), so the entire
        # history is empty in real usage.
        self._conn = sqlite3.connect(
            str(self.path), check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        # Module-level write lock — SQLite serialises writes
        # internally but the Python connection object is not
        # thread-safe for concurrent write attempts; the lock
        # gives us deterministic queue + commit semantics.
        self._write_lock = threading.Lock()
        with self._conn:
            self._conn.executescript(SCHEMA)

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001
            pass

    def __enter__(self) -> "HistoryDB":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @contextmanager
    def _txn(self):
        # Serialise all writes through _write_lock so concurrent
        # worker-thread inserts (transcription + download services
        # both fire from background threads) never trample each
        # other's commit boundaries.
        try:
            with self._write_lock, self._conn:
                yield self._conn
        except sqlite3.Error as e:
            logger.error("history.db transaction failed: %s", e)
            raise

    # ----- downloads --------------------------------------------------

    def insert_download(self, url: str, title: str = "", folder: str = "",
                        format_label: str = "", started_at: int | None = None) -> int:
        started_at = started_at if started_at is not None else int(time.time())
        with self._txn() as conn:
            cur = conn.execute(
                "INSERT INTO downloads (url, title, folder, format_label, status, started_at)"
                " VALUES (?, ?, ?, ?, 'running', ?)",
                (url, title, folder, format_label, started_at),
            )
            return int(cur.lastrowid or 0)

    def finish_download(self, row_id: int, status: str,
                        output_paths: Iterable[str] = (),
                        detected_language: str = "",
                        error: str = "") -> None:
        paths_json = json.dumps(list(output_paths))
        with self._txn() as conn:
            conn.execute(
                "UPDATE downloads SET status=?, finished_at=?, output_paths=?,"
                " detected_language=?, error=? WHERE id=?",
                (status, int(time.time()), paths_json, detected_language, error, row_id),
            )

    def list_downloads(self, limit: int = 200) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT * FROM downloads ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [_row_to_dict(r, ("output_paths",)) for r in cur.fetchall()]

    # ----- transcriptions ---------------------------------------------

    def insert_transcription(self, file_path: str, model: str = "",
                             started_at: int | None = None,
                             language: str = "") -> int:
        started_at = started_at if started_at is not None else int(time.time())
        with self._txn() as conn:
            cur = conn.execute(
                "INSERT INTO transcriptions (file_path, model, status, started_at, language)"
                " VALUES (?, ?, 'running', ?, ?)",
                (file_path, model, started_at, language),
            )
            return int(cur.lastrowid or 0)

    def finish_transcription(self, row_id: int, status: str,
                             output_paths: Iterable[str] = (),
                             duration_seconds: float = 0.0,
                             language: str = "",
                             error: str = "") -> None:
        paths_json = json.dumps(list(output_paths))
        with self._txn() as conn:
            conn.execute(
                "UPDATE transcriptions SET status=?, finished_at=?,"
                " output_paths=?, duration_seconds=?, language=?, error=? WHERE id=?",
                (status, int(time.time()), paths_json, duration_seconds, language, error, row_id),
            )

    def list_transcriptions(self, limit: int = 200) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT * FROM transcriptions ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [_row_to_dict(r, ("output_paths",)) for r in cur.fetchall()]

    # ----- maintenance -------------------------------------------------

    def mark_interrupted(self) -> int:
        """Move every still-running row to ``interrupted``. Returns rows touched."""
        with self._txn() as conn:
            d = conn.execute(
                "UPDATE downloads SET status='interrupted' WHERE status IN ('running','waiting')"
            ).rowcount
            t = conn.execute(
                "UPDATE transcriptions SET status='interrupted' WHERE status IN ('running','waiting')"
            ).rowcount
        return int(d) + int(t)

    def stats(self) -> dict[str, Any]:
        """Quick stats for the Statistics dialog."""
        rows = {}
        rows["downloads_total"] = self._conn.execute("SELECT COUNT(*) FROM downloads").fetchone()[0]
        rows["downloads_finished"] = self._conn.execute(
            "SELECT COUNT(*) FROM downloads WHERE status='finished'"
        ).fetchone()[0]
        rows["transcriptions_total"] = self._conn.execute(
            "SELECT COUNT(*) FROM transcriptions"
        ).fetchone()[0]
        rows["transcriptions_finished"] = self._conn.execute(
            "SELECT COUNT(*) FROM transcriptions WHERE status='finished'"
        ).fetchone()[0]
        rows["transcription_minutes"] = round(
            (self._conn.execute(
                "SELECT COALESCE(SUM(duration_seconds), 0) FROM transcriptions WHERE status='finished'"
            ).fetchone()[0] or 0) / 60.0,
            1,
        )
        top_langs = self._conn.execute(
            "SELECT language, COUNT(*) c FROM transcriptions WHERE language != '' "
            "GROUP BY language ORDER BY c DESC LIMIT 5"
        ).fetchall()
        rows["top_languages"] = [(r[0], int(r[1])) for r in top_langs]
        return rows


def _row_to_dict(row: sqlite3.Row, json_fields: tuple[str, ...]) -> dict[str, Any]:
    out = dict(row)
    for key in json_fields:
        raw = out.get(key)
        if raw:
            try:
                out[key] = json.loads(raw)
            except (TypeError, ValueError):
                pass
    return out
