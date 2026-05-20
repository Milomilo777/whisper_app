# v0.7.1 — Hands-off polish push

Packages the Session-14 hands-off polish push as a tagged release.
Same three install methods, same single source on
`release/v0.7.0-installer-3-options`, every "Remaining work" item
from `docs/HANDOFF_NEXT_SESSION.md` now landed.

## Pick one

| | **Portable** | **Setup-Compact** | **Setup-Standard** |
|---|---|---|---|
| Asset | `WhisperProject-v0.7.1-Portable.exe` | `WhisperProject-v0.7.1-Setup-Compact.exe` | `WhisperProject-v0.7.1-Setup-Standard.exe` |
| Install step | none — double-click | silent ~20 s | silent ~45 s |
| Start-up | ~6 s (every launch unpacks) | ~3 s | ~3 s |
| AV exposure | onefile binaries trigger more false positives | lower | lowest (real CPython on disk) |
| Source-tree visibility for debug | none | none (PyInstaller-bundled) | full — every `.py` is readable |
| Best for | one-off use, USB sticks, easy hand-off | most Windows users | developers and the AV-paranoid |

## What's new in 0.7.1

Twelve high-impact additions land in one tagged release:

- **Filename templating** — `output_filename_template` honoured by every
  writer. Tokens `{base}`, `{ext}`, `{lang}`, `{date}`,
  `{speaker_count}` resolve at write time. Templates may include
  sibling subdirectories (`transcripts/{base}.{ext}`); those folders
  are created on the fly. Malformed templates fall back to the legacy
  layout.

- **Pluggable Whisper backends** — `core/backends/` houses an ABC +
  two implementations. `faster_whisper` (default) preserves the
  CTranslate2 path; `whisper_cpp` (opt-in) drives pywhispercpp on
  quantised ggml models (~1.1 GB for large-v3-q5_0). The Advanced
  dialog grows a backend picker + a "Download whisper.cpp
  model..." button.

- **Word-level alignment refinement (stable-ts)** — opt-in DTW pass
  after the main transcribe. Tightens word boundaries to ±50 ms.
  Available via the Advanced dialog's "Word alignment" dropdown.

- **Transcript viewer enhancements** — `Ctrl+F` Find-and-Replace,
  right-click "Rename speaker (everywhere)", word-confidence colour
  coding (green ≥ 0.85 / amber / red), one-click "Remove fillers"
  (uh / um / er / …), `Ctrl+S` atomic save via the JSON writer.

- **Karaoke-style word highlight** — when VLC is playing, the
  active word in the segment panel is bracketed and the active
  segment row glows. Follows the playhead at 250 ms tick rate.

- **System tray + minimise-to-tray + native toast** — pystray +
  Pillow on a daemon thread. Right-click menu Show / Hide / Exit.
  Icon flips between hollow blue (idle) and red dot (active).
  `config["minimise_to_tray"]` (Advanced dialog) makes
  WM_DELETE_WINDOW hide instead of exit. Completed jobs raise a
  native toast.

- **High-DPI scaling** — Tk scaling now computed from
  `winfo_fpixels('1i')` on launch. Fonts and paddings stop
  shrinking on 125 % / 150 % Windows displays.

- **Anonymous opt-in telemetry** — `config["telemetry_opt_in"]`
  gates both Sentry crash reporting (needs `$SENTRY_DSN`) and a
  one-shot launch ping (needs `$WHISPER_TELEMETRY_URL`). Ping
  carries `{os, version, python, anonymised_id}` only;
  anonymised_id is a SHA-256 of a one-shot UUID4 stashed under
  `user_cache_dir()/telemetry_id`.

- **Auto-resume after crash** — rows the `history.db` flagged
  `interrupted` on the previous run get re-enqueued when their
  source files still exist.

- **Per-folder `.whisperproject.json` overrides** — drop a JSON
  next to (or above) a media file to override the global config
  for that folder. Dict-valued keys (`model`, …) deep-merge one
  level. Bad JSON / non-object roots are silently ignored.

