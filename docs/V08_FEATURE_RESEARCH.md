# v0.8 Feature Research — outside-the-box

این فایل تحقیقات دو شارد موازی است که در پایان دور دوم audit انجام شد:
یکی برای مرور competitor + trends، یکی برای deep-dive فنی سه حوزه (live
streaming + local LLM + hardware autodetect). هدف: یک نقشه‌ی feature
برای v0.8 که هم تمایزآفرین باشد، هم با ethos «offline + single-installer»
سازگار بماند.

## TL;DR — شورت‌لیست پنج‌گانه برای v0.8

اگر فقط پنج چیز اضافه شود، به این ترتیب:

1. **Hardware autodetect wizard** (S effort، روی هر کاربر اول‌بار اثر فوری)
2. **Multi-model picker** (S effort، سرعت ۵-۶× ممکن می‌شود)
3. **Vocal separation pre-processing** با Demucs (S effort، WER بزرگ روی صوت نویزی)
4. **Local LLM panel** با download-on-first-use (M effort، بزرگ‌ترین گپ feature نسبت به رقبا)
5. **Live mic mode** با RealtimeSTT (M effort، تنها دسته‌ی بزرگی که نداریم)

این پنج‌تا روی هم پروژه را از «Whisper desktop wrapper» به یک
«complete audio-to-insight workstation» تبدیل می‌کنند، و هیچ‌کدام cloud
یا Mac-only نیستند.

---

## ۱۰ ویژگی برتر کاندید (مرتب بر اساس impact/effort)

| # | ویژگی | چرا الان مهم است | تلاش | ابزار پیشنهادی |
|---|---|---|---|---|
| ۱ | **Local LLM panel** (summary / Q&A / action-items / translate) | بزرگ‌ترین گپ نسبت به Otter / Fireflies / MacWhisper-AI | M | `llama-cpp-python` + Qwen2.5-1.5B Q4_K_M (~1 GB) + GBNF برای JSON تضمینی |
| ۲ | **Live mic streaming** | اکثر ابزارهای desktop فقط batch هستند | M | RealtimeSTT (MIT، wrapper faster-whisper موجود) + Silero VAD + distil-small.en stream + final batch روی فایل ضبط‌شده |
| ۳ | **System audio capture (WASAPI loopback)** | meeting recording بدون bot — قابلیت سیگنیچر Meetily / BB Recorder | M | `soundcard` یا `pyaudiowpatch` |
| ۴ | **Cross-file speaker fingerprint DB** | "Alice" را یک‌بار enroll کن، در همه فایل‌های آینده شناسایی شود | M | `pyannote/embedding` (TDNN+SincNet) + sqlite + cosine match |
| ۵ | **Vocal separation pre-processing** (Demucs toggle) | کاهش WER و hallucination روی صوت پر-سروصدا | S | `demucs` (htdemucs پیش‌فرض) — فقط vocals stem |
| ۶ | **Auto-chapter markers + LLM titles** | navigation فایل‌های طولانی؛ دلیل اصلی پرداختی Descript | M | embedding boundary detection (MiniLM cosine threshold) + Qwen برای title |
| ۷ | **Hardware autodetect wizard** | کاربر اول‌بار نمی‌داند device/compute_type چه باشد؛ benchmark ۳ ثانیه‌ای اعتمادسازی می‌کند | M | probe: CUDA → QNN/NPU → Intel-NPU → OpenVINO-GPU → DirectML → OpenVINO-CPU → CPU int8، با کلیپ ۵s |
| ۸ | **Hallucination detector flag** | Whisper تکرار / حلقه می‌زند روی سکوت طولانی | S | regex repetition + VAD-disagreement + BoH wordlist |
| ۹ | **Multi-model picker** (distil-v3.5 / turbo / Parakeet-tdt-v3) | کاربران مدل سریع‌تر می‌خواهند؛ Parakeet ۵× سریع‌تر از turbo روی اروپایی + ONNX-DirectML سازگار | S برای UI + L برای adapter جدید | faster-whisper turbo built-in + sherpa-onnx adapter جدید برای Parakeet |
| ۱۰ | **Search across all transcripts** | history.db همه چیز دارد ولی هیچ UI برای جست‌وجو نیست | S | MiniLM embedding + sqlite FTS5 |

---

## ۵ ایده‌ی **واقعاً outside-the-box** (در هیچ رقیب فعلی نیست)

