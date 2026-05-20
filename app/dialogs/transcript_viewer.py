"""TranscriptViewer — modal Toplevel that shows a saved JSON transcript.

  - Left side: scrollable segment list. Each row carries the
    timestamp, optional speaker label, and the segment text.
  - Right side: a media player (when python-vlc + libvlc are
    available on the system), or a fallback "Open in system
    player" button when VLC isn't installed.
  - Single-click on a segment → seek the media to that segment's
    start time (when VLC is up).
  - Search box at the top filters the segment list.
  - Ctrl+F opens the Find-and-replace dialog operating on segment
    text in memory; "Save Changes" writes back via the JSON writer.
  - Right-click on a speaker cell → "Rename speaker..." rewrites
    every segment with the same speaker label.
  - Word-confidence colour coding when a segment carries ``words``
    with probabilities.
  - Filler-word remove tool (one-click button) strips ``uh``, ``um``,
    ``er``, … from every segment text.
  - Karaoke-style word highlight follows the VLC playhead through
    the active segment's ``words`` list.

The viewer reads the ``.json`` output that core/writers/json_writer
produces. The matching media file is found next to the JSON by
checking the configured ``output_formats`` of the run — falls back
to any common audio/video extension that lives next to the JSON.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Optional


logger = logging.getLogger(__name__)


_MEDIA_EXTENSIONS = (".mp4", ".mp3", ".wav", ".m4a", ".mkv", ".webm", ".flac", ".ogg", ".aac")

# Words considered "fillers" by the one-click cleanup tool. Conservative
# — we don't strip "like" or "you know" because those frequently carry
# semantic weight; tweak the list here if you want a stricter pass.
_FILLER_WORDS = ("uh", "um", "uhm", "er", "erm", "eh", "ah", "mm", "mmm", "hm")


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


def _filler_regex() -> re.Pattern[str]:
    """Build a single regex that matches any filler with optional
    trailing punctuation. Whole-word match, case-insensitive."""
    words = "|".join(re.escape(w) for w in _FILLER_WORDS)
    return re.compile(rf"(?i)\b(?:{words})\b[,.!?\s]*\s?")


def _segment_min_probability(seg: dict[str, Any]) -> float | None:
    """Min word-confidence in a segment, or None when not available."""
    words = seg.get("words") or []
    probs: list[float] = []
    for w in words:
        try:
            probs.append(float(w.get("probability", 0.0)))
        except (TypeError, ValueError):
            continue
    if not probs:
        return None
    return min(probs)


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


def _strip_fillers(text: str, pattern: re.Pattern[str]) -> str:
    """Return ``text`` with filler words removed, internal whitespace
    collapsed, and leading punctuation cleaned up."""
    cleaned = pattern.sub("", text)
    # Collapse double spaces and tidy leading punctuation
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    cleaned = re.sub(r"^[,.!?\s]+", "", cleaned)
    return cleaned


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
        self.geometry("1180x720")
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.json_path = json_path
        self.media_path = media_path or _find_media_next_to(json_path)

        self.segments: list[dict[str, Any]] = []
        self.filtered_indices: list[int] = []
        self._dirty = False
        self._active_segment_idx: int | None = None
        self._active_word_idx: int | None = None

        self.vlc_mod, self.vlc_unavailable_reason = _try_load_vlc()
        self.vlc_instance: Any = None
        self.vlc_player: Any = None
        self.vlc_seek_after: str | None = None

        self._build_widgets()
        self._load_segments()
        self._populate_listbox()
        if self.vlc_mod is not None and self.media_path:
            self._init_vlc_player()

        # Find-and-replace shortcut.
        self.bind("<Control-f>", lambda _e: self._open_find_replace())
        self.bind("<Control-F>", lambda _e: self._open_find_replace())
        self.bind("<Control-s>", lambda _e: self._save_changes())
        self.bind("<Control-S>", lambda _e: self._save_changes())

    # -- widgets ---------------------------------------------------------

    def _build_widgets(self) -> None:
        outer = ttk.Frame(self, padding=8)
        outer.pack(fill="both", expand=True)

        # Top bar: media file label + search box + edit tools
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
        ttk.Entry(topbar, textvariable=self.search_var, width=24).pack(side="left")
        ttk.Button(topbar, text="Clear", command=lambda: self.search_var.set("")).pack(
            side="left", padx=(4, 0)
        )

        # Edit tools group
        ttk.Separator(topbar, orient="vertical").pack(side="left", padx=8, fill="y")
        ttk.Button(topbar, text="Find & Replace  (Ctrl+F)",
                   command=self._open_find_replace).pack(side="left", padx=(0, 4))
        ttk.Button(topbar, text="Remove fillers",
                   command=self._remove_fillers).pack(side="left", padx=(0, 4))
        ttk.Button(topbar, text="Save changes  (Ctrl+S)",
                   command=self._save_changes).pack(side="left", padx=(0, 4))

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
        self.tree.column("speaker", width=110, anchor="w")
        self.tree.column("text", width=620)
        # Confidence colour tags. The cell text becomes the colour;
        # background stays unchanged so the row's highlight tag
        # (for karaoke) layers cleanly on top.
        self.tree.tag_configure("conf_high", foreground="#1e6f1e")     # green
        self.tree.tag_configure("conf_med", foreground="#9c6f00")      # amber
        self.tree.tag_configure("conf_low", foreground="#a00000")      # red
        self.tree.tag_configure("active", background="#fffacd")        # karaoke
        vsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._on_segment_select)
        self.tree.bind("<Double-Button-1>", self._on_segment_double_click)
        # Right-click menu — currently only the speaker rename entry,
        # extensible later. Track which item was clicked so the menu
        # acts on the right row even when no row is selected.
        self.tree.bind("<Button-3>", self._on_segment_right_click)

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

        # Karaoke word panel — shows the active segment's words with
        # the current one highlighted. When the segment has no word
        # timestamps, falls back to the segment text.
        self._words_lbl = ttk.Label(
            parent, text="", justify="left", wraplength=380, padding=(2, 4),
        )
        self._words_lbl.pack(anchor="w", fill="x", pady=(8, 0))

        if self.vlc_mod is None:
            note = ttk.Label(
                parent,
                text=self.vlc_unavailable_reason
                or "Embedded playback not available.",
                foreground="#a44",
                wraplength=360,
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
            min_prob = _segment_min_probability(seg)
            tags: tuple[str, ...] = ()
            if min_prob is not None:
                if min_prob >= 0.85:
                    tags = ("conf_high",)
                elif min_prob >= 0.6:
                    tags = ("conf_med",)
                else:
                    tags = ("conf_low",)
            self.tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(_fmt_hms(float(seg.get("start", 0.0))), speaker, text),
                tags=tags,
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
        self._set_active_segment(idx)

    def _on_segment_double_click(self, _event: tk.Event) -> None:
        # Same as single-select but also start playback if paused.
        self._on_segment_select(_event)
        if self.vlc_player is not None and not self.vlc_player.is_playing():
            self.vlc_player.play()
            self.play_btn.configure(text="⏸ Pause")

    def _on_segment_right_click(self, event: tk.Event) -> None:
        """Pop the segment context menu.

        Currently exposes:
          - Rename speaker (when the row carries one)
          - Copy text
        """
        item = self.tree.identify_row(event.y)
        if not item:
            return
        try:
            idx = int(item)
        except ValueError:
            return
        # Select the row so subsequent edit ops act on it.
        self.tree.selection_set(item)
        seg = self.segments[idx]
        speaker = (seg.get("speaker") or "").strip()
        menu = tk.Menu(self, tearoff=0)
        if speaker:
            menu.add_command(
                label=f"Rename '{speaker}' (everywhere)...",
                command=lambda s=speaker: self._rename_speaker(s),
            )
        menu.add_command(
            label="Copy text", command=lambda: self._copy_to_clipboard(
                (seg.get("text") or "").strip()
            )
        )
        menu.tk_popup(event.x_root, event.y_root)

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

    # -- edit operations -------------------------------------------------

    def _open_find_replace(self) -> None:
        FindReplaceDialog(self).show()

    def _rename_speaker(self, current: str) -> None:
        new = simpledialog.askstring(
            "Rename speaker",
            f"Rename every '{current}' to:",
            parent=self,
            initialvalue=current,
        )
        if not new or new.strip() == current:
            return
        renamed = 0
        for seg in self.segments:
            if (seg.get("speaker") or "").strip() == current:
                seg["speaker"] = new.strip()
                renamed += 1
        if renamed:
            self._dirty = True
            self._populate_listbox()
            messagebox.showinfo(
                "Renamed",
                f"Renamed {renamed} segment(s). Use Save changes (Ctrl+S) to write.",
                parent=self,
            )

    def _remove_fillers(self) -> None:
        if not messagebox.askyesno(
            "Remove fillers",
            "Remove ‘uh’, ‘um’, ‘er’, ‘ah’, … from every segment?",
            parent=self,
        ):
            return
        pattern = _filler_regex()
        changed = 0
        for seg in self.segments:
            original = (seg.get("text") or "")
            cleaned = _strip_fillers(original, pattern)
            if cleaned != original.strip():
                seg["text"] = cleaned
                changed += 1
        if changed:
            self._dirty = True
            self._populate_listbox()
        messagebox.showinfo(
            "Fillers removed",
            f"Updated {changed} segment(s). Use Save changes (Ctrl+S) to write.",
            parent=self,
        )

    def _save_changes(self) -> None:
        if not self._dirty:
            return
        try:
            from core.writers import json_writer as _jw  # type: ignore[import-not-found]
            payload_s = _jw.write(self.segments, audio_path=self.media_path or "")
        except Exception:  # noqa: BLE001
            # Fall back to a stdlib json.dumps if the project import
            # ever fails in a stripped-down environment.
            payload_s = json.dumps(self.segments, indent=2, ensure_ascii=False) + "\n"
        part = self.json_path + ".part"
        try:
            with open(part, "w", encoding="utf-8", newline="\n") as f:
                f.write(payload_s)
            os.replace(part, self.json_path)
        except Exception as e:  # noqa: BLE001
            try:
                os.unlink(part)
            except OSError:
                pass
            messagebox.showerror("Save failed", str(e), parent=self)
            return
        self._dirty = False
        messagebox.showinfo(
            "Saved",
            f"Wrote {len(self.segments)} segment(s) → "
            f"{os.path.basename(self.json_path)}",
            parent=self,
        )

    def _copy_to_clipboard(self, text: str) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
        except Exception:  # noqa: BLE001
            pass

    # -- VLC + karaoke ---------------------------------------------------

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
            self._update_karaoke(cur_ms / 1000.0)
        except Exception:  # noqa: BLE001
            pass
        self.vlc_seek_after = self.after(250, self._update_position)

    def _set_active_segment(self, idx: int) -> None:
        """Mark a segment as the active one (visually + for karaoke).

        Adds the ``active`` tag to the row in the Treeview and stashes
        the index so the karaoke updater knows which segment's words
        to scan.
        """
        if self._active_segment_idx == idx:
            return
        # Clear the previous row's active tag.
        if self._active_segment_idx is not None:
            try:
                prev = str(self._active_segment_idx)
                if self.tree.exists(prev):
                    self.tree.item(prev, tags=self._tags_for(self._active_segment_idx))
            except Exception:  # noqa: BLE001
                pass
        self._active_segment_idx = idx
        self._active_word_idx = None
        try:
            cur = str(idx)
            if self.tree.exists(cur):
                # Layer "active" on top of the colour tag.
                tags = ("active",) + self._tags_for(idx)
                self.tree.item(cur, tags=tags)
                self.tree.see(cur)
        except Exception:  # noqa: BLE001
            pass

    def _tags_for(self, idx: int) -> tuple[str, ...]:
        if idx < 0 or idx >= len(self.segments):
            return ()
        min_prob = _segment_min_probability(self.segments[idx])
        if min_prob is None:
            return ()
        if min_prob >= 0.85:
            return ("conf_high",)
        if min_prob >= 0.6:
            return ("conf_med",)
        return ("conf_low",)

    def _update_karaoke(self, t_seconds: float) -> None:
        """Refresh the active segment + word highlight from the playhead."""
        # Find the active segment (the one whose [start, end] covers t).
        active_idx: int | None = None
        for idx, seg in enumerate(self.segments):
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", start))
            if start <= t_seconds <= end:
                active_idx = idx
                break
        if active_idx is None:
            return
        if active_idx != self._active_segment_idx:
            self._set_active_segment(active_idx)

        seg = self.segments[active_idx]
        words = seg.get("words") or []
        if not words:
            self._words_lbl.configure(text=(seg.get("text") or "").strip())
            return
        # Find the active word inside the segment.
        active_w_idx: int | None = None
        for w_idx, w in enumerate(words):
            try:
                ws = float(w.get("start", 0.0))
                we = float(w.get("end", ws))
            except (TypeError, ValueError):
                continue
            if ws <= t_seconds <= we:
                active_w_idx = w_idx
                break
        if active_w_idx == self._active_word_idx:
            return
        self._active_word_idx = active_w_idx
        # Build the karaoke string. Active word wrapped in […].
        parts: list[str] = []
        for w_idx, w in enumerate(words):
            token = str(w.get("word", "") or "").strip()
            if not token:
                continue
            if w_idx == active_w_idx:
                parts.append(f"[{token}]")
            else:
                parts.append(token)
        self._words_lbl.configure(text=" ".join(parts))

    # -- cleanup ---------------------------------------------------------

    def _on_close(self) -> None:
        if self._dirty:
            if not messagebox.askyesno(
                "Discard changes?",
                "There are unsaved transcript edits. Close anyway?",
                parent=self,
            ):
                return
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


class FindReplaceDialog(tk.Toplevel):
    """Compact Ctrl+F dialog.

    Operates on the parent viewer's ``segments`` list in memory:
    ``Find next`` scrolls + selects the next matching row, ``Replace``
    overwrites the selected match, ``Replace all`` does the whole list
    in one shot. Save is a separate explicit step in the viewer.
    """

    def __init__(self, viewer: "TranscriptViewer") -> None:
        super().__init__(viewer)
        self.viewer = viewer
        self.title("Find and replace")
        self.transient(viewer)
        self.geometry("420x180")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.find_var = tk.StringVar()
        self.replace_var = tk.StringVar()
        self.case_var = tk.BooleanVar(value=False)
        self.last_match_idx: int = -1

        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="Find").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(body, textvariable=self.find_var, width=42).grid(
            row=0, column=1, sticky="ew", padx=(6, 0)
        )
        ttk.Label(body, text="Replace").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(body, textvariable=self.replace_var, width=42).grid(
            row=1, column=1, sticky="ew", padx=(6, 0)
        )
        ttk.Checkbutton(body, text="Match case", variable=self.case_var).grid(
            row=2, column=1, sticky="w", padx=(6, 0)
        )

        btns = ttk.Frame(body)
        btns.grid(row=3, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="Find next", command=self.find_next).pack(
            side="left", padx=4
        )
        ttk.Button(btns, text="Replace", command=self.replace_current).pack(
            side="left", padx=4
        )
        ttk.Button(btns, text="Replace all", command=self.replace_all).pack(
            side="left", padx=4
        )
        ttk.Button(btns, text="Close", command=self.destroy).pack(
            side="left", padx=4
        )

        body.columnconfigure(1, weight=1)

    def show(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def _needle(self) -> str:
        return self.find_var.get() or ""

    def _match(self, haystack: str, needle: str) -> bool:
        if not needle:
            return False
        if self.case_var.get():
            return needle in haystack
        return needle.lower() in haystack.lower()

    def find_next(self) -> bool:
        needle = self._needle()
        if not needle:
            return False
        start = self.last_match_idx + 1
        n = len(self.viewer.segments)
        for offset in range(n):
            idx = (start + offset) % n
            seg = self.viewer.segments[idx]
            if self._match(seg.get("text", "") or "", needle):
                self.last_match_idx = idx
                self._reveal(idx)
                return True
        messagebox.showinfo("No match", f"'{needle}' not found.", parent=self)
        return False

    def _reveal(self, idx: int) -> None:
        item = str(idx)
        try:
            self.viewer.tree.see(item)
            self.viewer.tree.selection_set(item)
            self.viewer.tree.focus(item)
        except Exception:  # noqa: BLE001
            pass

    def replace_current(self) -> None:
        needle = self._needle()
        if not needle:
            return
        if self.last_match_idx < 0 or self.last_match_idx >= len(self.viewer.segments):
            if not self.find_next():
                return
        seg = self.viewer.segments[self.last_match_idx]
        text = seg.get("text", "") or ""
        replacement = self.replace_var.get() or ""
        if self.case_var.get():
            new_text = text.replace(needle, replacement)
        else:
            new_text = re.sub(re.escape(needle), replacement, text, flags=re.IGNORECASE)
        if new_text == text:
            self.find_next()
            return
        seg["text"] = new_text
        self.viewer._dirty = True
        self.viewer._populate_listbox()
        self.find_next()

    def replace_all(self) -> None:
        needle = self._needle()
        if not needle:
            return
        replacement = self.replace_var.get() or ""
        count = 0
        for seg in self.viewer.segments:
            text = seg.get("text", "") or ""
            if self.case_var.get():
                new_text = text.replace(needle, replacement)
            else:
                new_text = re.sub(
                    re.escape(needle), replacement, text, flags=re.IGNORECASE
                )
            if new_text != text:
                seg["text"] = new_text
                count += 1
        if count:
            self.viewer._dirty = True
            self.viewer._populate_listbox()
        messagebox.showinfo(
            "Replace all",
            f"Replaced in {count} segment(s).",
            parent=self,
        )


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
