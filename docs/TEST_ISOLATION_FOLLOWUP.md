# Test-suite isolation follow-up (pre-existing, discovered 2026-06-16)

Status: **NOT a product bug.** Every failing test PASSES in isolation. The
product code (incl. the macOS packaging/runtime path) is sound; this is purely
a test-suite hygiene issue. Recorded for a future focused session — do NOT fix
blindly.

## Symptom

`python -m pytest tests/ --ignore=tests/smoke -q` produces order-dependent
failures, and **which** tests fail shifts with machine state:

- With `creds/gcloud_stt.json` present (dev/build machine): failures in
  `test_cancel_checkpoint.py`, `test_transcribe_end_to_end.py::test_transcribe_writes_srt_and_json`,
  `test_transcriber_self_heal.py` (x2), `test_hub_setup_dialog.py`.
- With the key absent (CI-like): failures move to
  `test_v08_real_file_e2e.py` (`_FakeWhisperModel` object has no attribute
  `transcribe` at `core/transcriber.py:1450`), plus fd corruption
  (`OSError: [Errno 9] Bad file descriptor`, `I/O operation on closed file`).

Each of these files passes 100% when run alone.

## Root causes (at least three, independent)

1. **`core.transcriber` module globals leak across files.** `_ALT_BACKEND` /
   `_ALT_BACKEND_NAME` (set in `_load_alt_backend` / `load_existing_model`) stay
   populated after a test that activates a non-default backend. A later test's
   `get_effective_device()` (transcriber.py:210-218) then reads the stale
   alt-backend's `downgraded=False` instead of the faster_whisper model's flag
   → the self-heal assertions fail.
2. **A `_FakeWhisperModel` leaks** so a sibling test calls `.transcribe()` on a
   fake that doesn't implement it.
3. **File-descriptor corruption** from a worker/subprocess test bleeds into
   pytest's capture in later tests.

## Why the obvious fix is WRONG

A blanket autouse `conftest` fixture that resets `core.transcriber` globals
between every test would break the module-scoped E2E fixtures (e.g.
`test_v08_real_file_e2e.py` uses `@pytest.fixture(scope="module")` to load the
model once and run ~10 tests against it — a per-function reset wipes it after
test 1). The correct fix is surgical, per-file:

- Give each file/group that depends on clean global state its own
  function-scoped fixture that snapshots + restores the specific
  `core.transcriber` globals it touches (`MODEL`, `PIPELINE`, `MODEL_READY`,
  `MODEL_ERROR`, `_ALT_BACKEND`, `_ALT_BACKEND_NAME`).
- Pin `transcribe_backend="faster_whisper"` in tests that monkeypatch the model
  but assume the offline path, so they don't depend on whether a bundled key
  flips the default to `google_cloud_stt`.
- Find and fix the fd-closing test (likely a worker/subprocess test) so it
  restores stdout/stderr.

Verify by running the full `tests/ --ignore=tests/smoke` suite BOTH with and
without `creds/gcloud_stt.json` present — both must be green.
