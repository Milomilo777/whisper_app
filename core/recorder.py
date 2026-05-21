"""Audio recording — mic + system loopback (v0.8 Phase 2).

Two record modes the UI surfaces:

  * **Microphone** — captures from the default (or user-picked) input
    device via :mod:`sounddevice`. Falls back to a clean
    ``RecorderUnavailable`` raise when the package isn't installed.
  * **System audio (WASAPI loopback)** — captures whatever is playing
    on the default speakers via :mod:`pyaudiowpatch` (a fork of
    PyAudio that exposes Windows WASAPI loopback devices). Same
    fallback when missing.

Both modes write a mono 16-kHz int16 WAV next to the user's chosen
download folder (or a temp dir). The existing transcribe pipeline
takes the resulting WAV from there — no special path needed.

Design notes:

* No background services. Recording is started from the UI button,
  produces a single WAV when stopped, and that's it. The Live tab
  uses this module as the recorder; live-streaming transcription
  itself is a Phase 2 RealtimeSTT integration if/when that lands.
* The recorder runs in a daemon thread so the UI stays responsive.
  Stop is non-blocking — we set an event the recording loop polls.
* All numpy/IO errors surface via ``Recorder.last_error``; the UI
  surfaces them through the app log + a messagebox.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2  # int16


class RecorderUnavailable(RuntimeError):
    """Raised when the requested recording backend isn't installed."""


# ---------------------------------------------------------------- availability


def mic_available() -> bool:
    """True iff sounddevice imports cleanly."""
    try:
        import sounddevice  # type: ignore[import-not-found] # noqa: F401
    except ImportError:
        return False
    return True


def mic_availability_reason() -> str:
    if mic_available():
        return ""
    return (
        "sounddevice not installed — `pip install sounddevice` to "
        "enable microphone recording."
    )


def loopback_available() -> bool:
    """True iff pyaudiowpatch imports cleanly (Windows-only WASAPI loopback)."""
    if os.name != "nt":
        return False
    try:
        import pyaudiowpatch  # type: ignore[import-not-found] # noqa: F401
    except ImportError:
        return False
    return True


def loopback_availability_reason() -> str:
    if os.name != "nt":
        return "System-audio capture requires Windows (WASAPI loopback)."
    if loopback_available():
        return ""
    return (
        "pyaudiowpatch not installed — `pip install PyAudioWPatch` to "
        "enable system-audio (loopback) recording."
    )


# ---------------------------------------------------------------- devices


@dataclass(frozen=True)
class InputDevice:
    index: int
    name: str
    max_input_channels: int
    default_samplerate: float


def list_mic_devices() -> list[InputDevice]:
    """Enumerate available microphone input devices.

    Returns an empty list when sounddevice isn't installed (rather
    than raising) so the UI can fall back to "default device" mode.
    """
    if not mic_available():
        return []
    try:
        import sounddevice as sd  # type: ignore[import-not-found]
        out: list[InputDevice] = []
        for idx, info in enumerate(sd.query_devices()):
            channels = int(info.get("max_input_channels", 0))
            if channels <= 0:
                continue
            out.append(InputDevice(
                index=idx,
                name=str(info.get("name", f"Device {idx}")),
                max_input_channels=channels,
                default_samplerate=float(info.get("default_samplerate", SAMPLE_RATE)),
            ))
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("list_mic_devices failed: %s", e)
        return []


# ---------------------------------------------------------------- recorder


