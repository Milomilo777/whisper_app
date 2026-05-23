# Architecture

Two packages, one entry point.

```
gui.py             Entry point — dispatches to App or worker mode.
app/               Tk UI. Depends on core. Owns dialogs, widgets, App.
  domain/          Pure-Python task models (TranscriptionTask, VideoDownloadTask).
  services/        Long-running side-effecting concerns (download_service).
core/              Headless logic. No Tk. Importable from the worker.
  integrations/    Per-site download integrations (smtv).
bin/               Bundled ffmpeg + ffprobe + yt-dlp.
```

## Two-process model

Whisper inference is CPU-bound (or GPU-bound) and would freeze the Tk event loop if it ran in the same process. We use a long-lived worker subprocess instead.

```
+------------------------+         JSON-on-stdin          +----------------------+
|   Tk app (gui.py)      | --------------------------->   |   worker subprocess  |
|   - one main thread    | <---------------------------   |   (gui.py --worker)  |
|   - poll() reads events|         JSON-on-stdout         |   - loads model once |
+------------------------+                                +----------------------+
```

The protocol lives in `core/worker.py`. The full event/command list is in the module docstring there.

Events the parent cares about:

- `ready` — worker loaded the model; safe to send `transcribe`.
- `startup_error` — model load failed; show the friendly error.
- `log`, `progress` — UI updates.
- `language_detected` — fills the Language column.
- `started`, `done` — task lifecycle.
- `error` — task failed; payload includes a friendly message + suggestion.
- `heartbeat` — emitted every 5 s by a daemon thread; lets the parent (future) declare a wedged worker.

## Lifecycle of one transcribe

1. **App startup** — health-check runs, hub-folder dialog fires if needed. Worker is NOT spawned yet.
2. **User drops a file** — task lands in `self.queue` and appears in the Treeview.
3. **User clicks Transcribe** —
   * If the model isn't on disk → `ModelDownloadDialog` runs `core.model_manager.ensure_model` (MD5-verified).
   * Worker is spawned with `WHISPER_WORKER_TOKEN` set in env.
   * `ModelLoadingDialog` blocks the UI until the worker emits `ready`.
   * App writes `{"action":"transcribe","file_path":"..."}` to the worker stdin.
4. **During transcribe** — worker emits one `progress` per Whisper segment. App's `_poll_worker_events` (running every 100 ms on the Tk main thread) updates the progress bar + queue row + console.
5. **On done** — App dispatches the next waiting task. Worker stays alive.
6. **On error** — App shows a `messagebox.showerror` with the friendly message + suggestion. Worker stays alive (the error was per-task).
7. **On cancel** — App marks the task cancelled + kills the worker. Next click re-spawns lazily.

## Files-out

The transcriber writes `.srt`, `.json`, `.txt` next to the source media via `core/writers/`. Every write is atomic: writer renders to a `.part` file in the destination directory, then `os.replace` swaps it onto the final name. A mid-write crash never produces a half-baked file.

## Defaults

Everything is baked into `core.config.DEFAULT_CONFIG`:

- Model: `faster-whisper-large-v3` (no other models, no other backends).
- Language: `auto` (per-file detection by Whisper).
- Output formats: `["srt", "json", "txt"]` (always all three).
- VAD: on (cuts silence cleanly).
- Device: `auto` (CUDA when present, otherwise CPU).
- Compute type: `int8` on CPU, `float16` on CUDA.

No UI exposes any of these. Editing `config.json` by hand still works — the file is at `<user_config_dir>/WhisperProjectBasic/config.json`.

## Self-diagnostics

`core/health_check.py` runs eight probes at startup AND on demand from Help → Diagnose:

1. Python version >= 3.11.
2. `faster_whisper` importable.
3. `ffmpeg` present (bundled or on PATH).
4. `ffprobe` works (smoke `-version`).
5. Disk writable at `<user_config_dir>`.
6. `config.json` parses + has required keys.
7. Hub folder configured (informational — first-run dialog will fire).
8. Model present on disk (informational — download will fire).

A failure surfaces a single `messagebox.showerror` at startup with `"Issue: <X>. Try: <Y>."`.

`core/error_messages.py` is a regex table mapping common Whisper / network / disk exceptions to user-actionable strings. The worker calls `friendly_error()` before emitting the `error` event so the user sees actionable prose, not raw tracebacks.

## Downloading videos

The single-screen UI also exposes an optional **Download Videos** section. Each non-blank line in the URL Text widget becomes one `VideoDownloadTask` in `app.download_queue`. `core.url_kind.url_kind` classifies each URL into one of three buckets:

- `smtv` → `core.integrations.smtv.download` streams the chosen file (mp3 by default) directly from the SMTV CDN in a daemon thread inside the parent process. The bundled transcript text (when present) is written next to the saved file.
- `yt-dlp` → `app.services.download_service.DownloadService` builds an argv for `bin/yt-dlp.exe` and spawns it as a subprocess. Stdout is parsed line-by-line for `[download] N.N%` progress and `Destination:` paths. Cancel runs `taskkill /F /T` on the PID so child ffmpeg processes go too.
- `unsupported` → the URL is skipped and the user is warned.

Both backends post events on the existing `worker_events` queue. The App's `_poll_worker_events` already drains it on the Tk main thread, so the download path doesn't introduce a second event loop. The Queue Treeview gained a `kind` column (`transcribe` / `download`) to keep both task types in the same widget.

Optional time-range slice: when **Start** / **End** are filled, yt-dlp gets `--download-sections "*start-end"`. SMTV has no server-side slicing — `core.integrations.smtv.warn_time_range_unsupported` logs one WARN line and the full file downloads. Both bounds are optional; either may be left open.

When **Auto-transcribe after download** is checked, a successful download enqueues its saved file into the transcribe queue and triggers the normal Transcribe path — which lazily downloads the Whisper model on the first run, exactly as a manual click would.

## Known maintainability debt

`app/app.py` is 840 lines — over the project's 500-line
per-module target documented in `CONTRIBUTING.md`. It orchestrates
the Tk root, the in-memory queue, the worker subprocess lifecycle,
and the event-loop pump in one class. Splitting it on the natural
seams — `app/app.py` (Tk root + UI build) plus
`app/controller.py` (queue + worker lifecycle + dispatch) — is
the right next refactor when the file next needs a non-trivial
change. It was kept whole on first ship to avoid surface area
without a concrete trigger.

Everything else in `app/` and `core/` is under 400 lines.
