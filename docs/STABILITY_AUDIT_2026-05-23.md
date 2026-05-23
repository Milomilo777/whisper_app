# Stability & long-uptime audit — 2026-05-23

Scope: read-only audit of `app/` and `core/` looking for failure
modes that only surface on multi-day uninterrupted runs on slow
commodity hardware (no GPU, old CPU, slow disk, busy filesystem).
Trigger was the v1.0.x diarisation-watchdog bug: a single C call
ran past `LIVENESS_TIMEOUT_S` (then 30 s, now 120 s) with no
progress events, so the parent killed the worker mid-pass on a
14-minute file.

The audit hunts for the same shape (silent long C call) plus the
nine adjacent reliability classes the prompt called out.

---

## Priority buckets

### P0 — fix before next release (definite long-uptime breakage)

- **P0-1** Alt-backends (`parakeet`, `whisper_cpp`) emit zero
  progress events while the C-level transcribe runs. Watchdog will
  kill any non-trivial file. Same root cause as the original diar
  bug.
- **P0-2** `stable-ts` word alignment (`core/alignment.py`) is a
  single `model.align(audio, result, ...)` call with no progress
  callback. On a slow CPU, a 14-min file takes minutes; watchdog
  fires. Re-runs the just-fixed diarisation pattern on a different
  code path.
- **P0-3** Demucs vocal-separation runs as a synchronous CLI
  subprocess for up to 600 s, with **zero events emitted to the
  worker stdout while it runs**. Watchdog kills mid-separation on
  any non-trivial file.
- **P0-4** Local LLM chapter titling (`core/llm.py` via
  `core/chapters.py:title_chapters_with_llm`) does N synchronous
  llama-cpp completions back-to-back, each 10–60 s on CPU. No
  events between chapters; watchdog kills 14-min file with 8+
  chapters.
- **P0-5** First-time `Llama(...)` model load inside
  `LLMRunner.load()` blocks for 10–30 s on slow CPU with no
  heartbeat from `_chat`. Combined with P0-4, the post-pipeline
  silence balloons.
- **P0-6** `transcriber._apply_runtime_overrides` mutates the
  module-level `config` dict in place. Per-folder `.whisperproject.json`
  overrides leak across files transcribed by the same worker.
  A user enabling diarisation in folder A leaks the toggle into
  every later file in folder B (which has no override).
- **P0-7** `app/app.py:435,445` (`_burn_subs_for` worker) and
  `app/widgets/hardware_wizard.py:260` (`_benchmark_worker`) call
  `self.after(0, …)` from a background daemon thread. Python 3.14
  raises `RuntimeError` (and prior 3.x is undefined). The current
  swallow-and-pass blocks make this a silent UI-stall bug, not a
  crash.

### P1 — fix soon (likely breakage on slow hardware)

- **P1-1** Cold model load (`WhisperModel(path, ...)` on a 3 GB
  large-v3 from a slow HDD) can exceed `LIVENESS_TIMEOUT_S = 120`.
  The watchdog seed at spawn covers this window only barely. On a
  busy filesystem with antivirus scanning the model files, this
  trips routinely.
- **P1-2** Console `tk.Text` widget grows unbounded. `app.log()`
  appends every line for the lifetime of the process. Multi-day
  session → MB of text, Tk redraw slows, eventual OOM.
- **P1-3** `history.db` never VACUUMs. WAL file grows monotonically;
  finished rows accumulate forever. No retention policy.
- **P1-4** `Recorder._frames: list[bytes]` is unbounded. A multi-
  hour mic / loopback session holds the entire audio in RAM until
  `stop()`. Overnight recording on a 4 GB box OOMs.
- **P1-5** `core/separator.py:126` `tempfile.mkdtemp(...)` is
  NEVER removed on the success path. Each Demucs run leaks a
  whole demucs output tree (~30–50 MB) under `user_cache_dir() /
  demucs/`. Over months, cache directory grows without bound.
- **P1-6** `yt-dlp` Popen in `_subtitle_phase` / `_media_phase`
  has NO subprocess timeout. A hung yt-dlp on a network blip
  blocks the download worker forever; user has to manually cancel.
- **P1-7** `transcription_service.poll()` re-arms `app.after(100, self.poll)`
  on every tick AND every `start_worker` separately arms one. Over
  many worker restarts the number of parallel `poll` chains can
  grow — wasted CPU, racy worker state mutation.
