"""Search across saved transcripts (v0.8 Phase 3).

Two engines, picked at query time based on what's available:

  * **Semantic** — embed every segment with
    ``sentence-transformers/all-MiniLM-L6-v2`` (~22 MB, ONNX),
    store the vectors in a sidecar SQLite table, query via cosine
    similarity. Best result quality but the dep is heavy.
  * **FTS5** — sqlite's built-in full-text index on the segment
    text column. Works on the stock library, no extra dep, fast
    enough on ~50k segments. Worse on synonyms / paraphrase.

The :func:`search` function tries semantic first when available
and falls back to FTS5 transparently. Same return shape from
both: a list of :class:`SearchHit` (json_path + segment_index +
text + score + start_seconds).

Both engines walk the existing ``history.db`` to discover saved
transcripts; the JSON file next to each row is the source of
truth for segment text. No duplication of segment data — only
the embeddings live in their own table.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .config import user_data_dir

logger = logging.getLogger(__name__)


SEARCH_DB_NAME = "search.db"


def search_db_path() -> Path:
    return user_data_dir() / SEARCH_DB_NAME


# ---------------------------------------------------------------- availability


def semantic_available() -> bool:
    """True iff sentence-transformers (or a minimal substitute) is importable."""
    try:
        import sentence_transformers  # type: ignore[import-not-found] # noqa: F401
    except ImportError:
        return False
    return True


def semantic_availability_reason() -> str:
    if semantic_available():
        return ""
    return (
        "sentence-transformers not installed — `pip install "
        "sentence-transformers` to enable semantic search. Falling "
        "back to keyword search (FTS5)."
    )


# ---------------------------------------------------------------- result type


@dataclass
class SearchHit:
    json_path: str
    segment_index: int
    text: str
    score: float
    start_seconds: float = 0.0
    end_seconds: float = 0.0


# ---------------------------------------------------------------- index schema


_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
    json_path UNINDEXED,
    segment_index UNINDEXED,
    text,
    start_seconds UNINDEXED,
    end_seconds UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS embeddings (
    json_path TEXT NOT NULL,
    segment_index INTEGER NOT NULL,
    vector BLOB NOT NULL,
    dim INTEGER NOT NULL,
    PRIMARY KEY (json_path, segment_index)
);
CREATE TABLE IF NOT EXISTS indexed_files (
    json_path TEXT PRIMARY KEY,
    mtime REAL,
    size INTEGER
);
"""


def _open_db(path: Path | None = None) -> sqlite3.Connection:
    p = path if path is not None else search_db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.executescript(_FTS_SCHEMA)
    return conn


# ---------------------------------------------------------------- indexing


def _read_segments(json_path: str) -> list[dict[str, Any]]:
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [s for s in data if isinstance(s, dict)]


def _file_needs_reindex(conn: sqlite3.Connection, json_path: str) -> bool:
    try:
        st = os.stat(json_path)
    except OSError:
        return False
    cur = conn.execute(
        "SELECT mtime, size FROM indexed_files WHERE json_path=?",
        (json_path,),
    )
    row = cur.fetchone()
    if row is None:
        return True
    return abs(float(row["mtime"]) - float(st.st_mtime)) > 0.5 or int(row["size"]) != int(st.st_size)


def _mark_file_indexed(conn: sqlite3.Connection, json_path: str) -> None:
    try:
        st = os.stat(json_path)
    except OSError:
        return
    conn.execute(
        "INSERT OR REPLACE INTO indexed_files (json_path, mtime, size) "
        "VALUES (?, ?, ?)",
        (json_path, float(st.st_mtime), int(st.st_size)),
    )


def index_file(
    json_path: str,
    *,
    conn: sqlite3.Connection | None = None,
    embedder: "Embedder | None" = None,
) -> int:
    """Reindex one transcript JSON. Returns segment count indexed.

    Idempotent: re-running on the same unchanged file is a no-op
    (size + mtime cache check). When ``embedder`` is provided, also
    writes per-segment vectors into the ``embeddings`` table.
    """
    owns_conn = conn is None
    conn = conn or _open_db()
    try:
        if not _file_needs_reindex(conn, json_path):
            return 0
        segments = _read_segments(json_path)
        with conn:
            conn.execute(
                "DELETE FROM segments_fts WHERE json_path=?", (json_path,)
            )
            conn.execute(
                "DELETE FROM embeddings WHERE json_path=?", (json_path,)
            )
            for idx, seg in enumerate(segments):
                text = (seg.get("text") or "").strip()
                if not text:
                    continue
                start = float(seg.get("start", 0.0))
                end = float(seg.get("end", start))
                conn.execute(
                    "INSERT INTO segments_fts (json_path, segment_index, "
                    "text, start_seconds, end_seconds) VALUES (?, ?, ?, ?, ?)",
                    (json_path, idx, text, start, end),
                )
                if embedder is not None:
                    vec = embedder.embed(text)
                    conn.execute(
                        "INSERT INTO embeddings (json_path, segment_index, "
                        "vector, dim) VALUES (?, ?, ?, ?)",
                        (json_path, idx, _vector_to_blob(vec), len(vec)),
                    )
            _mark_file_indexed(conn, json_path)
        return sum(1 for seg in segments if (seg.get("text") or "").strip())
    finally:
        if owns_conn:
            conn.close()


