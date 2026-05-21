"""Generate ``tests/fixtures/sample.wav`` — a 1-second 16 kHz mono
silence WAV used by tests that need a tiny on-disk audio file.

Run once when the file is missing:

    python tests/fixtures/generate_sample_wav.py

Avoids checking a binary blob into git; the script is the source
of truth.
"""
from __future__ import annotations

import wave
from pathlib import Path


def main(out_path: Path) -> int:
    sample_rate = 16000
    duration_s = 1
    channels = 1
    sampwidth = 2  # int16
    n_frames = sample_rate * duration_s

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(sample_rate)
        # Silence — all-zero int16 frames.
        w.writeframes(b"\x00\x00" * n_frames)
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "sample.wav"
    raise SystemExit(main(out))