- **Watched-folder UI wiring** — `core.watcher.FolderWatcher` is
  exposed through the Advanced dialog. New media files dropped in
  are stability-checked (size stable for 1.2 s) then auto-enqueued.

- **Windows Explorer "Transcribe with Whisper Project"** — both
  installers ship an optional `shellext` task that registers
  `HKCR\*\shell\WhisperProjectTranscribe`. Right-click any file →
  the existing CLI mode (`WhisperProject.exe transcribe "%1"`)
  picks it up.

## Test coverage

Hermetic unit suite: **259 passing** after the deep-audit pass
(was 191 at start of session, 237 after first round of v0.7.1
work, 259 after the audit fixes added 22 more tests). Smoke suite:
3 passes against the freshly built portable exe with a real 60 s
news clip + the SMTV-clip CLI feature smoke. Pyright clean on
`app/` + `core/`.

## Deep-audit pass (post-Session-14)

After the initial v0.7.1 cut, a 7-shard parallel audit ran over
every Session-14 zone. The audits surfaced 2 blockers, 12 serious
issues, and ~20 minor nits — all fixed before this release:

  * **Transcript viewer**: race between the `_update_position`
    tick and `_on_close` that scheduled callbacks on a destroyed
    Tcl interpreter (BLOCKER) — fixed with an explicit `_closing`
    flag + TclError guards on re-arm. Find/replace lambda guards
    backreferences (`\1`, `\g<…>`) from being interpreted as
    regex syntax. Karaoke `_update_karaoke` rewritten with
    `bisect_right` (O(log N) per 250-ms tick) + active highlight
    cleared in segment gaps. `_populate_listbox` re-applies the
    active row tag after edit ops. `_rename_speaker` and find-
    replace reject whitespace-only inputs.
  * **System tray**: tray-runner crash (BLOCKER) now nulls
    `self._icon` AND posts a `setattr(app, "tray", None)` to the
    Tk thread so the app stops dispatching to a dead controller.
    File → Exit + Ctrl+Q always exit (new `_force_exit()` bypasses
    the minimise-to-tray redirect; the X button still honours it).
  * **Watched folder**: per-path dedup with `after_cancel` so
    Windows on_created + on_modified bursts no longer
    double-enqueue the same file. App-wide `_closing` flag
    short-circuits watcher callbacks during teardown.
  * **Backend dispatch**: runtime-config refresh keys
    (diarization/alignment) now run BEFORE the
    faster_whisper/whisper_cpp branch so both backends honour UI
    toggles. `_get_alt_backend` holds an `_ALT_BACKEND_LOCK`
    during the cache step. `worker.py` emits `get_model_error()`
    in the `startup_error` payload so backend-load failures
    surface to the parent UI.
  * **Filename templating**: catches a broader exception set
    (KeyError, TypeError, AttributeError); positional `{0}`
    correctly falls back to the legacy `{base}.{ext}` layout;
    path-traversal templates (`../etc/passwd.{ext}`) are rejected
    after render.
  * **Per-folder overrides**: recursive deep-merge replaces the
    one-level `dict.update`, so `{"model": {"sub": {"deeper": 1}}}`
    keeps every sibling key under `model.sub` intact.
    `UnicodeDecodeError` is caught explicitly so a project file
    saved in cp1252 degrades silently.
  * **CLI mode**: `--formats` and `--diarization` now take effect
    on the FIRST CLI run (previously the in-memory `config`
    snapshot from module import time shadowed the on-disk save).
    CLI mode now writes a `history.db` row so CLI usage shows up
    in Statistics + Recent files alongside GUI runs.
  * **Build pipeline**: `pyproject.toml [project].dependencies`
    grew the Session-13+14 runtime deps so `pip install
    whisper-project` yields a runnable install (previously the
    PyPI installer was non-functional). Both PyInstaller specs
    pick up `collect_dynamic_libs('pywhispercpp')` so the bundled
    whisper.cpp native lib travels with the exe. `[UninstallDelete]`
    blocks now sweep `__pycache__`, `gui.py`, `sitecustomize.py`
    so clean uninstalls really clean.

