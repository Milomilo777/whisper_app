"""yt-dlp format lookup service.

Runs ``yt-dlp --dump-single-json`` in a daemon thread and posts the parsed
info dict back to the App via ``app.format_events``.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from queue import Empty
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.app import App


class FormatService:
    def __init__(self, app: "App") -> None:
        self.app = app

    def schedule_lookup(self) -> None:
        if self.app.format_lookup_after:
            self.app.after_cancel(self.app.format_lookup_after)
        self.app.format_lookup_after = self.app.after(800, self.lookup_formats)

    def lookup_formats(self) -> None:
        url = self.app.download_url_var.get().strip()
        self.app.format_lookup_after = None
        self.app.audio_format_map = {}
        self.app.video_format_map = {}
        self.app.current_video_title = ""
        self.app.current_video_language = ""
        self.app.audio_format_combo["values"] = []
        self.app.video_format_combo["values"] = []
        self.app.audio_format_var.set("")
        self.app.video_format_var.set("")
        if not url:
            self.app.format_status_var.set("Enter a URL to load available formats")
            return

        self.app.format_status_var.set("Loading formats...")

        def run() -> None:
            try:
                cmd = [
                    self.app.yt_dlp_path(),
                    "--ffmpeg-location",
                    self.app.bin_path(),
                    "--dump-single-json",
                    "--no-playlist",
                    "--no-warnings",
                    url,
                ]
                r = subprocess.run(
                    cmd,
                    cwd=os.path.dirname(os.path.abspath(self.app.entry_file)),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=60,
                )
                if r.returncode:
                    raise RuntimeError(
                        (r.stderr or r.stdout or "yt-dlp could not read this URL").strip()
                    )
                info = json.loads(r.stdout)
                self.app.format_events.put(("formats", url, info))
            except Exception as e:  # noqa: BLE001
                self.app.format_events.put(("error", url, str(e)))

        threading.Thread(target=run, daemon=True).start()

    def poll(self) -> None:
        app = self.app
        while True:
            try:
                kind, url, payload = app.format_events.get_nowait()
            except Empty:
                break

            if url != app.download_url_var.get().strip():
                continue

            if kind == "error":
                app.format_status_var.set(payload)
                continue

            audio_values = ["Best audio"]
            video_values = ["Best video"]
            app.audio_format_map = {"Best audio": {"kind": "best_audio"}}
            app.video_format_map = {"Best video": {"kind": "best_video"}}
            app.current_video_title = payload.get("title", "")
            lang = payload.get("language") or ""
            if not lang:
                auto_caps = payload.get("automatic_captions") or {}
                lang = next(iter(auto_caps.keys()), "") if auto_caps else ""
            app.current_video_language = lang

            for fmt in payload.get("formats", []):
                format_id = str(fmt.get("format_id", ""))
                ext = fmt.get("ext") or "unknown"
                resolution = fmt.get("resolution") or (
                    f"{fmt.get('width')}x{fmt.get('height')}"
                    if fmt.get("width") and fmt.get("height")
                    else ""
                )
                note = fmt.get("format_note") or ""
                acodec = fmt.get("acodec") or ""
                vcodec = fmt.get("vcodec") or ""
                if not format_id:
                    continue

                if acodec and acodec != "none" and (not vcodec or vcodec == "none"):
                    abr = f"{fmt.get('abr')}k" if fmt.get("abr") else ""
                    label = " | ".join(p for p in (format_id, ext, note, abr, f"a:{acodec}") if p)
                    if label not in app.audio_format_map:
                        audio_values.append(label)
                        app.audio_format_map[label] = {"kind": "format_id", "format_id": format_id}

                if vcodec and vcodec != "none":
                    fps = f"{fmt.get('fps')}fps" if fmt.get("fps") else ""
                    label = " | ".join(
                        p for p in (format_id, ext, resolution, note, fps, f"v:{vcodec}") if p
                    )
                    if label not in app.video_format_map:
                        video_values.append(label)
                        app.video_format_map[label] = {"kind": "format_id", "format_id": format_id}

            app.audio_format_combo["values"] = audio_values
            app.video_format_combo["values"] = video_values
            if audio_values:
                app.audio_format_var.set(audio_values[0])
            if video_values:
                app.video_format_var.set(video_values[0])
            app.update_download_mode()
            if audio_values or video_values:
                app.format_status_var.set(
                    f"{len(audio_values)} audio and {len(video_values)} video formats loaded"
                )
            else:
                app.format_status_var.set("No formats found")

        app.after(200, self.poll)
