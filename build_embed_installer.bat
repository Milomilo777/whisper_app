@echo off
setlocal EnableDelayedExpansion
REM build_embed_installer.bat — produce the embed_build\ tree that
REM installer_embed.iss turns into WhisperProject-vX.Y.Z-Setup-Standard.exe.
REM
REM Why python-build-standalone, not python.org's embeddable zip:
REM the embeddable distro ships *without* tkinter and the Tcl/Tk
REM runtime, which the UI needs. python-build-standalone's
REM "install_only" tarball is a full CPython install (Lib/, DLLs/,
REM tcl/, Scripts/) suitable for embedding, including tkinter.
REM
REM Output layout under embed_build\ at the end:
REM   python\python.exe         — CPython 3.11 interpreter
REM   python\pythonw.exe        — windowed launcher used by shortcuts
REM   python\Lib\               — full stdlib including tkinter
REM   python\DLLs\              — _tkinter.pyd, native deps
REM   python\tcl\               — Tcl runtime
REM   Lib\site-packages\        — runtime deps from requirements.txt
REM   app\                      — Tk UI package
REM   core\                     — transcription / download / paths modules
REM   bin\                      — ffmpeg.exe, ffprobe.exe, yt-dlp.exe
REM   gui.py                    — entry point (pythonw gui.py)

set ROOT=%~dp0
set BUILD=%ROOT%embed_build
set PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe
set PYBSD_VER=3.11.15
set PYBSD_TAG=20260510
set ASSET=cpython-%PYBSD_VER%+%PYBSD_TAG%-x86_64-pc-windows-msvc-install_only.tar.gz
set URL=https://github.com/astral-sh/python-build-standalone/releases/download/%PYBSD_TAG%/%ASSET%

if exist "%BUILD%" rmdir /S /Q "%BUILD%"
mkdir "%BUILD%"

echo [embed] downloading %ASSET%
"%PS%" -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri '%URL%' -OutFile '%BUILD%\python.tar.gz'"
if errorlevel 1 (
  echo [embed] download failed
  exit /b 1
)

echo [embed] extracting Python install_only tarball
REM Use the Windows system tar (bsdtar). Git's tar misinterprets "C:"
REM as a remote-host argument and fails with "Cannot connect to C:".
"%SystemRoot%\System32\tar.exe" -xzf "%BUILD%\python.tar.gz" -C "%BUILD%"
if errorlevel 1 (
  echo [embed] tar extract failed
  exit /b 2
)
del "%BUILD%\python.tar.gz"

echo [embed] verifying tkinter is present in the extracted distro
"%BUILD%\python\python.exe" -c "import tkinter; print('tkinter version', tkinter.TkVersion)"
if errorlevel 1 (
  echo [embed] tkinter not importable — wrong distro variant?
  exit /b 3
)

echo [embed] installing runtime requirements into Lib\site-packages
mkdir "%BUILD%\Lib"
"%BUILD%\python\python.exe" -m pip install --no-warn-script-location --target "%BUILD%\Lib\site-packages" -r "%ROOT%requirements.txt"
if errorlevel 1 (
  echo [embed] pip install failed
  exit /b 4
)

echo [embed] copying source tree
xcopy /E /I /Y "%ROOT%app" "%BUILD%\app" >nul
xcopy /E /I /Y "%ROOT%core" "%BUILD%\core" >nul
xcopy /E /I /Y "%ROOT%bin" "%BUILD%\bin" >nul
copy "%ROOT%gui.py" "%BUILD%\" >nul

echo [embed] writing sitecustomize.py to teach python where site-packages lives
> "%BUILD%\python\Lib\sitecustomize.py" echo import sys, os
>> "%BUILD%\python\Lib\sitecustomize.py" echo _here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
>> "%BUILD%\python\Lib\sitecustomize.py" echo _site = os.path.join(_here, "Lib", "site-packages")
>> "%BUILD%\python\Lib\sitecustomize.py" echo if os.path.isdir(_site) and _site not in sys.path:
>> "%BUILD%\python\Lib\sitecustomize.py" echo     sys.path.insert(0, _site)

echo [embed] sanity import check (full stack)
"%BUILD%\python\python.exe" -c "import faster_whisper, ctranslate2, sv_ttk, platformdirs, tkinter; print('embed_import_ok')"
if errorlevel 1 (
  echo [embed] sanity import failed — bundle is incomplete
  exit /b 5
)

echo [embed] verifying gui.py worker entry point parses
"%BUILD%\python\python.exe" -c "import ast; ast.parse(open(r'%BUILD%\gui.py').read())"
if errorlevel 1 (
  echo [embed] gui.py parse failed
  exit /b 6
)

echo [embed] build complete: %BUILD%
exit /b 0
