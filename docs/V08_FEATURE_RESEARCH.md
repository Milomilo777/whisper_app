# v0.8 Feature Research — outside-the-box

Two parallel research shards: competitor + trend scan, and a technical
deep-dive across three angles (live streaming + local LLM + hardware
autodetect). Goal: a v0.8 feature map that's both differentiating and
on-brand for "offline + single-installer".

## TL;DR — 5-item shortlist for v0.8

If we can only pick five, ship them in this order:

1. **Hardware autodetect wizard** (S effort, immediate impact on every
   first-launch user)
2. **Multi-model picker** (S effort, unlocks 5-6× speedup)
3. **Vocal separation pre-processing** with Demucs (S effort, big WER
   win on noisy audio)
4. **Local LLM panel** with download-on-first-use (M effort, biggest
   feature gap vs competitors)
5. **Live mic mode** with RealtimeSTT (M effort, the one major
   feature category we lack)

Together these turn the project from "Whisper desktop wrapper" into
a "complete audio-to-insight workstation", and none require cloud or
Mac-only APIs.

---

## Top 10 candidate features (sorted by impact/effort)

| # | Feature | Why it matters in 2026 | Effort | Tool |
|---|---|---|---|---|
| 1 | **Local LLM panel** (summary / Q&A / action-items / translate) | Biggest gap vs Otter / Fireflies / MacWhisper-AI | M | `llama-cpp-python` + Qwen2.5-1.5B Q4_K_M (~1 GB) + GBNF for guaranteed JSON output |
| 2 | **Live mic streaming** | Most desktop tools are batch-only | M | RealtimeSTT (MIT, wraps faster-whisper) + Silero VAD + distil-small.en stream + final batch on the recorded file |
| 3 | **System audio capture (WASAPI loopback)** | Meeting recording without a bot — the signature feature of Meetily / BB Recorder | M | `soundcard` or `pyaudiowpatch` |
| 4 | **Cross-file speaker fingerprint DB** | Enroll "Alice" once, recognise her in every future file | M | `pyannote/embedding` (TDNN+SincNet) + sqlite + cosine match |
| 5 | **Vocal separation pre-processing** (Demucs toggle) | Cuts WER + hallucinations on noisy audio | S | `demucs` (htdemucs default) — vocals stem only |
| 6 | **Auto-chapter markers + LLM titles** | Navigation of long files; the main reason people pay Descript | M | embedding boundary detection (MiniLM cosine threshold) + Qwen for titles |
| 7 | **Hardware autodetect wizard** | First-time users don't know device / compute_type; a 3-second benchmark builds confidence | M | probe: CUDA → QNN/NPU → Intel-NPU → OpenVINO-GPU → DirectML → OpenVINO-CPU → CPU int8, with a 5 s sample clip |
| 8 | **Hallucination detector flag** | Whisper loops / repeats on long silence | S | regex repetition + VAD-disagreement + BoH wordlist |
| 9 | **Multi-model picker** (distil-v3.5 / turbo / Parakeet-tdt-v3) | Users want speed; Parakeet is 5× faster than turbo on European languages and ships ONNX-DirectML | S for UI + L for adapter | faster-whisper built-in turbo + sherpa-onnx adapter for Parakeet |
| 10 | **Search across all transcripts** | history.db has everything but no UI to search | S | MiniLM embedding + sqlite FTS5 |

---

## 5 truly outside-the-box ideas (no competitor ships these)

- **Smart audio cutting à la Descript Underlord** — delete a word from
  the transcript = cut the audio. We already have word-level
  timestamps; ffmpeg does the rest. **A unique signature feature for
  us.**
- **Selective re-transcription**: select a time range + click "rerun
  with larger model". The larger model runs on just that segment. Makes
  sense for users who saw one segment go wrong.
- **Auto-extract glossary** from prior transcripts → the app builds a
  per-domain (medical / legal) `initial_prompt` automatically.
- **Voice fingerprint enrollment in 30 s** — user says "this is me"
  once, and every future transcript labels them as "Me".