- **Smart audio cutting à la Descript Underlord** — حذف کلمه از
  transcript = حذف صدا. ما alفbet word-level timestamps را داریم؛
  ffmpeg بقیه را انجام می‌دهد. **یک قابلیت سیگنیچر یونیک برای ما.**
- **Selective re-transcription**: انتخاب یک رنج زمانی + دکمه‌ی
  "rerun with larger model" — مدل بزرگ‌تر فقط روی آن قطعه اجرا شود.
  منطقی برای کاربری که segment خاصی اشتباه شده.
- **Auto-extract glossary** از transcript‌های گذشته → برای کاربر
  domain-specific (پزشکی / حقوقی) خودکار `initial_prompt` می‌سازد.
- **Voice fingerprint enrollment in 30s** — کاربر یک‌بار "این صدای
  من است" را ثبت می‌کند، در همه‌ی transcript‌های آینده "Me" برچسب
  می‌خورد.
- **Webhook + tiny REST API mode** (`gui.py serve --port 8080`) —
  automation با n8n / Home Assistant / homelab.

---

## طرح v0.8 — سه track همگرا

### Track 1 — Live & Capture (M)

RealtimeSTT روی همان `WhisperModel` موجود + WASAPI loopback. خروجی:
تب "Live" که هم‌زمان متن می‌نویسد + در پایان session pipeline batch
فعلی روی فایل کامل ضبط‌شده دقیق‌سازی می‌کند.

  - **Library**: `RealtimeSTT` (MIT، KoljaB، نسخه 1.0.0 / 2026-05)
    — `pip install "RealtimeSTT[faster-whisper]"`
  - **Latency on i7 12gen با distil-small.en**: ~380-520 ms end-to-end
  - **System audio**: `soundcard` (cross-platform) یا `pyaudiowpatch`
    (Windows-specific WASAPI loopback)
  - **Two-stage pattern**: streaming preview (small.en) + final batch
    re-transcribe (large-v3-turbo) — الگوی default RealtimeSTT

### Track 2 — AI Layer (M، opt-in download)

llama.cpp + Qwen2.5-1.5B Q4_K_M با **download-on-first-use** (نه bundle
همیشگی) — Portable از 447 MB → 450 MB ثابت می‌ماند. GBNF خروجی JSON
تضمینی برای chapters / summary / action-items.

  - **Runtime**: `llama-cpp-python` (~10 MB binary) با CUDA / Vulkan
    / Metal backends
  - **مدل**: Qwen2.5-1.5B Q4_K_M (~1.0 GB، 128K context، چندزبانه قوی
    شامل فارسی / عربی / اسپانیایی)
  - **Throughput**: 25-40 tok/s روی i7 CPU، 100+ tok/s روی RTX 3060
  - **GBNF**: تبدیل خودکار از JSON Schema → grammar در سطح توکن، خروجی
    معتبر تضمین می‌شود (مگر max_tokens زده شود)
  - **Translate**: Qwen خودش به جای bundle کردن NLLB-200 جداگانه —
    یک مدل کمتر، کیفیت قابل قبول روی جفت‌های پرکاربرد
  - **Semantic search**: `sentence-transformers/all-MiniLM-L6-v2`
    (~22 MB، 384-dim، ONNX-ready) برای جست‌وجوی متنی روی history.db

### Track 3 — Hardware & Quality (M)

Wizard اول‌بار + 5s benchmark + ذخیره در `hardware.json`، Demucs
toggle، hallucination detector، multi-model picker.

  - **Probe order**: CUDA → QNN/NPU (Snapdragon X Elite) → Intel-NPU
    (Meteor Lake via OpenVINO NPU plugin) → OpenVINO-GPU → DirectML
    (AMD/Intel) → OpenVINO-CPU → faster-whisper int8 CPU
  - **CUDA detection safety**: `ctranslate2.contains_cuda_device()`
    در try/except (torch.cuda.is_available روی Windows اگر
    cublas64_12.dll مفقود باشد crash می‌دهد بدون پیام روشن)
  - **Benchmark**: یک کلیپ ۵s pre-bundled روی لایه‌ی برنده، RTF واقعی
    اندازه می‌گیریم
  - **UI تأیید**: "Detected: NVIDIA RTX 3060 — Acceleration: CUDA +
    float16 — Benchmark: 0.04 RTF (25× real-time)"
  - **Demucs**: `htdemucs` پیش‌فرض — فقط vocals stem برای pre-process
  - **Hallucination detector**: regex repetition + VAD-disagreement
    (segment که VAD سکوت می‌گوید ولی Whisper متن تولید کرد) + BoH list

