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
import subprocess
import sys
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


# Resolution of the transport-bar seek slider. The slider runs 0..N and
# we map that to libvlc's 0.0..1.0 fractional position. A higher number
# = finer scrubbing granularity.
_SEEK_SLIDER_MAX = 1000


def _fmt_mmss(ms: float) -> str:
    """``MM:SS`` (or ``H:MM:SS`` past an hour) from a millisecond count.

    Used by the transport-bar time readout. libvlc returns ``-1`` for an
    unknown time/length (no media loaded yet, or a stream with no
    duration), so anything <= 0 collapses to ``00:00`` rather than a
    bogus negative clock.
    """
    total_s = int(ms // 1000) if ms and ms > 0 else 0
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _slider_to_fraction(value: float) -> float:
    """Map a transport-slider value (0.._SEEK_SLIDER_MAX) → 0.0..1.0.

    Clamped so a stray out-of-range value from the Tk scale can never
    drive libvlc ``set_position`` outside its valid domain.
    """
    frac = value / float(_SEEK_SLIDER_MAX)
    if frac < 0.0:
        return 0.0
    if frac > 1.0:
        return 1.0
    return frac


def _fraction_to_slider(fraction: float) -> float:
    """Map a libvlc position (0.0..1.0) → transport-slider value.

    Inverse of :func:`_slider_to_fraction`; clamped to the slider's
    range so a transient out-of-bounds ``get_position`` (libvlc returns
    values slightly past 1.0 near end-of-media) can't overshoot the
    widget.
    """
    if fraction < 0.0:
        fraction = 0.0
    elif fraction > 1.0:
        fraction = 1.0
    return fraction * _SEEK_SLIDER_MAX


def _clamp_time_ms(current_ms: float, delta_ms: float, total_ms: float) -> int:
    """Skip-button arithmetic: ``current + delta`` clamped to the media.

    Never returns < 0. When ``total_ms`` is known (> 0) the result is
    also capped just below the end (``total - 1``) so a forward skip
    past the end doesn't drive libvlc to a position it rejects; when the
    length is unknown (libvlc ``-1``/``0``) only the lower bound applies.
    """
    target = int(current_ms) + int(delta_ms)
    if target < 0:
        target = 0
    if total_ms and total_ms > 0 and target > total_ms - 1:
        target = int(total_ms) - 1
        if target < 0:
            target = 0
    return target


def _filler_regex() -> re.Pattern[str]:
    """Build a single regex that matches any filler with optional
    trailing punctuation + one trailing space. Whole-word match,
    case-insensitive. We deliberately do NOT eat the leading space:
    swallowing it on "Hello, um, world" would collapse to
    "Hello,world", losing the natural punctuation spacing. Instead
    ``_strip_fillers`` post-processes any "  " or " ." artefacts."""
    words = "|".join(re.escape(w) for w in _FILLER_WORDS)
    return re.compile(rf"(?i)\b(?:{words})\b[,.!?]*\s?")


def _seg_float(seg: dict[str, Any], key: str, default: float = 0.0) -> float:
    """Read ``seg[key]`` as a float, coercing defensively to ``default``.

    Transcript JSON is user-supplied (or hand-edited), so a segment's
    ``start`` / ``end`` may carry a non-numeric value — a European
    decimal string like ``"1,5"``, a stray ``"abc"``, or ``None``. A
    bare ``float(seg.get(...))`` on those raises ``ValueError`` /
    ``TypeError`` and crashes the viewer at construction, bypassing the
    friendly "pick the .json" guard in :meth:`_load_segments`. Coercing
    to ``default`` (0.0) keeps the row visible with a sane timestamp
    instead of taking down the whole window.
    """
    try:
        return float(seg.get(key, default))
    except (TypeError, ValueError):
        return default


def _segment_min_probability(seg: dict[str, Any]) -> float | None:
    """Min word-confidence in a segment, or None when not available.

    A segment's ``words`` is normally a list of dicts, but a hand-edited
    / unrelated JSON may carry a list of NON-dict elements (e.g.
    ``words: [1, 2]`` or ``["a"]``). Calling ``.get(...)`` on a non-dict
    raises ``AttributeError`` — which the ``(TypeError, ValueError)``
    handler does NOT catch — crashing the viewer at construction and
    bypassing the friendly "pick the .json" guard in
    :meth:`_load_segments`. Skip non-dict entries defensively, mirroring
    the :func:`_seg_float` coercion style.
    """
    words = seg.get("words") or []
    probs: list[float] = []
    for w in words:
        if not isinstance(w, dict):
            continue
        try:
            probs.append(float(w.get("probability", 0.0)))
        except (TypeError, ValueError):
            continue
    if not probs:
        return None
    return min(probs)


def _os_open(path: str) -> None:
    """Open a file or folder with the OS default handler (cross-platform)."""
    if sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    elif os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.run(["xdg-open", path], check=False)


def _dir_has_vlc_lib(d: str) -> bool:
    """True if dir ``d`` contains the platform's libvlc shared library."""
    if not d or not os.path.isdir(d):
        return False
    if os.name == "nt":
        return os.path.isfile(os.path.join(d, "libvlc.dll"))
    try:
        for entry in os.listdir(d):
            # libvlc.dylib (mac) / libvlc.so, libvlc.so.5 (linux)
            if entry.startswith("libvlc.") and (".so" in entry or entry.endswith(".dylib")):
                return True
    except OSError:
        return False
    return False


def _locate_vlc_dir() -> str | None:
    """Best-effort path to the dir holding the libvlc shared library.

    python-vlc ctypes-loads libvlc at *import* time; if VLC is installed in
    a standard location that the loader doesn't search, the import fails
    even though VLC is present (the user's "VLC says not installed"
    report). Returning its dir lets _try_load_vlc point python-vlc at it.
    Covers Windows (registry + Program Files), macOS (VLC.app), and Linux
    (the usual library dirs).
    """
    candidates: list[str] = []
    if os.name == "nt":
        try:
            import winreg  # type: ignore[import-not-found]

            for flag in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\VideoLAN\VLC",
                        0, winreg.KEY_READ | flag,
                    ) as key:
                        install_dir, _ = winreg.QueryValueEx(key, "InstallDir")
                        if install_dir:
                            candidates.append(str(install_dir))
                except OSError:
                    pass
        except ImportError:
            pass
        for env_var in ("PROGRAMW6432", "PROGRAMFILES", "PROGRAMFILES(X86)"):
            base = os.environ.get(env_var)
            if base:
                candidates.append(os.path.join(base, "VideoLAN", "VLC"))
    elif sys.platform == "darwin":
        candidates += [
            "/Applications/VLC.app/Contents/MacOS/lib",
            os.path.expanduser("~/Applications/VLC.app/Contents/MacOS/lib"),
        ]
    else:  # linux / other unix — usual shared-library dirs
        candidates += [
            "/usr/lib", "/usr/lib64", "/usr/local/lib",
            "/usr/lib/x86_64-linux-gnu", "/usr/lib/aarch64-linux-gnu",
            "/snap/vlc/current/usr/lib",
        ]
    for d in candidates:
        if _dir_has_vlc_lib(d):
            return d
    return None


