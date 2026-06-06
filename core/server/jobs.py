"""Bounded, single-worker transcription job manager for the LAN server.

This module is intentionally Tk-free and imports nothing from ``app/``.
It owns a small in-memory job table and a SINGLE background worker thread
that processes queued jobs one at a time. Sequential processing is a
deliberate design choice, not a limitation:

  * ``core.transcriber`` keeps the ~3 GB Whisper model in a module-global
    (``MODEL`` / ``PIPELINE``). Loading it once and reusing it keeps the
    model HOT across jobs.
  * Running ``transcribe()`` concurrently against that shared global is
    unsafe; one worker thread naturally bounds concurrency to 1.

Each job's media is written into a per-job temp dir under
``user_cache_dir()/server_jobs/<uuid>/``. ``core.transcriber.transcribe``
writes its outputs NEXT TO the input file (the beside-input contract), so
the outputs land in that same per-job dir with no path-traversal risk.

A job is one of:

  * an UPLOAD — raw media bytes the handler streamed into the per-job dir,
  * a URL — an http(s) link downloaded with yt-dlp into the per-job dir
    first, then transcribed.

The transcribe driver is injected (``transcribe_fn``) so tests can run the
whole state machine against a fake that just writes dummy output files —
never the real model.
"""
from __future__ import annotations

import logging
import os
import queue
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from core.config import user_cache_dir

logger = logging.getLogger(__name__)


# --- public types ------------------------------------------------------------

# Status values a job moves through. Terminal states are "finished",
# "error", and "cancelled".
STATUS_QUEUED = "queued"
STATUS_DOWNLOADING = "downloading"
STATUS_RUNNING = "running"
STATUS_FINISHED = "finished"
STATUS_ERROR = "error"
STATUS_CANCELLED = "cancelled"

_TERMINAL = frozenset({STATUS_FINISHED, STATUS_ERROR, STATUS_CANCELLED})


class TranscribeFn(Protocol):
    """The transcribe callable the manager drives.

    Mirrors ``core.transcriber.transcribe`` (task, progress_cb, log_cb,
    language_cb) so the real engine can be passed straight through, while
    tests inject a fake that writes dummy outputs.
    """

    def __call__(
        self,
        task: Any,
        progress_cb: Callable[[int], None] | None = None,
        log_cb: Callable[[str], None] | None = None,
        language_cb: Callable[[str, float], None] | None = None,
    ) -> None: ...


# A callable that downloads an http(s) URL into ``dest_dir`` and returns the
# saved media path. Injected so tests don't hit the network.
DownloadFn = Callable[[str, str], str]


