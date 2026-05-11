# Phase 2a — Acceptance

| ID    | What                                                                                  | How |
|-------|---------------------------------------------------------------------------------------|-----|
| 2A-T1 | `transcribe` applies VAD by default                                                   | `python -c "from core.transcriber import _vad_parameters, config; assert config['vad_enabled']; assert _vad_parameters() is not None"` |
| 2A-T2 | `word_timestamps=True` produces non-empty `words` arrays for non-silent audio         | `python -m pytest tests/core/test_transcribe_end_to_end.py::test_transcribe_with_word_timestamps_enriches_json -q` |
| 2A-T3 | Each writer in `core/writers/` produces a valid file body                             | `python -m pytest tests/core/test_writers.py -q` |
| 2A-T4 | UI shows the detected language next to the queue tree row                             | Worker emits `language_detected`; `TranscriptionService.poll` writes it to `task.detected_language` + `task.language_probability`; `App.refresh()` formats it in the `language` column. Verify by reading `app/services/transcription_service.py` lines 190–194 and `app/app.py` `refresh()` (`detected_language`/`language_probability` lookup). |
| 2A-T5 | `BatchedInferencePipeline` is used when `device == "cuda"`                            | `python -m pytest tests/core/test_batched_pipeline.py::test_wrap_returns_pipeline_on_cuda -q` |
| 2A-T6 | `detect_device` works without `torch` installed                                       | `python -m pytest tests/core/test_batched_pipeline.py::test_detect_device_works_without_torch -q` |
| 2A-T7 | Real-audio smoke: tiny.en → silent_1s.wav → no crash + language captured              | `python -m pytest tests/core/test_transcribe_smoke.py -q` (auto-skips offline) |
| 2A-T8 | All Phase 0 + 1a + 1b + 2-oTranscribe tests still pass                                | `python -m pytest tests/ -q` |

## What changed in `core/transcriber.py`

- New top-level `BatchedInferencePipeline` import is wrapped in `try/except`
  for older `faster-whisper` wheels.
- `MODEL` and a new `PIPELINE` global (the batched wrapper, or `None`).
- `transcribe()` builds a `transcribe_kwargs` dict from config:
  `vad_filter` + `vad_parameters` (when VAD on), `word_timestamps`,
  `language` (forwarded from the worker command if set), `initial_prompt`,
  `hotwords`, and `batch_size` (only when running through the pipeline).
- Output writing pulled out into `core/writers/` and routed by
  `config["output_formats"]`. Default is `["srt", "json"]`; the user can
  pick any subset of `srt | vtt | tsv | txt | json | lrc` from the
  Advanced dialog.
- A `language_cb(lang, prob)` callback is invoked once per transcribe with
  the values from `info.language` / `info.language_probability`. The
  worker forwards this as a `language_detected` event.

## Worker JSON protocol additions (backward-compatible)

```
{"event": "language_detected", "language": "fa", "probability": 0.97, "file_path": "..."}
```

Existing events (`ready`, `started`, `progress`, `done`, `error`,
`worker_exit`) are unchanged.

## Test fixtures

- `tests/fixtures/audio/silent_1s.wav` — 16 kHz mono PCM, 1 s of silence
- `tests/fixtures/audio/tone_440hz_2s.wav` — 16 kHz mono PCM, 2 s of 440 Hz sine

Both are committed (≈ 96 KB combined). Regeneration script in the fixture
folder's README.

## Coverage snapshot

```
TOTAL: 81% line coverage on core/
  config.py                        83%
  integrations/otranscribe.py      91%
  logging_setup.py                 78%
  model_manager.py                 82%
  task.py                          100%
  transcriber.py                   62%   (real-audio paths covered by smoke + e2e)
  worker.py                        89%
  writers/__init__.py              100%
  writers/base.py                  94%
  writers/json_writer.py           100%
  writers/lrc.py                   100%
  writers/srt.py                   100%
  writers/tsv.py                   100%
  writers/txt.py                   100%
  writers/vtt.py                   96%
```