- **Webhook + tiny REST API mode** (`gui.py serve --port 8080`) —
  automation with n8n / Home Assistant / homelab.

---

## v0.8 plan — three converging tracks

### Track 1 — Live & Capture (M)

RealtimeSTT on the existing `WhisperModel` instance + WASAPI loopback.
Output: a new "Live" tab that writes text as the user speaks; at session
end, the existing batch pipeline runs over the full recorded file to
produce the exact final SRT.

  - **Library**: `RealtimeSTT` (MIT, KoljaB, v1.0.0 / 2026-05) —
    `pip install "RealtimeSTT[faster-whisper]"`
  - **Latency on i7 12gen + distil-small.en**: ~380-520 ms end-to-end
  - **System audio**: `soundcard` (cross-platform) or `pyaudiowpatch`
    (Windows-specific WASAPI loopback)
  - **Two-stage pattern**: streaming preview (small.en) + final batch
    re-transcribe (large-v3-turbo) — RealtimeSTT's default

### Track 2 — AI Layer (M, opt-in download)

llama.cpp + Qwen2.5-1.5B Q4_K_M with **download-on-first-use** (NOT
bundled) — keeps Portable at ~450 MB instead of growing to 1.5 GB. GBNF
guarantees JSON output for chapters / summary / action-items.

  - **Runtime**: `llama-cpp-python` (~10 MB binary) with CUDA / Vulkan
    / Metal backends
  - **Model**: Qwen2.5-1.5B Q4_K_M (~1.0 GB, 128K context, strong
    multilingual including Persian / Arabic / Spanish)
  - **Throughput**: 25-40 tok/s on i7 CPU, 100+ tok/s on RTX 3060
  - **GBNF**: token-level grammar transformer from JSON Schema → valid
    JSON output guaranteed (provided `max_tokens` is generous)
  - **Translate**: use Qwen itself instead of bundling separate NLLB-200
    — one less model, acceptable quality on common language pairs
  - **Semantic search**: `sentence-transformers/all-MiniLM-L6-v2`
    (~22 MB, 384-dim, ONNX-ready) for full-text search across history.db

### Track 3 — Hardware & Quality (M)

First-launch wizard + 5-second benchmark + persisted `hardware.json`,
Demucs toggle, hallucination detector, multi-model picker.

  - **Probe order**: CUDA → QNN/NPU (Snapdragon X Elite) → Intel-NPU
    (Meteor Lake via OpenVINO NPU plugin) → OpenVINO-GPU → DirectML
    (AMD/Intel) → OpenVINO-CPU → faster-whisper int8 CPU
  - **CUDA detection safety**: `ctranslate2.contains_cuda_device()`
    inside try/except (torch.cuda.is_available on Windows crashes
    without a clear message when cublas64_12.dll is missing)
  - **Benchmark**: a pre-bundled 5 s clip runs on the winning tier and
    measures real-world RTF
  - **Confirmation UI**: "Detected: NVIDIA RTX 3060 — Acceleration: CUDA
    + float16 — Benchmark: 0.04 RTF (25× real-time)"
  - **Demucs**: `htdemucs` default — vocals stem only for pre-process
  - **Hallucination detector**: regex repetition + VAD-disagreement
    (segments VAD says are silence but Whisper still emitted text) +
    BoH (Bag-of-Hallucinations) wordlist

---

## State of the art — findings from Shard 2

### Live streaming (all tested on Windows)

| Approach | Pros | Cons | Verdict |
|---|---|---|---|
| `whisper.cpp` stream | Simplest, native C++ | SDL2 dep, outside our stack | Skip |
| UFAL `whisper_streaming` + LocalAgreement-2 | Academic paper, MIT, pure Python | 3.3 s average latency (on ESIC EN corpus) | Possible |
| Collabora WhisperLive | TensorRT, OpenVINO | Docker required, server-client architecture | Skip |
| **RealtimeSTT (KoljaB)** | Clean Python wrapper, MIT, Silero+WebRTC VAD, multiprocessing | New release (v1.0.0 / 2026-05) | **Pick** |

