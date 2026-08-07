# Feature gaps vs. Voice-Pro (2026-08-07)

Target of comparison: [abus-aikorea/voice-pro](https://github.com/abus-aikorea/voice-pro),
v4.0, an open-source project in the same problem space.

Companion to `docs/GAPS_AGAINST_PEERS_2026.md` (desktop transcription apps:
MacWhisper, Buzz, Vibe) and `docs/COMPETITIVE_ANALYSIS_2026.md` (ASR model /
cloud-API landscape). Those two cover *transcription* peers. Voice-Pro is a
different shape of competitor and deserves its own sheet.

Claims about our own code below were checked against the tree on 2026-08-07;
claims about Voice-Pro come from its README at that date.

## What the two projects are

**Voice-Pro** is a Gradio web-UI *dubbing studio*: transcribe → translate →
text-to-speech → dubbed video. NVIDIA-GPU-first (driver ≥ 570, 4–8 GB VRAM),
~20 GB install, `Internet: Required`, LGPL/GPL-3.0. Its README states
development is currently on hold.

**Whisper Project** is an offline-first Tkinter desktop app: transcribe →
export in 13 formats, plus media download, a resumable queue, diarization,
video tiling and an optional LAN server.

**The gap is not transcription quality.** It is the entire *output* half of the
pipeline: translation, speech synthesis, dubbing.

## Major gaps

### 1. Text-to-speech engine — MISSING ENTIRELY

Voice-Pro ships Edge-TTS (100+ languages, 400+ voices, free, no API key),
F5-TTS, E2-TTS, CosyVoice, Kokoro, and optional Azure TTS.

We have no TTS code anywhere under `core/` or `app/`.

Recommendation: start with `edge-tts` alone — pure Python, no GPU, no model
download, no API key, and it survives the slim embeddable-Python build's
dependency pruning in `build_embed_installer.bat`.

### 2. Translation as a real feature

Voice-Pro translates subtitles into 100+ languages via `deep-translator`
(free Google endpoint, with retry/backoff on rate-limiting), plus an optional
Azure Translator path for restricted networks.

We have `core/llm.py`'s `translate()` (local Qwen2.5-1.5B), but per the
`PROJECT_INDEX.md` onboarding notes it has **no discoverable UI entry point**,
and a 1.5B local model is slow and weak on long subtitle runs.

Recommendation: a provider-pluggable translation service (free Google endpoint
by default; DeepL / Azure as opt-in keys), a "Translate subtitles" action in
`app/dialogs/transcript_viewer.py`, and a target-language column in the queue.

### 3. Dubbing pipeline — the flagship gap

Voice-Pro's "Dubbing Studio" chains: download → denoise → transcribe →
translate → per-segment TTS → time-stretch to fit the original timing → mux
the new audio onto the video.

Entirely absent from our app. This is the single biggest differentiator.

Recommendation: a `core/dubbing.py` orchestrator layered on the existing
segment-list middle representation plus ffmpeg, so it reuses `core/writers/`
and `core/burn_subs.py` rather than growing a parallel pipeline.

### 4. Voice cloning / reference-voice library — low priority

Zero-shot cloning (F5-TTS / E2-TTS / CosyVoice) plus a bundled library of 40+
reference voices (English, Chinese, Korean, Japanese).

`core/voiceprint.py` only *recognises* speakers; it cannot reproduce a voice.

Recommendation: **do not build this.** Heavy (torch + GPU), legally sensitive,
and directly opposed to our offline / slim-build identity.

### 5. Audio denoise — distinct from vocal separation

Voice-Pro exposes a denoise level (0–2) before transcription.

`core/separator.py` (Demucs) splits vocals from music — a different operation;
it does not clean hiss or room noise.

Recommendation: a light noise-suppression pre-pass using ffmpeg's own `afftdn`
/ `arnndn` filters — zero new Python dependency, and ffmpeg is already
vendored in `bin/`.

### 6. ASS / SSA subtitle format — high value, low cost

Voice-Pro reads and writes styled ASS/SSA subtitles.

Our 13 formats (srt, vtt, tsv, txt, json, lrc, md, otr, elan, inqscribe,
express_scribe, docx, pdf) do not include it. ASS is what video editors and
karaoke/styling workflows expect, and it is the natural target for our
word-level timing data, which currently only reaches VTT.

Recommendation: one new module under `core/writers/`, registered in
`core/writers/__init__.py`, plus a parser entry in `core/convert.py`'s
`PARSE_FORMATS`.

### 7. Browser UI that is actually a UI

Voice-Pro's whole product *is* a browser UI (Gradio 6), reachable from any
device on the network.

`core/server/` is a deliberately minimal, stdlib-only job-submission page:
upload a file, watch a progress bar.

Recommendation: **do not adopt Gradio** — it would pull in a large dependency
tree and break the slim embed build. Grow `core/server/static/index.html`
incrementally instead (settings, transcript preview, format picker), keeping
the `escapeHtml()` discipline documented in `PROJECT_INDEX.md`.

### 8. Live / real-time transcription and translation — cheapest big win

Voice-Pro's "Translate" tab does live microphone speech recognition with
on-the-fly translation.

We ship `core/recorder.py` (microphone + Windows WASAPI loopback capture), but
nothing under `app/` imports it — written, tested, and unreachable from the UI,
the same situation as `core/llm.py`, `core/chapters.py` and `core/search.py`.

Recommendation: highest value-per-effort item on this list. The engine already
exists; it needs a tab and a streaming chunk loop.

### 9. TTS prosody controls

Speed / volume / pitch sliders for generated speech. Blocked on gap 1.

### 10. Multi-language README

Voice-Pro ships README files in Korean, English, Chinese (simplified and
traditional), Japanese, German, Spanish and Portuguese. We ship English only.

Note: translated *public READMEs* are user-facing localisation and do not
conflict with the repo's English-only rule for code, docs and commit messages.

## Minor / optional gaps

| # | Gap | Assessment |
|---|-----|------------|
| 11 | MDX-Net separation model alongside Demucs | Low priority; faster on some material only |
| 12 | `.env` file for cloud API keys | Ours (`config.json` + `creds/`) is arguably safer; very low priority |
| 13 | One-click self-update script | `core/updates.py` is notify-only by design. Keep that for installed builds; a Windows source-install update script would match `platform/linux/update.sh` |
| 14 | Whisper-timestamped / WhisperX backends | **Not a real gap.** stable-ts alignment + sherpa-onnx diarization already cover this. Do not add engines to match a bullet list |

## Where we are already ahead

- Fully offline by default. Voice-Pro's README states `Internet: Required`.
- 13 output formats vs. their subtitle-plus-audio set. ELAN, InqScribe,
  Express Scribe, oTranscribe, DOCX and PDF are research / transcription-
  industry formats they do not target at all.
- CPU is a first-class path. Voice-Pro assumes an NVIDIA GPU with a recent
  driver, 4–8 GB VRAM and ~20 GB of disk.
- A real desktop app: drag-and-drop, system tray, watched folders,
  crash-resume, a pausable/resumable queue, and checkpointed transcription.
- 5 pluggable ASR backends, including two cloud options and NVIDIA Parakeet.
- Windows installer + portable zip, Linux source install, CI-built macOS
  `.app`/`.dmg`.
- 174 test files, a pyright 0-error/0-warning gate, and a maintained release
  process.
- Voice-Pro's README says its development is on hold; ours is active.

## Suggested order of work

**Tier 1** — cheap, high value, no heavy dependency:
gap 8 (wire the existing recorder into a Live tab), gap 6 (ASS/SSA writer +
parser), gap 5 (ffmpeg denoise pre-pass), gap 10 (translated READMEs).

**Tier 2** — new dependency, still light:
gap 1 (Edge-TTS speech generation), gap 2 (translation service).

**Tier 3** — the flagship, only after tiers 1 and 2:
gap 3 (dubbing pipeline), gap 9 (prosody controls), gap 7 (richer browser UI).

**Tier 4** — probably never:
gap 4 (voice cloning), gap 11 (MDX-Net), gap 14 (extra ASR engines).

## Bilingual copy

A Persian + English version of this list exists as `VOICE_PRO_GAP_FA_EN.txt`
at the repo root. It is **not committed** — the repository is English-only per
`CLAUDE.md`. That file is a working document for the owner.