22 new tests cover the fixed paths: find/replace backreference
safety, whitespace-needle reject, speaker rename empty-input
reject, filler punctuation tidy, template positional/traversal/
zero-speaker, deep-merge >1-level, UnicodeDecodeError graceful
degradation, UNC-path non-blocking probe, watcher availability
+ start errors, crash-resume mark/dedup/filter, HiDPI scaling
math.

## Deep-audit pass (round 2) — with opt-in deps installed

After the first audit + fix cycle, the user requested a second
deep-audit pass with `pywhispercpp`, `stable-ts`, `sentry-sdk`,
`pystray`, `watchdog`, `darkdetect` actually installed in the
audit environment so the shards could exercise the opt-in code
paths the previous audit had to skip. 8 parallel shards surfaced
**11 blockers + 22 serious issues** — all fixed.

### Blocker fixes

- **HistoryDB cross-thread silent failure** — `core/history.py`'s
  single shared connection was created without
  `check_same_thread=False`. Every cross-thread insert
  (transcription + download services dispatch from worker
  threads) raised `sqlite3.ProgrammingError` which the callers'
  broad `except Exception` swallowed. The history table was
  effectively empty for the entire app's lifetime. Fix: open
  with `check_same_thread=False` + a module-level write lock
  that serialises commits across threads.
- **FolderWatcher.start() self-deadlock** — held a non-reentrant
  `threading.Lock` then called `self.stop()` which tried to
  acquire the same lock. `RLock` is the one-line fix.
- **Watched-folder cross-thread `after()`** — watchdog's worker
  thread called `self.after(0, ...)` directly on the Tk root;
  Python 3.14 raises `RuntimeError("main thread is not in main
  loop")`. Replaced with a `queue.Queue` drained on the Tk
  main thread by `_drain_watched_paths`.
- **Drag-and-drop silently never registered** —
  `TkinterDnD._require(self)` only loads the Tcl extension; the
  `drop_target_register` method only exists on
  `TkinterDnD.DnDWrapper`. We were calling it on a plain
  `tk.Tk` instance, which raised AttributeError caught by the
  broad except, so drag-and-drop was dead in production. Fix:
  graft `DnDWrapper` into the App's class so the instance gains
  the methods.
- **Parallel-worker `.part` collision** — two workers
  transcribing the same source file race-wrote to identical
  `.part` paths and Windows `PermissionError`'d. Unique
  per-PID + per-thread suffix on the `.part` filename eliminates
  the collision.
- **`stop_worker` stdin hang** — `stdin.write` to a worker
  mid-transcribe (worker only reads stdin between tasks)
  blocked the Tk main thread when the pipe filled. The write
  now runs on a daemon thread so the UI never hangs.
- **Writers crash on numeric speaker label** — `(raw or '').strip()`
  used to crash on an int with `AttributeError`. New
  `core/writers/base.speaker_prefix()` defensively str-casts;
  all 5 affected writers use it.
- **stable-ts `align()` wrong shape** — the module was passing a
  dict list to `stable_whisper.align()` which expects a
  WhisperResult. Whole module rewritten to build a
  `WhisperResult` from segments_data then call
  `model.align(audio, result)`. Handles `align` returning None
  (a real stable-ts code path for unrelatable clips).
- **stable-ts not bundled in the portable** — `hiddenimports`
  listed `core.alignment` but not the actual `stable_whisper`
  module. Both PyInstaller specs now `collect_all` on
  `stable_whisper`, `whisper`, and `tiktoken`. Portable EXE
  grew from 262 MB → 447 MB (torch is the bulk) but alignment
  now actually runs inside the bundled exe.
- **pywhispercpp not bundled in the portable** —
  `collect_dynamic_libs('pywhispercpp')` returned `[]` because
  the native `_pywhispercpp.pyd` ships as a TOP-LEVEL module,
  not inside the pywhispercpp package. `collect_all` on both
  names gathers everything. Verified end-to-end: the rebuilt
  portable EXE successfully transcribes with the whisper_cpp
  backend against a real SMTV clip.