def reindex_all_history(
    *,
    embedder: "Embedder | None" = None,
) -> int:
    """Walk history.db, reindex every transcript JSON. Returns rows touched."""
    from .history import HistoryDB

    total = 0
    db_conn = _open_db()
    try:
        with HistoryDB() as hist:
            for row in hist.list_transcriptions(limit=10_000):
                paths = row.get("output_paths") or []
                if isinstance(paths, str):
                    try:
                        paths = json.loads(paths)
                    except json.JSONDecodeError:
                        paths = []
                for p in paths or []:
                    if isinstance(p, str) and p.lower().endswith(".json") and os.path.isfile(p):
                        total += index_file(p, conn=db_conn, embedder=embedder)
    finally:
        db_conn.close()
    return total


# ---------------------------------------------------------------- query


def search(
    query: str,
    *,
    limit: int = 20,
    embedder: "Embedder | None" = None,
    conn: sqlite3.Connection | None = None,
) -> list[SearchHit]:
    """Run the query against whichever engine is best.

    When ``embedder`` is provided we use semantic similarity over the
    pre-computed vectors. Otherwise we fall back to FTS5 keyword
    matching.
    """
    query = (query or "").strip()
    if not query:
        return []
    owns_conn = conn is None
    conn = conn or _open_db()
    try:
        if embedder is not None:
            hits = _semantic_query(conn, query, embedder, limit)
            if hits:
                return hits
        return _fts_query(conn, query, limit)
    finally:
        if owns_conn:
            conn.close()


def _fts_query(conn: sqlite3.Connection, query: str, limit: int) -> list[SearchHit]:
    # FTS5's MATCH grammar wants its own syntax; sanitise common punctuation
    # by quoting the whole query so user-typed `:` etc. don't crash sqlite.
    safe = re.sub(r'"', '""', query)
    cur = conn.execute(
        "SELECT json_path, segment_index, text, start_seconds, end_seconds, "
        "bm25(segments_fts) AS rank FROM segments_fts "
        "WHERE segments_fts MATCH ? ORDER BY rank LIMIT ?",
        (f'"{safe}"', limit),
    )
    rows = cur.fetchall()
    out: list[SearchHit] = []
    for r in rows:
        out.append(SearchHit(
            json_path=str(r["json_path"]),
            segment_index=int(r["segment_index"]),
            text=str(r["text"]),
            # bm25 returns smaller-is-better; convert to 0..1 for UI.
            score=1.0 / (1.0 + max(0.0, float(r["rank"]))),
            start_seconds=float(r["start_seconds"]),
            end_seconds=float(r["end_seconds"]),
        ))
    return out


def _semantic_query(
    conn: sqlite3.Connection,
    query: str,
    embedder: "Embedder",
    limit: int,
) -> list[SearchHit]:
    qvec = embedder.embed(query)
    qnorm = math.sqrt(sum(x * x for x in qvec)) or 1.0
    cur = conn.execute(
        "SELECT e.json_path, e.segment_index, e.vector, e.dim, s.text, "
        "s.start_seconds, s.end_seconds FROM embeddings e "
        "JOIN segments_fts s ON e.json_path = s.json_path "
        "AND e.segment_index = s.segment_index"
    )
    hits: list[SearchHit] = []
    for r in cur.fetchall():
        vec = _blob_to_vector(bytes(r["vector"]), int(r["dim"]))
        if not vec:
            continue
        vnorm = math.sqrt(sum(x * x for x in vec)) or 1.0
        dot = sum(a * b for a, b in zip(qvec, vec))
        score = dot / (qnorm * vnorm)
        hits.append(SearchHit(
            json_path=str(r["json_path"]),
            segment_index=int(r["segment_index"]),
            text=str(r["text"]),
            score=float(score),
            start_seconds=float(r["start_seconds"]),
            end_seconds=float(r["end_seconds"]),
        ))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]


# ---------------------------------------------------------------- embedder


class Embedder:
    """Wraps a sentence-transformers model.

    Construct with ``Embedder(model_name="all-MiniLM-L6-v2")`` —
    the first :meth:`embed` call loads the model lazily so import-
    time stays cheap.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model: Any = None

    def _load(self) -> None:
        if self._model is not None:
            return
        if not semantic_available():
            raise RuntimeError(semantic_availability_reason())
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
        self._model = SentenceTransformer(self.model_name)

    def embed(self, text: str) -> list[float]:
        self._load()
        assert self._model is not None
        vec = self._model.encode(text, normalize_embeddings=False)
        return [float(x) for x in (vec.tolist() if hasattr(vec, "tolist") else vec)]


# ---------------------------------------------------------------- BLOB pack


def _vector_to_blob(vec: Iterable[float]) -> bytes:
    """Pack a float list into a compact little-endian float32 blob."""
    import struct
    return b"".join(struct.pack("<f", float(x)) for x in vec)


def _blob_to_vector(blob: bytes, dim: int) -> list[float]:
    import struct
    if len(blob) < dim * 4:
        return []
    return list(struct.unpack(f"<{dim}f", blob[: dim * 4]))
