# Install

Two paths: run the portable exe, or run from source.

## Portable exe (Windows)

1. Grab `WhisperProjectBasic-Portable.exe` from a release (or build it locally — see below).
2. Double-click.
3. On the first launch you'll see a hub-folder picker. Either accept the default (next to the exe) or pick a folder on a roomy drive.
4. Drop a media file into the window, click **Transcribe**. The first click triggers a one-off ~3 GB model download.

The exe is fully self-contained: it bundles ffmpeg, ffprobe, and the Python runtime. No system installation needed.

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

## Build the portable exe yourself

```
pip install pyinstaller
pyinstaller --noconfirm --clean whisper_project_basic.spec
```

Output lands in `dist/WhisperProjectBasic-Portable.exe`.

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