- **P1-8** Worker event queue (`Queue(maxsize=2000)`) consumers
  block on `put` when full. If the Tk main thread stalls (heavy
  GUI redraw, modal dialog) the worker reader thread blocks
  indefinitely. The watchdog can't see this because the worker
  itself is still alive — only the event flow is stuck.
- **P1-9** `core/backends/whisper_cpp.py:88`
  `urllib.request.urlopen(url)` has NO timeout. A hung TCP
  connection during model download wedges the download forever.

### P2 — worth doing eventually (edge cases / hardening)

- **P2-1** Tray controller (`app/widgets/tray.py:129,189`) calls
  `self.app.after(0, …)` from the pystray background thread.
  Wrapped in try/except so it doesn't crash on Python 3.14, but
  every tray menu click silently no-ops.
- **P2-2** `search._semantic_query` does `cur.fetchall()` over the
  whole embeddings table, then sorts in Python. On a multi-day
  workload with thousands of indexed transcripts, this is unbounded
  memory + CPU.
- **P2-3** `search.reindex_all_history` iterates up to 10 000
  transcripts and embeds each one in the calling thread with no
  cancellation hook + no progress events.
- **P2-4** `model_manager._download_zip` `r.iter_content(chunk_size=1MB)`
  has connect/read timeout `(10, 30)` but per-chunk reads can
  block longer; not a fatal but the download UI sees no progress
  during a slow chunk.
- **P2-5** `core/llm.py:144` `r.read(chunk_size)` inside the LLM
  download loop has no per-chunk timeout (only the initial 60 s
  on urlopen). A connection that stalls mid-stream wedges
  forever; no cancel from UI.
- **P2-6** `voiceprint._open_db` and `search._open_db` open the
  SQLite DB per call (returning) without WAL mode set. Concurrent
  open with `history.db` cousin paths could create lock contention.
  Lower urgency than history.db because both are rarely written.
- **P2-7** `_apply_runtime_overrides` adds keys to `config` dict
  but never removes overrides set by a prior `.whisperproject.json`.
  Even if P0-6 is fixed by a snapshot/restore pattern, audit the
  full set of keys touched.
- **P2-8** `core/backends/parakeet.py:_load_audio_as_float32` has
  NO timeout on the ffmpeg subprocess. Mirrors a hard-coded `timeout=600`
  in `core/diarization.py:_prepare_audio_16k_mono` but Parakeet
  was missed.
- **P2-9** `core/separator.py:_run_demucs_cli` uses Python's
  `["python", "-m", "demucs", ...]` rather than `[sys.executable, ...]`.
  In the frozen exe build, `python` on PATH is the system's
  ambient Python (or absent), not the one we ship — Demucs is
  effectively unusable from the bundled exe.
- **P2-10** 156 `# noqa: BLE001` sites; sampled, most log + re-
  raise OR log + fall back. ~20 in `app/app.py` swallow with
  bare `pass`. Sweep for ones that swallow without `logger.exception`.

---

## Detailed findings

### P0-1 — Parakeet & whisper.cpp backends silent during decode

**Where**: `core/backends/parakeet.py:191`, `core/backends/whisper_cpp.py:214`

```python
# parakeet
self._recognizer.decode_stream(stream)   # single C call, whole file

# whisper.cpp
segments = self._model.transcribe(audio_path, **kwargs)   # blocking
for idx, seg in enumerate(segments):     # already finished
    ...
    if progress_cb: progress_cb(pct)
```

**Symptom**: any file long enough that decode > 120 s gets killed
by `LIVENESS_TIMEOUT_S`. For Parakeet on weak CPU that's roughly
> 3 min audio; for whisper.cpp q5_0 on CPU that's > 5 min audio.

**Probability**: Likely. These backends explicitly exist because
the user has weak hardware.

**Suggested fix**: emit a synthetic `progress` (or even just
`log`) tick from a side thread while the C call runs, so the
worker's heartbeat is supplemented with a "still alive on file X"
beacon. Simplest:
```python
import threading
done = threading.Event()
def _tick():
    while not done.wait(10):
        if log_cb: log_cb(f"[backend] still decoding {audio_path}...")
threading.Thread(target=_tick, daemon=True).start()
try:
    self._recognizer.decode_stream(stream)
finally:
    done.set()
```
Same shape for `whisper.cpp`. Long-term: switch whisper.cpp to its
streaming generator API if it ships one, else keep the tick.

---

### P0-2 — stable-ts alignment is a single silent call

**Where**: `core/alignment.py:119`

```python
refined = model.align(audio_path, coarse_result,
                       language=language or coarse_result.language or "en")
```

