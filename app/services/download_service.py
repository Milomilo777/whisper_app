"""yt-dlp download service.

Builds yt-dlp argv lists, runs them in a daemon thread, and posts events on
``app.download_events``. The Tk side drains the events on its main loop.

The two pure helpers, :func:`build_subtitle_command` and
:func:`build_download_command`, are exposed at module level for unit testing.
They take a task object and a "tools" descriptor and return a complete argv.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from queue import Empty
from typing import TYPE_CHECKING, Any

from app.domain.languages import subtitle_lang_args
from core.config import save_config

if TYPE_CHECKING:
    from app.app import App
    from app.domain.tasks import VideoDownloadTask


# Module-level pure builders (tested in tests/test_download_command.py) ---------


def build_subtitle_command(
    task: "VideoDownloadTask",
    lang: str,
    *,
    yt_dlp_path: str,
    bin_path: str,
) -> list[str]:
    output = os.path.join(task.folder, "%(title)s.%(ext)s")
    sub_langs = subtitle_lang_args(lang)
    return [
        yt_dlp_path,
        "--ffmpeg-location",
        bin_path,
        "--newline",
        "--skip-download",
        "--write-auto-subs",
        "--write-subs",
        "--sub-langs",
        sub_langs,
        "--no-playlist",
        "-o",
        output,
        task.url,
    ]


def build_download_command(
    task: "VideoDownloadTask",
    *,
    yt_dlp_path: str,
    bin_path: str,
    sponsorblock_categories: list[str] | None = None,
    progress_template: str | None = None,
) -> list[str]:
    output = os.path.join(task.folder, "%(title)s.%(ext)s")
    command = [yt_dlp_path, "--ffmpeg-location", bin_path, "--newline", "-o", output]
    if progress_template:
        command.extend(["--progress-template", progress_template])
    if sponsorblock_categories:
        command.extend(["--sponsorblock-remove", ",".join(sponsorblock_categories)])
    fmt = task.format_info
    output_format = fmt.get("output", "mp4")
    audio = fmt.get("audio") or {"kind": "best_audio"}
    video = fmt.get("video") or {"kind": "best_video"}

    if fmt.get("mode") == "Audio":
        audio_selector = "ba/bestaudio" if audio["kind"] == "best_audio" else audio["format_id"]
        command.extend(["-f", audio_selector, "-x", "--audio-format", output_format])
    else:
        if video["kind"] == "best_video":
            video_selector = (
                "bv*[ext=mp4]/bestvideo[ext=mp4]/bv*/bestvideo"
                if output_format == "mp4"
                else "bv*/bestvideo"
            )
        else:
            video_selector = video["format_id"]
        if audio["kind"] == "best_audio":
            audio_selector = (
                "ba[ext=m4a]/bestaudio[ext=m4a]/ba/bestaudio"
                if output_format == "mp4"
                else "ba/bestaudio"
            )
        else:
            audio_selector = audio["format_id"]
        command.extend(
            ["-f", f"{video_selector}+{audio_selector}/best", "--merge-output-format", output_format]
        )
    command.append(task.url)
    return command


_PERCENT_RE = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
_DEST_RE = re.compile(r"^\[(?:download|Merger|ExtractAudio)\] (?:Destination|Merging formats into):\s+(.+)$")


def parse_progress_line(line: str) -> dict[str, Any] | None:
    """Parse one stdout line from yt-dlp.

    Recognized shapes:
      * ``--progress-template "%(progress)j"`` JSON: returns the dict as-is plus
        a derived ``percent`` field when ``downloaded_bytes`` and
        ``total_bytes`` are both present.
      * Legacy ``[download] N.N%`` regex: returns ``{"percent": ...}``.
      * Anything else: returns ``None``.
    """
    line = (line or "").strip()
    if not line:
        return None
    if line.startswith("{") and line.endswith("}"):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        downloaded = payload.get("downloaded_bytes")
        total = payload.get("total_bytes") or payload.get("total_bytes_estimate")
        if isinstance(downloaded, (int, float)) and isinstance(total, (int, float)) and total > 0:
            payload["percent"] = min(100.0, (downloaded / total) * 100.0)
        return payload
    m = _PERCENT_RE.search(line)
    if m:
        return {"percent": float(m.group(1))}
    return None


def parse_destination_line(line: str) -> str | None:
    """Pick out a saved-file path from yt-dlp output (auto-transcribe wiring)."""
    if not line:
        return None
    m = _DEST_RE.match(line.strip())
    return m.group(1).strip() if m else None


# Service class wired into the App ------------------------------------------------


class DownloadService:
    def __init__(self, app: "App") -> None:
        self.app = app

    # Helpers exposed to the App
    def resolve_subtitle_lang(self, task: "VideoDownloadTask") -> str:
        lang = task.subtitle_lang or task.detected_language or ""
        return lang.strip()

    def build_subtitle_command(self, task: "VideoDownloadTask", lang: str) -> list[str]:
        return build_subtitle_command(
            task, lang, yt_dlp_path=self.app.yt_dlp_path(), bin_path=self.app.bin_path()
        )

    def build_download_command(self, task: "VideoDownloadTask") -> list[str]:
        return build_download_command(
            task,
            yt_dlp_path=self.app.yt_dlp_path(),
            bin_path=self.app.bin_path(),
            sponsorblock_categories=list(self.app.app_config.get("sponsorblock_categories") or []),
            progress_template="%(progress)j",
        )

    def maybe_update_yt_dlp(self, task: "VideoDownloadTask") -> None:
        cfg = self.app.app_config
        if not cfg.get("auto_update_yt_dlp", False):
            return
        last = cfg.get("last_yt_dlp_update_check") or ""
        if last:
            try:
                last_dt = datetime.fromisoformat(last)
                if datetime.now(timezone.utc) - last_dt < timedelta(hours=24):
                    return
            except ValueError:
                pass
        try:
            update_cmd = [self.app.yt_dlp_path(), "--update"]
            update = subprocess.run(
                update_cmd,
                cwd=os.path.dirname(os.path.abspath(self.app.entry_file)),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if update.stdout.strip():
                self.app.download_events.put(("log", task, update.stdout.strip()))
            if update.stderr.strip():
                self.app.download_events.put(("log", task, update.stderr.strip()))
            if update.returncode:
                self.app.download_events.put(
                    ("log", task, f"yt-dlp update returned code {update.returncode}; continuing")
                )
        except subprocess.TimeoutExpired:
            self.app.download_events.put(("log", task, "yt-dlp update timed out; continuing"))
        except Exception as e:  # noqa: BLE001
            self.app.download_events.put(("log", task, f"yt-dlp update skipped: {e}"))
        cfg["last_yt_dlp_update_check"] = datetime.now(timezone.utc).isoformat()
        try:
            save_config(cfg)
        except Exception:  # noqa: BLE001
            pass

    def enqueue_from_form(self) -> None:
        """Read the download tab form, validate, build a task, and enqueue."""
        from tkinter import messagebox
        from app.domain.languages import SUBTITLE_LANGUAGES
        from app.domain.tasks import VideoDownloadTask

        app = self.app
        url = app.download_url_var.get().strip()
        folder = app.download_folder_var.get().strip()
        mode = app.download_mode_var.get()
        audio_label = app.audio_format_var.get()
        video_label = app.video_format_var.get()
        output = app.output_format_var.get()
        if not url:
            messagebox.showwarning("Missing URL", "Enter a URL first.", parent=app)
            return
        if not folder:
            messagebox.showwarning("Missing folder", "Select a download folder first.", parent=app)
            return
        if not audio_label or audio_label not in app.audio_format_map:
            messagebox.showwarning("Missing audio format",
                                   "Wait for formats to load, then select an audio format.", parent=app)
            return
        if mode == "Audio and video" and (not video_label or video_label not in app.video_format_map):
            messagebox.showwarning("Missing video format",
                                   "Wait for formats to load, then select a video format.", parent=app)
            return
        if not output:
            messagebox.showwarning("Missing output", "Select an output format.", parent=app)
            return

        os.makedirs(folder, exist_ok=True)
        app.app_config["download_folder"] = folder
        title = app.current_video_title or url
        subtitles_enabled = app.download_subtitles_var.get()
        sub_lang_name = app.subtitle_lang_var.get()
        sub_lang_code = next((code for name, code in SUBTITLE_LANGUAGES if name == sub_lang_name), "")
        app.app_config["download_subtitles_enabled"] = subtitles_enabled
        app.app_config["download_subtitle_lang"] = sub_lang_name
        save_config(app.app_config)
        label_extra = f" + subs ({sub_lang_name})" if subtitles_enabled else ""
        format_label = f"{mode} -> {output}{label_extra}"
        format_info = {
            "mode": mode,
            "audio": app.audio_format_map[audio_label],
            "video": app.video_format_map.get(video_label),
            "output": output,
        }
        app.download_queue.append(
            VideoDownloadTask(
                url, folder, format_label, format_info, title,
                subtitles_enabled=subtitles_enabled,
                subtitle_lang=sub_lang_code,
                detected_language=app.current_video_language,
            )
        )
        app.refresh_download_queue()
        self.process_queue()

    # Driver
    def process_queue(self) -> None:
        app = self.app
        if app.download_current:
            return
        task = next((t for t in app.download_queue if t.status == "waiting"), None)
        if not task:
            return

        app.download_current = task
        task.status = "running"
        task.progress = 0
        import time as _t  # local to avoid shadow on type-checking

        task.start_time = _t.time()
        app.refresh_download_queue()

        threading.Thread(target=self._run_task, args=(task,), daemon=True).start()

    def _run_task(self, task: "VideoDownloadTask") -> None:
        app = self.app
        app.download_events.put(("subtitle_status", task, ""))
        # Phase 3a — record start in history.
        if getattr(app, "history", None):
            try:
                task.history_id = app.history.insert_download(
                    url=task.url, title=task.title, folder=task.folder,
                    format_label=task.format_label,
                )
            except Exception:  # noqa: BLE001
                task.history_id = 0
        try:
            self.maybe_update_yt_dlp(task)

            if task.subtitles_enabled and not task.cancelled:
                self._subtitle_phase(task)
                if task.cancelled:
                    return

            self._media_phase(task)
        except Exception as e:  # noqa: BLE001
            app.download_events.put(("error", task, str(e)))
        finally:
            task.process = None

    def _subtitle_phase(self, task: "VideoDownloadTask") -> None:
        app = self.app
        sub_lang = self.resolve_subtitle_lang(task)
        if not sub_lang:
            app.download_events.put(("subtitle_status", task, "no language detected"))
            app.download_events.put(("log", task, "Skipping subtitles: original language could not be detected."))
            return

        app.download_events.put(("subtitle_status", task, f"fetching subtitles ({sub_lang})..."))
        app.download_events.put(("log", task, f"--- Subtitle phase: requesting {sub_lang} ---"))
        task.process = subprocess.Popen(
            self.build_subtitle_command(task, sub_lang),
            cwd=os.path.dirname(os.path.abspath(app.entry_file)),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        wrote_files: list[str] = []
        no_subs_warning = False
        for line in task.process.stdout:  # type: ignore[union-attr]
            line = line.rstrip()
            if not line:
                continue
            app.download_events.put(("log", task, line))
            if "Writing video subtitles to:" in line:
                wrote_files.append(line.split("Writing video subtitles to:", 1)[1].strip())
            elif (
                "no subtitles for the requested languages" in line.lower()
                or "no automatic captions for the requested languages" in line.lower()
            ):
                no_subs_warning = True
        sub_rc = task.process.wait()
        task.process = None
        if task.cancelled:
            for partial in wrote_files:
                try:
                    if os.path.isfile(partial):
                        os.unlink(partial)
                        app.download_events.put(("log", task, f"Removed partial subtitle file: {partial}"))
                except OSError as e:
                    app.download_events.put(
                        ("log", task, f"Could not remove partial subtitle file {partial}: {e}")
                    )
            app.download_events.put(("subtitle_status", task, "cancelled"))
            app.download_events.put(("done", task, "cancelled"))
            return
        if wrote_files:
            app.download_events.put(
                (
                    "subtitle_status",
                    task,
                    f"✓ saved {len(wrote_files)} subtitle file{'s' if len(wrote_files) != 1 else ''}",
                )
            )
            app.download_events.put(("log", task, f"--- Subtitle phase: wrote {len(wrote_files)} file(s) ---"))
        elif no_subs_warning:
            app.download_events.put(("subtitle_status", task, "no captions available"))
            app.download_events.put(("log", task, "--- Subtitle phase: no captions available for the requested language ---"))
        elif sub_rc:
            app.download_events.put(("subtitle_status", task, f"failed (rc={sub_rc})"))
            app.download_events.put(
                ("log", task, f"--- Subtitle phase: yt-dlp exit code {sub_rc} (continuing with media) ---")
            )
        else:
            app.download_events.put(("subtitle_status", task, "completed (no files written)"))
            app.download_events.put(("log", task, "--- Subtitle phase: completed without writing files ---"))

    def _media_phase(self, task: "VideoDownloadTask") -> None:
        app = self.app
        task.process = subprocess.Popen(
            self.build_download_command(task),
            cwd=os.path.dirname(os.path.abspath(app.entry_file)),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        saved_path: str | None = None
        for line in task.process.stdout:  # type: ignore[union-attr]
            line = line.rstrip()
            parsed = parse_progress_line(line)
            if parsed and "percent" in parsed:
                app.download_events.put(("progress", task, float(parsed["percent"])))
            elif line:
                dest = parse_destination_line(line)
                if dest:
                    saved_path = dest
                app.download_events.put(("log", task, line))

        return_code = task.process.wait()
        if task.cancelled:
            app.download_events.put(("done", task, "cancelled"))
        elif return_code:
            app.download_events.put(("error", task, f"yt-dlp exited with code {return_code}"))
        else:
            payload = {"status": "finished", "saved_path": saved_path}
            app.download_events.put(("done_full", task, payload))

    def poll(self) -> None:
        app = self.app
        while True:
            try:
                kind, task, payload = app.download_events.get_nowait()
            except Empty:
                break

            if kind == "progress":
                task.progress = min(100, int(payload))
            elif kind == "log":
                app.log(payload)
            elif kind == "subtitle_status":
                app.subtitle_status_var.set(payload)
            elif kind == "done":
                self._finish(task, payload, saved_path=None)
            elif kind == "done_full":
                self._finish(task, payload["status"], saved_path=payload.get("saved_path"))
            elif kind == "error":
                task.status = "error"
                app.log(payload)
                if app.download_current is task:
                    app.download_current = None
                self.process_queue()

            app.refresh_download_queue()

        app.after(300, self.poll)

    def _finish(self, task: "VideoDownloadTask", status: str, saved_path: str | None) -> None:
        app = self.app
        task.status = status
        if status == "finished":
            task.progress = 100
            if app.app_config.get("auto_transcribe_after_download") and saved_path:
                try:
                    app.enqueue_transcription_from_download(saved_path, task.detected_language)
                    app.log(f"→ Queued for transcription: {os.path.basename(saved_path)}")
                except Exception as e:  # noqa: BLE001
                    app.log(f"Auto-transcribe wiring failed: {e}")
        # Phase 3a — finalise the history row.
        if getattr(app, "history", None) and getattr(task, "history_id", 0):
            try:
                app.history.finish_download(
                    task.history_id,
                    status=status,
                    output_paths=[saved_path] if saved_path else [],
                    detected_language=task.detected_language or "",
                )
            except Exception as e:  # noqa: BLE001
                app.log(f"history record update failed: {e}")
        if app.download_current is task:
            app.download_current = None
        self.process_queue()
