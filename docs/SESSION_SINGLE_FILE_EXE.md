# Session: single-file exe pivot

Branch: `release/single-file-exe`

Goal: turn the existing onedir output (a folder of 109 files) into a
single double-clickable artefact end users can hand to non-technical
recipients. The only first-run network requirement that survives is
the Whisper model download — that flow predates this session and was
intentionally untouched.

## Outcome

`dist\WhisperProject.exe` — 190.8 MB — boots in ~6 s, transcribes a
real video end-to-end. No accompanying DLLs, no `bin/` directory, no
extract step required from the user.

## Phase 0 — completing the Session 9 after-callback fix

The handoff context flagged that the Tk teardown warnings (`invalid
command name "<id>poll"`) that Session 9 claimed to fix were still
appearing. Investigation:

* `tk.call("after", "info")` returns a **tuple** of IDs when ≥1
  callback is pending and an empty string `""` when none are.
* The Session 9 commit 8235503 parsed it with `str(pending).split()`,
  which for a tuple produces garbage tokens like `"('after#0',)"`.
* `after_cancel` accepts unknown IDs silently — no exception — so the
  try/except wrapper swallowed the failure and the commit message
  reported "no errors on exit" while the underlying callbacks were
  in fact never cancelled.

Reproducer (run interactively, no test framework needed):
```python
import tkinter as tk
r = tk.Tk(); r.withdraw()
r.after(10_000, lambda: None)
broken = str(r.tk.call('after', 'info')).split()  # -> ["('after#0',)"]
for t in broken:
    try: r.after_cancel(t)
    except: pass
print(r.tk.call('after', 'info'))  # still ('after#0',)
```

Fix: handle the tuple/list case explicitly, fall back to whitespace
split for any future Tcl variant. Three regression tests pin both the
`tk.call` contract and the destroy logic — including a marker test
that fails loudly if anyone reverts the parser.

Commit: `6266aab` — *audit: complete Session 9 after-callback
cancellation*.

## Phase 1 — switch to onefile

### Resource resolution

The onedir code assumed `bin/` sat next to the exe and resolved it via
`dirname(self.entry_file) + "/bin"`. With `--onefile`, PyInstaller
extracts everything (DLLs, `bin/`, faster_whisper assets) into a
temporary directory exposed at `sys._MEIPASS`. The old resolver gives
back the user's exe directory, where nothing lives.

New helper: `core/paths.py::resource_base()` returns

| context             | base                                 |
|---------------------|--------------------------------------|
| onefile exe         | `sys._MEIPASS`                       |
| onedir exe          | `os.path.dirname(sys.executable)`    |
| python source       | repo root                            |

`yt_dlp_path()` / `bin_path()` (in `app/app.py`) and the
`bundled_binary("ffprobe")` call site (in `core/transcriber.py`) all
read from this helper, so the same source builds correctly under any
of the three modes.

`entry_file` is unchanged — it still resolves to `sys.executable`
under any frozen build and to `gui.py` under source. The subprocess
spawner uses it for `cwd=` only; absolute paths to ffmpeg / yt-dlp
flow through `resource_base()` instead.

### Spec rewrite

`whisper_project.spec` changed shape:

```
# old: onedir
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
          contents_directory='.', ...)
coll = COLLECT(exe, a.binaries, a.datas, name='WhisperProject')

# new: onefile
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
          name='WhisperProject', console=False, upx=False, icon=None, ...)
# (no COLLECT — embedding everything in EXE is what makes it onefile)
```

`contents_directory` has no meaning in onefile (nothing sits *next to*
the exe) and was removed.

`core.paths` was added to `hiddenimports` because PyInstaller's static
analyser doesn't see imports that cross from `app/app.py`'s top-level
`from core.paths import bin_dir` into the spec-collected module graph
unless told explicitly.

Commit: `a9cdbde` — *spec(onefile): pivot to single-file exe via
sys._MEIPASS resolution*.

### Test suite adjustments

`tests/smoke/conftest.py` — `DEFAULT_EXE` is now
`dist/WhisperProject.exe` (no nested directory). `$WHISPER_SMOKE_EXE`
still overrides for the clean-folder D6 check.

`tests/smoke/test_exe_real_e2e.py` lost two checks that assumed onedir
layout (`bin/` and `faster_whisper/assets/` next to the exe). In
onefile mode the bundle is opaque from the filesystem, so honest
substitutes were added:

* `test_exe_size_within_expected_range` — 150 MB ≤ exe ≤ 400 MB.
* `test_exe_boots_and_loads_bundle` — spawn `exe --worker`, wait for
  the `ready` event. Reaching `ready` means PyInstaller extracted
  every bundled asset and the worker loaded the Whisper model — the
  onefile analogue of the per-asset filesystem checks.

