"""TranscriptViewer — modal Toplevel that shows a saved JSON transcript.

  - Left side: scrollable segment list. Each row carries the
    timestamp, optional speaker label, and the segment text.
  - Right side: a media player (when python-vlc + libvlc are
    available on the system), or a fallback "Open in system
    player" button when VLC isn't installed.
  - Single-click on a segment → seek the media to that segment's
    start time (when VLC is up).
  - Search box at the top filters the segment list.

The viewer reads the ``.json`` output that core/writers/json_writer
produces. The matching media file is found next to the JSON by
checking the configured ``output_formats`` of the run — falls back
to any common audio/video extension that lives next to the JSON.
"""
from __future__ import annotations

import json
import logging
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Optional


logger = logging.getLogger(__name__)


_MEDIA_EXTENSIONS = (".mp4", ".mp3", ".wav", ".m4a", ".mkv", ".webm", ".flac", ".ogg", ".aac")


def _find_media_next_to(json_path: str) -> str | None:
    """Find a media file that pairs with the JSON next to it."""
    base, _ = os.path.splitext(json_path)
    for ext in _MEDIA_EXTENSIONS:
        candidate = base + ext
        if os.path.isfile(candidate):
            return candidate
    return None


def _fmt_hms(seconds: float) -> str:
    """``HH:MM:SS`` short-form."""
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def _try_load_vlc() -> tuple[Any, str]:
    """Return ``(vlc_module_or_None, error_message)``.

    Two ways for VLC to be unavailable: the python-vlc Python
    binding isn't installed, or it is but libvlc.dll can't be
    found on the system. python-vlc raises FileNotFoundError (a
    subclass of OSError) at import time when libvlc.dll is
    missing on Windows — catch both.
    """
    try:
        import vlc  # type: ignore[import-not-found]
    except ImportError as e:
        return None, f"python-vlc binding not installed: {e}"
    except OSError:
        # libvlc.dll not on PATH — the python-vlc import itself
        # ctypes-loads the native library and dies here.
        return None, (
            "VLC media player isn't installed on this system "
            "(libvlc.dll not found). Install VLC to enable embedded "
            "playback. The viewer still works in read-only mode."
        )
    try:
        inst = vlc.Instance()
        if inst is None:
            raise RuntimeError("vlc.Instance() returned None")
        return vlc, ""
    except Exception:  # noqa: BLE001
        return None, (
            "VLC media player isn't installed on this system "
            "(libvlc.dll not found). Install VLC to enable embedded "
            "playback. The viewer still works in read-only mode."
        )


