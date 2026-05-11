"""Transcription worker lifecycle.

Each worker is a long-lived subprocess of ``python -m core.worker`` (or
``<exe> --worker`` when frozen). The service owns spawning, restarting, and
draining stdout into the App's queue.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from queue import Empty
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.app import App


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
            worker = {
                "id": app.next_worker_id,
                "process": None,
                "ready": False,
                "task": None,
                "temporary": temporary,
            }
            app.next_worker_id += 1
            app.workers.append(worker)
        else:
            worker["temporary"] = temporary

        app.model_loading = True
        worker["ready"] = False
        worker["task"] = None
        app.status_var.set(f"Loading model worker {worker['id']}...")

        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--worker"]
        else:
            cmd = [sys.executable, "-u", "-m", "core.worker"]
        kwargs: dict[str, Any] = {
            "cwd": os.path.dirname(os.path.abspath(app.entry_file)),
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        process = subprocess.Popen(cmd, **kwargs)
        worker["process"] = process

        def reader() -> None:
            for line in process.stdout:  # type: ignore[union-attr]
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    event = {"event": "log", "message": line}
                event["_pid"] = process.pid
                event["_worker_id"] = worker["id"]
                app.worker_events.put(event)
            return_code = process.wait()
            app.worker_events.put(
                {"event": "worker_exit", "return_code": return_code, "_pid": process.pid, "_worker_id": worker["id"]}
            )

        threading.Thread(target=reader, daemon=True).start()
        app.after(100, self.poll)

    def stop_worker(self, worker: dict[str, Any]) -> None:
        process = worker.get("process")
        if process and process.poll() is None:
            try:
                if process.stdin:
                    process.stdin.write(json.dumps({"action": "shutdown"}) + "\n")
                    process.stdin.flush()
            except Exception:  # noqa: BLE001
                pass
            process.terminate()

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
        for worker in self.app.workers:
            process = worker.get("process")
            if (
                worker["id"] == event.get("_worker_id")
                and process
                and process.pid == event.get("_pid")
            ):
                return worker
        return None

    def poll(self) -> None:
        app = self.app
        while True:
            try:
                event = app.worker_events.get_nowait()
            except Empty:
                break

            event_type = event.get("event")
            worker = self.worker_for_event(event)
            if not worker:
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

        if self.active_workers():
            app.after(100, self.poll)

    def finish_task(self, worker: dict[str, Any], keep_status: bool = False) -> None:
        task = worker["task"]
        if not task:
            return
        if not keep_status and not task.cancelled:
            task.status = "finished"
            task.progress = 100
        worker["task"] = None
        self.app.update_overall_progress()
        if worker.get("temporary") and not any(t.status == "waiting" for t in self.app.queue):
            self.retire_worker(worker)