**Symptom**: identical to the original diarisation bug. On a 14-min
file with the bundled `tiny` Whisper alignment model, this takes
2–10 min on CPU. No events during. Watchdog kills.

**Probability**: Likely — alignment is opt-in but enabled by users
who want better word timestamps.

**Suggested fix**: same side-thread tick as P0-1, scoped to the
align call. Bonus: stable-ts has a `verbose=True` flag that logs
to stdout — capture and pump through `log_cb`. Even better:
extract `_run_post_pipeline`'s diarisation `progress_cb` pattern
(maps 0..1 → 90..99 %) into a shared helper and apply to
alignment too.

---

### P0-3 — Demucs subprocess silent for up to 600 s

**Where**: `core/separator.py:196`

```python
kwargs["timeout"] = 600
subprocess.run(cmd, **kwargs)   # blocks; no event emission
```

**Symptom**: separator runs on a 14-min file → 2–8 min on CPU. No
events to worker stdout. Watchdog kills mid-separation. User loses
the partial demucs output AND the whole transcription.

**Probability**: Likely.

**Suggested fix**: replace `subprocess.run(...)` with `Popen + line-
streaming stdout`. Demucs's stdout already emits progress lines
("44%|████"); pipe them to `log_cb` so the worker emits one event
every few seconds.

---

### P0-4 — LLM chapter titling silent across N completions

**Where**: `core/chapters.py:146-164` + `core/llm.py:230-249`

```python
for boundary in boundaries:
    ...
    raw = runner.ask(text, "Write a 4-7 word headline...")  # 10-60s each
```

**Symptom**: 14-min file with 8 chapters, each 10–30 s LLM call
on CPU = 80–240 s of silence. Watchdog kills.

**Probability**: Likely once the user enables `ai_enabled`.

**Suggested fix**: after each `runner.ask` returns, the chapters
helper has no callback to ping the worker; pass a `tick_cb` into
`title_chapters_with_llm` and ping from chapters.py between
iterations. The `_run_post_pipeline` already has `progress_cb` —
plumb it down.

---

### P0-5 — Llama load blocks first call

**Where**: `core/llm.py:204-224`

```python
def load(self) -> None:
    ...
    self._llama = Llama(**kwargs)   # 5-30s
```

**Symptom**: first LLM call in a session (typically inside chapter
titling) eats 5–30 s before the first completion starts.

**Probability**: Possible. Compounds P0-4.

**Suggested fix**: load the model from a side thread BEFORE the
post-pipeline starts (e.g. at worker startup if `ai_enabled`).
Then emit `log` "AI model loaded" event — that itself ticks the
watchdog.

---

### P0-6 — Per-folder config overrides leak across files

**Where**: `core/transcriber.py:739-765`

```python
def _apply_runtime_overrides(task):
    runtime_cfg = load_config()
    project_overrides = load_project_overrides(task.file_path)
    for k, v in project_overrides.items():
        ...
        config[k] = v       # mutates module-level config in place
```

**Symptom**: worker transcribes folder A (`.whisperproject.json`
sets `diarization_enabled=true`), then folder B (no override).
Folder B gets diarisation too, silently. User-visible: random
files get speaker labels they shouldn't have.

**Probability**: Likely once user adopts per-folder overrides.

**Suggested fix**: snapshot the module-level config at worker
startup, restore after each `transcribe()` call.
```python
import copy
_BASE_CONFIG = None
def _apply_runtime_overrides(task):
    global _BASE_CONFIG
    if _BASE_CONFIG is None:
        _BASE_CONFIG = copy.deepcopy(config)
    config.clear()
    config.update(copy.deepcopy(_BASE_CONFIG))
    runtime_cfg = load_config()
    ... apply project_overrides to fresh config ...
```

---

### P0-7 — `after(0, ...)` from background threads (Tk RuntimeError)

**Where**:
- `app/app.py:435` — `_burn_subs_for` daemon thread
- `app/app.py:445` — same
- `app/widgets/hardware_wizard.py:260` — `_benchmark_worker`
- `app/widgets/tray.py:129,189` — tray loop (P2-1)

```python
def worker():
    try:
        burn_subs.burn(...)
        self.after(0, lambda: self._burn_subs_done(out_path))   # ← off main
```

**Symptom**: Python 3.14 raises `RuntimeError("calling Tcl from a
different thread")`. In `_burn_subs_for` the exception escapes the
daemon thread → logged + dropped. UI never updates with success/
failure, file appears to vanish.