`tests/core/test_transcriber_helpers.py` — two monkeypatches moved
from `transcriber.BIN_DIR` (deleted) to `core.paths.bin_dir`.

## Definition of Done — evidence

| ID  | Requirement                              | Evidence                                                                                                                                                |
|-----|------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------|
| D1  | pyinstaller exit code 0                  | `build_logs/onefile_build_20260520_000029.log` ends with `Building EXE from EXE-00.toc completed successfully.` and exit code 0                          |
| D2  | only `dist\WhisperProject.exe` in `dist` | `find dist/` returns exactly two entries: the dir and the exe                                                                                            |
| D3  | size between 150 MB and 400 MB           | 200 094 653 bytes = 190.8 MB                                                                                                                            |
| D4  | smoke E2E passes                         | `tests/smoke/test_exe_real_e2e.py ... 3 passed in 140.56 s`                                                                                              |
| D5  | exe transcribes a real video end-to-end  | `test_exe_worker_transcribes_real_video` passes — produces `E:\3029-NWN-Daily-Scroll-2m_0002.srt` (860 B, contains `-->`) and `.json` (1117 B)          |
| D6  | clean-folder run works                   | Copied exe to `C:\Temp\clean_test\WhisperProject.exe`, ran smoke with `$WHISPER_SMOKE_EXE` override → all 3 tests pass in 140.32 s                       |
| D7  | model detected (or downloaded) on launch | Worker spawned by the exe found the existing local model at `%LOCALAPPDATA%\WhisperProject\Cache\models\models--Systran--faster-whisper-large-v3` and emitted `ready` in well under the 300 s timeout. The download path through `core.model_manager.ensure_model()` was not touched by this session. |
| D8  | window appears within 30 s               | `tools/measure_startup.py` reports 5.82 s and 5.79 s for two clean runs (third run skewed by leaked `_MEI*` temp dirs from a prior run — see Caveats)   |
| D9  | session doc + gitignore                  | This file. `.gitignore` already covers `dist/`, `build/`, `build_logs/`, `*.log` (lines 11, 70–72, 64).                                                  |
| D10 | atomic commits on the release branch     | `git log release/single-file-exe ^master` shows two commits: `6266aab` (audit) + `a9cdbde` (onefile pivot), plus a final doc commit                       |

## Caveats and follow-ups

### MEIPASS temp-dir cleanup under forced termination

`--onefile` extracts the bundle to `%TEMP%\_MEI<random>` on launch and
relies on the bootloader's atexit hook to remove it on clean exit.
Kills via `taskkill /F` (or process-tree-kill from a test harness)
skip the hook and leak the directory.

Real users closing the window leave nothing behind. The
`tools/measure_startup.py` script uses taskkill between runs and
leaked ~200 MB per cycle until the C: drive filled and the third run
failed to launch. The mitigation in this session was a manual sweep
of `%TEMP%\_MEI*` and removal of the leftover PyInstaller `build/`
directory. The measurement loop and the test harness should be taught
to send a graceful WM_CLOSE if this becomes a recurring issue; for
now, two clean cold-start samples (5.82 s, 5.79 s) are adequate
evidence for D8.

### Each worker subprocess re-extracts the bundle

`TranscriptionService.start_worker` spawns `sys.executable --worker`,
which under onefile means each worker is itself a fresh PyInstaller
bootstrap that re-extracts ~200 MB to its own `_MEIPASS`. With
`parallel_workers=2`, peak temp usage is roughly 600 MB (UI + two
workers). This is the unavoidable cost of onefile + multiprocess
worker model.

If users with constrained disks report this, the next step is to
switch the worker invocation from a subprocess to an in-process thread
pool — but doing so loses the crash-isolation property the current
architecture relies on, so it would need a separate design pass.

### `build.bat` is unchanged

The old `build.bat` ran `pyinstaller` against the same spec and then
fell back to `xcopy bin\* dist\WhisperProject\bin\` if PyInstaller's
`('bin', 'bin')` data tuple silently dropped the binaries. The xcopy
fallback is dead code under onefile (there is no destination
directory) but is harmless — it'll just print "file not found" if
ever triggered. Left alone to minimise the diff; can be cleaned up
in a follow-up if anyone audits the build script.

## Build command

```
python -m PyInstaller --noconfirm --clean whisper_project.spec
```

Output: `dist\WhisperProject.exe`.

## How a user runs the deliverable

1. Receive the single `WhisperProject.exe` file.
2. Double-click. First launch unpacks the bundle (~6 s) and opens
   the window.
3. If the Whisper model has never been downloaded, the model-setup
   dialog appears and offers to fetch `faster-whisper-large-v3` from
   the CDN. Subsequent launches reuse the cached model.

No installer, no extraction step, no path configuration.
