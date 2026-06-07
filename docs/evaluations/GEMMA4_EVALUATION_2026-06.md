# Evaluation — should we add "Gemma 4 12B" as a transcription backend?

**Date:** 2026-06-06
**Verdict:** ❌ **SKIP for transcription now.** ⏳ Revisit later only as an
optional *audio-chat / summarise* adjunct to the existing local-LLM panel
(`core/llm.py`), **not** as a transcription engine.

This note answers the owner's request to (a) check whether the newly
open-sourced Google model is worth adding, and (b) — if yes — define the
hardware-capability check the app would need ("the system must verify it can
handle this model"). The conclusion is "not worth it for transcription", with
the integration + hardware-gate sketch recorded below in case that changes.

---

## What the model actually is (verified)

"Gemma 4 12B" is **real**. It exists on Hugging Face as `google/gemma-4-12B`
and `google/gemma-4-12B-it`.

Confirmed from the official model cards + Google's launch material:

- **License:** Apache 2.0 (permissive; compatible with this repo's BSD-3-Clause).
- **Architecture:** encoder-free, unified decoder-only transformer (~11.95 B
  params, 48 layers, 262 K vocab, 256 K context). Raw audio waveforms and
  image patches are projected straight into the LLM embedding space via
  lightweight linear layers (no separate audio/vision encoder).
- **Modalities:** text, audio, image, video — like the E2B / E4B variants.
- **Native audio is genuinely transcription-grade**, not just "understanding":
  the card lists *"Automatic speech recognition (ASR) and speech-to-translated-
  text translation across multiple languages"* and ships an ASR prompt
  template.
- **Languages:** 140+ pre-trained, 35+ "out of the box".
- **Hardware headline:** "runs on a ~16 GB unified-memory / VRAM laptop" — but
  see the caveat below; that figure is for **quantized text**, not audio.

### Article claims that did NOT verify

- **Multi-Token Prediction (MTP):** not mentioned on either model card. Treat
  as article embellishment.
- **"Runs everywhere incl. llama.cpp / Ollama" — for AUDIO this is false
  today.** Audio is the Hugging Face Transformers reference path only.
  `llama.cpp` audio support is still in progress (open issue + PR, below), and
  a community report finds quantized GGUF **breaks audio** — you must load
  BF16 weights for audio to work at all right now.

---

## Why it is the wrong tool for THIS app

The project's value is **offline, fast, long-form, timestamped** transcription
shipped in a slim embeddable-Python tree. Gemma 4 12B fails three hard tests:

1. **30-second audio cap.** The model card states *"Audio supports a maximum
   length of 30 seconds."* This app transcribes full videos/podcasts. A 30 s
   ceiling forces VAD-chunking every file into ≤30 s windows, one 12 B-LLM pass
   per window, then stitching — losing cross-chunk context, multiplying latency,
   and yielding **no reliable word-level timestamps** (the app's
   word-timestamps / karaoke highlight / word-level diarisation all degrade,
   because an LLM emits plain text, not aligned word offsets).

2. **No lightweight runtime for audio.** `faster-whisper` (CTranslate2),
   `whisper.cpp`, and the Parakeet / sherpa-onnx path are all C / ONNX engines
   with **no torch**. Gemma audio needs `transformers + torch + torchvision +
   librosa + accelerate` at **BF16** (~24 GB+ VRAM for the unquantized 12 B).
   That is exactly the ~700 MB+ torch download `core/optional_deps.py` was
   built to avoid bundling, plus weights far above the CPU-int8 / CUDA-fp16
   tiers most users hit. The "16 GB laptop" headline is for quantized **text**;
   quantized **audio** is broken today.

3. **No speed or accuracy win for pure ASR.** A 12 B autoregressive LLM is
   dramatically slower per audio-second than Whisper-large-v3-turbo
   (CTranslate2) or Parakeet-TDT, with no published WER advantage for
   transcription. The project already ships the two best on-device ASR engines
   for this job.

The owner's own instinct — "the system must verify it can handle this model" —
is correct precisely **because almost no target machine can**, which is itself
the signal to skip it as a transcription backend.

---

## Where it *could* fit later (the WAIT path)

Gemma's real edge is "ask questions about this audio/video" and translation —
an adjunct to the existing `core/llm.py` panel (already a local-LLM
summarise / ask / translate surface using llama-cpp + Qwen2.5-1.5B). When
`llama.cpp` audio support lands and stabilises, a GGUF Gemma-4 with audio could
power "ask about this clip" via the **existing torch-free llama-cpp
dependency** — no torch, no separate heavy stack. Re-evaluate in roughly six
months (the community estimate for stable llama.cpp audio).

Track:
- llama.cpp audio support: `ggml-org/llama.cpp` issue #21325, PR #21421,
  discussion #21334.

---

## If it is ever added anyway — integration + hardware-gate sketch

This is the minimal, slim-respecting design (mirrors `core/backends/parakeet.py`
exactly). **Not implemented** — recorded for a future decision.

1. **`core/backends/gemma4.py`** — `class Gemma4Backend(Backend)`, `name='gemma4'`.
   - `runtime_available()`: `try import torch, transformers` → `False` on any
     exception (mirror `parakeet.runtime_available`).
   - `load()`: lazy-import transformers; `AutoProcessor` +
     `AutoModelForMultimodalLM.from_pretrained(dtype='auto', device_map='auto')`;
     set `self._error` on failure.
   - `transcribe_to_segments()`: reuse the ffmpeg-decode helper to get 16 kHz
     mono, **VAD-chunk into ≤30 s windows**, run the ASR prompt template per
     chunk, offset timestamps by chunk start, wrap each `model.generate` in
     `core._liveness_tick.liveness_tick(...)`. Return Whisper-shaped segment
     dicts + `LanguageInfo`. Segment-level timestamps only (no reliable
     per-word offsets).

2. **`core/backends/__init__.py`** — register `gemma4` in `get_backend()`.

3. **`core/optional_deps.py`** — add a `gemma4` FEATURES entry
   (`transformers, torch, torchvision, librosa, accelerate`) so it pip-installs
   on first use into the user extras dir, exactly like the alignment /
   whisper_backend entries — **never bundled**.

4. **Weights** — download-on-first-use to `user_cache_dir()/gemma4` (mirror
   `core/model_manager.py` / `core/llm.py`), not in the installer.

5. **The hardware gate the owner asked for** — add a VRAM/RAM probe to
   `core/hardware.py`:
   - `torch.cuda.get_device_properties(0).total_memory` for VRAM, plus system
     RAM, returning available memory in GB.
   - `gemma4_supported() -> tuple[bool, str]`: require CUDA with ≳24 GB VRAM for
     BF16 (or a documented quantized-CPU path with ≳16 GB RAM, with a loud
     slow-speed warning).
   - In `app/widgets/hardware_wizard.py`, surface a tier row
     *"Gemma 4 12B (needs ~24 GB VRAM) — unsupported on this machine"* and
     **refuse selection** rather than letting it OOM mid-transcribe (reuse the
     existing "backend not bundled" tier pattern).

6. **Specs hygiene** — add `core/backends/gemma4.py` to the hidden-import lists
   in BOTH `whisper_project_onefile.spec` and `whisper_project_onedir.spec`.

7. **Pyright 0/0/0** — torch/transformers are untyped here; use the same
   `# type: ignore[import-not-found]` + `try/except → return False`
   degradation the other optional backends use.

---

## Sources (fetched 2026-06-05/06)

- Hugging Face model cards: `https://huggingface.co/google/gemma-4-12B`,
  `https://huggingface.co/google/gemma-4-12B-it` (Apache 2.0; "Automatic
  speech recognition (ASR)…"; "Audio supports a maximum length of 30 seconds";
  install line `pip install -U transformers torch torchvision librosa
  accelerate`; `AutoModelForMultimodalLM`; BF16; 35+/140+ languages; **no**
  mention of MTP).
- Google blog:
  `https://blog.google/innovation-and-ai/technology/developers-tools/introducing-gemma-4-12b/`
  and `https://developers.googleblog.com/gemma-4-12b-the-developer-guide/`
  (encoder-free, on-device).
- VentureBeat (title only; body 403):
  `https://venturebeat.com/technology/googles-new-open-source-gemma-4-12b-analyzes-audio-video-and-runs-entirely-locally-on-a-typical-16gb-enterprise-laptop`.
- Gigazine: `https://gigazine.net/gsc_news/en/20260604-google-ai-gemma-4-12b/`
  (16 GB VRAM).
- llama.cpp audio gaps: `https://github.com/ggml-org/llama.cpp/issues/21325`,
  `https://github.com/ggml-org/llama.cpp/pull/21421`,
  `https://github.com/ggml-org/llama.cpp/discussions/21334`.
- Community traps report (quantized GGUF breaks audio; BF16-only for audio
  today; framework support ~6 months out):
  `https://note.com/unco3/n/n5b1c21ca3a98?hl=en`.
- Unsloth docs: `https://unsloth.ai/docs/models/gemma-4`.

> ⚠️ These facts postdate the assistant's training cutoff and were gathered by
> live web research; re-verify the model card before acting on this note, as
> fast-moving model details (model names, the 30 s cap, runtime support) change
> frequently.
