# Build

How to produce Windows binaries from source. v0.7.1 ships three
independent installation methods; each has its own build pipeline.

## TL;DR

```cmd
:: Method A — Portable single-file exe (~447 MB)
pyinstaller --noconfirm --clean whisper_project_onefile.spec
:: Output: dist\WhisperProject-v0.7.1-Portable.exe

:: Method B — Compact installer (~326 MB)
pyinstaller --noconfirm --clean --distpath dist_onedir whisper_project_onedir.spec
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer.iss
:: Output: dist_installer\WhisperProject-v0.7.1-Setup-Compact.exe

:: Method C — Standard installer with embeddable Python (~349 MB)
build_embed_installer.bat
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer_embed.iss
:: Output: dist_installer\WhisperProject-v0.7.1-Setup-Standard.exe
```

## Prerequisites

* Python 3.10+ on PATH (used to invoke PyInstaller and pip).
* `pip install pyinstaller` in the working environment.
* `bin\ffmpeg.exe`, `bin\ffprobe.exe`, `bin\yt-dlp.exe` checked into
  the repo's `bin\` folder — Method A and B bundle them via the
  spec's `('bin', 'bin')` data entry; Method C copies them with
  `xcopy`.
* Inno Setup 6 for Methods B and C. Install via `winget install
  JRSoftware.InnoSetup`. It lands at
  `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`.
* Method C also needs `tar.exe` from `%SystemRoot%\System32\` (the
  Windows-native bsdtar, not Git's tar — Git's tar tries to treat
  the `C:\` path as a remote host).

## Method A — Portable

```cmd
pyinstaller --noconfirm --clean whisper_project_onefile.spec
```

Builds a single self-extracting executable. At launch, PyInstaller
unpacks the bundle to `%TEMP%\_MEI<random>\` (~5 s on a typical
machine) and runs the app from there. `core.paths.resource_base()`
points to that temp dir at runtime.

Output: `dist\WhisperProject-v0.7.1-Portable.exe` (~447 MB; the bundled
`stable_whisper` + transitive `torch` pushed the v0.7.0 ~190 MB up by
the audit-2 polish push).

## Method B — Compact installer

Two steps. First produce the onedir tree:

```cmd
pyinstaller --noconfirm --clean --distpath dist_onedir whisper_project_onedir.spec
```

This drops a fully-extracted PyInstaller bundle under
`dist_onedir\WhisperProject\` with the exe and its sibling DLLs
flat at the top (the spec sets `contents_directory='.'`).

Then wrap it in an Inno Setup installer:

```cmd
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer.iss
```

The installer uses LZMA2 ultra compression, packs the ~478 MB
onedir tree to ~137 MB, ships per-user / per-machine shortcuts, and
gives users a real Add/Remove Programs entry.

Output: `dist_installer\WhisperProject-v0.7.1-Setup-Compact.exe`
(~137 MB).

## Method C — Standard installer with embeddable Python

```cmd
build_embed_installer.bat
```

The batch script:

1. Downloads
   `cpython-3.11.15+20260510-x86_64-pc-windows-msvc-install_only.tar.gz`
   from
   [python-build-standalone](https://github.com/astral-sh/python-build-standalone).
   This is a full CPython install with `tkinter` and the Tcl/Tk
   runtime — python.org's "embeddable" zip is stripped of tkinter,
   so we cannot use it directly.
2. Extracts it with the Windows-native `tar.exe`.
3. Verifies tkinter is importable.
4. `pip install --target` reads `requirements.txt` into the
   embed-build's `Lib\site-packages\`.
5. Copies `app\`, `core\`, `bin\`, and `gui.py` into the embed tree.
6. Writes a `sitecustomize.py` that prepends the bundle's
   `Lib\site-packages\` to `sys.path` whenever the embedded
   interpreter starts.
7. Runs a sanity import (`faster_whisper`, `ctranslate2`, `sv_ttk`,
   `platformdirs`, `tkinter`) to confirm the bundle is complete.

Then wrap the tree in an Inno Setup installer:

```cmd
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer_embed.iss
```

Output: `dist_installer\WhisperProject-v0.7.1-Setup-Standard.exe`
(~153 MB).

Method C's shortcuts launch `pythonw.exe gui.py` rather than a
frozen exe, so the entire Python source tree lives on disk after
install — friendlier for debugging or local patching at the cost
of a slightly larger installed footprint.

## Sanity check after any build

```cmd
python -m pytest tests\ --ignore=tests\smoke
```

Expected: 162 passed.

For the compiled artefacts, run the smoke E2E against each:

```cmd
:: Method A
set WHISPER_SMOKE_EXE=dist\WhisperProject-v0.7.1-Portable.exe
python -m pytest tests\smoke\test_exe_real_e2e.py

:: Method B (after silent install to C:\Temp\test_B)
set WHISPER_SMOKE_EXE=C:\Temp\test_B\WhisperProject.exe
python -m pytest tests\smoke\test_exe_real_e2e.py

:: Method C (after silent install to C:\Temp\test_C)
set WHISPER_SMOKE_EXE=C:\Temp\test_C\python\pythonw.exe
set WHISPER_SMOKE_GUI=C:\Temp\test_C\gui.py
python -m pytest tests\smoke\test_exe_real_e2e.py
```

Each must report `test_exe_worker_transcribes_real_video PASSED`
(plus a skipped size check on Methods B and C — see the test for
why).

## Files involved

| File | Role |
|---|---|
| `whisper_project_onefile.spec` | Method A — embedded `EXE()` (no `COLLECT`) |
| `whisper_project_onedir.spec` | Method B — `EXE() + COLLECT()` for the onedir tree |
| `installer.iss` | Method B — wraps `dist_onedir\` into Setup-Compact |
| `build_embed_installer.bat` | Method C — builds `embed_build\` |
| `installer_embed.iss` | Method C — wraps `embed_build\` into Setup-Standard |
| `requirements.txt` | runtime deps installed into Method C's embed tree |
| `bin\` | bundled `ffmpeg.exe`, `ffprobe.exe`, `yt-dlp.exe` (all methods) |

## Build outputs are gitignored

`dist/`, `dist_onedir/`, `dist_installer/`, `embed_build/`,
`build/`, and `build_logs/` are all in `.gitignore`. Commit only
specs, batch scripts, and `.iss` files.
