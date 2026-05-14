# Build

How to produce a Windows binary from source.

## TL;DR

```cmd
build.bat clean
```

Output lands at `dist\WhisperProject\WhisperProject.exe`.

## Modes

`build.bat` accepts one optional argument:

| Mode    | What it does                                                                                                  |
|---------|----------------------------------------------------------------------------------------------------------------|
| (none)  | Run PyInstaller, then verify required files are in `dist\`.                                                    |
| `clean` | Wipe `build\` and `dist\` first, then full build + verify.                                                     |
| `verify`| Skip PyInstaller. Just check that `dist\` has the exe, `bin\ffmpeg.exe`, `bin\ffprobe.exe`, `bin\yt-dlp.exe`. |
| `smoke` | After verify (and build, unless paired with `verify`), launch the exe for 5 s and confirm it stays alive.    |

## Exit codes

| Code | Meaning                                                                                          |
|------|---------------------------------------------------------------------------------------------------|
| 0    | Success.                                                                                          |
| 1    | PyInstaller failed.                                                                               |
| 2    | Post-build verification failed — at least one required file (`exe` or one of the three binaries) is missing from `dist\`. |
| 3    | Smoke launch failed — the exe died within 5 seconds (only possible with `build.bat smoke`).      |

## What `build.bat` actually does

1. (`clean` only) deletes `build\` and `dist\`.
2. (unless `verify`) runs `pyinstaller --noconfirm whisper_project.spec`.
3. If `dist\bin\` is missing — historically PyInstaller's `datas=` could
   silently drop directories — **falls back to a manual `xcopy` of the
   repo's `bin\` into `dist\bin\`.** As of Session 7's spec fix
   (`contents_directory='.'` on the `EXE()` call), this path is dead on
   a clean build; the spec emits the right layout natively. The fallback
   stays in place as a belt-and-suspenders defense.
4. Verifies `dist\WhisperProject\WhisperProject.exe`,
   `dist\WhisperProject\bin\ffmpeg.exe`,
   `dist\WhisperProject\bin\ffprobe.exe`,
   `dist\WhisperProject\bin\yt-dlp.exe` all exist. Any missing → exit 2.
5. (`smoke` only) starts the exe, waits 5 s, checks `tasklist`, kills it.

### Critical packaging detail: `collect_data_files('faster_whisper')`

Session 8 found that `build.bat smoke`'s "exe stays alive for 5 s" check
is **necessary but not sufficient**. The exe started fine but crashed
the worker the moment a transcription kicked off, because the spec did
not bundle `faster_whisper/assets/silero_vad_v6.onnx` and `faster-whisper`
loads it by file path when VAD is enabled (the default).

The fix lives at the top of `whisper_project.spec`:

```python
from PyInstaller.utils.hooks import collect_data_files
faster_whisper_datas = collect_data_files('faster_whisper')
```

…spread into `Analysis(datas=[..., *faster_whisper_datas])`.

If you ever add a new heavy dependency that loads data files by path
(common offenders: ML packages with bundled model weights, tokenizer
vocab JSONs, language-detection N-gram tables), repeat the pattern.

### Real packaging-bug test (CI-skipped, locally enforced)

`tests/smoke/test_exe_real_e2e.py` spawns `WhisperProject.exe --worker`,
sends a real `transcribe` command via stdin, and asserts an SRT lands on
disk. It is the only test that catches packaging regressions like the
silero VAD miss. Run it before releasing:

```
python -m pytest tests/smoke/ -v -s
```

On a clean machine without the model or test video, the suite skips
cleanly instead of failing.

## Why `config.json` is NOT in `dist\`

Phase 1.2 moved the user's config to
`%LOCALAPPDATA%\WhisperProject\config.json`. On first launch
`load_config()` builds a fresh one from `DEFAULT_CONFIG`. There is no
need to ship a copy next to the exe.

If you need a *portable* build (where the user's preferences travel with
the exe folder), add a new `portable` mode to `build.bat` that:

1. Sets an env var `WHISPER_PORTABLE=1` for the spec file.
2. Patches `core/config.py` at startup to use a path next to the exe.
3. Drops a starter `config.json` into `dist\WhisperProject\` after the
   verify step.

That's a future enhancement; the default mode is the right one for
distributing to users on their own machines.

## What's in `dist\WhisperProject\` after a successful build

```
dist\WhisperProject\
├── WhisperProject.exe         <- main entry; also doubles as worker via --worker
├── _internal\                  <- PyInstaller runtime
│   ├── ...                     <- frozen Python + packages
│   └── ...
└── bin\
    ├── ffmpeg.exe
    ├── ffprobe.exe
    └── yt-dlp.exe
```

## Known PyInstaller hook quirks

- **`sv-ttk`** ships its theme files separately. PyInstaller usually
  picks them up via the built-in hook. If the launched exe falls back to
  the default Tk look, add the package's `sv_ttk\sv_ttk` directory to
  `datas` in `whisper_project.spec`.
- **`faster-whisper`** drags in `ctranslate2`. The CT2 wheel has CUDA
  binaries that PyInstaller will bundle whether you use them or not.
  Total `dist\` size will be ~250–500 MB depending on the wheel.
- **`huggingface_hub`** has a pure-Python fallback for `hf_xet` that
  gets noisy in logs but doesn't break anything.
- **antivirus**: `--onedir` (what we use) has a much lower
  false-positive rate than `--onefile`. Stay one-dir.

## Re-running the spec file by hand

```cmd
pyinstaller --noconfirm whisper_project.spec
```

This is what `build.bat` does internally. Useful when you want to debug
PyInstaller flags without re-running the verification logic.