### Serious fixes

- `load_config` catches `UnicodeDecodeError` (cp1252 saves)
  and coerces wrong-type values back to defaults so
  `parallel_workers="many"` doesn't crash downstream.
- `save_config` module-level lock serialises concurrent saves
  so two threads racing `os.replace` don't `PermissionError`
  on Windows.
- Disk-full mid-batch: previously-written formats are rolled
  back so the user never ends up with a mix of fresh + stale
  outputs.
- DOCX writer: control-char sanitiser strips XML-illegal bytes
  before handing to python-docx (otherwise a NUL byte in
  segment text crashed the whole docx build).
- SRT + VTT: literal `-->` in segment text is replaced with a
  unicode arrow so downstream parsers don't see a phantom
  timecode line.
- JSON writer: `_safe_float` clamps NaN/Infinity to 0.0 and
  `allow_nan=False` enforces strict JSON for browsers / Go /
  Rust consumers.
- MD writer: escapes markdown control characters from the
  title so a weird basename doesn't render as a link / inject
  HTML.
- Tray controller: `thread.join(timeout=2.0)` before stop()
  returns so an in-flight menu-callback bounce doesn't fire on
  a destroyed Tcl interpreter.
- SMTV scraper: handle the new `max` video-quality label,
  reserved Windows device names (CON/PRN/AUX/NUL/COM/LPT),
  and `ConnectionResetError` that previously escaped past the
  `URLError` clause.
- Diarization: `ffmpeg` `FileNotFoundError` wrapped as
  `DiarizationUnavailable` to match the documented contract.
- Worker JSON protocol: max 1 MB line bound rejects DOS attempts
  instead of OOM-ing on a single huge command.
- Crash-resume modal: singular/plural grammar fix
  (was/were + transcription/transcriptions + it/them).
- Alignment: failures now WARN-log instead of silently
  swallowing, so a user enabling stable-ts knows when the
  refinement didn't actually happen.

### Tests + verification

- Hermetic unit suite: 259 → **275 passing** (16 new tests
  covering the audit-2 fixed paths).
- Pyright basic-mode: 0 errors, 0 warnings on `app/` + `core/`.
- Comprehensive CLI smoke against the rebuilt portable on
  a real SMTV clip: **5 / 5 PASS**, including
  `whisper_cpp_in_portable` (verifying the bundled
  pywhispercpp + native lib runs end-to-end).

### Artefact size growth

The bundled stable-ts + torch + tiktoken pushes the portable
exe past the original 400 MB upper bound:

| Method | v0.7.1 (before audit-2) | v0.7.1 (after audit-2) |
|---|---:|---:|
| Portable | 262 MB | **447 MB** |
| Setup-Compact | 197 MB | (rebuilt — see release page) |
| Setup-Standard | 349 MB | (rebuilt — see release page) |

The size cost buys actual whisper_cpp + stable_ts
functionality in the bundled exes — previously both features
silently fell back to skipping on every install.

## Known limitations

- **SmartScreen warning.** None of the three exes are code-signed.
  First-launch shows the standard "Windows protected your PC"
  prompt; click **More info → Run anyway**.
- **First launch is slow on Method A.** Portable unpacks ~260 MB
  to `%TEMP%\_MEI<random>\` on every launch. Methods B and C
  unpack once at install time.
- **stable-ts ships torch.** Enabling word alignment loads a tiny
  Whisper model via stable-ts which transitively pulls torch
  (~125 MB), shipped in Setup-Standard for completeness even when
  the user keeps the default `none` alignment.

## Build and contribute

See [docs/BUILD.md](BUILD.md) for the three build pipelines and
[docs/ROADMAP.md](ROADMAP.md) for where the project is heading.

The full Session-14 narrative + design notes live in
[docs/RELEASE_NOTES_v0.7.0.md](RELEASE_NOTES_v0.7.0.md) under
"Hands-off polish push" — same content, slightly more prose.
