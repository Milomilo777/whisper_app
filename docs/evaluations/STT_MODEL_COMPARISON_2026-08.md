# Evaluation — 26-way STT model comparison on a hard real-world clip

**Date:** 2026-08-10
**Verdict:** Local **`large-v3`** (the app's default) produced the cleanest,
most complete transcript of all 26 configurations tested, at no cost. Cloud
**`chirp_3`** was the best of the 8 Google Cloud STT v2 models. **Avoid the
Large-v3-Turbo family on ambiguous/noisy audio** — see the hallucination
finding below.

This note records an ad hoc quality comparison run across every model this
app can reach: all 8 Google Cloud Speech-to-Text v2 models
(`core/backends/google_cloud_stt.py`) and all 18 local faster-whisper
models in `core/model_manager.MODEL_REGISTRY`. Useful as a reference the
next time a user asks "which model/backend should I pick".

---

## Test setup

- **Source clip:** ~23 seconds, real-world recording. Deliberately a hard
  case, not a clean sample: weak/low recording level and multiple people
  talking over each other. Results below should be read as "best effort
  on hard audio", not a word-error-rate benchmark on clean speech.
- **Google Cloud STT v2:** all 8 selectable models (`chirp`, `chirp_2`,
  `chirp_3`, `long`, `short`, `telephony`, `telephony_short`,
  `chirp_telephony`), standard (online) mode, auto or `en-US` language
  depending on what each model accepts.
- **Local faster-whisper:** all 18 `MODEL_REGISTRY` entries, `device="auto"`,
  `compute_type="int8"`, default (non-VAD) settings.
- Ranked by **overall trustworthiness**, not raw "seconds of audio
  covered" — a transcript that covers *more* than the real clip length is
  a red flag (the model kept generating after the audio ended), not a win.

## Finding: a real hallucination bug in Whisper Large-v3-Turbo

Both Turbo variants (`large-v3-turbo` and the community `deepdml`
conversion) repeatedly inserted the phrase **"Shri Mataji —"** into the
transcript — text with no relationship to the source audio. This matches a
documented contamination artifact in the Whisper large-v3-turbo family
(traced to leaked training data), not random noise. It surfaced on this
clip specifically because the audio is weak/ambiguous; clean audio is far
less likely to trigger it, but the risk is real for any low-quality or
overlapping-speech recording.

**Practical takeaway:** don't default to Turbo for content where accuracy
matters and the source audio may be poor. This app's `DEFAULT_MODEL_SLUG`
is already `large-v3` (not Turbo), which is the right default; this result
is a reason to keep it that way rather than "upgrade" the default to Turbo
for speed.

The `small` and `distil-small.en` local models showed a milder version of
the same failure mode: their transcripts ran past the real clip length and
`small` visibly looped on repeated phrases — classic repetition
hallucination under acoustic stress.

## Google Cloud STT v2 — per-model behavior on this clip

| Model | Result |
|---|---|
| `chirp_3` | Full-length, coherent, best of the 8. |
| `telephony` | Full-length, coherent, one invented detail near the end. |
| `chirp` | Full-length content, but no punctuation/casing (expected — this is a v1 model characteristic, not a bug). |
| `chirp_2` | Stopped after ~7s of the ~23s clip. |
| `long` | Stopped after ~7s. |
| `telephony_short` | Stopped after ~5s. |
| `short` | Returned nothing — built for brief single utterances, not a good fit here. |
| `chirp_telephony` | Returned nothing — tuned for narrowband 8 kHz phone audio, not this file. |

All 8 models bill at the **same flat rate** — the model choice does not
change price. Standard (online) mode is ~$0.016/min; batch mode is
~75% cheaper (~$0.003–0.004/min) but is not instant (Google queues it,
commonly within a few hours, with a documented ~24h ceiling), and needs a
Cloud Storage bucket. Every project also gets 60 free minutes/month
(ongoing) plus a one-time $300 new-customer credit — see
[CLOUD_STT_GOOGLE.md](../CLOUD_STT_GOOGLE.md) for full setup/pricing detail.

## Local faster-whisper — headline results

- **`large-v3`** (default): cleanest, full-length, no hallucination.
- The `large-v2`, `large-v1`, `medium(.en)`, and `distil-large-*` tiers all
  produced full-length, broadly coherent transcripts with only minor
  wording errors — reasonable fallbacks when `large-v3` is too slow for
  the hardware.
- **`large-v3-turbo` / `deepdml-large-v3-turbo`**: fabricated content (see
  above) — do not recommend as a default despite their speed advantage.
- **`tiny`, `tiny.en`, `base`, `base.en`**: noticeably degraded wording, as
  expected for their size class; usable for quick drafts only.
- **`small`, `distil-small.en`**: showed the mild hallucination pattern
  described above on this specific hard clip.

## Recommendation

For weak or overlapping-speaker audio: use local `large-v3` as the primary
pass (free, best result here), and treat `chirp_3` or `telephony` as an
optional cloud cross-check. Do not rely on the Turbo variants, or the
tiny/base/small tier, for content where transcript accuracy matters.

## Caveats

- Single clip, single run — this is a spot check, not a statistically
  robust benchmark. The Turbo hallucination is a known, reproducible model
  characteristic (not clip-specific), but exact wording will vary run to
  run.
- Timing was not measured under controlled/repeatable conditions (mixed
  sequential and parallel downloads, some models already cached) and is
  not included here for that reason — do not treat this note as a speed
  comparison.