**Real-world latency**:
- i7 12gen + 8-thread + faster-whisper int8 + small.en: ~0.2 RTF,
  end-to-end ~380-520 ms
- Ryzen 5 4500U + whisper.cpp small: 7-14 s (borderline acceptable)
- Sub-1 s only with GPU: RTX 3060 12GB is the practical minimum, RTX
  4090 needed for sub-200 ms

### Local LLM augmentation

**Bundling candidates (target under 2 GB, response under 5 s on i7 CPU)**:

| Model | Q4_K_M size | context | Multilingual | IFEval / MMLU |
|---|---|---|---|---|
| **Qwen2.5-1.5B-Instruct** | ~1.0 GB | 128K | excellent (incl. Persian) | 47.4 / 60.9 |
| **Qwen2.5-3B-Instruct** | ~1.9 GB | 128K | excellent | 67.4 / 65.6 |
| Phi-3.5-mini-instruct | ~2.3 GB | 128K | moderate | 59.2 / 69.0 |
| Llama-3.2-3B-Instruct | ~2.0 GB | 128K | moderate | 77.4 / 63.4 |
| Gemma-2-2B | ~1.5 GB | **only 8K** | moderate | — |

**Pick**: Qwen2.5-1.5B for typical users (fast, multilingual); offer
"upgrade to 3B" for power users.

**Guaranteed JSON output**: llama.cpp supports GBNF (token-level
grammars). Auto-conversion from JSON Schema → GBNF exists. ⚠ Valid
output is only guaranteed if `max_tokens` is large enough.

**Translation**: three options evaluated:

1. Whisper's built-in `translate` mode — English-only target, zero
   extra cost, but quality on tiny/small is bad. Skip for Persian users.
2. NLLB-200-distilled-600M — 200 langs, many-to-many, CTranslate2 int8
   ~600 MB, 5-20 s/sentence on CPU. Acceptable for batch, bad for live.
3. **Qwen itself with a translate prompt** — acceptable fa-en quality,
   one fewer model in the installer. **Pick.**

**Semantic search**: `all-MiniLM-L6-v2` (~22 MB, 384 dim) with ONNX
backend is 2-3× faster. Sufficient for search-across-transcripts. If
multilingual quality matters, `BGE-small-multilingual` (~120 MB) is the
better substitute.

**Size economics**:

```
Portable v0.7.1 = 447 MB
+ llama.cpp runtime ≈ 10 MB
+ Qwen2.5-1.5B Q4_K_M ≈ 1.0 GB
+ MiniLM ≈ 22 MB
─────────────────────────────
total if bundled = ~1.45 GB
total if download-on-first-use = ~450 MB (installer keeps original
                                          size)
```

**Recommendation**: download-on-first-use with an "Enable AI features"
button in the Advanced dialog. LM Studio / Ollama pattern.

### Hardware acceleration (May 2026)

**Tiers and speed on large-v3-turbo**:

| Tier | Hardware | RTF |
|---|---|---|
| faster-whisper int8 | i5/i7 12gen + 8 thread | 0.10-0.20 |
| faster-whisper float16 | RTX 3060 12GB | 0.02-0.04 |
| faster-whisper float16 | RTX 4090 | 0.005-0.01 |
| OpenVINO int8 | Intel Core Ultra NPU | 0.04-0.08 (est.) |
| DirectML fp16 | AMD RX 6700 | 0.05-0.10 |
| QNN fp16 | Snapdragon X Elite NPU (45 TOPS) | 0.03-0.06 |

**Technical notes**:

- CUDA: `ctranslate2.contains_cuda_device()` is the official way. CT2
  4.5+ requires CuDNN v9 (CUDA ≥ 12.3).
- DirectML: works on any DX12-capable GPU on Windows 10+, including
  AMD Radeon / Intel Arc / NVIDIA. Microsoft announced DirectML is in
  "sustained engineering" with development moving to Windows ML, but
  it's still the only practical AMD path on Windows.
