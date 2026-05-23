# Install

Two paths: run the Setup installer, or run from source.

## Setup-Standard installer (Windows)

1. Grab `WhisperProjectBasic-v0.1.0-Setup.exe` from a release (or
   build it locally — see below).
2. Double-click. Click **Yes** on the UAC prompt.
3. Confirm the install location (default `C:\Program Files\WhisperProjectBasic\`).
4. Optionally tick "Create a desktop icon".
5. Click **Install**.

After install, launch from the Start Menu under **Whisper
Project (basic)** or from the desktop icon. The first launch
shows a hub-folder picker — accept the default (next to the
install) or pick a folder on a roomy drive. The first
**Transcribe** click triggers a one-off ~3 GB model download.

The installer ships a full Python interpreter on disk so the
source tree is browsable under
`C:\Program Files\WhisperProjectBasic\app\` and `\core\`. There
is no frozen `.exe` — friendly for debugging and local patching.

Uninstall from **Settings → Apps → Whisper Project (basic) →
Uninstall** or via the install folder's `unins000.exe`. If your
hub folder lives outside the install directory, the uninstaller
asks before deleting the (potentially multi-GB) model files.

## From source

Python 3.11 or 3.12.

```
git clone https://github.com/Milomilo777/whisper-project.git
cd whisper-project
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python gui.py
```

## Build the installer yourself

Prerequisite: install Inno Setup 6 (`winget install JRSoftware.InnoSetup`).

```cmd
build_embed_installer.bat
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer_embed.iss
```

`build_embed_installer.bat` downloads CPython 3.11 from
[python-build-standalone](https://github.com/astral-sh/python-build-standalone),
pip-installs `requirements.txt` into the bundle, copies `app/` +
`core/` + `bin/` + `gui.py` in, writes a `sitecustomize.py` so
the embedded interpreter finds its `Lib\site-packages\` on
launch, and runs a sanity import. Then Inno Setup wraps the
~250 MB `embed_build\` tree into a ~80 MB compressed installer.

Output: `dist_installer\WhisperProjectBasic-v0.1.0-Setup.exe`.

## CUDA (optional)

If you have an NVIDIA GPU and want to use it, install the matching CUDA + cuDNN runtime libraries. faster-whisper picks them up automatically; the hardware probe will switch the app from CPU to CUDA on the next launch.

For a self-contained CUDA wheel pair:

```
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

If the libraries are missing or the wrong version, the app falls back to CPU silently. Run **Help → Diagnose** to see exactly which device was picked.

## Where files live

Per Windows / macOS / Linux conventions via `platformdirs`:

- Config — `<user_config_dir>/WhisperProjectBasic/config.json`
- Logs — `<user_log_dir>/WhisperProjectBasic/app.log` (5 MB, 3-file rotation)
- Model — under `<hub_folder>/models--Systran--faster-whisper-large-v3/` (default hub: `<app_dir>/hub`)

Output `.srt`, `.json`, `.txt` are written **next to the source media file**, not into a separate folder.
