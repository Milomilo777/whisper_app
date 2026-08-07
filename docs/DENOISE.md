# Audio denoise pre-process

Optional, off by default. Turn it on in **Advanced > AI Layer > Reduce
background noise before transcribing**. Implemented in `core/denoise.py`.

Uses the bundled ffmpeg only — no extra Python package, no model
download, no network, and nothing that the slim embeddable-Python build
prunes. It works offline and on CPU like the rest of the app.

## Why it exists

Noise is the biggest driver of Whisper hallucination and word-error rate
on real material: field recordings, phone audio, low-bitrate downloads,
air-conditioning hum, mic hiss, and the re-encoded audio that comes off
the Download tab.

`core/hallucination.py` already *flags* hallucinated segments after the
fact. This attacks the cause instead of the symptom. It also helps the
stages that read the same audio — VAD segmentation, speaker diarization
and word alignment all degrade on a noisy signal.

## Why it is not just a strength knob

Whisper was trained on ~680k hours of noisy web audio, so it is *already*
robust to ordinary noise. Denoising a clean recording adds artefacts the
model has never heard and makes transcripts **worse**. A fixed
"denoise level 0-2" control — the usual design — applies the same
processing to a studio interview and a windy street recording.

So the pipeline is **measure -> decide -> apply -> verify**:

| Stage | What happens |
|---|---|
| Measure | `astats` over sampled windows; estimate speech-to-noise ratio |
| Decide | map SNR to `off` / `light` / `medium` / `strong` |
| Apply | filter chain parameterised by the *measured* noise floor |
| Verify | re-measure; discard the result if it removed speech, not noise |

Every stage can bail out to "use the original audio". Nothing in this
module can fail a transcription.

### Measure

One ffmpeg pass produces two `astats` blocks — full-band, and band-passed
to the 300–3400 Hz speech band. SNR is estimated as:

```
speech_level = max(RMS_level, RMS_peak - 10 dB)
SNR          = speech_level - noise_floor
```

`RMS_peak - 10` is the fallback for sparse speech: on a file that is
mostly silence the overall RMS understates the speech level and would
over-trigger denoising on a quiet-but-clean recording.

Files longer than 3 minutes are **sampled** at 15%, 50% and 80% (30 s
each) rather than scanned end to end, and the **median** window is used.
Analysis therefore costs the same on a 3-hour file as on a 10-minute one,
and a music intro or one silent gap cannot steer the decision.

### Decide

| Measured SNR | Level |
|---|---|
| no measurable noise floor, or ≥ 30 dB | `off` — left completely untouched |
| 20 – 30 dB | `light` |
| 10 – 20 dB | `medium` |
| < 10 dB | `strong` |

An unusable measurement also means `off`: never denoise on a guess.
Setting **Strength** to a named level overrides all of this — it is then
applied even to clean audio.

### Apply

```
light   highpass=f=70:poles=2,afftdn=nr=10:nf=<measured>:tn=1
medium  highpass=f=80:poles=2,afftdn=nr=16:nf=<measured>:tn=1
strong  highpass=f=90:poles=2,afftdn=nr=24:nf=<measured>:tn=1
```

- The high-pass removes rumble, HVAC and handling noise from below the
  speech fundamental.
- `afftdn` is spectral denoise; `tn=1` tracks a *changing* noise bed
  instead of assuming it is stationary.
- `nf` is the **measured** noise floor, clamped to ffmpeg's accepted
  −80…−20 dB, not a hard-coded guess.
- `nr` stays at or below 24 dB on purpose. Deeper settings produce
  musical noise — isolated spectral artefacts that hurt ASR more than
  the noise they removed.

Output is 16 kHz mono WAV, which is what every ASR backend resamples to
anyway, so this replaces a decode rather than adding one.

### Verify

A denoised result is **rejected and the original used** when either:

1. **Speech-band energy fell more than the measured noise can explain.**
   At SNR *s* the noise carries `10^(-s/10)` of the power, so removing it
   perfectly costs `10*log10(1 + 10^(-s/10))` dB. The allowance is that
   plus 0.8 dB. This scaling matters: a clean file may lose almost
   nothing before it counts as damage, while a genuinely noisy file is
   allowed a large *expected* drop. A fixed threshold would reject
   exactly the heavy-noise cases the feature exists for.
2. **Entropy collapsed** by more than 0.12. This catches gating, which
   barely moves total energy while chopping speech onsets and tails.

