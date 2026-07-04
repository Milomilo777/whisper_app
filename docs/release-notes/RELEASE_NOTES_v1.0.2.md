# Whisper Project v1.0.2

A reliability + UX release on top of v1.0.1. Two themes:

1. **Resume from cancellation, pause, or crash** — no more starting
   a 3-hour transcription over because you pressed Cancel at 47 %.
2. **Multi-day stability** — every silent C call that could trip
   the worker-liveness watchdog on slow hardware is now wrapped;
   every off-thread Tk call is queued; the per-folder config
   override leak is closed.

This release **skips the Setup-Compact installer.** Portable and
Setup-Standard between them cover every supported install
scenario; Compact added install surface without distinguishing UX.

---

## What's new

### Resume from where you left off

The transcribe loop now writes a checkpoint to
`%LOCALAPPDATA%\WhisperProject\partials\` every 10 segments or
20 seconds, whichever fires first. The checkpoint is invisible
to you during normal use — it's deleted automatically when
transcription finishes.

But if anything interrupts the run — you click **Cancel**, you
**Pause**, the app crashes, the machine reboots — the checkpoint
stays on disk. A new **Resume** entry appears in the queue
right-click menu for the cancelled row. Click it and the app:

1. Validates the checkpoint (same source file, same model, same
   transcription-affecting config).
2. Slices the audio from the last segment boundary onward via
   ffmpeg's fast seek.
3. Transcribes only the remaining audio.
4. Offsets the new segments back into the original timeline and
   merges them with the segments already on disk.
5. Runs diarisation / chapters / alignment / voiceprint on the
   full merged result.
6. Writes the final outputs as if a single run had produced them.

Limitations to know up front:

- **Faster-whisper only.** whisper.cpp and Parakeet deliver
  segments in a single batch return, so a slice-based resume
  doesn't map onto their API. With those backends the checkpoint
  is silently discarded and the run starts from scratch — clearly
  logged so you're not surprised.
- **Validation is strict by design.** If the source file's
  mtime / size changed, or you switched models or VAD settings,
  resume refuses (logs why, deletes the partial) and you get a
  fresh run. Better than silently producing a garbage transcript.

### Pause is now reachable from the UI

The engine already supported pause (the segment loop checks
`task.paused`), but the right-click menu didn't expose it on
running tasks. Now it does: **right-click a running row →
Pause**. Then **Resume** later when you're ready.

### The About dialog tells you what the app actually does

The previous About box was three lines of text. The new one is a
scrollable Toplevel listing every capability of the app grouped
into nine sections (Transcription engine, Output formats,
Post-processing, Video download, Transcript viewer, Workflow +
system integration, Search + statistics, Keyboard shortcuts,
Privacy). Many features ship enabled but live behind the
Advanced dialog — this is the canonical "what does this thing
do" reference.

---

## What's fixed

### Liveness watchdog no longer kills slow operations

On v1.0.1 the parent's worker-liveness watchdog killed
diarisation on any file long enough for sherpa-onnx to take more
than 30 seconds. The stability audit catalogued four more
identical patterns — stable-ts alignment, the Demucs CLI
subprocess, Parakeet's `decode_stream`, and whisper.cpp's
`transcribe`. Each is now wrapped in a small `liveness_tick`
context manager that emits a "still working…" log line every
10 s during the call. Bumped the timeout from 30 s to 120 s as
defence in depth. Net effect on slow hardware: no more
mysterious mid-run worker restarts.

### Per-folder config overrides no longer leak across files

`.whisperproject.json` overrides mutated the worker's module-level
config in place. A `diarization_enabled=True` set in folder A's
config silently turned on for every later file in folder B. Now
wrapped in a scope that snapshots and restores touched keys
around every file. Eight regression tests pin the new behaviour.

### `tk.after(0, …)` from background threads

On Python 3.14 this raises `RuntimeError`; on earlier 3.x it's
undefined and our `try/except: pass` blocks silently dropped the
callback. A new main-thread queue + drainer accepts off-thread
calls and runs them on the Tk main thread. Burn-subs results,
hardware-benchmark results, and tray-click handlers all flow
through it now.

### Demucs temp directory leak

`tempfile.mkdtemp(...)` in the separator was never cleaned up
on the success path, leaking 30–50 MB per separation under your
cache directory. Cleanup now lives in a `finally:`.

---

## Migration

No migration required. The checkpoint format is new for v1.0.2;
v1.0.1 users have no partials on disk and nothing to upgrade.
The hub folder and `config.json` are unchanged.

---

## Quality bar

| Metric | Result |
|---|---|
| pyright `app/ core/` | 0 errors, 0 warnings, 0 informations |
| Unit + integration suite | 551/551 passing |
| Real-file end-to-end (SMTV clip) | 10/10 |
| Smoke + end-to-end (Whisper model) | 7/7 |

---

## Deliverables

| Asset | Size | Best for |
|---|---|---|
| `WhisperProject-v1.0.2-Portable.exe` | ~447 MB | one file, no install |
| `WhisperProject-v1.0.2-Setup-Standard.exe` | ~349 MB | inspectable install — Python visible on disk |

Setup-Compact is intentionally skipped — between Portable and
Setup-Standard there is no audience Compact uniquely served.

Step-by-step install: [INSTALL.md](INSTALL.md).