def _vlc_lib_file(d: str) -> str | None:
    """Absolute path to the libvlc shared library inside dir ``d``."""
    if os.name == "nt":
        p = os.path.join(d, "libvlc.dll")
        return p if os.path.isfile(p) else None
    try:
        for entry in sorted(os.listdir(d)):
            if entry.startswith("libvlc.") and (".so" in entry or entry.endswith(".dylib")):
                return os.path.join(d, entry)
    except OSError:
        return None
    return None


def _vlc_plugins_dir(d: str) -> str | None:
    """Best-effort VLC plugins dir. Layouts: <vlc>/plugins (Windows),
    <...>/MacOS/plugins (sibling of the lib dir on macOS), and
    <libdir>/vlc/plugins (Linux)."""
    for cand in (
        os.path.join(d, "plugins"),
        os.path.join(os.path.dirname(d), "plugins"),
        os.path.join(d, "vlc", "plugins"),
    ):
        if os.path.isdir(cand):
            return cand
    return None


def _try_load_vlc() -> tuple[Any, str]:
    """Return ``(vlc_module_or_None, error_message)``.

    Two ways for VLC to be unavailable: the python-vlc Python
    binding isn't installed, or it is but libvlc.dll can't be
    found on the system. python-vlc raises FileNotFoundError (a
    subclass of OSError) at import time when libvlc.dll is
    missing on Windows — catch both.
    """
    # Point python-vlc at a standard VLC install before importing, so an
    # installed-but-not-on-PATH VLC is still found.
    vlc_dir = _locate_vlc_dir()
    if vlc_dir:
        lib_file = _vlc_lib_file(vlc_dir)
        if lib_file:
            os.environ.setdefault("PYTHON_VLC_LIB_PATH", lib_file)
        plugins = _vlc_plugins_dir(vlc_dir)
        if plugins:
            os.environ.setdefault("PYTHON_VLC_MODULE_PATH", plugins)
        if os.name == "nt":
            try:
                os.add_dll_directory(vlc_dir)  # type: ignore[attr-defined]
            except (OSError, AttributeError):
                pass
    try:
        import vlc  # type: ignore[import-not-found]
    except ImportError as e:
        return None, f"python-vlc binding not installed: {e}"
    except OSError:
        # libvlc.dll not loadable — either VLC isn't installed, or it's the
        # wrong architecture (this app is 64-bit, so it needs 64-bit VLC).
        return None, (
            "VLC media player isn't installed (or is the 32-bit build — "
            "this app is 64-bit and needs the 64-bit VLC). Install the "
            "64-bit VLC to enable embedded playback. The viewer still "
            "works in read-only mode."
        )
    try:
        inst = vlc.Instance()
        if inst is None:
            raise RuntimeError("vlc.Instance() returned None")
        # Release the probe instance immediately. Leaking it (and then
        # creating a SECOND instance in _init_vlc_player) keeps two native
        # libvlc instances alive at once, which worsens the native
        # instability around the HWND bind on Windows.
        try:
            inst.release()
        except Exception:  # noqa: BLE001
            pass
        return vlc, ""
    except Exception:  # noqa: BLE001
        return None, (
            "VLC loaded but could not start (its plugins may be missing or "
            "the architecture doesn't match — this app is 64-bit). "
            "Reinstall the 64-bit VLC to enable embedded playback. The "
            "viewer still works in read-only mode."
        )


