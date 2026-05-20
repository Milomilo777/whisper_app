# Session: dual deliverable (single-file exe + Windows installer)

Branch: `release/single-file-exe`

Continues `docs/SESSION_SINGLE_FILE_EXE.md`. Method A (the onefile
`WhisperProject.exe`) was already complete; this session adds
Method B — a traditional Windows installer
`WhisperProject-Setup.exe` produced with Inno Setup 6 on top of a
separate onedir PyInstaller build.

## Why two deliverables

Single-file is unbeatable for hand-off ("download this one file, run
it"). Onedir-via-installer is what most Windows users expect from
real software: Start Menu entry, optional desktop icon, a proper
uninstaller in *Apps & features*. Same source code, two artefacts
shipped from the same branch:

```
dist\WhisperProject.exe             # Method A: 190.8 MB onefile
dist_installer\WhisperProject-Setup.exe  # Method B: 137.1 MB installer
```

The installer expands to `~478 MB` of onedir files at install time;
the compression ratio (28.7 %) is normal for LZMA2 ultra against a
binary-heavy tree.

## Pipeline

```
gui.py + app/ + core/
        |
        +---- whisper_project.spec ----------> dist\WhisperProject.exe  (Method A)
        |     (onefile EXE with embedded
        |     binaries+datas)
        |
        +---- whisper_project_onedir.spec ----> dist_onedir\WhisperProject\  (intermediate)
              (COLLECT + contents_directory='.')           |
                                                          v
                                                installer.iss
                                                          |
                                                          v
                                                dist_installer\WhisperProject-Setup.exe  (Method B)
```

Both specs share the same `Analysis` block (datas, hidden imports,
faster_whisper data collection). The only structural difference is
that the onedir spec keeps `exclude_binaries=True` + a `COLLECT` step,
where the onefile spec embeds everything directly into `EXE()`.

`core.paths.resource_base()` works for both layouts unchanged: it
checks `sys._MEIPASS` first (onefile), falls back to
`dirname(sys.executable)` (onedir), then to the repo root (source).

## Inno Setup script summary

`installer.iss` keeps the configuration minimal:

* `AppName=SMTV Whisper Project`, `AppVersion=0.7.0`
* Default install dir `{autopf}\WhisperProject` (Program Files), admin
  privileges required
* `Compression=lzma2/ultra` + `SolidCompression=yes`
* `ArchitecturesInstallIn64BitMode=x64compatible` (the deprecated
  `x64` directive triggers a compiler warning in Inno 6.4+)
* Single `[Files]` entry sweeping
  `dist_onedir\WhisperProject\*` with
  `recursesubdirs createallsubdirs`
* Shortcuts: Start Menu (app + uninstall), Desktop (optional via the
  `desktopicon` task)
* `[Run]` block launches the app at the end of an interactive install
  with `nowait postinstall skipifsilent` so silent runs do not auto-
  launch

## Definition of Done — evidence

| ID  | Requirement                                                   | Evidence                                                                                                                                                                                                                                                                  |
|-----|---------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| DB1 | `dist_installer\WhisperProject-Setup.exe` produced            | ISCC returned: `Successful compile (161.843 sec). Resulting Setup program filename is: ...\dist_installer\WhisperProject-Setup.exe`                                                                                                                                       |
| DB2 | size 150–350 MB (lzma2/ultra)                                 | 143 796 992 bytes = **137.1 MB** — 13 MB below the prompt's lower hint. The hint was an estimate; the actual layout was verified intact in DB4 (every required file present after install), so the lower compression result reflects LZMA2 efficiency, not missing data. |
| DB3 | silent install succeeds                                       | `WhisperProject-Setup.exe /SILENT /SUPPRESSMSGBOXES /DIR="C:\Temp\installed_test"` returned exit code 0 in 20 s                                                                                                                                                          |
| DB4 | installed tree contains exe, bin/, faster_whisper assets, unins000.exe | Verified after install: `WhisperProject.exe`, `bin\ffmpeg.exe`, `bin\ffprobe.exe`, `bin\yt-dlp.exe`, `faster_whisper\assets\silero_vad_v6.onnx`, `unins000.exe` all present                                                                                              |
| DB5 | `test_exe_worker_transcribes_real_video` passes against installed exe | With `WHISPER_SMOKE_EXE=C:\Temp\installed_test\WhisperProject.exe`: `1 passed in 128.06s`. Output: `E:\3029-NWN-Daily-Scroll-2m_0002.srt` (860 B, contains `-->` arrows), `E:\3029-NWN-Daily-Scroll-2m_0002.json` (1117 B)                                                |
| DB6 | silent uninstall + folder empty                               | Re-installed with default tasks (desktop icon enabled), confirmed shortcuts exist (`%PUBLIC%\Desktop\Whisper Project.lnk`, `%ProgramData%\Microsoft\Windows\Start Menu\Programs\Whisper Project\{Whisper Project,Uninstall Whisper Project}.lnk`), then `unins000.exe /SILENT` → exit 0, install dir gone, Public Desktop shortcut gone, Start Menu group gone |
| DB7 | metrics log                                                   | Captured below                                                                                                                                                                                                                                                            |

### DB7 metrics

```
installer size:        143 796 992 bytes (137.1 MB)
ISCC compile time:     161.8 s
silent install time:   20 s   (admin elevation accepted by sandbox)
silent uninstall time: < 5 s  (the launched unins000.exe re-execs itself
                                from %TEMP% and exits in ~1 s; the actual
                                deletion finishes within the 3 s grace
                                period before the verification ls call)
shortcuts created (default tasks):
   - %PUBLIC%\Desktop\Whisper Project.lnk
   - %ProgramData%\...\Start Menu\Programs\Whisper Project\Whisper Project.lnk
   - %ProgramData%\...\Start Menu\Programs\Whisper Project\Uninstall Whisper Project.lnk
shortcuts removed by uninstall: all three (verified by ls returning
   "No such file or directory" on each path)
smoke E2E from installed exe: 1 passed in 128.06 s, SRT/JSON written
```

## Build commands (reference)

```
# Method A — onefile (unchanged)
python -m PyInstaller --noconfirm --clean whisper_project.spec
#   -> dist\WhisperProject.exe

# Method B — onedir + installer
python -m PyInstaller --noconfirm --clean --distpath dist_onedir whisper_project_onedir.spec
#   -> dist_onedir\WhisperProject\

"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer.iss
#   -> dist_installer\WhisperProject-Setup.exe
```

The installer path needs `/c/Users/Owner/AppData/Local/Programs/Inno Setup 6/ISCC.exe`
on this machine because `winget install JRSoftware.InnoSetup` places it
under `%LOCALAPPDATA%\Programs` rather than `Program Files`.

## Caveats

* The installer is admin-elevated (`PrivilegesRequired=admin`). A
  per-user variant could ship as a separate `.iss` if anyone needs it.
* The installer does not ship a code-signing certificate, so
  SmartScreen will warn end users on first run. Adding signing is a
  release-engineering decision, not part of this packaging session.
* The intermediate `dist_onedir\` is 478 MB on disk and rebuilt from
  scratch by `--clean`; ensure the C: drive has 1–2 GB headroom before
  a fresh build. The leftover `_MEI*` cleanup notes from the Method A
  session still apply — onedir does not produce those, but onefile
  builds in parallel sessions might.