**Probability**: Likely as Python 3.14 ships. Currently works only
because Tk's CPython binding is permissive.

**Suggested fix**: use the queue+drain pattern already implemented
for `_watched_path_queue`. New queue (e.g. `app._main_thread_calls`)
fed by `put_nowait`, drained by a `_drain_main_calls` after()
loop. All "bounce back to main" calls go through it.

---

### P1-1 — Cold model load races the watchdog

**Where**: `core/transcriber.py:187` (`WhisperModel(...)`),
`core/worker.py:93` calls `load_existing_model` BEFORE `emit("ready")`,
seed of `last_event_at` at parent spawn time = `time.time()`.

**Symptom**: on a 3 GB model from a slow HDD (or one fighting
antivirus), `WhisperModel(...)` takes 90–180 s. Heartbeat
hasn't started yet (it starts AFTER load, in worker.py:116).
Parent watchdog at 120 s sees `last_event_at` not updated past
the spawn seed → kills worker mid-load. Worker spawn loop
restarts → same thing.

**Probability**: Possible; reproduces only on slow disks.

**Suggested fix**: start the heartbeat thread BEFORE
`load_existing_model`, with a special `loading` event so the
parent grants extra slack during load. OR: emit a "loading model"
event every 5 s from a side thread until `emit("ready")`.

---

### P1-2 — Console `tk.Text` grows forever

**Where**: `app/app.py:1820`

```python
def log(self, msg: str) -> None:
    self._ui_logger.info(msg)
    if hasattr(self, "txt") and self.txt is not None:
        self.txt.insert("end", msg + "\n")
        self.txt.see("end")
```

**Symptom**: after several days of transcribing 100s of files,
the Text widget holds several MB of text. Tk redraw becomes
noticeably slow; memory keeps growing.

**Probability**: Likely on multi-day uptime.

**Suggested fix**: trim oldest lines when buffer exceeds, e.g.
10 000 lines:
```python
last = int(self.txt.index("end-1c").split(".")[0])
if last > 10_000:
    self.txt.delete("1.0", f"{last - 10_000}.0")
```

---

### P1-3 — history.db has no VACUUM or retention

**Where**: `core/history.py`

**Symptom**: `transcriptions` and `downloads` tables grow forever.
WAL file in particular bloats. After a year of daily use, history
queries (e.g. recent-files menu, statistics dialog) slow down;
the DB file alone reaches 100s of MB.

**Probability**: Possible on long-term install.

**Suggested fix**: add a `vacuum_if_needed()` method run at app
startup (after `mark_interrupted`):
```python
size = self.path.stat().st_size
if size > 50_000_000:
    self._conn.execute("VACUUM")
```
And add a config-driven retention `DELETE FROM transcriptions WHERE
finished_at < ?` for rows older than e.g. 365 days. The
`clear_recent` UI hook already expects a `delete_old_transcriptions`
method — implement it.

---

### P1-4 — `Recorder._frames` unbounded

**Where**: `core/recorder.py:147`

```python
_frames: list[bytes] = field(default_factory=list, repr=False)
```

**Symptom**: long mic / loopback recording sessions hold all
captured audio in RAM. 8 h at 16 kHz mono int16 = ~921 MB. On a
4 GB box, OOM.

**Probability**: Possible — only triggered by long unattended
recordings, but users do leave the recorder running.

**Suggested fix**: stream frames to disk directly into a
`wave.open(path, "wb")` while recording, instead of accumulating
in memory. `_finalize_wav` becomes a header-rewrite (frames
written, size, etc.).

---

### P1-5 — Demucs temp directory leaks

**Where**: `core/separator.py:126,139,145`

```python
out_dir = Path(tempfile.mkdtemp(prefix="demucs_", dir=str(cache_dir())))
...
found = _find_vocals_in(out_dir)        # finds vocals.wav inside out_dir
os.replace(str(found), str(cached))      # moves the one file out
# out_dir is left on disk, with the htdemucs/<stem>/ subtree intact
```

**Symptom**: each Demucs run leaves a `demucs_xxxx/` directory in
the cache. Cleanup never happens.

**Probability**: Likely if user runs Demucs regularly.

**Suggested fix**: `shutil.rmtree(out_dir, ignore_errors=True)`
in a `finally:` block after the `os.replace`. Cache itself
keeps the moved `vocals.wav`.

---

### P1-6 — yt-dlp subprocess has no timeout

**Where**: `app/services/download_service.py:638,700`