Both guards are needed — see the calibration below for the case each one
misses on its own. The decision is deliberately asymmetric: a wrong
"revert" wastes one ffmpeg pass, a wrong "keep" degrades every segment of
the transcript.

## Calibration

Thresholds were derived from measurement, not taste. Test material:
Windows SAPI speech mixed with pink noise at seven amplitudes, plus
synthetic tone-burst signals. Reproduced with the bundled ffmpeg
(2026-05-06 build).

Auto-decision and outcome on real speech:

| noise amp | measured SNR | level chosen | SNR gain | speech-band drop | allowed | verdict |
|---|---|---|---|---|---|---|
| 0 | no floor | `off` | — | — | — | skipped |
| 0.005 | 36.1 dB | `off` | — | — | — | skipped |
| 0.01 | 30.5 dB | `off` | — | — | — | skipped |
| 0.03 | 20.8 dB | `light` | +8.2 dB | 0.278 dB | 1.04 dB | keep |
| 0.08 | 12.4 dB | `medium` | +11.2 dB | 0.416 dB | 1.24 dB | keep |
| 0.15 | 6.9 dB | `strong` | +13.0 dB | 0.708 dB | 1.81 dB | keep |
| 0.3 | 1.2 dB | `strong` | +19.4 dB | 2.022 dB | 3.45 dB | keep |
| 0.5 | −2.2 dB | `strong` | +14.4 dB | 3.016 dB | 5.25 dB | keep |

Deliberately destructive chains, at ~30 dB baseline SNR:

| chain | speech-band drop | entropy drop | caught by |
|---|---|---|---|
| `afftdn=nr=60:nf=-20` | 1.214 dB | 0.092 | band guard |
| `afftdn=nr=97:nf=-20` | 1.214 dB | 0.092 | band guard |
| `lowpass=f=1000` | 0.942 dB | 0.030 | band guard |
| hard `agate` | 0.183 dB | 0.151 | **entropy guard only** |

The gate row is why there are two guards: it slips past an energy check
because loud speech still dominates the RMS.

Two findings worth keeping in mind:

- **SNR alone is a fraudable metric.** An over-aggressive filter drives
  the noise floor to digital silence and scores "infinite SNR" while
  gutting the signal. That is why verification watches speech-band
  energy and entropy instead.
- **A fixed band threshold false-rejects.** Before the SNR scaling was
  added, legitimate `strong` passes at 1.2 and −2.2 dB SNR — gaining
  +19.4 and +14.4 dB — were being thrown away.

## Known issue: `anlmdn` is not used

ffmpeg's `anlmdn` (non-local-means denoise) measurably helped, but it
**segfaults non-deterministically** in the bundled ffmpeg build:
identical arguments on identical input crashed one run and succeeded the
next. With it removed, the strong chain ran 20/20 without a failure.

Do not add it back without repeating that stability check.
`tests/core/test_denoise.py::test_chain_never_contains_anlmdn` guards
against it being reintroduced by accident.

(ffmpeg dying on a signal is handled anyway — a non-zero exit falls back
to the original audio — but a random crash on the user's noisiest files
is not something to rely on a fallback for.)

## Cost

Roughly 20–40 seconds per hour of audio for measurement plus filtering on
a typical CPU. Renders are cached under `user_cache_dir()/denoise` and
capped by `denoise_cache_mb` (default 1024 MB), oldest evicted first.

A time-range ("clip") transcription denoises only the slice it actually
transcribes, and that render is not cached — its cache key could never be
hit again.

## Where it applies

- The default faster-whisper path.
- Every alternative backend (whisper.cpp, Gemini, Google Cloud STT,
  NVIDIA Parakeet) — noise hurts all of them.
- The resume path, so a resumed tail is conditioned exactly like the
  first half. `denoise_enabled` / `denoise_level` are part of the
  checkpoint fingerprint, so changing them mid-job invalidates the
  partial rather than splicing mismatched halves.

Diarization, alignment and chapters still read the **original** file, as
they did before.

## Related

- `demucs_enabled` (**vocal separation**) is a different tool: it splits
  vocals from music and needs a ~150 MB model plus torch. Denoise is for
  hiss, hum and rumble, costs nothing extra, and the two can be combined
  — separation runs first, then denoise.
- [CONFIG.md](CONFIG.md) — the three `denoise_*` keys.