def _strip_fillers(text: str, pattern: re.Pattern[str]) -> str:
    """Return ``text`` with filler words removed, internal whitespace
    collapsed, and leading punctuation cleaned up. We also tidy up
    space-before-punctuation artefacts like ``"Hello !"`` that come
    from removing an inline filler with trailing ``!`` already
    attached."""
    cleaned = pattern.sub("", text)
    # Collapse double spaces and tidy leading punctuation.
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    cleaned = re.sub(r"^[,.!?\s]+", "", cleaned)
    # Remove the orphan space that lands BEFORE a punctuation mark
    # when an inline filler with its trailing punctuation got eaten
    # (e.g. "Hello um!" → "Hello !" → "Hello!").
    cleaned = re.sub(r"\s+([,.!?])", r"\1", cleaned)
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
        # Set on _on_close so any pending after() tick or watcher
        # callback short-circuits before touching destroyed widgets.
        self._closing = False
        # Track find/replace dialog so we can destroy it before the
        # parent viewer closes (otherwise it becomes a zombie that
        # crashes on the next button click).
        self._find_dialog: "FindReplaceDialog | None" = None

        self.vlc_mod, self.vlc_unavailable_reason = _try_load_vlc()
        self.vlc_instance: Any = None
        self.vlc_player: Any = None
        self.vlc_seek_after: str | None = None
        # True while the user is dragging the transport seek slider. The
        # position loop checks this and skips updating the slider so its
        # thumb doesn't snap back to the playhead mid-drag (see
        # _update_position / _on_seek_*).
        self._seeking = False

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

        # Transport keyboard niceties — bound to THIS Toplevel only (not
        # bind_all) so they don't leak into the main app window. Left /
        # Right scrub ∓5s; Space toggles play/pause. All call guarded
        # player methods, so they're harmless when there's no embedded
        # player.
        self.bind("<Left>", self._on_key_skip_back)
        self.bind("<Right>", self._on_key_skip_fwd)
        self.bind("<space>", self._on_key_toggle_play)

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
        # v0.8 — segments the hallucination detector flagged as suspect.
        # Light-red background so the row stands out at a glance; the
        # confidence foreground colour layers on top normally.
        self.tree.tag_configure("suspect", background="#ffe0e0")
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

        # -- transport bar: draggable seek slider + skip + readout ------
        # A horizontal scale the user drags to scrub. The position loop
        # writes the playhead into it, EXCEPT while the user is dragging
        # (self._seeking) so the thumb doesn't fight the drag. On release
        # we jump the player to the slider's fraction.
        self._transport = ttk.Frame(parent)
        self._transport.pack(fill="x", pady=(8, 0))

        self.seek_var = tk.DoubleVar(value=0.0)
        self.seek_scale = ttk.Scale(
            self._transport,
            from_=0.0,
            to=float(_SEEK_SLIDER_MAX),
            orient="horizontal",
            variable=self.seek_var,
            command=self._on_seek_drag,
        )
        self.seek_scale.pack(fill="x")
        # Drag lifecycle: press → suppress auto-update; release → commit
        # the seek to the player and resume auto-update.
        self.seek_scale.bind("<ButtonPress-1>", self._on_seek_press)
        self.seek_scale.bind("<ButtonRelease-1>", self._on_seek_release)

        skips = ttk.Frame(self._transport)
        skips.pack(fill="x", pady=(4, 0))
        self._skip_btns: list[ttk.Button] = []
        for label, delta in (
            ("⏪ -10s", -10000),
            ("◀ -5s", -5000),
            ("+5s ▶", 5000),
            ("+10s ⏩", 10000),
        ):
            b = ttk.Button(
                skips, text=label, width=8,
                command=lambda d=delta: self._skip(d),
            )
            b.pack(side="left", padx=(0, 4))
            self._skip_btns.append(b)

        # MM:SS / MM:SS readout. Kept in its own var (separate from the
        # legacy HH:MM:SS position_var used elsewhere) so the transport
        # bar shows the compact clock the spec asks for.
        self.time_var = tk.StringVar(value="00:00 / 00:00")
        ttk.Label(skips, textvariable=self.time_var).pack(side="right")

        # Retained for backwards compatibility — some callers/tests refer
        # to position_var. The loop keeps it updated alongside time_var.
        self.position_var = tk.StringVar(value="00:00:00 / 00:00:00")

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
            # No embedded player → the transport bar can't control
            # anything, so grey it out. "Open in system player" stays.
            self._set_transport_enabled(False)

    def _set_transport_enabled(self, enabled: bool) -> None:
        """Enable/disable every transport-bar control as a group.

        Used both when VLC is absent at build time and when the deferred
        HWND bind fails at runtime (_disable_embedded_playback). All
        lookups are guarded so this is safe even before the widgets
        exist or after they're destroyed.
        """
        state = ["!disabled"] if enabled else ["disabled"]
        for attr in ("seek_scale",):
            widget = getattr(self, attr, None)
            if widget is not None:
                try:
                    widget.state(state)
                except Exception:  # noqa: BLE001
                    pass
        for b in getattr(self, "_skip_btns", []):
            try:
                b.state(state)
            except Exception:  # noqa: BLE001
                pass

    # -- loading ---------------------------------------------------------

    def _load_segments(self) -> None:
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, list):
                # A transcript JSON is always a list of segment dicts. A dict
                # root almost always means the user picked the wrong file
                # (e.g. a credentials/config JSON), so say so plainly.
                raise ValueError(
                    "This looks like a credentials/config file, not a "
                    "transcript JSON — pick the .json next to your "
                    "audio/video."
                )
            # The root is a list, but it may be a list of NON-dict elements
            # (e.g. ``[1, 2, 3]`` or ``["a", "b"]`` from an unrelated JSON
            # array). Downstream code calls ``.get(...)`` on each segment, so
            # keep only the dict entries. If nothing qualifies, the file isn't
            # a transcript at all — surface the same "pick the .json" guidance
            # instead of crashing with an AttributeError in _populate_listbox.
            segments = [item for item in payload if isinstance(item, dict)]
            if payload and not segments:
                raise ValueError(
                    "This JSON is a list, but none of its entries look like "
                    "transcript segments — pick the .json next to your "
                    "audio/video."
                )
            self.segments = segments
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
        active_idx = self._active_segment_idx
        for idx, seg in enumerate(self.segments):
            text = (seg.get("text") or "").strip()
            speaker = (seg.get("speaker") or "").strip()
            if query and query not in text.lower() and query not in speaker.lower():
                continue
            self.filtered_indices.append(idx)
            min_prob = _segment_min_probability(seg)
            conf_tags: tuple[str, ...] = ()
            if min_prob is not None:
                if min_prob >= 0.85:
                    conf_tags = ("conf_high",)
                elif min_prob >= 0.6:
                    conf_tags = ("conf_med",)
                else:
                    conf_tags = ("conf_low",)
            # v0.8 — light-red row background when the hallucination
            # detector flagged this segment. Layer underneath karaoke
            # 'active' so playback highlight still wins on the active
            # row.
            base_tags: tuple[str, ...] = conf_tags
            if seg.get("suspect"):
                base_tags = ("suspect",) + conf_tags
            # Re-layer the karaoke 'active' tag on top of the
            # confidence + suspect colours when this row is the
            # currently-playing segment.
            if active_idx is not None and idx == active_idx:
                tags = ("active",) + base_tags
            else:
                tags = base_tags
            self.tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(_fmt_hms(_seg_float(seg, "start")), speaker, text),
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
        self._seek_to(_seg_float(seg, "start"))
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
            _os_open(folder)
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
            _os_open(self.media_path)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Open failed", str(e), parent=self)

    # -- edit operations -------------------------------------------------

    def _open_find_replace(self) -> None:
        if self._find_dialog is not None:
            try:
                if self._find_dialog.winfo_exists():
                    self._find_dialog.show()
                    return
            except Exception:  # noqa: BLE001
                pass
        self._find_dialog = FindReplaceDialog(self)
        self._find_dialog.show()

    def _rename_speaker(self, current: str) -> None:
        new = simpledialog.askstring(
            "Rename speaker",
            f"Rename every '{current}' to:",
            parent=self,
            initialvalue=current,
        )
        # Guard against the user pressing OK with empty / whitespace-
        # only input — that would erase every matching speaker label.
        if new is None:
            return
        new_clean = new.strip()
        if not new_clean or new_clean == current:
            return
        renamed = 0
        for seg in self.segments:
            if (seg.get("speaker") or "").strip() == current:
                seg["speaker"] = new_clean
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
            # CRITICAL: do NOT bind the native window handle here. This runs
            # during __init__, before the Toplevel has been realized/mapped,
            # so video_canvas.winfo_id() is either 0 or a not-yet-valid HWND.
            # Calling libvlc set_hwnd() on an unrealized window triggers a
            # native Windows access-violation that bypasses Python try/except
            # and kills the whole process ("View transcript closes the app").
            # Defer the bind until the window is actually mapped.
            self.after(0, self._bind_vlc_window)
        except Exception as e:  # noqa: BLE001
            logger.warning("VLC init failed: %s", e)
            self.vlc_player = None
            self.play_btn.state(["disabled"])

    def _bind_vlc_window(self) -> None:
        """Bind libvlc to the video canvas — only once it is realized.

        Must run AFTER the Toplevel is mapped: set_hwnd/set_xwindow/
        set_nsobject on an unmapped window or a zero window id is a native
        crash on Windows. We force a layout pass, then verify the canvas is
        mapped and has a non-zero id; if not, we degrade to the "Open in
        system player" button rather than risk the access-violation, and we
        do NOT start the position loop (no embedded surface to track).
        """
        if self._closing or self.vlc_player is None:
            return
        try:
            # Force the geometry manager to realize + map the canvas so its
            # native handle is valid before we hand it to libvlc.
            self.update_idletasks()
            mapped = bool(self.video_canvas.winfo_ismapped())
            handle = int(self.video_canvas.winfo_id())
        except Exception as e:  # noqa: BLE001
            logger.warning("VLC window not ready: %s", e)
            self._disable_embedded_playback()
            return
        if not mapped or handle == 0:
            # Not realized yet / no valid surface — fall back to the system
            # player button instead of calling set_hwnd on a dead handle.
            logger.info(
                "VLC video surface not mapped (mapped=%s, id=%s); using "
                "system player fallback.", mapped, handle,
            )
            self._disable_embedded_playback()
            return
        try:
            # The libvlc call differs per platform: HWND on Windows, an
            # NSObject (NSView) on macOS, an X11 window id on Linux.
            if sys.platform == "darwin":
                self.vlc_player.set_nsobject(handle)
            elif os.name == "nt":
                self.vlc_player.set_hwnd(handle)
            else:
                self.vlc_player.set_xwindow(handle)
        except Exception as e:  # noqa: BLE001
            logger.warning("VLC set window handle failed: %s", e)
            self._disable_embedded_playback()
            return
        # Start the position-update loop ONLY after a successful bind.
        self.after(250, self._update_position)

    def _disable_embedded_playback(self) -> None:
        """Tear down embedded playback so only the system-player path stays.

        Called when the video surface can't be bound safely. Releases the
        player and disables the Play button; "Open in system player" still
        works, so the viewer keeps degrading gracefully.
        """
        try:
            if self.vlc_player is not None:
                self.vlc_player.stop()
        except Exception:  # noqa: BLE001
            pass
        self.vlc_player = None
        try:
            self.play_btn.state(["disabled"])
        except Exception:  # noqa: BLE001
            pass
        # Nothing left to scrub — grey out the seek slider + skip buttons.
        self._set_transport_enabled(False)

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

    # -- transport bar: skip + drag-to-seek ------------------------------

    def _skip(self, delta_ms: int) -> None:
        """Jump the playhead by ``delta_ms`` (negative = back), clamped.

        Wired to the ⏪/⏩ buttons and the Left/Right keys. Fully guarded:
        a None / not-yet-bound / VLC-absent player is a silent no-op so
        no exception escapes into the Tk event loop.
        """
        if self.vlc_player is None:
            return
        try:
            cur_ms = self.vlc_player.get_time() or 0
            total_ms = self.vlc_player.get_length() or 0
            target = _clamp_time_ms(cur_ms, delta_ms, total_ms)
            self.vlc_player.set_time(target)
        except Exception:  # noqa: BLE001
            pass

    def _typing_in_entry(self) -> bool:
        """True when keyboard focus is inside a text-entry widget.

        The transport hotkeys are bound on the Toplevel, so they'd
        otherwise hijack Space / arrow keys while the user types in the
        Search box or the Find-and-replace fields. Skip the hotkey then
        and let the keystroke reach the entry normally.
        """
        try:
            focused = self.focus_get()
        except Exception:  # noqa: BLE001
            return False
        if focused is None:
            return False
        return isinstance(focused, (tk.Entry, ttk.Entry))

    def _focus_on_tree(self) -> bool:
        """True when the segment Treeview holds keyboard focus.

        Left/Right normally drive the tree's own column scroll and Up/Down
        its row navigation; we don't want the video-skip hotkey to fight
        that, so the arrow hotkeys defer to the tree when it's focused.
        """
        try:
            return self.focus_get() is self.tree
        except Exception:  # noqa: BLE001
            return False

    def _on_key_skip_back(self, _event: tk.Event) -> str | None:
        # Defer to a focused entry/tree so we don't hijack their arrows.
        if self._typing_in_entry() or self._focus_on_tree():
            return None
        self._skip(-5000)
        return "break"

    def _on_key_skip_fwd(self, _event: tk.Event) -> str | None:
        if self._typing_in_entry() or self._focus_on_tree():
            return None
        self._skip(5000)
        return "break"

    def _on_key_toggle_play(self, _event: tk.Event) -> str | None:
        # Space in an entry types a space; elsewhere (including the tree,
        # where Space has no useful default) it toggles play/pause.
        if self._typing_in_entry():
            return None
        self._toggle_play()
        return "break"

    def _on_seek_press(self, _event: tk.Event) -> None:
        """User grabbed the slider — suppress the auto-update so the
        position loop stops writing the playhead into the thumb and
        fighting the drag."""
        self._seeking = True

    def _on_seek_drag(self, _value: str) -> None:
        """Fires continuously while the slider moves (ttk.Scale command).

        We don't seek the player on every motion event (that would
        stutter the decoder); we only keep the MM:SS readout live so the
        user sees where they're scrubbing to. The actual seek happens on
        button release. Only acts while a drag is in progress.
        """
        if not self._seeking or self.vlc_player is None:
            return
        try:
            total_ms = self.vlc_player.get_length() or 0
            if total_ms and total_ms > 0:
                frac = _slider_to_fraction(self.seek_var.get())
                preview_ms = frac * total_ms
                self.time_var.set(
                    f"{_fmt_mmss(preview_ms)} / {_fmt_mmss(total_ms)}"
                )
        except Exception:  # noqa: BLE001
            pass

    def _on_seek_release(self, _event: tk.Event) -> None:
        """User let go of the slider — commit the seek, then resume the
        auto-update. We prefer set_time(fraction*duration) when the
        length is known (frame-accurate); otherwise fall back to
        set_position(fraction) for streams with no duration."""
        if self.vlc_player is None:
            self._seeking = False
            return
        try:
            frac = _slider_to_fraction(self.seek_var.get())
            total_ms = self.vlc_player.get_length() or 0
            if total_ms and total_ms > 0:
                self.vlc_player.set_time(int(frac * total_ms))
            else:
                self.vlc_player.set_position(frac)
        except Exception:  # noqa: BLE001
            pass
        finally:
            # Always clear the flag so a failed seek doesn't freeze the
            # slider's auto-update forever.
            self._seeking = False

    def _update_position(self) -> None:
        # Guard against ticks that fire after the viewer's been
        # destroyed. _on_close sets _closing BEFORE destroy() so a
        # tick mid-flight short-circuits cleanly rather than calling
        # self.after() on a dead Tcl interpreter.
        if self._closing or self.vlc_player is None:
            return
        try:
            cur_ms = self.vlc_player.get_time() or 0
            total_ms = self.vlc_player.get_length() or 0
            self.position_var.set(
                f"{_fmt_hms(cur_ms / 1000.0)} / {_fmt_hms(total_ms / 1000.0)}"
            )
            # Transport bar: compact MM:SS readout + slider position.
            # Skip BOTH while the user is dragging the slider — updating
            # time_var would be harmless but updating the thumb would
            # yank it back to the playhead (the "snap-back" the spec
            # warns against). _on_seek_drag keeps the readout live during
            # the drag instead.
            if not self._seeking:
                self.time_var.set(
                    f"{_fmt_mmss(cur_ms)} / {_fmt_mmss(total_ms)}"
                )
                pos = self.vlc_player.get_position()
                if pos is not None and pos >= 0.0:
                    self.seek_var.set(_fraction_to_slider(float(pos)))
            self._update_karaoke(cur_ms / 1000.0)
        except Exception:  # noqa: BLE001
            pass
        # Re-arm only if we're still alive. Without this re-check a
        # close that lands between the try block and the after()
        # schedules a tick on a destroyed window.
        if self._closing:
            return
        try:
            self.vlc_seek_after = self.after(250, self._update_position)
        except tk.TclError:
            self.vlc_seek_after = None

    def _set_active_segment(self, idx: int | None) -> None:
        """Mark a segment as the active one (visually + for karaoke).

        ``idx=None`` clears the active highlight without selecting a
        new row — used when the playhead lands in a gap between
        segments.
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
        if idx is None:
            # Clear the karaoke word panel so a stale highlighted
            # word doesn't linger between segments.
            try:
                self._words_lbl.configure(text="")
            except Exception:  # noqa: BLE001
                pass
            return
        try:
            cur = str(idx)
            if self.tree.exists(cur):
                # Layer "active" on top of the colour tag.
                tags = ("active",) + self._tags_for(idx)
                self.tree.item(cur, tags=tags)
                self.tree.see(cur)
        except Exception:  # noqa: BLE001
            pass
        # Reset the karaoke panel to the new segment's text (or empty
        # if no words list); the per-word highlight will fill in on
        # the next tick.
        try:
            seg = self.segments[idx] if 0 <= idx < len(self.segments) else None
            if seg is not None:
                self._words_lbl.configure(text=(seg.get("text") or "").strip())
        except Exception:  # noqa: BLE001
            pass

    def _tags_for(self, idx: int) -> tuple[str, ...]:
        if idx < 0 or idx >= len(self.segments):
            return ()
        seg = self.segments[idx]
        min_prob = _segment_min_probability(seg)
        conf: tuple[str, ...] = ()
        if min_prob is not None:
            if min_prob >= 0.85:
                conf = ("conf_high",)
            elif min_prob >= 0.6:
                conf = ("conf_med",)
            else:
                conf = ("conf_low",)
        if seg.get("suspect"):
            return ("suspect",) + conf
        return conf

    def _update_karaoke(self, t_seconds: float) -> None:
        """Refresh the active segment + word highlight from the playhead.

        Uses ``bisect_left`` over the (sorted) segment-start list to
        find the candidate segment in O(log N) per tick — without
        this, the 250-ms tick costs O(N) which becomes noticeable on
        transcripts with thousands of segments.
        """
        from bisect import bisect_right

        if not self.segments:
            return
        starts = [_seg_float(s, "start") for s in self.segments]
        # Candidate: largest start <= t_seconds.
        i = bisect_right(starts, t_seconds) - 1
        active_idx: int | None = None
        if 0 <= i < len(self.segments):
            seg = self.segments[i]
            start = _seg_float(seg, "start")
            end = _seg_float(seg, "end", start)
            if start <= t_seconds <= end:
                active_idx = i
        if active_idx is None:
            # Playhead in a gap between segments — clear any lingering
            # highlight rather than leaving the previous segment lit.
            if self._active_segment_idx is not None:
                self._set_active_segment(None)
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
        # Set the closing flag FIRST so any after()-loop tick in
        # flight (notably _update_position → _update_karaoke) sees
        # it and short-circuits before touching widgets.
        self._closing = True
        if self.vlc_seek_after is not None:
            try:
                self.after_cancel(self.vlc_seek_after)
            except Exception:  # noqa: BLE001
                pass
            self.vlc_seek_after = None
        # Destroy any open find/replace dialog so it doesn't become
        # a zombie referencing this viewer's destroyed widgets.
        if self._find_dialog is not None:
            try:
                self._find_dialog.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._find_dialog = None
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

    def _is_valid_needle(self, needle: str) -> bool:
        """Reject empty or whitespace-only needles — replacing every
        space in every segment with a user-supplied string is almost
        never intentional and breaks the transcript silently."""
        return bool(needle) and bool(needle.strip())

    def _match(self, haystack: str, needle: str) -> bool:
        if not needle:
            return False
        if self.case_var.get():
            return needle in haystack
        return needle.lower() in haystack.lower()

    def find_next(self) -> bool:
        needle = self._needle()
        if not self._is_valid_needle(needle):
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

    @staticmethod
    def _safe_replace(text: str, needle: str, replacement: str, case_sensitive: bool) -> str:
        """Replace ``needle`` with ``replacement`` literally.

        Critical: we use a lambda over re.sub so backreferences in
        ``replacement`` (``\\1``, ``\\g<name>``, ``\\\\``) are kept as
        literal characters rather than parsed as regex syntax. The
        previous implementation interpreted ``\\1`` as group-1 and
        either crashed or silently mangled the segment text.
        """
        if case_sensitive:
            return text.replace(needle, replacement)
        # Use lambda to avoid re.sub's parsing of \\1 / \\g<...> /
        # \\\\ in the replacement string.
        return re.sub(
            re.escape(needle), lambda _m: replacement, text, flags=re.IGNORECASE
        )

    def replace_current(self) -> None:
        needle = self._needle()
        if not self._is_valid_needle(needle):
            return
        if self.last_match_idx < 0 or self.last_match_idx >= len(self.viewer.segments):
            if not self.find_next():
                return
        seg = self.viewer.segments[self.last_match_idx]
        text = seg.get("text", "") or ""
        replacement = self.replace_var.get() or ""
        new_text = self._safe_replace(text, needle, replacement, self.case_var.get())
        if new_text == text:
            self.find_next()
            return
        seg["text"] = new_text
        self.viewer._dirty = True
        self.viewer._populate_listbox()
        self.find_next()

    def replace_all(self) -> None:
        needle = self._needle()
        if not self._is_valid_needle(needle):
            return
        replacement = self.replace_var.get() or ""
        case_sensitive = self.case_var.get()
        count = 0
        for seg in self.viewer.segments:
            text = seg.get("text", "") or ""
            new_text = self._safe_replace(text, needle, replacement, case_sensitive)
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

    def destroy(self) -> None:  # type: ignore[override]
        # Clear the parent's reference so re-opening Ctrl+F builds a
        # fresh dialog instead of a stale one.
        try:
            if self.viewer._find_dialog is self:
                self.viewer._find_dialog = None
        except Exception:  # noqa: BLE001
            pass
        super().destroy()


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