- NPU detection: Windows 11 build 28020+ shows NPU in Task Manager. At
  the code level: WinML or vendor-specific APIs.
- OpenVINO 2026: improved NPU support. On Intel Core i5/i7, INT8
  Whisper-base is ~1.4-5.1× faster than raw PyTorch.

---

## "Worth investigating" items (need a prototype)

| # | Feature | Challenge |
|---|---|---|
| 11 | Edit-by-text (delete word = cut audio) à la Descript | Word-boundary sync with ffmpeg, lots of edge cases |
| 12 | Selective re-transcription with a larger model | UI workflow for time-range selection + on-the-fly rerun |
| 13 | Semantic search on history.db with embeddings | DB size + indexing strategy, but high value |
| 14 | Code-switching (two languages in one sentence) | No open-source model handles this well; NeMo Canary-1B-flash maybe |
| 15 | Streaming Sortformer for live diarization | New (2025), unstable on Windows |
| 16 | Highlight / clip export with timestamps | Simple but needs thoughtful UI |
| 17 | Auto-detect speaker count + name suggestion | An LLM can guess names from conversation context |

---

## "Skip" items (don't fit single-exe + offline)

| Feature | Why not |
|---|---|
| Bot-in-meeting integration (Otter, Fireflies) | Cloud auth required, breaks the no-cloud ethos |
| CRM integration (Salesforce / HubSpot) | Offline-only, B2B feature out of scope |
| Voice cloning (Overdub) | Ethical concerns + heavy model + abuse risk |
| Cross-meeting shared workspaces | Needs a server, breaks single-exe |
| OpenAI Realtime API streaming | Cloud-only |
| iOS keyboard companion | Scope creep, platform mismatch |

---

## Top 5 user pain points in 2026 (from HN / Reddit)

From HN thread 44225953 and r/LocalLLM:

1. **No local summarisation / Q&A** — users want action-items /
   ask-questions offline after transcribing. → covered by Track 2.
2. **Hallucinations on long silence / long audio** — see arXiv
   2501.11378 (BoH + VAD mitigation). → covered by shortlist #8.
3. **Code-switching (multilingual within one utterance)** — e.g.
   Dutch-English Whisper handles poorly. → Worth investigating #14.
4. **Quiet / far-from-mic speakers** — current diarization misses them.
   → Demucs + cross-file fingerprint can help.
5. **Live visual feedback during dictation** — users want text to
   appear as they speak, not after stop. → covered by Track 1.

---

## Key references (~50 sources gathered, key ones below)