```python
task.process = subprocess.Popen(self.build_subtitle_command(task, sub_lang), ...)
for line in task.process.stdout:
    ...
sub_rc = task.process.wait()    # blocks forever if yt-dlp hangs
```

**Symptom**: yt-dlp hangs on a stalled connection (we've seen
this on SMTV CDN, on YouTube during region blocks, on networks
behind captive portals). The download thread blocks forever.
User can cancel — but if they're away from the keyboard, the
whole download queue is frozen.

**Probability**: Likely on flaky networks over multi-day uptime.

**Suggested fix**: use Popen + a stall-detector based on time
since last stdout line. If > 5 min with no output, kill the
process and surface as a "stall" error.

---

### P1-7 — Multiple `poll()` chains can stack up

**Where**: `app/services/transcription_service.py:143,347`

```python
# in start_worker:
app.after(100, self.poll)
# in poll itself, when active_workers() truthy:
app.after(100, self.poll)
```

**Symptom**: after N worker restarts (which trigger N `start_worker`
calls), N parallel poll chains can exist. Each fires every 100 ms,
all on the same Tk thread. Compounds CPU + adds racy state
mutation (e.g. two ticks both call `finish_task` for the same
event before the queue is drained).

**Probability**: Possible on a long-running session with many
worker restarts (which is the whole point of the watchdog —
restarts happen).

**Suggested fix**: guard poll-arming with a single sentinel
`self._poll_armed: bool`; only arm if not already armed. Clear
at the top of `poll()`.

---

### P1-8 — `worker_events.put` blocks when queue fills

**Where**: `app/services/transcription_service.py:133`,
`app/services/format_service.py:93`,
`app/services/download_service.py` (39 occurrences)

```python
app.worker_events.put(event)    # blocking; Queue(maxsize=2000)
```

**Symptom**: if Tk main thread stalls (heavy GUI redraw, modal
dialog, long synchronous Python loop in user-facing code), the
worker's stdout-reader thread blocks on `put`. The worker keeps
emitting events into a full pipe → eventually the worker's
`print(line, flush=True)` blocks on OS buffer pressure → worker
stops doing useful work. Watchdog won't fire because the worker
is still "alive". Whole pipeline deadlocks.

**Probability**: Possible on multi-day uptime where any modal
dialog accidentally left open by the user matters.

**Suggested fix**: use `put_nowait` everywhere and on `queue.Full`
log a single warning + drop the oldest event:
```python
try:
    app.worker_events.put_nowait(event)
except queue.Full:
    try: app.worker_events.get_nowait()
    except queue.Empty: pass
    try: app.worker_events.put_nowait(event)
    except queue.Full: pass
    logger.warning("worker_events full; dropped oldest event")
```

---

### P1-9 — whisper.cpp model download has no timeout

**Where**: `core/backends/whisper_cpp.py:88`

```python
with urllib.request.urlopen(url) as resp:  # noqa: S310 — known URL
```

**Symptom**: a hung TCP connection during the 1 GB download
wedges forever (no per-read timeout, no urlopen timeout).

**Probability**: Possible on flaky networks.

**Suggested fix**: add `timeout=60` to `urlopen`, and wrap the
`resp.read()` loop in a per-chunk stall check (kill after 60 s
of no bytes).

---

### P2-1 — Tray after-0 silently no-ops on Py3.14

**Where**: `app/widgets/tray.py:129,189`

```python
def _post(self, fn):
    try:
        self.app.after(0, fn)
    except Exception:  # noqa: BLE001
        pass
```

**Symptom**: on Python 3.14 the `after` raises RuntimeError;
caught and dropped. Every tray menu click does nothing.

**Probability**: Edge case for now; Likely once 3.14 ships and
users upgrade.

**Suggested fix**: same queue pattern as P0-7.

---

### P2-2 — `_semantic_query` loads whole embeddings table

**Where**: `core/search.py:301-306`

```python
cur = conn.execute("SELECT e.json_path, e.segment_index, e.vector, ... FROM embeddings e ...")
for r in cur.fetchall():    # whole table into memory
```

**Symptom**: 10 000 transcripts * 200 segments avg * 384-dim float32
= ~3 GB. Search becomes unusable.

**Probability**: Edge case; only long-term users with semantic
search enabled.

**Suggested fix**: precompute query embedding, then run cosine
via `numpy.dot` on a `numpy.memmap`'d vector table, or sample
top-N via ANN. Short-term: paginate the cursor + early-exit when
score < threshold.

---

### P2-3 — `reindex_all_history` blocks

**Where**: `core/search.py:210-233`

