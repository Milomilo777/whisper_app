"""Hardware autodetect wizard (v0.8).

Modal Toplevel that surfaces every accelerator tier the host
supports (probed by :mod:`core.hardware`), highlights the one the
bundled faster_whisper backend can actually drive, lets the user
override the auto-pick, and persists the choice to
``hardware.json``. ``core.transcriber.detect_device`` reads that
file on the next model load.

Layout:

  +----------------------------------------------------------+
  |  Detected hardware:                                       |
  |  +------+---------------------------------+-------------+ |
  |  |  ✓   | NVIDIA CUDA (float16) — RTX… | recommended  | |
  |  |      | Snapdragon X NPU (QNN) — …    | install ext. | |
  |  |      | CPU int8 — Intel i7-…         | fallback     | |
  |  +------+---------------------------------+-------------+ |
  |  Selected tier: NVIDIA CUDA (float16)                     |
  |  [ Re-probe ]  [ Run 5 s benchmark ]                      |
  |                                                           |
  |                    [ Cancel ] [ Save and use ]            |
  +----------------------------------------------------------+

Benchmark is opt-in via a button — it loads the in-process whisper
model on the chosen tier and measures wall time on a 5-second
silent clip generated through bundled ffmpeg. Skipping the
benchmark on first launch keeps the wizard snappy.
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Optional

from core import hardware as _hw
from core.paths import bundled_binary

if TYPE_CHECKING:
    from app.app import App


logger = logging.getLogger(__name__)


_BENCHMARK_SECONDS = 5


class HardwareWizard(tk.Toplevel):
    """Modal wizard for picking the acceleration tier."""

    def __init__(self, master: "tk.Tk | tk.Toplevel", *, app: "App | None" = None) -> None:
        super().__init__(master)
        self.app = app
        self.title("Hardware autodetect")
        self.transient(master)
        self.grab_set()
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._tiers: list[_hw.Tier] = []
        self._selected_idx: int = -1
        self._benchmark_rtf: float | None = None

        self._build()
        self._reprobe()

    # ---------- UI -----------------------------------------------------

    def _build(self) -> None:
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        ttk.Label(
            body,
            text="Detected hardware (best first):",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w", pady=(0, 6))

        cols = ("pick", "label", "note")
        self.tree = ttk.Treeview(
            body, columns=cols, show="headings", height=8,
        )
        self.tree.heading("pick", text="")
        self.tree.heading("label", text="Tier")
        self.tree.heading("note", text="Status")
        self.tree.column("pick", width=40, anchor="center")
        self.tree.column("label", width=480, anchor="w")
        self.tree.column("note", width=140, anchor="w")
        self.tree.tag_configure("supported", foreground="#1e6f1e")
        self.tree.tag_configure("unsupported", foreground="#888")
        self.tree.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        self.status_var = tk.StringVar(value="Probing…")
        ttk.Label(body, textvariable=self.status_var, foreground="#666").pack(
            anchor="w", pady=(6, 0)
        )

        self.benchmark_var = tk.StringVar(value="")
        ttk.Label(body, textvariable=self.benchmark_var, foreground="#1e6f1e").pack(
            anchor="w"
        )

        tools = ttk.Frame(body)
        tools.pack(fill="x", pady=(8, 4))
        ttk.Button(tools, text="Re-probe", command=self._reprobe).pack(side="left")
        self.bench_btn = ttk.Button(
            tools, text=f"Run {_BENCHMARK_SECONDS} s benchmark",
            command=self._run_benchmark,
        )
        self.bench_btn.pack(side="left", padx=(8, 0))

        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="Cancel", command=self._on_close).pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(actions, text="Save and use", command=self._save_and_close).pack(
            side="right"
        )

    # ---------- behaviour ----------------------------------------------

    def _reprobe(self) -> None:
        """Re-run the probe and refresh the table."""
        try:
            self._tiers = _hw.probe_tiers()
        except Exception as e:  # noqa: BLE001
            logger.exception("Hardware probe failed: %s", e)
            self._tiers = _hw._probe_cpu()
        self._refresh_tree()
        if not self._tiers:
            self.status_var.set("No tier detected — falling back to CPU.")
            return
        recommended = _hw.first_supported_tier(self._tiers)
        # Pre-select the recommended tier so the user can just hit Save.
        for idx, t in enumerate(self._tiers):
            if t.slug == recommended.slug:
                self._select_index(idx)
                break
        self.status_var.set(
            f"Recommended: {recommended.label}  "
            f"(device={recommended.device}, compute_type={recommended.compute_type})"
        )

    def _refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for idx, tier in enumerate(self._tiers):
            supported = tier.backend == "faster_whisper"
            note = "ready" if supported else "needs backend"
            tags = ("supported",) if supported else ("unsupported",)
            self.tree.insert(
                "", "end", iid=str(idx),
                values=("", tier.label, note), tags=tags,
            )

    def _select_index(self, idx: int) -> None:
        if not (0 <= idx < len(self._tiers)):
            return
        self._selected_idx = idx
        for child in self.tree.get_children():
            try:
                self.tree.set(child, "pick", "")
            except tk.TclError:
                continue
        try:
            self.tree.set(str(idx), "pick", "✓")
            self.tree.selection_set(str(idx))
            self.tree.focus(str(idx))
        except tk.TclError:
            pass

    def _on_select(self, _event: tk.Event) -> None:
        sel = self.tree.focus()
        if not sel:
            return
        try:
            idx = int(sel)
        except ValueError:
            return
        self._select_index(idx)
        if 0 <= idx < len(self._tiers):
            t = self._tiers[idx]
            self.status_var.set(
                f"Selected: {t.label}  "
                f"(device={t.device}, compute_type={t.compute_type})"
            )

    # ---------- benchmark ----------------------------------------------

    def _run_benchmark(self) -> None:
        """Time the in-process WhisperModel on a 5 s silent clip.

        The model must already be loaded by the main app (transcriber
        module global ``MODEL``). We re-use it as-is — re-loading on
        a different device here would clobber the user's session.
        """
        if not (0 <= self._selected_idx < len(self._tiers)):
            messagebox.showinfo(
                "Pick a tier", "Select a tier in the table first.", parent=self
            )
            return
        tier = self._tiers[self._selected_idx]
        if tier.backend != "faster_whisper":
            messagebox.showinfo(
                "Benchmark unavailable",
                "Benchmark only runs on the bundled faster_whisper backend; "
                "the chosen tier needs a different backend.",
                parent=self,
            )
            return
        try:
            from core import transcriber as _t
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Benchmark failed", str(e), parent=self)
            return
        if not _t.is_model_ready() or _t.MODEL is None:
            messagebox.showinfo(
                "Model not loaded",
                "Load the Whisper model first by starting (and cancelling) "
                "one transcription, then re-open this wizard.",
                parent=self,
            )
            return

        self.bench_btn.state(["disabled"])
        self.benchmark_var.set(f"Benchmarking on a {_BENCHMARK_SECONDS} s silent clip…")
        threading.Thread(
            target=self._benchmark_worker, args=(tier,), daemon=True,
        ).start()

    def _benchmark_worker(self, tier: _hw.Tier) -> None:
        rtf: float | None = None
        err: str | None = None
        try:
            clip = self._make_silent_clip(_BENCHMARK_SECONDS)
            try:
                from core import transcriber as _t
                start = time.time()
                segments, _info = _t.MODEL.transcribe(clip, vad_filter=False)
                # The faster-whisper generator is lazy; force materialise.
                _ = list(segments)
                wall = max(time.time() - start, 1e-6)
                rtf = wall / float(_BENCHMARK_SECONDS)
            finally:
                try:
                    os.unlink(clip)
                except OSError:
                    pass
        except Exception as e:  # noqa: BLE001
            err = str(e)
        self._benchmark_rtf = rtf
        self.after(
            0, lambda: self._benchmark_done(tier, rtf, err)
        )

    def _benchmark_done(self, tier: _hw.Tier, rtf: float | None, err: str | None) -> None:
        try:
            self.bench_btn.state(["!disabled"])
        except tk.TclError:
            return
        if err is not None:
            self.benchmark_var.set(f"Benchmark failed: {err}")
            return
        if rtf is None:
            self.benchmark_var.set("Benchmark produced no result.")
            return
        speedup = (1.0 / rtf) if rtf > 0 else float("inf")
        self.benchmark_var.set(
            f"Benchmark on {tier.label}: RTF={rtf:.3f} ({speedup:.1f}× real-time)"
        )

    def _make_silent_clip(self, seconds: int) -> str:
        """Render a temporary 16 kHz mono silent WAV via bundled ffmpeg."""
        ffmpeg = bundled_binary("ffmpeg")
        fd, out_path = tempfile.mkstemp(prefix="hw_bench_", suffix=".wav")
        os.close(fd)
        cmd = [
            ffmpeg, "-y", "-f", "lavfi",
            "-i", f"anullsrc=channel_layout=mono:sample_rate=16000",
            "-t", str(int(seconds)),
            "-acodec", "pcm_s16le",
            out_path,
        ]
        kwargs: dict[str, object] = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "timeout": 30,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        subprocess.run(cmd, check=True, **kwargs)  # type: ignore[arg-type]
        return out_path

    # ---------- save / close -------------------------------------------

    def _save_and_close(self) -> None:
        if not (0 <= self._selected_idx < len(self._tiers)):
            messagebox.showinfo(
                "Pick a tier", "Select a tier in the table first.", parent=self
            )
            return
        tier = self._tiers[self._selected_idx]
        try:
            path = _hw.save_hardware_choice(tier, benchmark_rtf=self._benchmark_rtf)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Save failed", str(e), parent=self)
            return
        if self.app is not None:
            self.app.log(
                f"Hardware preference saved → {path}  "
                f"(device={tier.device}, compute_type={tier.compute_type})"
            )
        self._on_close()

    def _on_close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


def open_hardware_wizard(
    master: "tk.Tk | tk.Toplevel",
    *,
    app: Optional["App"] = None,
) -> None:
    """Helper for callers that want to spawn the wizard programmatically."""
    HardwareWizard(master, app=app)