class TranscriptViewer(tk.Toplevel):
    """Modal viewer for a saved transcript JSON.

    Build it via :func:`open_viewer` from anywhere in the app.
    """

    def __init__(
        self,
        master: "tk.Tk | tk.Toplevel",
        json_path: str,
        media_path: str | None = None,
    ) -> None:
        super().__init__(master)
        self.title(f"Transcript — {os.path.basename(json_path)}")
        self.geometry("1100x680")
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.json_path = json_path
        self.media_path = media_path or _find_media_next_to(json_path)

        self.segments: list[dict[str, Any]] = []
        self.filtered_indices: list[int] = []
        self.vlc_mod, self.vlc_unavailable_reason = _try_load_vlc()
        self.vlc_instance: Any = None
        self.vlc_player: Any = None
        self.vlc_seek_after: str | None = None

        self._build_widgets()
        self._load_segments()
        self._populate_listbox()
        if self.vlc_mod is not None and self.media_path:
            self._init_vlc_player()

    # -- widgets ---------------------------------------------------------

    def _build_widgets(self) -> None:
        outer = ttk.Frame(self, padding=8)
        outer.pack(fill="both", expand=True)

        # Top bar: media file label + search box
        topbar = ttk.Frame(outer)
        topbar.pack(fill="x", pady=(0, 6))
        media_label = (
            f"Media: {os.path.basename(self.media_path)}"
            if self.media_path
            else "Media: (none found next to JSON)"
        )
        ttk.Label(topbar, text=media_label, foreground="#666").pack(side="left")

        ttk.Label(topbar, text="Search:").pack(side="left", padx=(20, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refilter())
        ttk.Entry(topbar, textvariable=self.search_var, width=30).pack(side="left")
        ttk.Button(topbar, text="Clear", command=lambda: self.search_var.set("")).pack(
            side="left", padx=(4, 0)
        )
        ttk.Button(topbar, text="Open JSON folder", command=self._open_json_folder).pack(
            side="right"
        )

        # Body: left = segment list, right = media controls
        body = ttk.PanedWindow(outer, orient="horizontal")
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        body.add(left, weight=3)

        cols = ("time", "speaker", "text")
        self.tree = ttk.Treeview(left, columns=cols, show="headings")
        self.tree.heading("time", text="Time")
        self.tree.heading("speaker", text="Speaker")
        self.tree.heading("text", text="Segment")
        self.tree.column("time", width=80, anchor="w")
        self.tree.column("speaker", width=100, anchor="w")
        self.tree.column("text", width=600)
        vsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._on_segment_select)
        self.tree.bind("<Double-Button-1>", self._on_segment_double_click)

        right = ttk.Frame(body, padding=(8, 0, 0, 0))
        body.add(right, weight=2)
        self._build_media_panel(right)

    def _build_media_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Media", font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w"
        )
        # The video frame — VLC will render into this widget id when
        # available. Always pack it so the layout doesn't shift when
        # VLC is missing; just keep it blank.
        self.video_canvas = tk.Frame(parent, bg="black", height=300)
        self.video_canvas.pack(fill="both", expand=True, pady=(4, 6))

        controls = ttk.Frame(parent)
        controls.pack(fill="x")
        self.play_btn = ttk.Button(controls, text="▶ Play", command=self._toggle_play)
        self.play_btn.pack(side="left")
        ttk.Button(controls, text="⏮ Restart", command=self._restart).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(controls, text="Open in system player",
                   command=self._open_in_system_player).pack(side="right")

        self.position_var = tk.StringVar(value="00:00:00 / 00:00:00")
        ttk.Label(parent, textvariable=self.position_var).pack(anchor="w", pady=(6, 0))

        if self.vlc_mod is None:
            note = ttk.Label(
                parent,
                text=self.vlc_unavailable_reason
                or "Embedded playback not available.",
                foreground="#a44",
                wraplength=320,
                justify="left",
            )
            note.pack(anchor="w", pady=(8, 0))
            self.play_btn.state(["disabled"])

    # -- loading ---------------------------------------------------------

    def _load_segments(self) -> None:
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, list):
                raise ValueError("JSON root must be a list of segments")
            self.segments = payload
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(
                "Failed to load transcript",
                f"Could not read {self.json_path}:\n{e}",
                parent=self,
            )
            self.segments = []

    def _populate_listbox(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.filtered_indices = []
        query = (self.search_var.get() if hasattr(self, "search_var") else "").strip().lower()
        for idx, seg in enumerate(self.segments):
            text = (seg.get("text") or "").strip()
            speaker = (seg.get("speaker") or "").strip()
            if query and query not in text.lower() and query not in speaker.lower():
                continue
            self.filtered_indices.append(idx)
            self.tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(_fmt_hms(float(seg.get("start", 0.0))), speaker, text),
            )

    def _refilter(self) -> None:
        self._populate_listbox()

    # -- callbacks -------------------------------------------------------

    def _on_segment_select(self, _event: tk.Event) -> None:
        item = self.tree.focus()
        if not item:
            return
        try:
            idx = int(item)
        except ValueError:
            return
        seg = self.segments[idx]
        self._seek_to(float(seg.get("start", 0.0)))

    def _on_segment_double_click(self, _event: tk.Event) -> None:
        # Same as single-select but also start playback if paused.
        self._on_segment_select(_event)
        if self.vlc_player is not None and not self.vlc_player.is_playing():
            self.vlc_player.play()

    def _open_json_folder(self) -> None:
        folder = os.path.dirname(self.json_path) or "."
        try:
            if os.name == "nt":
                os.startfile(folder)  # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Open failed", str(e), parent=self)

    def _open_in_system_player(self) -> None:
        if not self.media_path:
            messagebox.showinfo(
                "No media",
                "No media file was found alongside the transcript JSON.",
                parent=self,
            )
            return
        try:
            if os.name == "nt":
                os.startfile(self.media_path)  # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Open failed", str(e), parent=self)

    # -- VLC -------------------------------------------------------------

    def _init_vlc_player(self) -> None:
        try:
            self.vlc_instance = self.vlc_mod.Instance("--no-xlib", "--quiet")
            self.vlc_player = self.vlc_instance.media_player_new()
            media = self.vlc_instance.media_new(self.media_path)
            self.vlc_player.set_media(media)
            # Bind player to the right-side canvas via the canvas's
            # window ID (HWND on Windows).
            try:
                hwnd = self.video_canvas.winfo_id()
                self.vlc_player.set_hwnd(hwnd)
            except Exception:  # noqa: BLE001
                pass
            # Position-update loop
            self.after(250, self._update_position)
        except Exception as e:  # noqa: BLE001
            logger.warning("VLC init failed: %s", e)
            self.vlc_player = None
            self.play_btn.state(["disabled"])

    def _toggle_play(self) -> None:
        if self.vlc_player is None:
            return
        if self.vlc_player.is_playing():
            self.vlc_player.pause()
            self.play_btn.configure(text="▶ Play")
        else:
            self.vlc_player.play()
            self.play_btn.configure(text="⏸ Pause")

    def _restart(self) -> None:
        if self.vlc_player is None:
            return
        self.vlc_player.set_time(0)
        if not self.vlc_player.is_playing():
            self.vlc_player.play()
            self.play_btn.configure(text="⏸ Pause")

    def _seek_to(self, seconds: float) -> None:
        if self.vlc_player is None:
            return
        try:
            self.vlc_player.set_time(int(seconds * 1000))
        except Exception:  # noqa: BLE001
            pass

    def _update_position(self) -> None:
        if self.vlc_player is None:
            return
        try:
            cur_ms = self.vlc_player.get_time() or 0
            total_ms = self.vlc_player.get_length() or 0
            self.position_var.set(
                f"{_fmt_hms(cur_ms / 1000.0)} / {_fmt_hms(total_ms / 1000.0)}"
            )
        except Exception:  # noqa: BLE001
            pass
        self.vlc_seek_after = self.after(250, self._update_position)

    # -- cleanup ---------------------------------------------------------

    def _on_close(self) -> None:
        if self.vlc_seek_after is not None:
            try:
                self.after_cancel(self.vlc_seek_after)
            except Exception:  # noqa: BLE001
                pass
            self.vlc_seek_after = None
        if self.vlc_player is not None:
            try:
                self.vlc_player.stop()
                self.vlc_player.release()
            except Exception:  # noqa: BLE001
                pass
        if self.vlc_instance is not None:
            try:
                self.vlc_instance.release()
            except Exception:  # noqa: BLE001
                pass
        self.destroy()


def open_viewer(
    master: "tk.Tk | tk.Toplevel",
    json_path: Optional[str] = None,
) -> None:
    """Open the viewer.

    If ``json_path`` is None, prompt the user to pick one.
    """
    if json_path is None:
        chosen = filedialog.askopenfilename(
            title="Open transcript JSON",
            filetypes=[("Transcript JSON", "*.json"), ("All files", "*.*")],
            parent=master,
        )
        if not chosen:
            return
        json_path = chosen
    if not os.path.isfile(json_path):
        messagebox.showerror(
            "Transcript missing",
            f"That JSON file does not exist:\n{json_path}",
            parent=master,
        )
        return
    TranscriptViewer(master, json_path)