### Live streaming
- [github.com/KoljaB/RealtimeSTT](https://github.com/KoljaB/RealtimeSTT)
- [github.com/ufal/whisper_streaming](https://github.com/ufal/whisper_streaming)
- [arXiv 2307.14743 — Turning Whisper into Real-Time](https://arxiv.org/pdf/2307.14743)
- [github.com/collabora/WhisperLive](https://github.com/collabora/WhisperLive)
- [whisper.cpp stream example README](https://github.com/ggml-org/whisper.cpp/blob/master/examples/stream/README.md)
- [Silero VAD overview](https://medium.com/axinc-ai/silerovad-machine-learning-model-to-detect-speech-segments-e99722c0dd41)

### Local LLM
- [huggingface.co/Qwen/Qwen2.5-3B-Instruct](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct)
- [huggingface.co/microsoft/Phi-3.5-mini-instruct](https://huggingface.co/microsoft/Phi-3.5-mini-instruct)
- [llama.cpp GBNF README](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)
- [Simon Willison — llama-cpp-python grammars for JSON](https://til.simonwillison.net/llms/llama-cpp-python-grammars)
- [huggingface.co/facebook/nllb-200-distilled-600M](https://huggingface.co/facebook/nllb-200-distilled-600M)
- [huggingface.co/sentence-transformers/all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
- [aimagicx.com — Local AI Models 2026 hardware guide](https://www.aimagicx.com/blog/local-ai-models-2026-qwen-mistral-llama-hardware-guide)

### Hardware
- [github.com/SYSTRAN/faster-whisper issue 1086 — CUDA compat](https://github.com/SYSTRAN/faster-whisper/issues/1086)
- [github.com/OpenNMT/CTranslate2 issue 1630 — Windows](https://github.com/OpenNMT/CTranslate2/issues/1630)
- [Optimizing Whisper with OpenVINO + NNCF (Intel blog)](https://blog.openvino.ai/blog-posts/optimizing-whisper-and-distil-whisper-for-speech-recognition-with-openvino-and-nncf)
- [Phoronix — Intel OpenVINO 2026.0 Released](https://www.phoronix.com/news/Intel-OpenVINO-2026.0-Released)
- [huggingface.co/OpenVINO/whisper-large-v3-fp16-ov](https://huggingface.co/OpenVINO/whisper-large-v3-fp16-ov)
- [onnxruntime.ai DirectML provider docs](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html)
- [github.com/ChharithOeun/whisper-amd-windows](https://github.com/ChharithOeun/whisper-amd-windows)
- [onnxruntime.ai QNN provider — Snapdragon](https://onnxruntime.ai/docs/execution-providers/QNN-ExecutionProvider.html)
- [learn.microsoft.com — Copilot+ PCs developer guide](https://learn.microsoft.com/en-us/windows/ai/npu-devices/)

### Models
- [huggingface.co/openai/whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo)
- [huggingface.co/distil-whisper/distil-large-v3.5](https://huggingface.co/distil-whisper/distil-large-v3.5)
- [huggingface.co/nvidia/parakeet-tdt-0.6b-v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)
- [Northflank — Best open source STT 2026](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)

### Diarization + speaker recognition
- [huggingface.co/pyannote/embedding](https://huggingface.co/pyannote/embedding)
- [github.com/z3lx/speaker-identification](https://github.com/z3lx/speaker-identification)

### Auto-chaptering
- [arXiv 2410.16148 — PODTILE (Spotify Research)](https://arxiv.org/pdf/2410.16148)

### Vocal separation
- [dev.to/codesugar — htdemucs vs BS-RoFormer vs Spleeter 2026 benchmark](https://dev.to/codesugar_lin_037a57b06a4/htdemucs-vs-bs-roformer-vs-spleeter-a-2026-audio-source-separation-benchmark-2ll8)

### Competitor + UX research
- [github.com/chidiwilliams/buzz](https://github.com/chidiwilliams/buzz)
- [dev.to/zackriya — Meetily Ollama summaries](https://dev.to/zackriya/local-meeting-notes-with-whisper-transcription-ollama-summaries-gemma3n-llama-mistral--2i3n)
- [blog.buildbetter.ai — Best Local AI Meeting Recorders 2026](https://blog.buildbetter.ai/best-local-ai-meeting-recorders-no-cloud-2026/)
- [sonix.ai — Descript Underlord review 2026](https://sonix.ai/resources/descript-review-pricing/)
- [news.ycombinator.com/item?id=44225953 — software for transcription](https://news.ycombinator.com/item?id=44225953)
- [arXiv 2501.11378 — Investigation of Whisper Hallucinations](https://arxiv.org/pdf/2501.11378)
- [daveswift.com/macwhisper](https://daveswift.com/macwhisper/)
- [learn.microsoft.com — WASAPI loopback recording](https://learn.microsoft.com/en-us/windows/win32/coreaudio/loopback-recording)

---

## Notes for future sessions

- This research covers feature work; the remote-mode (cloud GPU
  burst-compute) research is in `docs/V09_REMOTE_MODE_RESEARCH.md`.
- If the AI Layer path is picked, CLAUDE.md + BUILD.md need updates to
  reflect the new shape (download-on-first-use, llama.cpp dep, Qwen
  GGUF).
- v0.8 smoke test: a live SMTV clip + (whichever track is enabled)
  validated end-to-end in the built exe, mirroring the audit-2 smoke.