No progress callback, no cancel, no chunking. UI calling this
freezes for the duration.

**Suggested fix**: add `progress_cb` + `cancel_event` parameters;
have the dialog drive both.

---

### P2-4 — model_manager chunk reads have no per-chunk timeout

**Where**: `core/model_manager.py:175-198`

`requests.get(timeout=(10, 30))` covers connect + initial read,
but `for chunk in r.iter_content(chunk_size=1MB)` does NOT inherit
the read timeout per chunk. A slow connection that delivers 100 B/s
will hang individual chunks for minutes.

**Suggested fix**: track time since last chunk; if > 60 s, raise.

---

### P2-5 — LLM download per-chunk timeout missing

**Where**: `core/llm.py:144`

```python
chunk = r.read(chunk_size)   # can block indefinitely
```

**Suggested fix**: per-chunk stall detector (same as P1-9).

---

### P2-6 — voiceprint / search DBs no WAL

**Where**: `core/voiceprint.py:90`, `core/search.py:109`

```python
conn = sqlite3.connect(str(p), check_same_thread=False)
# no PRAGMA journal_mode=WAL set
```

**Symptom**: concurrent reads block on writes (rare given write
patterns, but possible).

**Suggested fix**: set `PRAGMA journal_mode=WAL` after each open,
mirroring `history.py`.

---

### P2-7 — `_apply_runtime_overrides` audit

See P0-6. After fixing via snapshot/restore, sweep every key
that's ever set into `config` via per-folder JSON and verify
restore covers them all (not just diarisation + alignment).

---

### P2-8 — Parakeet audio decode has no ffmpeg timeout

**Where**: `core/backends/parakeet.py:235`

```python
proc = subprocess.run(cmd, **kwargs)   # no timeout=
```

**Suggested fix**: copy the `timeout=600` from
`core/diarization.py:_prepare_audio_16k_mono`.

---

### P2-9 — Demucs invocation uses ambient `python`

**Where**: `core/separator.py:180-185`

```python
cmd = ["python", "-m", "demucs", ...]
```

In the frozen exe build, `python` on PATH is the user's system
Python (or absent). Demucs is effectively broken from the
installed exe.

**Suggested fix**: use `sys.executable` when not frozen; when
frozen, either re-exec the worker with a `--demucs` flag or run
Demucs in-process via its Python API.

---

### P2-10 — Wide `except Exception: pass` audit

156 `# noqa: BLE001` sites across 33 files. Sampled: most log via
`logger.exception` then fall back. ~20 in `app/app.py` (and 13 in
`app/widgets/tray.py` etc.) do `pass` without logging — these are
the dangerous ones. Sweep with grep for `except Exception:.{,80}pass`
and verify each is intentional.

---

## Lowest-hanging fruit — what to do tonight

A focused 2-hour pass that knocks out 4 of the 7 P0s:

1. **P0-1 + P0-2 + P0-3**: add a tiny `core/_liveness_tick.py`
   helper — a `with liveness_tick(log_cb, label, interval=10):`
   context manager that spawns a daemon thread emitting a `log`
   line every 10 s until exit. Wrap the four offending C calls
   (`decode_stream`, `model.transcribe`, `model.align`,
   `subprocess.run(demucs)`) in it. One file added, four 3-line
   call-site changes, no behaviour change on the happy path,
   complete watchdog coverage on slow CPU.

2. **P0-6**: snapshot/restore `config` around `_apply_runtime_overrides`.
   ~10 lines of code, fixes a real correctness bug, no API change.

3. **P0-7**: introduce `app._main_thread_calls = queue.Queue()` +
   `_drain_main_calls()` after-loop, then mechanically replace the
   four off-thread `after(0, ...)` sites with `_main_thread_calls.put_nowait(fn)`.
   Removes a Python 3.14 RuntimeError that will start firing for
   real users in a few months.

4. **P1-5**: one `shutil.rmtree(out_dir, ignore_errors=True)` in
   the separator cleanup. Two lines.

Skip P0-4 / P0-5 (LLM titling) tonight — needs a slightly larger
plumbing change to thread `progress_cb` into chapters.py — but
flag them in the next-session handoff so they don't get lost.

After tonight's pass, the next-session list is:

- P1-1 heartbeat-before-load (small but worker-side).
- P1-2 console trim.
- P1-3 history VACUUM + retention.
- P1-6 yt-dlp stall detector.
- P1-8 queue.put_nowait everywhere (mechanical but touches many call sites).

Everything in P2 can wait for a quiet sprint.
