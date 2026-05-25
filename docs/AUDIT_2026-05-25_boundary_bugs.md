# Boundary-bug audit — 2026-05-25

Context: a collaborator hit four real bugs (silent downloads, a
transcribe-after-download freeze, the model-hub choice being ignored,
and a crash-resume prompt that nagged every launch) that survived
multiple deep debugging passes and a 578-test hermetic suite. This
doc records **why they escaped**, the **method** used to hunt for more,
and the **findings**.

## 1. Why the test suite missed them

All four bugs share one property: **none lives inside a single
function.** Each is emergent from an interaction across a boundary that
the hermetic unit tests deliberately do not cross. The suite's greatest
strength — fast, isolated, mock-heavy unit tests — is exactly the blind
spot:

- **Mocks hid the unit under test.** `test_auto_transcribe_wiring.py`
  stubs `App.enqueue_transcription_from_download`, so it verified that
  the download path *calls* the method but never ran the method's
  blocking body. "The mock passed, reality froze."
- **String-level assertions, not runtime behaviour.** The download
  tests asserted the yt-dlp format string contained `+` and `ext=mp4`;
  they never ran yt-dlp, so the missing-parentheses precedence bug
  (video-only stream selected → no audio) was invisible.
- **Single-shot tests can't see stateful / multi-launch bugs.**
  `model_path` reset and crash-resume nag only manifest across a
  save→reload cycle or a decline-then-relaunch cycle. Unit tests load
  config once.
- **Some bugs need real latency + the event loop.** The freeze only
  *feels* like a bug with a real ~10–60 s model load on the Tk main
  thread. Code review rarely reveals "this blocks for 30 s" because it
  takes a 3-hop chain (download handler → main thread → `Event.wait`)
  to see it.
- **The collaborator found them by USING the app**, not by testing.
  That is the tell: these are use-bugs, not logic-bugs.

Net: the project is over-indexed on isolated unit tests and
under-indexed on (a) integration/E2E that crosses process + thread +
time boundaries, and (b) hands-on usage.

## 2. The method: audit by boundary class

Rather than re-read everything, we ran four parallel read-only audits,
each targeting one boundary class matching one of the found bugs:

| Class | Boundary | Seed bug |
|---|---|---|
| A | Tk main thread blocking on slow work | transcribe-after-download freeze |
| B | config derived-then-persisted | model_path reset |
| C | subprocess command string vs. runtime parse | silent download |
| D | cross-session / state-machine | crash-resume nag |

This is reusable: when a bug is found, classify its boundary and audit
that whole class, not just the one instance.

## 3. Findings

Status legend: **FIXED** (in v1.0.4) · **DEFER** (real, queued) ·
**VERIFY** (needs a real-tool run before any change).

### Class A — main-thread freeze
- **FIXED** `_maybe_offer_crash_resume` "Yes" branch and the
  watched-folder enqueue (`_check_stable_then_enqueue`) called
  `ensure_worker_ready(headless=True)` — the same blocking
  `Event.wait(120 s)` on the Tk main thread as the original bug. All
  three paths now share `App._when_worker_ready`, an `after()`-polling
  helper that never blocks the loop.
- **DEFER** `HardwareWizard._reprobe` → `core.hardware.probe_tiers()`
  runs synchronous `torch` / `onnxruntime` / `openvino` imports on the
  main thread (Advanced → "Re-detect hardware"). Seconds-long stall, no
  progress UI. Fix: move to a `safe_thread` + `post_to_main`, mirroring
  the benchmark worker.

### Class B — config persistence
- **DEFER** `download_folder` has the same trap that `model_path` had,
  and is currently **unguarded**. `_apply_runtime_fallbacks` clears it
  to `""` when its drive is unmounted; any later `save_config` persists
  the `""`, so a download folder on a removable / network drive is
  forgotten permanently after one launch without the drive. Fix
  symmetric to `_persistable_model_path`: don't persist the cleared
  value when the clear was only due to a missing mount.

### Class C — subprocess command correctness (VERIFY before fixing)
These need a real yt-dlp/ffmpeg + ffprobe run to confirm; do **not**
change blindly — the time-range feature is shipped and E2E-tested.
- `--download-sections` without `--force-keyframes-at-cuts` may start
  the clip at the preceding keyframe (several seconds early) on
  sparse-keyframe sources.
- `--download-sections` + `--sponsorblock-remove` together apply two
  cut lists; the muxed span may be wrong.
- `_fmt_timecode` can emit a sub-second value (`0:01:25.5`) that some
  yt-dlp versions' section regex rejects → whole video downloaded.
- open-left bound `*-0:01:25` may be parsed as relative/negative by
  some yt-dlp versions (open-right `*0:00:51-` is the documented form).
- `core/transcriber.py` resume slice uses `-ss` before `-i` with no
  `-to`; keyframe snapping can drift the checkpoint seam.

### Class D — cross-session state
- **DEFER** `mark_interrupted()` flips **download** rows to
  `interrupted` too, but the crash-resume flow only reads / clears
  transcription rows. Killed-mid-download rows stay `interrupted`
  forever and skew `stats()` completion ratios. Fix: don't flip
  download rows (not resumable here) or count/clear them.
- **DEFER** `_pending_load_*` fields (and the `ModelLoadingDialog`) can
  dangle if the awaited worker dies via `worker_exit` / `startup_error`
  / watchdog restart instead of emitting `ready` — the interactive
  modal then hangs until the watchdog churns. Fix: in those branches,
  if `worker["id"] == _pending_load_worker_id`, signal the event and
  close the dialog with failure.
- **DEFER** one worker's `startup_error` calls `stop_all()` and clears
  `app.workers`, killing healthy parallel workers and orphaning a
  running task's reference. Fix: retire only the failing worker.
- **DEFER (minor)** `transcriptions_total` inflates by one per
  crash-resume re-run (new row each attempt). Orphaned resume
  checkpoints under `partials/` are never swept when a cancelled task's
  source is deleted (slow disk leak).

## 4. Landed in v1.0.4
Original four bugs + the two extra freeze sites (Class A). Everything
else above is queued with a clear fix direction; Class C is gated on a
real yt-dlp/ffprobe verification harness.

## 5. Recommended follow-ups (highest value first)
1. Build a small **real-subprocess E2E** harness: run yt-dlp on a short
   fixture and `ffprobe` the output (assert audio stream present;
   assert clip start within tolerance). This closes the Class C blind
   spot for good.
2. Fix `download_folder` persistence (Class B) — same one-liner-shaped
   fix as `model_path`.
3. Add **lifecycle / property tests** for config: save→load→save→load
   idempotency across every derived key.
4. Harden worker lifecycle (Class D: pending-load dangle, startup_error
   blast radius).
5. Keep a short **manual usage checklist** per release — the four
   original bugs were all found by using the app.