---

## وضعیت فناوری‌ها — یافته‌های شارد ۲

### Live streaming (همه روی Windows tested)

| Approach | Pros | Cons | حکم برای ما |
|---|---|---|---|
| `whisper.cpp` stream | ساده‌ترین، C++ بومی | SDL2 dep، خارج از stack ما | Skip |
| UFAL `whisper_streaming` + LocalAgreement-2 | کاغذ علمی، MIT، Python خالص | latency 3.3s متوسط (روی ESIC EN) | Possible |
| Collabora WhisperLive | TensorRT, OpenVINO | Docker لازم، معماری server-client | Skip |
| **RealtimeSTT (KoljaB)** | wrapper پایتونی تمیز، MIT، Silero+WebRTC VAD، multiprocessing، MIT | wrapper جدید (نسخه 1.0.0 / 2026-05) | **Pick** |

**latency واقعی**:
- i7 12gen + 8-thread + faster-whisper int8 + small.en: ~0.2 RTF، end-to-end ~380-520 ms
- Ryzen 5 4500U + whisper.cpp small: 7-14 s (مرز قابل قبول)
- زیر 1s فقط با GPU: RTX 3060 12GB حداقل عملی، RTX 4090 برای زیر 200 ms

### Local LLM augmentation

**مدل‌های قابل bundle (هدف زیر 2 GB، پاسخ زیر 5s روی i7 CPU)**:

| مدل | حجم Q4_K_M | context | چندزبانه | ifeval / mmlu |
|---|---|---|---|---|
| **Qwen2.5-1.5B-Instruct** | ~1.0 GB | 128K | عالی (شامل فارسی) | 47.4 / 60.9 |
| **Qwen2.5-3B-Instruct** | ~1.9 GB | 128K | عالی | 67.4 / 65.6 |
| Phi-3.5-mini-instruct | ~2.3 GB | 128K | متوسط | 59.2 / 69.0 |
| Llama-3.2-3B-Instruct | ~2.0 GB | 128K | متوسط | 77.4 / 63.4 |
| Gemma-2-2B | ~1.5 GB | **فقط 8K** | متوسط | — |

**انتخاب**: Qwen2.5-1.5B برای کاربران معمولی (سریع، چندزبانه)؛ گزینه‌ی
"upgrade to 3B" برای کاربران power.

**خروجی JSON تضمینی**: llama.cpp از GBNF (سطح-توکن grammar) پشتیبانی
می‌کند. تبدیل خودکار از JSON Schema → GBNF موجود است. ⚠️ تضمین خروجی
معتبر فقط در صورت max_tokens کافی.

**ترجمه**: سه گزینه ارزیابی شد:

1. حالت داخلی `translate` Whisper — فقط به انگلیسی، صفر هزینه
   اضافه، روی tiny/small کیفیت بد. Skip برای فارسی.
2. NLLB-200-distilled-600M — 200 زبان، many-to-many، حجم CTranslate2
   int8 ~600 MB، latency 5-20 s/جمله. مناسب batch، بد برای live.
3. **Qwen خودش با prompt مناسب** — کیفیت فا-en قابل قبول، یک مدل
   کمتر روی نصاب. **Pick.**

**Semantic search**: `all-MiniLM-L6-v2` (~22 MB، 384 dim) با ONNX
backend 2-3× سریع‌تر. کافی برای search-across-transcripts. اگر کیفیت
چندزبانه مهم است، `BGE-small-multilingual` (~120 MB) جایگزین بهتری
است.

**اقتصاد حجم**:

```
Portable v0.7.1 = 447 MB
+ llama.cpp runtime ≈ 10 MB
+ Qwen2.5-1.5B Q4_K_M ≈ 1.0 GB
+ MiniLM ≈ 22 MB
─────────────────────────────
کل اگر bundled = ~1.45 GB
کل اگر download-on-first-use = ~450 MB (نصاب اصلی)
```

**توصیه**: download-on-first-use با دکمه "Enable AI features" در
Advanced dialog. الگوی LM Studio و Ollama.

### Hardware acceleration (می ۲۰۲۶)

**لایه‌ها و سرعت روی large-v3-turbo**:

| لایه | سخت‌افزار | RTF |
|---|---|---|
| faster-whisper int8 | i5/i7 12gen + 8 thread | 0.10-0.20 |
| faster-whisper float16 | RTX 3060 12GB | 0.02-0.04 |
| faster-whisper float16 | RTX 4090 | 0.005-0.01 |
| OpenVINO int8 | Intel Core Ultra NPU | 0.04-0.08 (تخمینی) |
| DirectML fp16 | AMD RX 6700 | 0.05-0.10 |
| QNN fp16 | Snapdragon X Elite NPU (45 TOPS) | 0.03-0.06 |

**نکته‌های فنی**:

- CUDA: `ctranslate2.contains_cuda_device()` روش رسمی است. CT2 4.5+
  به CuDNN v9 (CUDA ≥ 12.3) نیاز دارد.
- DirectML: روی هر GPU سازگار با DX12 ویندوز 10+، شامل AMD Radeon /
  Intel Arc / NVIDIA. Microsoft اعلام کرد در «sustained engineering»
  و توسعه به Windows ML منتقل شده، اما هنوز روش عملی برای AMD روی
  ویندوز است.
- NPU detection: Windows 11 build 28020+ NPU را در Task Manager نشان
  می‌دهد. در سطح کد: WinML یا API های فروشنده.
- OpenVINO 2026: پشتیبانی NPU بهبود یافته. روی Intel Core i5/i7
  معمولی، نسخه INT8 از Whisper-base ~1.4-5.1× سریع‌تر از PyTorch خام.

---

## آیتم‌های "Worth investigating" (نیاز به prototype)

| # | ویژگی | چالش |
|---|---|---|
| ۱۱ | Edit-by-text (حذف کلمه = برش audio) à la Descript | همگام‌سازی word-boundaries با ffmpeg، edge-case ها زیاد |
| ۱۲ | Selective re-transcription با مدل بزرگ‌تر | UI workflow برای انتخاب رنج زمانی + re-run محلی |
| ۱۳ | Semantic search روی history.db با embeddings | سایز DB و indexing strategy، اما high value |
| ۱۴ | Code-switching (دو زبان در یک جمله) | هیچ مدل open-source فعلاً خوب نیست؛ NeMo Canary-1B-flash شاید |
| ۱۵ | Streaming Sortformer برای diarization زنده | جدید (2025)، روی Windows ناپایدار |
| ۱۶ | Highlight / clip export با timestamp | ساده اما نیاز به UI متفکرانه |
| ۱۷ | Auto-detect speaker count + name suggestion | LLM می‌تواند از conversation context حدس بزند |

---

## آیتم‌های "Skip" (نامناسب با single-exe + offline)

| ویژگی | چرا نه |
|---|---|
| Bot-in-meeting integration (Otter, Fireflies) | cloud auth لازم، خلاف ethos no-cloud |
| CRM integration (Salesforce / HubSpot) | offline-only، feature B2B غیرضروری |
| Voice cloning (Overdub) | حساسیت اخلاقی + مدل سنگین + abuse risk |
| Cross-meeting shared workspaces | server-side لازم، خلاف single-exe |
| OpenAI Realtime API streaming | cloud-only |
| iOS keyboard companion | scope creep، platform mismatch |

---

## ۵ شکایت اصلی کاربران ۲۰۲۶ (از HN / Reddit)

از HN thread 44225953 و r/LocalLLM:

1. **نبود خلاصه‌سازی / Q&A محلی** — کاربران می‌خواهند بعد از رونویسی،
   action-items / سؤال‌پرسی آفلاین داشته باشند. → Track 2 می‌پوشد.
2. **Hallucinations روی سکوت طولانی / صوت طولانی** — رفرنس:
   arXiv 2501.11378 (BoH + VAD mitigation). → آیتم #۸ شورت‌لیست
   می‌پوشد.
3. **چندزبانگی همزمان (code-switching)** — هلندی-انگلیسی در یک
   جمله که Whisper بد می‌فهمد. → Worth investigating #14.
4. **شناسایی گوینده‌ی کم‌صدا و دور از میکروفون** — diarization فعلی
   این را از دست می‌دهد. → Demucs + cross-file fingerprint می‌توانند
   کمک کنند.
5. **بازخورد بصری زنده هنگام dictation** — می‌خواهند متن همان لحظه
   ظاهر شود نه بعد از stop. → Track 1 می‌پوشد.