@dataclass
class Recorder:
    """Owns a single recording session.

    Construct one per session, ``start()`` to begin, ``stop()`` to
    flush + finalize. The output WAV path is in ``output_path``
    after stop() returns.
    """
    output_path: str
    mode: str = "mic"  # "mic" | "loopback"
    device_index: Optional[int] = None
    sample_rate: int = SAMPLE_RATE
    _frames: list[bytes] = field(default_factory=list, repr=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _thread: Optional[threading.Thread] = field(default=None, repr=False)
    _started_at: float = 0.0
    _stopped_at: float = 0.0
    last_error: Optional[str] = None

    def start(self) -> None:
        """Begin recording in a background daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("Recorder is already running")
        self._frames.clear()
        self._stop_event.clear()
        self.last_error = None
        self._started_at = time.time()
        self._stopped_at = 0.0
        if self.mode == "mic":
            if not mic_available():
                raise RecorderUnavailable(mic_availability_reason())
            target = self._mic_loop
        elif self.mode == "loopback":
            if not loopback_available():
                raise RecorderUnavailable(loopback_availability_reason())
            target = self._loopback_loop
        else:
            raise ValueError(f"Unknown recorder mode: {self.mode!r}")
        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    def stop(self, *, timeout: float = 5.0) -> str:
        """Stop the recording loop and finalize the WAV.

        Returns the path to the final WAV. Joins the recording
        thread with ``timeout`` so a wedged backend doesn't deadlock
        the UI; if the thread doesn't exit in time we still write
        whatever frames we have.
        """
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._stopped_at = time.time()
        self._finalize_wav()
        return self.output_path

    def duration_seconds(self) -> float:
        end = self._stopped_at or time.time()
        return max(0.0, end - self._started_at)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ---------- internals ------------------------------------------

    def _mic_loop(self) -> None:
        try:
            import sounddevice as sd  # type: ignore[import-not-found]
            stream_kwargs: dict[str, Any] = {
                "samplerate": self.sample_rate,
                "channels": CHANNELS,
                "dtype": "int16",
                "blocksize": 1024,
            }
            if self.device_index is not None:
                stream_kwargs["device"] = self.device_index
            with sd.RawInputStream(**stream_kwargs) as stream:
                while not self._stop_event.is_set():
                    data, _overflow = stream.read(1024)
                    if isinstance(data, memoryview):
                        self._frames.append(bytes(data))
                    else:
                        self._frames.append(bytes(data))
        except Exception as e:  # noqa: BLE001
            self.last_error = str(e)
            logger.exception("Mic recording failed: %s", e)

    def _loopback_loop(self) -> None:
        try:
            import pyaudiowpatch as pya  # type: ignore[import-not-found]
            with pya.PyAudio() as p:
                try:
                    info = p.get_default_wasapi_loopback()
                except OSError:
                    self.last_error = "No default WASAPI loopback device available."
                    return
                device_idx = int(info["index"])
                native_rate = int(info["defaultSampleRate"])
                channels = int(info["maxInputChannels"]) or 1
                stream = p.open(
                    format=pya.paInt16,
                    channels=channels,
                    rate=native_rate,
                    frames_per_buffer=1024,
                    input=True,
                    input_device_index=device_idx,
                )
                try:
                    while not self._stop_event.is_set():
                        data = stream.read(1024, exception_on_overflow=False)
                        self._frames.append(_downmix_to_mono_int16(data, channels))
                    # Re-sample at write time via the WAV header. We
                    # purposefully store the native rate frames here
                    # so the wav is faithful; the transcriber upsamples
                    # internally if needed.
                    self.sample_rate = native_rate
                finally:
                    stream.stop_stream()
                    stream.close()
        except Exception as e:  # noqa: BLE001
            self.last_error = str(e)
            logger.exception("Loopback recording failed: %s", e)

    def _finalize_wav(self) -> None:
        Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)
        # If we never captured anything, still produce a valid 0-frame
        # WAV so the caller's "open this file" path doesn't crash.
        with wave.open(self.output_path, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH_BYTES)
            wf.setframerate(self.sample_rate)
            wf.writeframes(b"".join(self._frames))


def _downmix_to_mono_int16(data: bytes, channels: int) -> bytes:
    """Average ``channels`` int16 samples per frame to mono.

    Inputs from WASAPI loopback are typically stereo; the rest of the
    transcribe pipeline expects mono. We do the downmix here in pure
    Python (numpy-optional) so the recorder has no hard numpy
    dependency.
    """
    if channels <= 1:
        return data
    try:
        import numpy as np  # type: ignore[import-not-found]
        arr = np.frombuffer(data, dtype=np.int16)
        if arr.size % channels != 0:
            # Trim trailing partial frame so reshape is safe.
            arr = arr[: (arr.size // channels) * channels]
        frames = arr.reshape(-1, channels)
        mono = frames.mean(axis=1).astype(np.int16)
        return mono.tobytes()
    except ImportError:
        # No numpy — fall back to interleaved pick of channel 0.
        # Acceptable for transcription where exact loudness doesn't
        # matter as much as content.
        sample_bytes = SAMPLE_WIDTH_BYTES * channels
        frames = [data[i:i + sample_bytes] for i in range(0, len(data), sample_bytes)]
        return b"".join(f[:SAMPLE_WIDTH_BYTES] for f in frames if len(f) >= SAMPLE_WIDTH_BYTES)
