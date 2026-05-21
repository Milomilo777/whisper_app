"""Transcription worker lifecycle.

Each worker is a long-lived subprocess of ``python -m core.worker`` (or
``<exe> --worker`` when frozen). The service owns spawning, restarting, and
draining stdout into the App's queue.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
from queue import Empty
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.app import App


logger = logging.getLogger(__name__)


class TranscriptionService:
    def __init__(self, app: "App") -> None:
        self.app = app

    # Queries -----------------------------------------------------------------
    def active_workers(self) -> list[dict[str, Any]]:
        return [w for w in self.app.workers if w["process"] and w["process"].poll() is None]

    def ready_workers(self) -> list[dict[str, Any]]:
        return [w for w in self.active_workers() if w["ready"]]

    def idle_workers(self) -> list[dict[str, Any]]:
        return [w for w in self.ready_workers() if w["task"] is None]

    def update_model_state(self) -> None:
        ready_count = len(self.ready_workers())
        self.app.worker_ready = ready_count > 0
        self.app.model_ready = self.app.worker_ready
        self.app.model_loading = not self.app.worker_ready
        if ready_count:
            self.app.status_var.set(
                f"Model ready ({ready_count} worker{'s' if ready_count != 1 else ''})"
            )

    # Lifecycle ---------------------------------------------------------------
    def start_standby(self) -> None:
        if not self.active_workers():
            self.start_worker(temporary=False)
        self.update_model_state()

    def start_worker(self, worker: dict[str, Any] | None = None, temporary: bool = False) -> None:
        app = self.app
        if worker and worker["process"] and worker["process"].poll() is None:
            return

        if worker is None:
            import uuid as _uuid
            worker = {
                "id": app.next_worker_id,
                "process": None,
                "ready": False,
                "task": None,
                "temporary": temporary,
                # Audit A4: per-worker UUID echoed back in every event
                # so PID recycling can't misroute an old event onto a
                # new worker.
                "token": _uuid.uuid4().hex,
                # Audit D8: monitored by poll(); updated on every event
                # the worker emits. If it lags by > LIVENESS_TIMEOUT_S
                # the worker is declared wedged and restarted.
                "last_event_at": 0.0,
            }
            app.next_worker_id += 1
            app.workers.append(worker)
        else:
            worker["temporary"] = temporary
            # Fresh token on every restart so stale events from the
            # dead instance can't survive.
            import uuid as _uuid
            worker["token"] = _uuid.uuid4().hex
            worker["last_event_at"] = 0.0

        app.model_loading = True
        worker["ready"] = False
        worker["task"] = None
        app.status_var.set(f"Loading model worker {worker['id']}...")

        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--worker"]
        else:
            cmd = [sys.executable, "-u", "-m", "core.worker"]
        env = os.environ.copy()
        env["WHISPER_WORKER_TOKEN"] = worker["token"]
        kwargs: dict[str, Any] = {
            "cwd": os.path.dirname(os.path.abspath(app.entry_file)),
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "env": env,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        process = subprocess.Popen(cmd, **kwargs)
        worker["process"] = process
        # Seed liveness timestamp at spawn so the watchdog grace
        # period covers initial model load.
        import time as _time
        worker["last_event_at"] = _time.time()

        def reader() -> None:
            for line in process.stdout:  # type: ignore[union-attr]
                line = line.strip()
                if not line:
                    continue
                event: dict[str, Any]
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    event = {"event": "log", "message": line}
                event["_pid"] = process.pid
                event["_worker_id"] = worker["id"]
                # Token is set by the worker if WHISPER_WORKER_TOKEN
                # was honoured (audit A4). Parent-side routing uses
                # it when present, falls back to PID otherwise.
                app.worker_events.put(event)
            return_code = process.wait()
            app.worker_events.put(
                {"event": "worker_exit", "return_code": return_code,
                 "_pid": process.pid, "_worker_id": worker["id"],
                 "_token": worker.get("token", "")}
            )

        from core._threads import safe_thread
        safe_thread(reader, name=f"worker-{worker['id']}-reader")
        app.after(100, self.poll)

    def stop_worker(self, worker: dict[str, Any]) -> None:
        """Audit D5: structured three-step shutdown.

        1. Send {"action": "shutdown"} on stdin (in a daemon thread so
           a full pipe never blocks the Tk main thread — audit A1).
        2. Wait up to 5 s for the worker to exit on its own.
        3. terminate() — graceful Windows-level signal.
        4. If still alive after another 2 s, kill() it.

        Each step is logged so a wedged worker is debuggable from
        the log alone.
        """
        process = worker.get("process")
        if not (process and process.poll() is None):
            return

        worker_id = worker.get("id", "?")
        shutdown_msg = json.dumps({"action": "shutdown"}) + "\n"

        def _async_shutdown() -> None:
            try:
                if process.stdin:
                    process.stdin.write(shutdown_msg)
                    process.stdin.flush()
            except Exception:
                logger.debug(
                    "stop_worker: stdin shutdown write failed for worker %s",
                    worker_id, exc_info=True,
                )
        threading.Thread(
            target=_async_shutdown, name=f"shutdown-w{worker_id}", daemon=True,
        ).start()

        try:
            process.wait(timeout=5.0)
            return
        except subprocess.TimeoutExpired:
            logger.info("stop_worker: worker %s ignored shutdown; terminating",
                        worker_id)
        try:
            process.terminate()
        except Exception:
            logger.exception("stop_worker: terminate() raised for worker %s",
                             worker_id)
        try:
            process.wait(timeout=2.0)
            return
        except subprocess.TimeoutExpired:
            logger.warning(
                "stop_worker: worker %s ignored terminate(); killing", worker_id,
            )
        try:
            process.kill()
        except Exception:
            logger.exception("stop_worker: kill() raised for worker %s",
                             worker_id)

    def stop_all(self) -> None:
        for w in self.active_workers():
            self.stop_worker(w)

    def restart_worker(self, worker: dict[str, Any]) -> None:
        self.stop_worker(worker)
        worker["process"] = None
        worker["ready"] = False
        worker["task"] = None
        self.app.model_loading = True
        self.app.after(300, lambda: self.start_worker(worker, temporary=worker.get("temporary", False)))

    def retire_worker(self, worker: dict[str, Any]) -> None:
        self.stop_worker(worker)
        worker["process"] = None
        worker["ready"] = False
        worker["task"] = None
        if worker in self.app.workers:
            self.app.workers.remove(worker)
        self.update_model_state()

    # Routing -----------------------------------------------------------------
    def worker_for_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Match event → worker.

        Audit A4 — prefer token match when both sides carry one
        (worker spawned with WHISPER_WORKER_TOKEN). Fall back to
        PID + worker_id for the worker_exit synthetic event the
        reader fires when the subprocess dies (which can no longer
        echo its own token at that point if it hard-crashed).
        """
        token = event.get("_token")
        if token:
            for worker in self.app.workers:
                if worker.get("token") == token:
                    return worker
        # Legacy / synthetic path — match on PID + worker id.
        for worker in self.app.workers:
            process = worker.get("process")
            if (
                worker["id"] == event.get("_worker_id")
                and process
                and process.pid == event.get("_pid")
            ):
                return worker
        return None

    # Audit D8: if a worker stops emitting events (including the
    # 5-second heartbeat) for this long, declare it wedged + restart.
    # 30 s easily covers a normal model load (~10 s on CPU) and any
    # one-segment Whisper transcribe burst, but catches a deadlocked
    # worker before the user has to kill the app.
    LIVENESS_TIMEOUT_S = 30.0

    def poll(self) -> None:
        app = self.app
        import time as _time
        now = _time.time()
        while True:
            try:
                event = app.worker_events.get_nowait()
            except Empty:
                break

            event_type = event.get("event")
            worker = self.worker_for_event(event)
            if not worker:
                continue

            # Audit D8: any event counts as liveness.
            worker["last_event_at"] = now
            if event_type == "heartbeat":
                # Pure liveness — already recorded above.
                continue

            if event_type == "log":
                app.model_status(event.get("message", ""))
            elif event_type == "ready":
                worker["ready"] = True
                self.update_model_state()
            elif event_type == "startup_error":
                worker["ready"] = False
                app.log(event.get("message", "Existing model failed to load."))
                if not app.model_setup_running:
                    app.log("Existing model failed to load. Starting required download.")
                    self.stop_all()
                    app.workers = []
                    app.ensure_model_with_modal(mandatory=True)
            elif event_type == "started":
                pass
            elif event_type == "progress":
                if worker["task"]:
                    p = event.get("percent", 0)
                    worker["task"].progress = p
                    app.update_overall_progress()
            elif event_type == "language_detected":
                if worker["task"]:
                    worker["task"].detected_language = event.get("language", "")
                    worker["task"].language_probability = event.get("probability", 0.0)
                    app.refresh()
            elif event_type == "done":
                self.finish_task(worker)
            elif event_type == "error":
                if worker["task"]:
                    worker["task"].status = "error"
                    app.log(event.get("message", "Worker error"))
                    self.finish_task(worker, keep_status=True)
                else:
                    app.log(event.get("message", "Worker error"))
            elif event_type == "worker_exit":
                worker["ready"] = False
                worker["process"] = None
                if worker["task"] and worker["task"].status == "running":
                    worker["task"].status = "error"
                    app.log(f"Transcription worker exited with code {event.get('return_code')}")
                    self.finish_task(worker, keep_status=True)
                self.update_model_state()

        # Audit D8: liveness watchdog. After draining the queue,
        # check every active worker. If one has been silent past the
        # threshold (heartbeat missed several times), restart it.
        for w in list(self.active_workers()):
            last = float(w.get("last_event_at") or 0.0)
            if last and now - last > self.LIVENESS_TIMEOUT_S:
                logger.warning(
                    "Worker %s missed heartbeats for %.1fs; restarting",
                    w.get("id", "?"), now - last,
                )
                app.log(
                    f"Worker {w.get('id', '?')} appears wedged; restarting."
                )
                if w["task"]:
                    w["task"].status = "error"
                    self.finish_task(w, keep_status=True)
                self.restart_worker(w)

        if self.active_workers():
            app.after(100, self.poll)

    def dispatch_waiting(self) -> None:
        """Spawn temporary workers as needed and hand them waiting tasks."""
        app = self.app
        if not app.queue:
            return
        waiting = [t for t in app.queue if t.status == "waiting"]
        if not waiting:
            return
        active_count = len(self.active_workers())
        idle_count = len(self.idle_workers())
        needed = min(len(waiting), app.parallel_workers) - idle_count
        for _ in range(max(0, needed)):
            if active_count >= app.parallel_workers:
                break
            self.start_worker(temporary=True)
            active_count += 1
        idle = self.idle_workers()
        if not idle:
            return
        import time as _time
        for worker, t in zip(idle, waiting):
            # Audit A3: insert the history row BEFORE marking the task
            # running and BEFORE telling the worker to start. If the
            # insert raises (locked DB, disk full), we abort the
            # dispatch — the task stays in `waiting` and the user can
            # retry; the alternative is a "running" task with no DB
            # record, which mark_interrupted() can't recover on
            # next launch.
            history = getattr(app, "history", None)
            if history is not None:
                try:
                    t.history_id = history.insert_transcription(
                        file_path=t.file_path,
                        model=str(app.app_config.get("model", {}).get("name", "")),
                        language=getattr(t, "language", "") or "",
                    )
                except Exception as e:
                    logger.exception(
                        "history insert failed for %s; deferring dispatch",
                        t.file_path,
                    )
                    app.log(f"Could not record task in history: {e}")
                    # Leave status='waiting' so the next dispatch
                    # tick picks it up again (transient DB locks
                    # are common on Windows with antivirus).
                    continue

            worker["task"] = t
            t.status = "running"
            t.progress = 0
            t.start_time = _time.time()
            # Clear any prior end_time (re-run path) so the freshly-
            # restarted task counter doesn't immediately freeze.
            t.end_time = None
            app.update_overall_progress()

            # Audit A1: stdin.write can block the Tk main thread when
            # the OS pipe buffer fills (~64 KB on Windows). Move the
            # write to a daemon thread — same pattern stop_worker
            # uses for its shutdown command. If the write fails OR
            # blocks > 5 s, we restart the worker.
            command = {
                "action": "transcribe",
                "file_path": t.file_path,
                "language": getattr(t, "language", None),
            }
            self._dispatch_command_async(worker, t, command)

    def _dispatch_command_async(
        self,
        worker: dict[str, Any],
        task: Any,
        command: dict[str, Any],
    ) -> None:
        """Write ``command`` to the worker's stdin from a daemon thread.

        On failure (write raises OR times out via process death),
        mark the task as error + restart the worker. We can't
        observe a blocked write directly, but a long-blocked
        worker is the same observable thing as a dead one — it
        stops emitting events, so the next progress tick reveals
        the wedge.
        """
        app = self.app
        msg = json.dumps(command) + "\n"
        worker_id = worker.get("id", "?")

        def _worker_dispatch() -> None:
            try:
                stdin = worker["process"].stdin
                if stdin is None:
                    raise RuntimeError("worker stdin is None")
                stdin.write(msg)
                stdin.flush()
            except Exception as e:
                logger.exception(
                    "Failed to dispatch task to worker %s: %s",
                    worker_id, e,
                )
                # Marshal the error back onto the worker_events
                # queue so the Tk poll loop handles cleanup on the
                # main thread (status flip + restart).
                try:
                    app.worker_events.put({
                        "event": "error",
                        "message": f"Failed to dispatch task: {e}",
                        "_pid": worker["process"].pid if worker.get("process") else 0,
                        "_worker_id": worker_id,
                    })
                except Exception:
                    logger.exception(
                        "Could not enqueue dispatch failure event"
                    )

        threading.Thread(
            target=_worker_dispatch,
            name=f"dispatch-w{worker_id}",
            daemon=True,
        ).start()

    def finish_task(self, worker: dict[str, Any], keep_status: bool = False) -> None:
        task = worker["task"]
        if not task:
            return
        import time as _time
        # Freeze the Elapsed-column counter ASAP — irrespective of
        # which terminal status (finished / cancelled / error) the
        # task ended in. Before this, app.fmt_time kept incrementing
        # via time.time() - start_time forever.
        if getattr(task, "end_time", None) is None:
            task.end_time = _time.time()
        newly_finished = (
            not keep_status and not task.cancelled
        )
        if newly_finished:
            task.status = "finished"
            task.progress = 100
            # Surface the success on the Transcribe tab so the user
            # sees a real "this is done, here are the files" card
            # rather than just a Treeview row flipping to "finished".
            try:
                self.app.show_last_result(task)
            except Exception:  # noqa: BLE001
                pass
        # Phase 3a — finalise the history row.
        app = self.app
        history = getattr(app, "history", None)
        if history is not None and getattr(task, "history_id", 0):
            import time as _time
            try:
                duration = (_time.time() - task.start_time) if task.start_time else 0.0
                base = task.file_path.rsplit(".", 1)[0]
                paths = [
                    f"{base}.{ext}"
                    for ext in (app.app_config.get("output_formats") or ["srt", "json"])
                ]
                history.finish_transcription(
                    task.history_id,
                    status=task.status,
                    output_paths=paths,
                    duration_seconds=float(duration),
                    language=getattr(task, "detected_language", "") or "",
                )
            except Exception as e:  # noqa: BLE001
                app.log(f"history record update failed: {e}")
        worker["task"] = None
        app.update_overall_progress()
        if worker.get("temporary") and not any(t.status == "waiting" for t in app.queue):
            self.retire_worker(worker)