---

## مراجع کلیدی (~۵۰ منبع جمع شد، انتخاب مهم‌ترین‌ها)

### Live streaming
- [github.com/KoljaB/RealtimeSTT](https://github.com/KoljaB/RealtimeSTT)
- [github.com/ufal/whisper_streaming](https://github.com/ufal/whisper_streaming)
- [arXiv 2307.14743 — Turning Whisper into Real-Time](https://arxiv.org/pdf/2307.14743)
- [github.com/collabora/WhisperLive](https://github.com/collabora/WhisperLive)
- [github.com/ggml-org/whisper.cpp stream README](https://github.com/ggml-org/whisper.cpp/blob/master/examples/stream/README.md)
- [huggingface.co/SileroVAD overview](https://medium.com/axinc-ai/silerovad-machine-learning-model-to-detect-speech-segments-e99722c0dd41)

### Local LLM
- [huggingface.co/Qwen/Qwen2.5-3B-Instruct](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct)
- [huggingface.co/microsoft/Phi-3.5-mini-instruct](https://huggingface.co/microsoft/Phi-3.5-mini-instruct)
- [github.com/ggml-org/llama.cpp GBNF README](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)
- [Simon Willison — llama-cpp-python grammars JSON](https://til.simonwillison.net/llms/llama-cpp-python-grammars)
- [huggingface.co/facebook/nllb-200-distilled-600M](https://huggingface.co/facebook/nllb-200-distilled-600M)
- [huggingface.co/sentence-transformers/all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
- [aimagicx.com — Local AI Models 2026 hardware guide](https://www.aimagicx.com/blog/local-ai-models-2026-qwen-mistral-llama-hardware-guide)

### Hardware
- [github.com/SYSTRAN/faster-whisper issue 1086 — CUDA compat](https://github.com/SYSTRAN/faster-whisper/issues/1086)
- [github.com/OpenNMT/CTranslate2 issue 1630 — Windows](https://github.com/OpenNMT/CTranslate2/issues/1630)
- [blog.openvino.ai — Optimizing Whisper with OpenVINO + NNCF](https://blog.openvino.ai/blog-posts/optimizing-whisper-and-distil-whisper-for-speech-recognition-with-openvino-and-nncf)
- [phoronix.com — Intel OpenVINO 2026.0 Released](https://www.phoronix.com/news/Intel-OpenVINO-2026.0-Released)
- [huggingface.co/OpenVINO/whisper-large-v3-fp16-ov](https://huggingface.co/OpenVINO/whisper-large-v3-fp16-ov)
- [onnxruntime.ai DirectML provider docs](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html)
- [github.com/ChharithOeun/whisper-amd-windows](https://github.com/ChharithOeun/whisper-amd-windows)
- [onnxruntime.ai QNN provider — Snapdragon](https://onnxruntime.ai/docs/execution-providers/QNN-ExecutionProvider.html)
- [learn.microsoft.com Copilot+ PCs developer guide](https://learn.microsoft.com/en-us/windows/ai/npu-devices/)

### Models
- [huggingface.co/openai/whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo)
- [huggingface.co/distil-whisper/distil-large-v3.5](https://huggingface.co/distil-whisper/distil-large-v3.5)
- [huggingface.co/nvidia/parakeet-tdt-0.6b-v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)
- [northflank.com — Best open source STT 2026](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)

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
- [learn.microsoft.com — Loopback Recording WASAPI](https://learn.microsoft.com/en-us/windows/win32/coreaudio/loopback-recording)

---

## یادداشت‌های آینده

- این تحقیق بخش feature بود؛ تحقیق remote-mode (سرور GPU ابری برای
  burst-compute) به‌صورت جداگانه در `docs/V09_REMOTE_MODE_RESEARCH.md`
  ثبت می‌شود (اگر آن دور هم تکرار شد، یا اگر تصمیم به ادامه گرفته
  شد).
- اگر مسیر AI Layer انتخاب شد، باید CLAUDE.md و BUILD.md به‌روزرسانی
  شوند تا shape جدید (download-on-first-use، llama.cpp dep، Qwen
  GGUF) را منعکس کنند.
- Smoke test برای v0.8: یک کلیپ زنده SMTV + (هر track فعال شد)
  validate end-to-end در exe ساخته شده، مشابه audit-2 smoke.