@dataclass
class Job:
    """One transcription request and its live state."""

    job_id: str
    kind: str  # "upload" | "url"
    formats: list[str]
    language: str = ""
    # Source description for history / logging (filename or URL).
    source: str = ""
    status: str = STATUS_QUEUED
    progress: int = 0
    error: str = ""
    # The media file to transcribe (set once an upload lands or a URL is
    # downloaded). Outputs are written beside it.
    media_path: str = ""
    # Per-job working directory; deleted on cleanup.
    work_dir: str = ""
    # Written output files, as (fmt, absolute_path) pairs.
    outputs: list[tuple[str, str]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    finished_at: float = 0.0
    # Cooperative-cancel flag; the transcribe task object mirrors this.
    cancelled: bool = False

    def public_dict(self) -> dict[str, Any]:
        """The JSON shape returned by ``GET /api/jobs/<id>``."""
        return {
            "job_id": self.job_id,
            "status": self.status,
            "progress": self.progress,
            "error": self.error,
            "outputs": [{"fmt": fmt, "name": os.path.basename(p)}
                        for fmt, p in self.outputs],
        }


class _ServerTask:
    """The task object passed to ``transcribe_fn`` for EVERY server job.

    Despite the lean shape, this is NOT a cancel-only helper: it is the one
    task duck-type the engine sees for all LAN/web jobs. It MUST mirror every
    attribute ``core.transcriber.transcribe`` (and ``resume_transcription``)
    reads off a task, or the engine raises ``AttributeError`` mid-run and the
    job dies with no output. Currently read by the engine:

      * ``file_path``, ``language``, ``output_formats`` (inputs)
      * ``output_paths``, ``detected_language``, ``language_probability``
        (written back by the engine)
      * ``resume``, ``clip_start``, ``clip_end``, ``history_id`` (inputs)
      * the cooperative ``cancelled`` flag AND the ``paused`` flag, both read
        bare inside the segment loop (``while task.paused and not
        task.cancelled``). ``paused`` has no UI to flip it on the server, but
        it must EXIST or the loop raises.

    Using a plain object keeps this module free of any ``app/`` task import
    while still satisfying the engine's duck-typed access. Keep this in sync
    with the attributes ``core.transcriber.transcribe`` reads.
    """

    def __init__(self, job: Job) -> None:
        self.file_path: str = job.media_path
        self.language: str | None = job.language or None
        self.output_formats: list[str] | None = list(job.formats) or None
        self.output_paths: list[str] | None = None
        self.detected_language: str = ""
        self.language_probability: float = 0.0
        self.paused: bool = False
        self.resume: bool = False
        self.clip_start: float | None = None
        self.clip_end: float | None = None
        self.history_id: int = 0
        self._job = job

    @property
    def cancelled(self) -> bool:
        return self._job.cancelled

    @cancelled.setter
    def cancelled(self, value: bool) -> None:
        self._job.cancelled = bool(value)


class JobManager:
    """Bounded queue + single worker thread driving transcriptions.

    Thread-safe. The handler thread(s) call :meth:`submit_upload` /
    :meth:`submit_url` / :meth:`get` / :meth:`cancel`; one private worker
    thread runs :meth:`_drain`.
    """

    def __init__(
        self,
        transcribe_fn: TranscribeFn,
        *,
        download_fn: DownloadFn | None = None,
        max_jobs: int = 100,
        max_queued: int = 50,
        record_history: bool = True,
        jobs_root: str | None = None,
    ) -> None:
        self._transcribe = transcribe_fn
        self._download = download_fn
        self._max_jobs = max_jobs
        self._max_queued = max_queued
        self._record_history = record_history
        self._jobs_root = (
            jobs_root if jobs_root is not None
            else str(user_cache_dir() / "server_jobs")
        )
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None

    # --- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        """Start the background worker thread (idempotent)."""
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            os.makedirs(self._jobs_root, exist_ok=True)
            self._stop.clear()
            self._worker = threading.Thread(
                target=self._drain, name="server-job-worker", daemon=True
            )
            self._worker.start()

    def stop(self, *, timeout: float = 5.0) -> None:
        """Signal the worker to exit and wait briefly for it."""
        self._stop.set()
        # Unblock a waiting get().
        self._queue.put("")
        w = self._worker
        if w is not None:
            w.join(timeout=timeout)

    # --- submission ----------------------------------------------------------

    def _new_job(self, kind: str, formats: list[str], language: str,
                 source: str) -> Job:
        """Create + register a job, enforcing the total-jobs cap.

        Caller must hold ``self._lock``.
        """
        if len(self._queued_ids()) >= self._max_queued:
            raise QueueFull("too many queued jobs; try again later")
        # Evict the oldest terminal job(s) once we exceed the total cap so a
        # long-lived server doesn't grow unbounded.
        self._evict_locked()
        if len(self._jobs) >= self._max_jobs:
            raise QueueFull("server is at capacity; try again later")
        job_id = uuid.uuid4().hex
        work_dir = os.path.join(self._jobs_root, job_id)
        os.makedirs(work_dir, exist_ok=True)
        job = Job(
            job_id=job_id, kind=kind, formats=list(formats),
            language=language, source=source, work_dir=work_dir,
        )
        self._jobs[job_id] = job
        self._order.append(job_id)
        return job

    def submit_upload(self, filename: str, data: bytes, formats: list[str],
                      language: str = "") -> str:
        """Register an upload job from already-read bytes; return job_id."""
        safe = _safe_filename(filename)
        with self._lock:
            job = self._new_job("upload", formats, language, safe)
            media_path = os.path.join(job.work_dir, safe)
            with open(media_path, "wb") as f:
                f.write(data)
            job.media_path = media_path
            self._queue.put(job.job_id)
            return job.job_id

    def submit_upload_stream(
        self, filename: str, formats: list[str], language: str = "",
    ) -> tuple[str, str]:
        """Register an upload job and return ``(job_id, media_path)``.

        The handler writes the streamed bytes to ``media_path`` itself
        (so a large file never has to sit fully in RAM) and then calls
        :meth:`enqueue_upload` to start processing.
        """
        safe = _safe_filename(filename)
        with self._lock:
            job = self._new_job("upload", formats, language, safe)
            job.media_path = os.path.join(job.work_dir, safe)
            return job.job_id, job.media_path

    def enqueue_upload(self, job_id: str) -> None:
        """Queue a streamed-upload job once its bytes are on disk."""
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
        self._queue.put(job_id)

    def submit_url(self, url: str, formats: list[str],
                   language: str = "") -> str:
        """Register a URL job; return job_id. Scheme is validated here."""
        if not is_safe_url(url):
            raise ValueError("only http(s) URLs are accepted")
        with self._lock:
            job = self._new_job("url", formats, language, url)
            job.media_path = ""  # filled in after the download
            self._queue.put(job.job_id)
            return job.job_id

    # --- queries -------------------------------------------------------------

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def output_path(self, job_id: str, fmt: str) -> str | None:
        """Absolute path of a finished job's output for ``fmt``, or None."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            for f, p in job.outputs:
                if f.lower() == fmt.lower():
                    return p
        return None

    def cancel(self, job_id: str) -> bool:
        """Flag a job for cooperative cancellation. Returns True if found."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job.status in _TERMINAL:
                return False
            job.cancelled = True
            return True

    def _queued_ids(self) -> list[str]:
        return [jid for jid, j in self._jobs.items()
                if j.status == STATUS_QUEUED]

    def _evict_locked(self) -> None:
        """Drop + clean up oldest terminal jobs once over the total cap.

        Caller holds ``self._lock``. Only terminal jobs are evicted so an
        in-flight job is never deleted out from under the worker.
        """
        while len(self._jobs) >= self._max_jobs:
            victim_id = next(
                (jid for jid in self._order
                 if jid in self._jobs and self._jobs[jid].status in _TERMINAL),
                None,
            )
            if victim_id is None:
                return  # nothing terminal to evict; the cap check will reject
            victim = self._jobs.pop(victim_id)
            self._order.remove(victim_id)
            _rmtree_quiet(victim.work_dir)

    # --- worker --------------------------------------------------------------

    def _drain(self) -> None:
        while not self._stop.is_set():
            try:
                job_id = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if self._stop.is_set():
                break
            if not job_id:
                continue
            job = self.get(job_id)
            if job is None or job.cancelled:
                if job is not None:
                    self._set_status(job, STATUS_CANCELLED)
                    _rmtree_quiet(job.work_dir)
                continue
            self._run_one(job)

    def _run_one(self, job: Job) -> None:
        history_db = None
        history_id = None
        started = time.time()
        try:
            if job.kind == "url":
                self._set_status(job, STATUS_DOWNLOADING)
                if self._download is None:
                    raise RuntimeError("URL downloads are not configured")
                job.media_path = self._download(job.source, job.work_dir)
            if job.cancelled:
                self._set_status(job, STATUS_CANCELLED)
                return
            if not job.media_path or not os.path.isfile(job.media_path):
                raise RuntimeError("no media file to transcribe")

            history_db, history_id = self._open_history(job)
            self._set_status(job, STATUS_RUNNING)
            task = _ServerTask(job)

            def _progress(p: int) -> None:
                job.progress = max(0, min(100, int(p)))

            self._transcribe(task, _progress, None, None)

            if job.cancelled:
                self._set_status(job, STATUS_CANCELLED)
            else:
                job.outputs = self._collect_outputs(job)
                job.progress = 100
                self._set_status(job, STATUS_FINISHED)
            self._finish_history(
                history_db, history_id, job, time.time() - started,
                getattr(task, "detected_language", "") or job.language,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("job %s failed", job.job_id)
            job.error = str(e)
            self._set_status(job, STATUS_ERROR)
            self._finish_history(
                history_db, history_id, job, time.time() - started,
                job.language, error=str(e),
            )

    def _collect_outputs(self, job: Job) -> list[tuple[str, str]]:
        """Find the files the engine wrote in the per-job dir.

        ``transcribe`` writes outputs beside the input, so they all live in
        ``job.work_dir``. Match by extension against the requested formats;
        the de-dupe "(1)" suffix is handled by globbing the dir.
        """
        out: list[tuple[str, str]] = []
        try:
            names = os.listdir(job.work_dir)
        except OSError:
            return out
        media_name = os.path.basename(job.media_path)
        for fmt in job.formats:
            ext = f".{fmt.lower()}"
            matches = [n for n in names
                       if n.lower().endswith(ext) and n != media_name]
            if not matches:
                continue
            # Newest by mtime wins (handles the "(1)" re-run case).
            matches.sort(
                key=lambda n: os.path.getmtime(os.path.join(job.work_dir, n)),
                reverse=True,
            )
            out.append((fmt, os.path.join(job.work_dir, matches[0])))
        return out

    def _set_status(self, job: Job, status: str) -> None:
        job.status = status
        if status in _TERMINAL:
            job.finished_at = time.time()

    # --- history (optional, never fatal) -------------------------------------

    def _open_history(self, job: Job) -> tuple[Any, int | None]:
        if not self._record_history:
            return None, None
        try:
            from core.history import HistoryDB
            db = HistoryDB()
            rid = db.insert_transcription(
                job.media_path or job.source, model="", language=job.language,
            )
            return db, rid
        except Exception as e:  # noqa: BLE001
            logger.warning("history.db unavailable for job %s: %s",
                           job.job_id, e)
            return None, None

    def _finish_history(self, db: Any, rid: int | None, job: Job,
                        duration_s: float, language: str,
                        error: str = "") -> None:
        if db is None or rid is None:
            return
        status_map = {
            STATUS_FINISHED: "finished",
            STATUS_ERROR: "error",
            STATUS_CANCELLED: "cancelled",
        }
        try:
            db.finish_transcription(
                rid, status_map.get(job.status, "error"),
                output_paths=[p for _, p in job.outputs],
                duration_seconds=duration_s, language=language, error=error,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("could not finish history row for job %s: %s",
                           job.job_id, e)
        finally:
            try:
                db.close()
            except Exception:  # noqa: BLE001
                pass


class QueueFull(Exception):
    """Raised when the server is at its job/queue cap (HTTP 503)."""


# --- pure helpers (unit-testable) --------------------------------------------

def _safe_filename(name: str) -> str:
    """Reduce an uploaded filename to a safe basename.

    Strips any directory components and rejects traversal so the media
    can only ever land inside the per-job dir. Falls back to a generic
    name when the input is empty or all-suspect.
    """
    base = os.path.basename(name or "").strip()
    # Drop anything that isn't a tame filename character; keep dots,
    # dashes, underscores, spaces, and alphanumerics.
    cleaned = "".join(
        c for c in base
        if c.isalnum() or c in (".", "-", "_", " ")
    ).strip()
    cleaned = cleaned.lstrip(".") or ""
    return cleaned or f"upload-{uuid.uuid4().hex[:8]}.bin"


def is_safe_url(url: str) -> bool:
    """True iff ``url`` is an http(s) URL with a host.

    Rejects ``file://``, ``ftp://``, bare paths, and anything without a
    network location. yt-dlp performs its own resolution beyond this, but
    the scheme gate stops the obvious local-file / SSRF-scheme attempts.
    """
    import urllib.parse as _up
    try:
        parsed = _up.urlparse((url or "").strip())
    except (ValueError, AttributeError):
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    return bool(parsed.netloc)


def _rmtree_quiet(path: str) -> None:
    if not path:
        return
    try:
        shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass
