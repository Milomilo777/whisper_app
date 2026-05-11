# Architecture Decision Records

Short notes on the load-bearing choices in this codebase. Each entry follows the template:

```
## NNNN-title
Status:   [Accepted | Superseded by NNNN | Deprecated]
Date:     YYYY-MM-DD
Context:  the problem
Decision: what we chose
Consequences: what this commits us to
```

Write a new ADR every time a choice has a non-obvious justification that future-you will want to know. They are append-only — when a decision changes, write a new ADR superseding the old one rather than editing history.

---

## 0001 — Subprocess workers, not threads, for transcription

**Status:** Accepted
**Date:** 2026-05-10

**Context:** Transcription work is CPU-bound (or GPU-bound, but with Python GIL contention on the host side). `faster-whisper` / CTranslate2 / torch are not free-threaded. Running multiple transcriptions in threads inside the GUI process means:

- Python GIL serializes the calls anyway
- A crash inside the model (segfault from a corrupted input, OOM) takes the whole UI with it
- The first model load is expensive (5-15 seconds), so we want it amortized across jobs

**Decision:** Each transcription runs in a long-lived subprocess (`python -u -m core.worker`). The parent talks to it over stdin/stdout with newline-delimited JSON. Workers are spawned up to `parallel_workers` concurrent.

**Consequences:**
- We pay startup time (one model load) per worker, not per job
- A worker crash is isolated — `worker_exit` event fires, UI continues
- The IPC layer is observable (JSON event log is the diagnostic trail)
- We can't share Python objects between worker and UI; everything is serializable JSON
- Cancel is `terminate()` on the subprocess, simple and robust

**Alternatives considered:**
- Threads — rejected because of crash isolation and GIL
- `multiprocessing.Pool` — rejected because it doesn't fit the long-lived-worker model and adds pickling-of-large-objects friction
- ProcessPoolExecutor with `loky` — same issues as multiprocessing

---

## 0002 — Ship yt-dlp as a vendored binary, not a Python library import

**Status:** Accepted
**Date:** 2026-05-08

**Context:** yt-dlp is available as a pip package (`pip install yt-dlp`) and as a standalone executable. The project needs to:

- Run on machines without a yt-dlp pip install
- Update yt-dlp independently of the rest of the app
- Survive yt-dlp API changes between releases without breaking the GUI

**Decision:** Ship `yt-dlp.exe` in `bin/`. Drive it via `subprocess.Popen` with structured flags and parse stdout.

**Consequences:**
- The user / packager doesn't need a Python yt-dlp install
- Updates are a single binary replacement (`yt-dlp --update`, or the planned auto-update in ROADMAP 3.2)
- We parse stdout (`[download] N%`, `Writing video subtitles to:`) rather than subscribing to a progress callback. Phase 3.1 replaces regex with `--progress-template "%(progress)j"` which gives us JSON progress events
- Cancellation is `terminate()`, which is always correct (no in-process state to clean up)
- The cost: we cannot directly inspect `info_dict` without a separate `--dump-single-json` invocation (we accept this — it's how `lookup_formats` works today)
- For users who want bleeding-edge yt-dlp features, an `extra_ytdlp_args` setting (ROADMAP 3.4) gives them an escape hatch without us needing UI for every flag

**Alternatives considered:**
- `import yt_dlp` library — rejected because of the dependency-on-pip-install problem and the inability to ship a self-contained binary
- Both library and binary — rejected as needless complexity for one-developer scope

---

## 0003 — Resumable MD5-verified ZIP for model distribution, not Hugging Face Hub

**Status:** Accepted
**Date:** 2026-05-06

**Context:** The model is ~3 GB. Users in Iran (the developer's geography) have unreliable, throttled, sometimes-blocked access to huggingface.co. `huggingface_hub.snapshot_download` requires reaching HF and authenticating gracefully with their CDN; in practice this fails for many users.

**Decision:** The model lives as a single ZIP on a CDN mirror (`smch.ir`), accompanied by an `.md5` manifest listing the MD5 of every file inside the archive. The app downloads the ZIP with HTTP `Range` resume support, extracts it, then verifies every file against the manifest. Mismatches trigger a full redownload.

**Consequences:**
- Robust against partial downloads (resume via `Range: bytes=N-`)
- Robust against corrupted extracts (file-by-file MD5 check)
- We pay the cost of hosting and updating the mirror when the model changes
- Users without smch.ir access can still hand-place the model at `config.model_path` and skip the download dialog
- One model URL per `config.json`. Multi-model support (ROADMAP 2.7) will keep the same shape, just a list of these objects.

**Alternatives considered:**
- HuggingFace Hub — rejected for the access reason
- BitTorrent / IPFS — overkill for the scale; no real reliability gain over a CDN + integrity check
- No verification — rejected because corrupt model files give silently-bad transcriptions

---

## 0004 — Single mutable `download_current` global, no lock

**Status:** Accepted (but flagged in AUDIT B3)
**Date:** 2026-05-09

**Context:** Only one download can be active at a time today. We need to remember which task is "the current one" so the worker thread can notify completion and the next task can pick up.

**Decision:** Use a module-global `download_current` variable. The convention is that all reads and writes of it happen on the Tk main thread (either directly, or via `download_events` queue events that the main thread drains).

**Consequences:**
- No locking complexity
- Works as long as the convention holds — and today it does
- Future parallel-downloads support (ROADMAP 3.7) requires replacing this with a list and using a `Semaphore` or similar
- The global is a smell that the AUDIT calls out; it should become `self.download_current` on the App when we refactor `gui.py` (ROADMAP 1.4)

**Alternatives considered:**
- `threading.Lock` — unnecessary given the single-thread-write convention
- Make it a method on a `DownloadService` class — what the refactor will do

---

## 0005 — `tkinter` over PyQt / web frameworks

**Status:** Accepted
**Date:** 2026-05-04

**Context:** Need a desktop GUI on Windows that ships easily, looks acceptable, doesn't bloat the install, and a solo developer can maintain.

**Decision:** Tkinter as the toolkit, with the planned upgrade to `sv-ttk` (ROADMAP 1.1) for modern Windows 11 styling.

**Consequences:**
- Zero install dependency on Windows (`tkinter` is in the stdlib's Python distribution)
- PyInstaller bundle stays small (~50-80 MB without the model)
- We're locked into the Tk widget model. Custom widgets need to be drawn on a Canvas or imported via niche libraries (`ttkwidgets`, `tkinterdnd2`)
- The default look is mediocre; mitigated by `sv-ttk`
- Switch cost to PyQt6 / Flet / NiceGUI is L (~1 week per ROADMAP estimate), so this is reversible if we ever need richer widgets

**Alternatives considered:**
- PyQt6 / PySide6 — better widget library and tooling, but adds 40-80 MB to the bundle and a steeper learning curve
- Flet / NiceGUI — fast iteration, but they're web-based under the hood and don't fit the "drives subprocesses on the user's filesystem" model as cleanly
- Electron — rejected, ~100 MB minimum bundle plus runtime, single-developer maintenance cost

---

## 0006 — Each transcription writes SRT + JSON next to the input file

**Status:** Accepted (under review for ROADMAP 2.4 multi-format output)
**Date:** 2026-05-05

**Context:** Where should output files go? Same folder as input? A configured output folder? A user prompt per file?

**Decision:** Same folder as input, same base name, `.srt` and `.json` extensions.

**Consequences:**
- Predictable for the user — output is right next to input
- Plays well with batch workflows where the user already has folders organized by topic
- Existing files of the same name are silently overwritten — documented but not yet a "confirm overwrite" prompt
- ROADMAP 2.4 adds VTT/TSV/TXT/LRC; this decision applies to all of them. The output formats are user-selectable, not auto-generated all-at-once.

**Alternatives considered:**
- Configured output folder — rejected as it forces the user to flatten their organization into one bucket
- Subfolder `<input>_transcripts/` — minor friction for the common case; possible future setting
- User prompt per file — overkill for a batch workflow
