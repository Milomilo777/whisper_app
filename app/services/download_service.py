"""yt-dlp download service.

Builds yt-dlp argv lists, runs them in a daemon thread, and posts events on
``app.download_events``. The Tk side drains the events on its main loop.

The two pure helpers, :func:`build_subtitle_command` and
:func:`build_download_command`, are exposed at module level for unit testing.
They take a task object and a "tools" descriptor and return a complete argv.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)
from datetime import datetime, timedelta, timezone
from queue import Empty
from typing import TYPE_CHECKING, Any

from app.domain.languages import subtitle_lang_args
from core.config import save_config
from core.integrations import smtv as smtv_mod

if TYPE_CHECKING:
    from app.app import App
    from app.domain.tasks import VideoDownloadTask


def _is_smtv_task(task: "VideoDownloadTask") -> bool:
    info = task.format_info or {}
    for key in ("audio", "video"):
        sub = info.get(key)
        if isinstance(sub, dict) and sub.get("kind") == "smtv":
            return True
    return False


def _smtv_basename_from_url(url: str) -> str | None:
    """Extract the filename the CDN encoded in ?file=… ."""
    import urllib.parse as _up
    parsed = _up.urlparse(url)
    files = _up.parse_qs(parsed.query).get("file") or []
    if not files:
        return None
    return os.path.basename(files[0])


def _quiet_unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _content_length_or_none(resp: Any) -> int | None:
    raw = resp.headers.get("Content-Length") if resp.headers else None
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


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
        except Exception:
            logger.exception("Failed to persist yt-dlp auto-update preference")

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

        raw_episode = getattr(app, "_smtv_episode", None)
        smtv_episode: smtv_mod.SmtvEpisode | None = (
            raw_episode
            if isinstance(raw_episode, smtv_mod.SmtvEpisode)
               and smtv_mod.is_smtv_url(url)
            else None
        )
        is_smtv = smtv_episode is not None
        if smtv_episode is not None:
            format_info["episode"] = smtv_episode
            format_label = f"SMTV {audio_label if mode == 'Audio' else video_label}"

        tasks_to_enqueue = [
            VideoDownloadTask(
                url, folder, format_label, format_info, title,
                subtitles_enabled=False if is_smtv else subtitles_enabled,
                subtitle_lang="" if is_smtv else sub_lang_code,
                detected_language=app.current_video_language,
            )
        ]

        if (
            smtv_episode is not None
            and getattr(app, "smtv_download_all_parts_var", None) is not None
            and bool(app.smtv_download_all_parts_var.get())
            and smtv_episode.siblings
        ):
            tasks_to_enqueue.extend(
                self._build_smtv_sibling_tasks(
                    smtv_episode,
                    mode=mode,
                    video_label=video_label,
                    folder=folder,
                    format_label=format_label,
                    output=output,
                )
            )

        for t in tasks_to_enqueue:
            app.download_queue.append(t)
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
        # Re-run path: clear a frozen end_time so the counter starts
        # incrementing again for the second attempt.
        task.end_time = None
        app.refresh_download_queue()

        from core._threads import safe_thread
        safe_thread(self._run_task, args=(task,), name="download-task")

    def _run_task(self, task: "VideoDownloadTask") -> None:
        app = self.app
        app.download_events.put(("subtitle_status", task, ""))
        # Phase 3a — record start in history.
        history = getattr(app, "history", None)
        if history is not None:
            try:
                task.history_id = history.insert_download(
                    url=task.url, title=task.title, folder=task.folder,
                    format_label=task.format_label,
                )
            except Exception:  # noqa: BLE001
                task.history_id = 0

        if _is_smtv_task(task):
            try:
                self._run_smtv_task(task)
            except Exception as e:  # noqa: BLE001
                app.download_events.put(("error", task, str(e)))
            finally:
                task.process = None
            return

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

    def _build_smtv_sibling_tasks(
        self,
        episode: smtv_mod.SmtvEpisode,
        *,
        mode: str,
        video_label: str,
        folder: str,
        format_label: str,
        output: str,
    ) -> list["VideoDownloadTask"]:
        """One VideoDownloadTask per sibling part.

        Each sibling page is fetched in this thread (cheap — one HTTP
        GET per part) so the per-task format_info carries the part-
        specific CDN URLs. The current episode is NOT included; the
        caller already enqueued it.
        """
        from app.domain.tasks import VideoDownloadTask

        # Detect chosen mode against the parent episode's format_info
        chosen_mode_video = None
        chosen_mode_audio = None
        if mode == "Audio":
            chosen_mode_audio = "audio"
        else:
            quality_lookup = {
                "HD 1080p": "video-1080",
                "HD 720p":  "video-720",
                "SD 396p":  "video-396",
            }
            chosen_mode_video = quality_lookup.get(video_label, "video-best")

        sibling_tasks: list["VideoDownloadTask"] = []
        for sib in episode.siblings:
            try:
                sib_episode = smtv_mod.fetch_episode(sib.url, timeout=30.0)
            except smtv_mod.SmtvError as e:
                self.app.download_events.put(
                    ("log", None, f"SMTV sibling fetch failed for {sib.url}: {e}")
                )
                continue

            try:
                if chosen_mode_audio:
                    sib_url = smtv_mod.best_url_for_mode(sib_episode, "audio")
                    sib_format = {
                        "mode": "Audio",
                        "audio": {
                            "kind": "smtv", "mode": "audio",
                            "quality": "audio", "url": sib_url,
                        },
                        "video": None,
                        "output": output,
                        "episode": sib_episode,
                    }
                else:
                    sib_url = smtv_mod.best_url_for_mode(sib_episode, chosen_mode_video or "video-best")
                    sib_format = {
                        "mode": "Audio and video",
                        "audio": None,
                        "video": {
                            "kind": "smtv", "mode": chosen_mode_video or "video-best",
                            "quality": chosen_mode_video or "video-best",
                            "url": sib_url,
                        },
                        "output": output,
                        "episode": sib_episode,
                    }
            except smtv_mod.SmtvError as e:
                self.app.download_events.put(
                    ("log", None, f"SMTV sibling mode unavailable for {sib.url}: {e}")
                )
                continue

            sibling_tasks.append(
                VideoDownloadTask(
                    sib.url,
                    folder,
                    f"{format_label} (part {sib.part})" if sib.part else format_label,
                    sib_format,
                    sib_episode.title,
                    subtitles_enabled=False,
                    subtitle_lang="",
                    detected_language=sib_episode.lang_prefix,
                )
            )

        return sibling_tasks

    def _run_smtv_task(self, task: "VideoDownloadTask") -> None:
        """Direct CDN download for an SMTV task, bypassing yt-dlp.

        The format_info dict (built by format_service._apply_smtv_formats
        and ratified by enqueue_from_form) holds the chosen mode and the
        CDN URL. We stream chunks, post progress events into the existing
        download_events queue, atomic-rename .part -> final, and (if the
        episode has an article-text transcript) write <base>.txt
        alongside. On completion we emit done_full so the
        auto-transcribe-after-download wiring works the same way as the
        YouTube flow.
        """
        app = self.app
        info = task.format_info or {}
        chosen = info.get("audio") if info.get("mode") == "Audio" else info.get("video")
        if not isinstance(chosen, dict) or chosen.get("kind") != "smtv":
            raise RuntimeError("SMTV task missing chosen format")
        cdn_url = chosen.get("url")
        if not isinstance(cdn_url, str) or not cdn_url:
            raise RuntimeError("SMTV task missing CDN url")

        # Try to recover the parsed episode (preferred path), else
        # re-fetch on the worker thread. fetch_episode raises on
        # failure, so `episode` is always a real SmtvEpisode after
        # this block.
        cached = info.get("episode")
        if isinstance(cached, smtv_mod.SmtvEpisode):
            episode: smtv_mod.SmtvEpisode = cached
        else:
            episode = smtv_mod.fetch_episode(task.url, timeout=30.0)

        basename = _smtv_basename_from_url(cdn_url) or smtv_mod.filename_for(
            episode, chosen.get("mode", "video-best")
        )
        target_path = os.path.join(task.folder, basename)
        part_path = target_path + ".part"

        app.download_events.put(
            ("log", task, f"--- SMTV download: {basename} ({cdn_url}) ---")
        )

        try:
            self._stream_smtv_file(task, cdn_url, part_path)
        except Exception:  # noqa: BLE001
            # Whatever went wrong, the partial file is useless to the
            # user — clean it up and re-raise so the caller posts the
            # error event.
            _quiet_unlink(part_path)
            raise

        if task.cancelled:
            _quiet_unlink(part_path)
            app.download_events.put(("done", task, "cancelled"))
            return

        try:
            os.replace(part_path, target_path)
        except OSError as e:
            raise RuntimeError(f"could not finalise download to {target_path}: {e}") from e

        transcript_text = (episode.transcript_text or "").strip()
        if transcript_text:
            transcript_basename = smtv_mod.transcript_filename(episode)
            mode = chosen.get("mode", "")
            if mode.startswith("video"):
                stem, _ = os.path.splitext(basename)
                transcript_basename = stem + ".txt"
            elif mode == "audio":
                stem, _ = os.path.splitext(basename)
                transcript_basename = stem + ".txt"
            transcript_path = os.path.join(task.folder, transcript_basename)
            try:
                with open(transcript_path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(transcript_text + "\n")
                app.download_events.put(
                    ("log", task, f"--- SMTV transcript saved: {transcript_basename} ---")
                )
            except OSError as e:
                app.download_events.put(
                    ("log", task, f"transcript write failed for {transcript_basename}: {e}")
                )

        app.download_events.put(
            ("done_full", task, {"status": "finished", "saved_path": target_path})
        )

    def _stream_smtv_file(
        self, task: "VideoDownloadTask", url: str, dest_path: str
    ) -> None:
        """Chunked GET → write to dest_path with progress events.

        Posts ``progress`` events throttled to once per ~500 ms so we
        don't drown the Tk poll loop. Honours ``task.cancelled``.
        """
        app = self.app
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WhisperProject"
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60.0) as resp:
                total = _content_length_or_none(resp)
                downloaded = 0
                last_emit = 0.0
                with open(dest_path, "wb") as out:
                    while True:
                        if task.cancelled:
                            return
                        chunk = resp.read(262144)
                        if not chunk:
                            break
                        out.write(chunk)
                        downloaded += len(chunk)
                        now = time.monotonic()
                        if total and (now - last_emit) >= 0.5:
                            percent = (downloaded / total) * 100.0
                            app.download_events.put(("progress", task, percent))
                            last_emit = now
                if total:
                    app.download_events.put(("progress", task, 100.0))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"SMTV CDN HTTP {e.code}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"SMTV CDN network error: {e.reason}") from e
        except TimeoutError as e:
            raise RuntimeError("SMTV CDN read timeout") from e

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
                import time as _time
                if getattr(task, "end_time", None) is None:
                    try:
                        task.end_time = _time.time()
                    except AttributeError:
                        pass
                app.log(payload)
                if app.download_current is task:
                    app.download_current = None
                self.process_queue()

            app.refresh_download_queue()

        app.after(300, self.poll)

    def _finish(self, task: "VideoDownloadTask", status: str, saved_path: str | None) -> None:
        app = self.app
        task.status = status
        # Freeze the Elapsed column the moment the task is terminal,
        # regardless of which status it ended in (finished / error /
        # cancelled). Without this, app.fmt_time kept ticking.
        # Defensive getattr — the unit suite passes a SimpleNamespace
        # mock that doesn't carry end_time.
        if getattr(task, "end_time", None) is None:
            import time as _time
            try:
                task.end_time = _time.time()
            except AttributeError:
                pass
        if status == "finished":
            task.progress = 100
            if saved_path:
                # Friendly completion line — the user actually wants
                # to know "what file landed, where, how big". Ring
                # the bell so they notice even if they're in another
                # window or scrolling the console.
                try:
                    size = os.path.getsize(saved_path)
                    if size < 1024 * 1024:
                        size_str = f"{size / 1024:.1f} KB"
                    elif size < 1024 * 1024 * 1024:
                        size_str = f"{size / (1024 * 1024):.1f} MB"
                    else:
                        size_str = f"{size / (1024 * 1024 * 1024):.2f} GB"
                except OSError:
                    size_str = "?"
                app.log(
                    f"✓ Downloaded: {os.path.basename(saved_path)} "
                    f"({size_str}) → {os.path.dirname(saved_path) or '.'}"
                )
                if getattr(app, "chime_on_complete_var", None) is not None:
                    try:
                        if app.chime_on_complete_var.get():
                            app.bell()
                    except Exception:  # noqa: BLE001
                        pass
            if app.app_config.get("auto_transcribe_after_download") and saved_path:
                try:
                    app.enqueue_transcription_from_download(saved_path, task.detected_language)
                    app.log(f"→ Queued for transcription: {os.path.basename(saved_path)}")
                except Exception as e:  # noqa: BLE001
                    app.log(f"Auto-transcribe wiring failed: {e}")
        # Phase 3a — finalise the history row.
        history = getattr(app, "history", None)
        if history is not None and getattr(task, "history_id", 0):
            try:
                history.finish_download(
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
