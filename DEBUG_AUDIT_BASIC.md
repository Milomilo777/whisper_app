# DEBUG_AUDIT_BASIC — hostile review of the basic edition

## Executive summary

The basic edition is small and most of the "obvious" attack-surface items
(atomic config writes, MD5 path-traversal guard, friendly-error mapper,
worker stdout discipline) are handled. The serious bugs are concentrated
in three areas: (1) the worker stdin-reading loop has unbounded-line and
length-after-strip semantics that defeat its own `MAX_COMMAND_BYTES`
guard; (2) the parent never reaps `startup_error` correctly (the
loading dialog gets cancelled, but the dialog had no `success` field
yet — and worse, `startup_error` is racy with `ready`); (3) several
filesystem operations (resume-download HEAD, manifest-vs-disk drift,
extraction over symlinks inside the zip) trust their inputs more than a
hostile CDN deserves. 30 findings follow.

---

## P0 — real defects, ship-blockers

### P0-1. `worker.py` MAX_COMMAND_BYTES guard is bypassed by stdin buffering

**Where** — `core/worker.py:120-132`

```python
for line in sys.stdin:
    if len(line) > MAX_COMMAND_BYTES:
        emit("error", message=(...))
        continue
    line = line.strip()
```

**Attack** — Parent (or a malicious process attached to the worker's
stdin) sends a 500 MB line with no `\n`. Python's `for line in sys.stdin`
buffers the entire line in memory before yielding it; the length-check
fires *after* the OOM has already happened. The guard is decorative.

**Symptom** — Worker process RSS climbs without bound; OOM-kill on a
constrained host. The "1 MB cap" promised in the docstring is not
enforced.

**Likelihood** — Edge (the parent we ship sends only short JSON), but a
hostile fuzzer or any other parent (the basic edition documents the
JSON-stdio protocol as an extension point) trips it immediately.

**Fix** — Read with a hard cap:
`raw = sys.stdin.buffer.readline(MAX_COMMAND_BYTES + 1)`; if
`len(raw) > MAX_COMMAND_BYTES and not raw.endswith(b"\n")`, drain the
rest of the line until newline, emit error, continue. Decode under
`utf-8 errors="replace"` after the size check.

---

### P0-2. `transcriber.transcribe` deadlocks if the model never loads

**Where** — `core/transcriber.py:263-266`

```python
while not MODEL_READY:
    if MODEL_ERROR:
        raise RuntimeError(MODEL_ERROR)
    time.sleep(0.5)
```

**Attack** — The worker's `main()` calls `load_existing_model` and only
calls `transcribe` after `ready` is emitted; that path is safe. BUT
`load_existing_model` sets `MODEL_ERROR` only when `WhisperModel(...)`
raises, not when it hangs (e.g. CUDA driver wedge, network FS stall on
the model files). If the load thread hangs forever, the worker's
heartbeat thread never starts (the heartbeat is launched *after*
`emit("ready")`), and the parent never sees `startup_error` nor
`heartbeat` — it just waits.

**Symptom** — Modal "Loading Whisper model…" dialog spins forever, the
user has only `Cancel` (which kills the worker), no diagnostic surfaced.

**Likelihood** — Possible (CUDA driver issues, NTFS-on-WSL model paths).

**Fix** — Start the heartbeat thread *before* `load_existing_model`
returns. Or wrap the load with a watchdog that emits `startup_error`
after N seconds.

---

### P0-3. Worker `for line in sys.stdin` silently exits on EOF, parent shows "Worker exited unexpectedly"

**Where** — `core/worker.py:120` and `app/app.py:599-606`

If the parent closes the worker's stdin (e.g. parent crashes, or the
shutdown path's stdin.write fails partway), the `for line in sys.stdin`
loop just falls through and the worker returns 0. The parent's
`worker_exit` handler classifies `rc=0` indistinguishably from a clean
shutdown:

```python
self._on_task_error(t, f"Worker exited unexpectedly (rc={rc}).")
```

That's correct only when a task was running; when no task was running,
the `rc=0` is silently swallowed. A worker that died after `ready` but
before any `transcribe` command (e.g. parent stdin closed by an antivirus
hook on Windows) leaves the App with `self.worker = None` and the next
Transcribe click respawns — *but the user's previous Add doesn't get
re-dispatched* because `_dispatch_next` is only called from
`_on_transcribe_click`, `_on_task_done`, `_on_worker_error`. Stale
queue rows sit at `waiting` indefinitely.

**Symptom** — UI looks healthy; tasks never run; no error.

**Likelihood** — Possible (CREATE_NO_WINDOW + Windows AV hooks
occasionally close child stdin).

**Fix** — Have the worker emit `error` (with a message like "stdin
closed without shutdown command") before returning. Have the parent's
`worker_exit` handler dispatch the next waiting task or surface a
visible warning.

---

### P0-4. `model_manager._download_zip` mis-handles non-Range server reply

**Where** — `core/model_manager.py:146-150`

```python
if existing and r.status_code != 206:
    existing = 0
    downloaded = 0
    mode = "wb"
```

**Attack** — A partial download exists on disk. The user retries. The
CDN returns 200 (full body, ignoring the Range header). The code resets
`existing` and `downloaded` and resets `mode` — but the file is *already
open* via `with open(zip_path, mode)` on line 154, which used the
*pre-reset* mode (`"ab"`). Result: the new full body is *appended* to
the existing partial. The file size is now (existing + content_length),
the MD5 fails, the next loop iteration restarts from zero. So it
eventually recovers, but it wastes one full re-download of a ~3 GB
archive — and worse, on a machine that's tight on disk, the intermediate
2× artefact may fill the drive.

**Symptom** — Doubled disk usage during recovery; spurious "MD5
mismatch" warning that wastes the user's time.

**Likelihood** — Likely on CDN edges that don't honour Range
(CloudFront occasionally, plain nginx without `--enable-range`).

**Fix** — Move the open() inside the response handling so the mode is
re-evaluated after the 200-vs-206 branch. Or `f.truncate(0); f.seek(0)`
when re-falling-back to wb.

---

### P0-5. `_dispatch_next` does not re-dispatch after a model-download dialog success

**Where** — `app/app.py:388-413`

```python
def _on_transcribe_click(self) -> None:
    ...
    if self.worker is None or not self._worker_alive():
        ok = self._spawn_worker_blocking()
        if not ok:
            return
    self._dispatch_next()
```

The model-download path correctly refreshes `config_dict`, and the
worker spawn opens `ModelLoadingDialog` which waits. But while
`wait_window` is blocking the Tk main thread, the `_poll_worker_events`
`after()` loop is *not* running (Tk's `wait_window` does process events,
so this is actually OK — but only because of an implementation detail of
Tk). HOWEVER: if the user clicks Transcribe a second time *while*
`_spawn_worker_blocking` is still inside `wait_window`, the button's
command runs (it isn't disabled), `is_model_on_disk` returns True (we
just downloaded), `_worker_alive` returns True (the just-spawned worker
is alive), and `_dispatch_next` is called on the *first* click's
dispatch path too — both will race to set `self.worker["task"]`.

Actually `_dispatch_next` itself guards `self.worker.get("task") is not
None` — but two near-simultaneous calls can both pass that check before
either has assigned. The send is fast (`proc.stdin.write` ~ microsecond),
so the practical window is tiny, but the worker would then receive two
`transcribe` commands back-to-back and process them serially while the
parent's `self.worker["task"]` only tracks the *second*. The first task
runs in the worker but the parent attributes progress/done/error events
to the wrong row.

**Symptom** — Two queued files mis-attributed in the UI; "done" event
for file A marks file B as done; file A's status sits at "running"
forever.

**Likelihood** — Possible (double-click on the Transcribe button is the
classic trigger).

**Fix** — Disable the Transcribe button while a worker spawn / dispatch
is in progress; re-enable on done/error/exit. Or queue dispatches and
serialise on the Tk main thread.

---

### P0-6. Worker stdout race: heartbeat thread vs main thread interleaves JSON lines

**Where** — `core/worker.py:56-99`

`emit` calls `print(line, flush=True)`. `print` on CPython is *not*
atomic for multi-thread writers when the line is large enough to cross
the stdio buffer boundary. The heartbeat thread and the main thread
both call `emit`; if a `log` event (which can contain a long whisper
segment text) is being written while the heartbeat fires, the parent's
`for line in process.stdout` may see two events split across lines (or
an interleaved garbled line). The parent's reader logs the garbled
line as `{"event": "log", "message": <garbled>}` — never crashes, but
the heartbeat is lost.

**Symptom** — Garbled log entries in the UI's console panel; missed
heartbeats. If a future watchdog uses missed heartbeats as "wedged"
evidence, this would cause false-positive kills.

**Likelihood** — Possible (CPython's `print` uses
`sys.stdout.write` which holds the per-stream RLock, so single
`print` calls *are* atomic — BUT `print(line, flush=True)` decomposes
into write + flush, and flush can yield. Empirically, multi-KB lines
under load do interleave on Windows.).

**Fix** — Wrap `emit` in a `threading.Lock` shared by the heartbeat
thread and the main thread.

---

### P0-7. `_apply_runtime_fallbacks` masks an empty `model.name` with a wrong path

**Where** — `core/config.py:105-136`

```python
model_name = (config.get("model") or {}).get("name") or ""
...
if needs_recompute and model_name:
    ...
    config["model_path"] = str(fallback)
return config
```

If `config["model"]["name"]` is empty (user deleted the key or the
`_merge_with_defaults` coerced it to `""` because they hand-edited to
`42`), `model_path` is left at the empty string. `is_model_on_disk`
correctly returns False so the download dialog fires — but
`ensure_model` then dereferences `config["model"]["url"]` which is
also missing/blank, and the request goes to `""` and raises
`MissingSchema`. The user sees a raw exception (the friendly_error
table has no rule for `requests.exceptions.MissingSchema`).

**Symptom** — Confusing low-level traceback dialog after a successful
"Preparing model" click.

**Likelihood** — Edge (only triggered by a corrupt config), but the
config recovery path in `load_config` already aspires to make hand-edits
safe — this defeats that promise.

**Fix** — If `model.url` or `model.name` is empty, reset the entire
`model` dict to the default before returning from `load_config`.

---

## P1 — definite weaknesses, fix soon

### P1-1. `_verify_extracted_files` resolves the path through user-controlled symlinks

**Where** — `core/model_manager.py:211-217`

```python
file_path = (cache_dir / relative_path).resolve()
try:
    file_path.relative_to(cache_root)
except ValueError:
    raise RuntimeError(f"Unsafe MD5 manifest path: {relative_path}")
```

The traversal check is correct against `../../etc/passwd` style paths.
BUT if the cache_dir *itself* contains a symlink (planted by a previous
extraction, or by a malicious zip), `resolve()` will follow it and the
verified file may live outside the user's intended cache. A malicious
zip that, on extract, plants `models--Systran--faster-whisper-large-v3/
sneaky -> /C/Users/Owner/.ssh/`, then a manifest entry
`models--Systran--faster-whisper-large-v3/sneaky/id_rsa` would let the
verifier *read* and MD5 a file outside the cache. Not a write, but it
breaks the "self-contained cache" promise.

**Symptom** — Information disclosure via timing (MD5 mismatch implies
the file exists; missing implies it doesn't).

**Likelihood** — Edge (requires a compromised CDN serving a malicious
zip — and at that point the attacker can do worse).

**Fix** — Reject zips whose entries contain absolute paths or `..`
segments at extract time (`zipfile.ZipFile.extractall` does NOT do
this); also refuse to follow symlinks during verification:
`if file_path.is_symlink(): raise RuntimeError(...)`.

---

### P1-2. `zipfile.ZipFile.extractall` happily writes outside cache_dir

**Where** — `core/model_manager.py:317-318`

```python
with zipfile.ZipFile(zip_path, "r") as z:
    z.extractall(cache_dir)
```

Python's `extractall` does basic name sanitisation (strips drive
letters, leading slashes) since Python 3.12+, but a malicious zip with
`../../../Windows/System32/foo.dll` entry is still extracted to the
parent's parent's parent on 3.11. Per pyproject the project targets
3.11+ so 3.11 *is* in scope.

**Symptom** — Arbitrary file write under the CDN's control. Since the
URL is hardcoded to `smch.ir`, the practical risk depends on that
domain's compromise resistance.

**Likelihood** — Edge.

**Fix** — Validate each `ZipInfo.filename` before calling extractall:
reject entries whose `os.path.normpath(name)` starts with `..` or
contains `..` segments, or whose resolved path doesn't sit under
`cache_dir`.

---

### P1-3. `_download_zip` doesn't validate Content-Type or detect HTML error pages served as 200

**Where** — `core/model_manager.py:144-183`

A CDN can return a 200 with an HTML error page (`<!DOCTYPE html>...`)
instead of the zip when its origin is wedged. The code writes that
HTML to disk; `zipfile.ZipFile(zip_path)` then raises `BadZipFile` and
the loop restarts the download — eventually it might recover or might
loop forever on a permanently-broken origin.

**Symptom** — Wasted bandwidth; user sees "Restarting download from
zero" repeatedly with no clear root cause.

**Likelihood** — Possible on CDN edge issues.

**Fix** — Check `r.headers["content-type"]` for
`application/zip`/`application/octet-stream`; OR validate the first 4
bytes of the response are the ZIP magic (`PK\x03\x04`). On mismatch,
fail with a clear "server returned non-zip content" error.

---

### P1-4. `ensure_model` infinite loop on persistent MD5 mismatch

**Where** — `core/model_manager.py:296-345`

```python
while True:
    ...
    if not mismatches:
        ...
        break
    ...
    _remove_path(zip_path)
    _remove_path(model_path)
```

A permanently-broken MD5 manifest (or a CDN that consistently corrupts
one file) puts this in an infinite redownload loop, eating bandwidth and
disk. The cancel event is checked at the top of the loop, but a user
who's stepped away will return to gigabytes of failed downloads.

**Symptom** — Bandwidth abuse, possible ISP cap hit.

**Likelihood** — Possible (manifest mistakes happen).

**Fix** — Cap to 3 attempts, then raise a `RuntimeError` with the list
of mismatched filenames.

---

### P1-5. Worker `for line in sys.stdin` uses default encoding

**Where** — `core/worker.py:120`

Python's `sys.stdin` on Windows under `pythonw.exe` defaults to the
console code page (cp1252 / cp65001 depending on locale). The parent
opens the subprocess with `text=True, encoding="utf-8"` so it *writes*
UTF-8, but the worker's `sys.stdin` may decode that as cp1252 because
the worker process doesn't force UTF-8. A file path with a non-ASCII
character (Persian, Chinese, Cyrillic) is then mangled before
`json.loads`. The parent's friendly_error table doesn't cover the
resulting `FileNotFoundError`.

**Symptom** — Silent file-not-found on non-ASCII paths.

**Likelihood** — Likely on non-English Windows installs (this is the
collaborator's documented use case — see the Chinese/Vietnamese entries
in `LANGUAGE_CHOICES`).

**Fix** — Worker should do
`sys.stdin.reconfigure(encoding="utf-8", errors="replace")` at entry.
Or use `sys.stdin.buffer` directly and decode each line as UTF-8.

---

### P1-6. The `for line in sys.stdin` size check uses post-strip length, but the strip happens after

**Where** — `core/worker.py:121-130`

The order is `len(line) > MAX_COMMAND_BYTES` → `continue`, then
`line = line.strip()`. That's correct. But the size check runs against
the raw line (including `\r\n`), so the limit is effectively
MAX_COMMAND_BYTES - 2. Not a real defect on its own; pair with P0-1.

**Likelihood** — Edge.

---

### P1-7. `Queue(maxsize=2000)` silently drops on overflow with a 5-second wait

**Where** — `app/app.py:474-476`

```python
self.worker_events.put(event, timeout=5.0)
```

If the Tk poll loop is starved (e.g. the user dragged the window or a
modal dialog is in front), 5 seconds elapses, `Full` is raised, the
event is logged as "dropped event %r" and discarded. The dropped event
might be a `done` / `error` / `worker_exit` — in which case the parent
permanently believes the task is still running.

**Symptom** — Task stuck at "running 99%" forever; user can't tell
whether the file actually got written.

**Likelihood** — Edge but cumulatively certain across a long session.

**Fix** — Lifecycle events (`done`, `error`, `worker_exit`,
`startup_error`, `ready`) should never be dropped — put them with
`block=True` (no timeout) on a dedicated lane. Only progress/log events
should be droppable.

---

### P1-8. `_append_console` keeps a growing Tk Text widget

**Where** — `app/app.py:677-686`

Trims to 4000 lines after each insert, but `int(self.console.index(...))`
is called on every log line — quadratic-ish for a noisy long session.
Worse, `Text.insert` of millions of lines triggers Tk re-layout on every
insert. After a 12-hour transcribe session the console panel becomes
laggy even after the trim.

**Symptom** — UI sluggishness late in long sessions.

**Likelihood** — Possible (long sessions are the documented use case).

**Fix** — Batch inserts, or use a fixed-size ring buffer rendered as a
read-only Text widget.

---

### P1-9. `_on_files_added` saves config on EVERY file added (no debounce)

**Where** — `app/app.py:349-355`

Drag in 100 files → 100 `save_config` calls → 100 tmpfile-rename
cycles → 100 fsync calls. On a slow disk (SD card, network share) this
takes seconds and blocks the Tk main thread.

**Symptom** — UI freeze on bulk drop.

**Likelihood** — Possible.

**Fix** — Save once after the loop, not per file.

---

### P1-10. `add_recent_file` is not bounded against malformed config values

**Where** — `core/config.py:227-243`

`recent = list(config.get("recent_files") or [])` — fine. But
`recent_files` ships at `limit=5`. If a user hand-edits the saved
config to contain 10,000 entries, the loop only filters case-insensitively
and slices to 5. Filtering 10,000 strings is fast — no real defect — but
the load_config defaults merge does NOT bound the length of
`recent_files` on read, so a malicious config.json (or one corrupted by
power loss mid-write into another structure) can keep an unbounded list
in memory.

**Symptom** — Trivial DoS via APPDATA tampering. Cosmetic only.

**Likelihood** — Edge.

**Fix** — Slice in `_merge_with_defaults`: `recent_files` capped at 50.

---

### P1-11. `bundled_binary` fallback returns the bare name, callers re-test with `isfile`

**Where** — `core/paths.py:33-41` and `core/health_check.py:42-56`

`bundled_binary("ffmpeg")` returns `"ffmpeg"` (just the name) when not
found in bin/. Then health_check does
`if not os.path.isfile(path):` — but `os.path.isfile("ffmpeg")` is False
unless the cwd happens to contain it. The fallback then does
`shutil.which(path)` correctly. But `transcriber.get_duration` calls
`subprocess.run([ffprobe, "-version", ...])` with the bare name and
relies on the OS PATH lookup. That works, but the error message on
failure is "FileNotFoundError: [WinError 2] The system cannot find the
file specified: 'ffprobe'", which is opaque. The friendly_error rule
matches against the exception text, and the regex
`FileNotFoundError.*ffprobe` matches — OK. But if PATH lookup succeeds
on a *different* ffprobe (e.g. a Chocolatey-installed one with a
different version), the bundle is bypassed silently and the version
skew can produce wrong durations on exotic containers.

**Symptom** — Wrong duration → wrong progress % → premature "100%".

**Likelihood** — Edge.

**Fix** — Log the resolved ffprobe path at startup; if a system ffprobe
is preferred over a missing bundled one, log a clear warning.

---

### P1-12. `crash.py` re-raises `previous(...)` only on hook construction failure, not on later mainloop swallows

**Where** — `app/dialogs/crash.py:175-178`

Tk's mainloop catches exceptions inside `command=` callbacks and prints
to stderr without invoking `sys.excepthook`. So if a `command=` raises,
the CrashDialog never appears even though the hook is installed. The
docstring describes the hook as the catch-all for crashes, which it
isn't for Tk callback errors.

**Symptom** — User-visible "Whisper Project — basic crashed" dialog
never appears for crashes inside button handlers. Just a silent error
dumped to (often-invisible) stderr.

**Likelihood** — Likely (most app crashes happen inside Tk callbacks).

**Fix** — Install `tk.Tk.report_callback_exception = _hook` after the
root is built; the existing `install_excepthook` then handles both
synchronous + Tk-callback paths.

---

### P1-13. `_stop_worker` shutdown via stdin can hang the daemon thread forever

**Where** — `app/app.py:755-764`

`_async_shutdown` writes to a possibly-broken pipe in a daemon thread.
The thread is daemon, so process exit doesn't block on it; but if the
write blocks (full pipe, hung child), the thread sits forever. Not
fatal — but if the user is rapidly opening/closing the worker
(cancel/transcribe in a loop), threads accumulate. There's no cap.

**Symptom** — Slow leak of daemon threads. Cosmetic at typical scale.

**Likelihood** — Edge.

**Fix** — Use `proc.stdin.close()` instead of writing a shutdown JSON
when the worker is reachable; EOF on stdin already triggers the worker's
`for line in sys.stdin` to exit.

---

### P1-14. `_write_outputs` rollback deletes prior outputs even on permission failure

**Where** — `core/transcriber.py:234-245`

If `srt` writes fine, then `json` fails with PermissionError (e.g. the
user has the .json file open in an editor), the except block deletes
the .srt that was just written *for the same task*. The user loses a
successful output because of a separate format's permission issue.

**Symptom** — Silent data loss of one format because another format
couldn't be written.

**Likelihood** — Possible (text editors lock .json files).

**Fix** — Don't roll back successfully-written outputs; just report the
formats that failed alongside the ones that succeeded.

---

### P1-15. `_write_outputs` `.part` filename uses pid+tid but two workers in the same dir collide

**Where** — `core/transcriber.py:228`

```python
part_path = f"{path}.{os.getpid()}-{threading.get_ident()}.part"
```

Within one worker process this is unique enough, but if a user transcribes
the same file from two workers (e.g. they launched the source-tree dev
version AND the installed Setup-Standard version with the same source
file selected), both produce `.part` files. The os.replace is atomic but
the *content* of the surviving file depends on race ordering and offers
no guarantee about which transcription "won".

**Symptom** — Mixed-content output file.

**Likelihood** — Edge.

**Fix** — Add a uuid4 hex to the part name; or take an OS-level file
lock on the target path.

---

### P1-16. `language_cb` is wrapped in `try/except` that swallows but `_segment_to_dict` is not

**Where** — `core/transcriber.py:288-294`

`language_cb` errors are caught (good). But the segment iteration on
line 298 can raise `RuntimeError("CUDA out of memory")` mid-stream and
the partially-collected `segments_data` is discarded; no salvage of the
work done so far. Worse, the worker emits an `error` event with the raw
exception — there's no "partial output" fallback even though SRT is
streamable and a 90%-done file is more useful than nothing.

**Symptom** — On a CUDA-OOM at 95% of a 4-hour file, the user gets
nothing.

**Likelihood** — Possible (the friendly_error table even has a rule for
CUDA OOM — meaning the team expects it).

**Fix** — Write a partial `.srt.partial` on exception before re-raising;
mention it in the error event.

---

### P1-17. `config._drive_is_mounted` is overly permissive on UNC paths

**Where** — `core/config.py:97-102`

```python
if drive.startswith("\\\\") or drive.startswith("//"):
    return True
```

This always claims UNC paths are mounted. So a `model_path` pointing at
`\\dead-server\share\model` survives the `needs_recompute` check, and
the next operation hangs for ~30 s waiting on SMB timeout. The comment
says "let downstream I/O surface the real error" — but the downstream
I/O is the WhisperModel constructor, which can hang for tens of seconds
without any indication to the user.

**Symptom** — Apparent freeze on launch for users with stale UNC model
paths.

**Likelihood** — Possible.

**Fix** — Use a bounded probe: try a `Path(drive).exists()` in a
1-second-timeout thread.

---

### P1-18. `_apply_runtime_fallbacks` imports `hub` at function-call time on every load

**Where** — `core/config.py:114`

```python
from . import hub as _hub  # local import to avoid bootstrap cycle
```

Not a bug, but `load_config` is called from many hot paths (worker
startup, `_dispatch_next`, `_check_*` health checks, `_open_recent`).
Each call re-runs the import (cached after first call, so cheap), but
each call also re-runs the full file read + JSON parse + merge — there's
no in-process cache. The worker calls `load_config` twice at startup
(once from `transcriber.py` module load, once from `worker.main`).

**Symptom** — Wasted I/O; harder to test config changes (must re-call
load_config).

**Likelihood** — N/A (no user impact in steady state).

**Fix** — Cache the loaded config; expose an `invalidate()` for the
hub_setup dialog.

---

### P1-19. Hub-setup dialog accepts any directory including `C:\Windows\System32`

**Where** — `app/dialogs/hub_setup.py:150-162` and `core/hub.py:57-61`

`normalise_hub_path` just resolves the path — no validation. A user can
pick `C:\Windows\System32` as their hub folder. The downloader will then
extract a 3 GB zip into a system directory (and require elevation that
the app doesn't have, producing a confusing PermissionError instead of
a clear "you can't put the model there" message).

**Symptom** — Hostile or absent-minded user breaks themselves; confusing
error chain.

**Likelihood** — Edge.

**Fix** — Validate that the chosen path is under the user profile, or
at least warn before saving if it sits under `C:\Windows`, `C:\Program
Files`, etc.

---

### P1-20. `ensure_model` doesn't check zip path traversal before extraction (see P1-2) AND doesn't validate the model URL is HTTPS

**Where** — `core/model_manager.py:264-302`

URL comes from `config["model"]["url"]`. Defaults to HTTPS, but a
hand-edited config can downgrade to HTTP — and the entire 3 GB zip is
downloaded without TLS, and there's no integrity check beyond the MD5
manifest that *also* comes from the same server. A MITM attacker on the
download path can serve a poisoned zip + matching MD5 manifest, and the
verification step happily passes.

**Symptom** — Trivial supply-chain attack against any user on an
untrusted network with a corrupted config.

**Likelihood** — Edge (requires hand-edited config) but "MD5 from same
server" defeats the purpose of integrity checking even for clean
installs.

**Fix** — Refuse non-HTTPS URLs by default; pin the MD5 manifest digest
in the source code, not behind another URL fetch.

---

## P2 — hardening / nits

### P2-1. `Show recent log` dialog renders the log verbatim — log lines contain user file paths (PII)

**Where** — `app/dialogs/show_log.py:68-76` and the log itself
(`core/transcriber.py:271` logs `f"Processing: {audio_path}"`)

If the user clicks Help → Show recent log → Copy, then pastes into a bug
report, they leak every file path they've transcribed. The user is
unaware. The CrashDialog Copy button has the same issue (its source is
the traceback, but a path-containing exception ends up in it).

**Fix** — Add a "Sanitize paths" toggle; or document the caveat.

---

### P2-2. `friendly_error` table doesn't include `requests.exceptions.MissingSchema`, `requests.exceptions.SSLError`, `requests.exceptions.TooManyRedirects`

**Where** — `core/error_messages.py:23-89`

These can all fire from `ensure_model`'s `requests.get` calls. User sees
raw traceback.

**Fix** — Add explicit rules.

---

### P2-3. `_check_python_version` says "3.11 / 3.12 supported" but the upper bound is implicit

**Where** — `core/health_check.py:184-194`

The check only verifies >= 3.11. Python 3.13/3.14 may or may not work
with the pinned faster-whisper. The check is silent on this.

**Fix** — Warn (not fail) on Python > 3.12 unless the test suite is run
against it.

---

### P2-4. `_drive_is_mounted` returns True on non-Windows for any path

**Where** — `core/config.py:88-89`

The function is a no-op on Linux. That's fine *if* the rest of the code
doesn't depend on it for cross-platform correctness. It doesn't, today
— but the comment doesn't say so.

**Fix** — Either generalise via `os.path.exists(Path(path).anchor)` on
POSIX, or drop the function on POSIX entirely with a clearer comment.

---

### P2-5. `installer_embed.iss` ExtractHubFolder parser is fragile

**Where** — `installer_embed.iss:67-99`

The Inno Pascal parser reads `config.json` line-by-line, finds the
first line that starts with `"hub_folder"`, then extracts the value by
matching the first `"` after the colon. This breaks on:
* `{"hub_folder": "C:\\foo"}` written on one line by a tool other than
  the Python writer (which uses indent=2).
* hub_folder values containing escaped quotes (rare but legal in JSON).
* Multi-line strings (none currently, but a future feature could break
  this).

If extraction fails the function returns empty and the prompt is
skipped — the user keeps multi-GB of model files without realising.

**Fix** — Either ship a sidecar `hub_folder.txt` written next to
config.json, or use a proper JSON parser (Pascal has none built in;
shell out to `python -c "import json,sys; print(...)"` if available).

---

### P2-6. `core.worker` `friendly_error` swallows the original traceback

**Where** — `core/worker.py:169-178`

The except converts the exception to a friendly string but never logs
the traceback. The `logger.exception` calls elsewhere DO log tracebacks
to the file, but the per-task error path doesn't. So a user reporting
"Whisper failed on this file" has no traceback in `app.log` unless
logger fired elsewhere first.

**Fix** — `logger.exception("transcribe failed for %s", file_path)`
before the emit.

---

### P2-7. `crash.py` creates a fresh `tk.Tk()` when master is None

**Where** — `app/dialogs/crash.py:33-37`

If the crash happens during App.__init__ *before* the Tk root is
constructed, `get_root()` returns None, the hook creates a hidden root
and shows the dialog. But on some platforms (Linux without DISPLAY),
`tk.Tk()` itself raises, and the `except Exception: previous(...)`
fallback in the hook fires — so the user gets only stderr. The basic
edition is Windows-only per pyproject classifier, but worth noting.

**Fix** — Catch the inner `tk.TclError` explicitly and fall back to
stderr.

---

### P2-8. `Show Log` dialog uses `read_recent_log(200)` but the App constant is `LOG_PANEL_LINES = 200` — duplicated

**Where** — `app/app.py:55` and `app/app.py:239`

Cosmetic; both happen to be 200. If one is changed without the other,
silent drift.

**Fix** — Pass `LOG_PANEL_LINES` from the App.

---

### P2-9. `_install_icon` calls `iconbitmap(default=...)` which requires a `.ico` file specifically

**Where** — `app/app.py:307-322`

The default branch finds `assets/whisper.ico`. On Linux, `iconbitmap`
silently fails with TclError (caught and logged as warning). Not a bug.

---

### P2-10. `worker.emit` `repr()` fallback can still raise

**Where** — `core/worker.py:75-81`

If a payload value's `__repr__` raises (custom objects with broken
repr), the fallback path itself crashes inside the heartbeat or main
emit. Worker dies. Parent sees `worker_exit` with no error event.

**Fix** — Wrap the dict-comp in a per-key try/except that uses
`f"<unrepr-able {type(v).__name__}>"` on failure.

---

### P2-11. `health_check._check_disk_writable` uses tempfile in the config dir, leaving it on Ctrl-C

**Where** — `core/health_check.py:97-100`

`delete=True` cleans up on normal close. On Ctrl-C during the check
(unlikely but possible during startup_checks since they run on the Tk
after()), the tempfile lingers. Cosmetic.

---

### P2-12. `_dispatch_next` does not detect a worker that exited cleanly without emitting `worker_exit`

**Where** — `app/app.py:501-512`

`_worker_alive` polls `proc.poll()` — fine. But if the reader thread's
`for line in process.stdout` ends and the thread crashes before posting
`worker_exit` (e.g. `worker_events.put` blocks 5 s and then raises Full
— caught and logged but `worker_exit` is then *not* put with a longer
timeout), the parent's `self.worker` stays set, `_worker_alive` returns
False on the next dispatch attempt, and the spawn machinery kicks in
correctly — but `self.worker["task"]` is still pointing at the old
task, which now sits at "running" forever.

**Fix** — In `_worker_alive`'s False branch, also reset
`self.worker["task"]` to None.

---

## Summary table

| Priority | Count |
|----------|------:|
| P0       |     7 |
| P1       |    20 |
| P2       |    12 |
| **Total**|  **39** |

Top 5 P0s by title:

1. `worker.py` MAX_COMMAND_BYTES guard is bypassed by stdin buffering
2. `transcriber.transcribe` deadlocks if the model never loads
3. Worker silently exits on parent stdin close; tasks stuck at "waiting"
4. `model_manager._download_zip` mis-handles non-Range server reply (appends)
5. `_dispatch_next` double-click race attributes events to wrong task

---

## Disposition (post-fix pass)

All P0 (1-7) and the critical P1 set (1-7, 10-20) are fixed in the
five hardening commits on `main` (worker IPC, model-load races,
download hardening, UI safety, lower-impact cleanups).

Deferred — not fixed in this pass, kept here for the next round:
**P2-1, P2-3, P2-4, P2-5, P2-7, P2-8, P2-10, P2-11**.
