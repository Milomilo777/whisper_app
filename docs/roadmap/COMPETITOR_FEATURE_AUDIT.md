# Competitor feature audit (2026-08-16)

Owner sent a list of 19 similar Whisper-transcription GitHub projects
and asked for a scan of what they have that this project doesn't. Full
comparison table lives in a private Claude Artifact (not part of the
repo); this file is the durable record of the outcome: what shipped,
and what was evaluated but deliberately left undone.

**Status: evaluated, not committed.** Nothing below is scheduled for a
release. It's a candidate list for a future session to pick from, not
a promise.

## Shipped this round (see CHANGELOG at next release cut)

- Transcript viewer AI Tools tab (summarise / action items / ask /
  translate) wired to `core/llm.py` — the engine existed, nothing
  called it.
- Transcript viewer Chapters tab, reading the `<name>.chapters.json`
  sidecar `core.chapters` already wrote.
- `Help > Search transcripts...` wired to `core/search.py` — same
  situation, an unused FTS5 engine.
- Bilingual subtitle export (`core/writers/bilingual_srt.py`, one
  segment translated at a time so it stays cue-aligned with the
  original).
- `core.llm.RemoteLLMRunner` — a user-configured OpenAI-compatible
  endpoint (real OpenAI API, or a self-hosted/proxy server) as an
  alternative to the bundled local model, for all four AI Layer
  functions.
- `core.config.NOISY_AUDIO_PRESET` + an "Apply noisy-audio preset"
  button in Advanced Settings.

## Already existed (audit corrected a mistaken gap)

The original scan proposed "custom prompt/hotwords before
transcription" as a gap, inspired by `CheshireCC/faster-whisper-GUI`.
It isn't one — Advanced Settings' "Prompt, hotwords & output naming"
section already has both fields (`initial_prompt` / `hotwords` in
`core/config.py`, wired since before this session). Caught by reading
the actual code before implementing instead of trusting the scan.

## Evaluated, not implemented

Ordered roughly by expected value vs. effort, highest first.

1. **Waveform view in the transcript viewer** — a visual audio
   timeline for dragging cue boundaries, instead of only the numeric
   "Edit timestamp..." dialog. Inspired by `URUWorks/TeroSubtitler`.
   Largest effort in this list (a new rendering + interaction surface,
   not a thin wrapper over an existing engine).

2. **Subtitle QC + spell-check** — reading-speed (characters/second)
   and line-length warnings against common subtitle-industry
   thresholds, plus a spell-checker pass over segment text. Also from
   TeroSubtitler. Needs a wordlist/spell-check dependency decision
   (bundled vs. on-demand install, matching the `core.optional_deps`
   pattern) before implementation.

3. **Live/real-time transcription** — partial results streamed while
   recording or while audio plays, instead of the current
   record-then-transcribe flow (`core/recorder.py` streams to a WAV
   file; there is no partial-result path). Came up independently from
   three different projects in the scan
   (`reriiasu/speech-to-text`, `papacasper/whisper-transcribe`, and a
   generic "Whisper GUI" match) — the most repeated request in the
   whole list. Real architectural work: needs a streaming decode loop
   distinct from the batch `core.transcriber.transcribe()` path.

4. **Audio speed-up before transcription** — trade some accuracy for
   throughput on slow hardware by resampling the input faster before
   it reaches the model. From `Topping1/whispercppGUI`. Small, isolated
   change (an ffmpeg pre-process step), low risk.

5. **Batch cue timestamp shift** — advance/delay every segment in a
   transcript by one fixed offset, for quick resync against a
   different cut of the same source. From `CheshireCC/faster-whisper-GUI`.
   Small: a pure function over the segments list plus one button in the
   transcript viewer.

6. **Frame-rate conversion** — retime a subtitle between common video
   frame rates (23.976/25/29.97fps). From TeroSubtitler. Niche
   (matters mainly to video editors syncing against a re-encoded cut);
   low priority.

7. **SMI output format** — one more writer alongside the current 13,
   for the Korean-market SAMI subtitle format. From
   `CheshireCC/faster-whisper-GUI`. Trivial to add whenever there's an
   actual user asking for it; not worth doing speculatively.

8. **Docker/Helm deployment path** — a containerized way to run this
   as a shared team server, alongside (not replacing) the existing
   optional LAN/web server (`core/server/`). From `kaixxx/noScribe`.
   Cross-cutting with packaging/release infrastructure, not a small
   change.

9. **Apple Silicon MLX backend** — a native `mlx-whisper` engine for
   much faster inference on M-series Macs, from `tsmdt/whisply`.
   **Logged for completeness only — this repo's standing rule is to
   never build or dispatch a macOS artifact** (see root `CLAUDE.md`,
   "macOS builds — do not build"). Revisit only if that rule changes.
