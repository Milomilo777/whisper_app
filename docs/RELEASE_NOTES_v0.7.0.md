# v0.7.0 — Three installation options

This release ships three independent installation methods. Pick the
one that fits your machine and your priorities — they're all built
from the same source on the same branch
(`release/v0.7.0-installer-3-options`).

## Pick one

| | **Portable** | **Setup-Compact** | **Setup-Standard** |
|---|---|---|---|
| Asset | `WhisperProject-v0.7.0-Portable.exe` | `WhisperProject-v0.7.0-Setup-Compact.exe` | `WhisperProject-v0.7.0-Setup-Standard.exe` |
| Size on disk | 190.8 MB | 137.2 MB | 153.6 MB |
| Install step | none — double-click | silent ~20 s | silent ~45 s |
| Start-up | ~6 s (every launch unpacks) | ~3 s | ~3 s |
| Disk footprint after install | n/a (runs from %TEMP%) | ~470 MB | ~660 MB |
| AV exposure | onefile binaries trigger more false positives | lower | lowest (real CPython on disk) |
| Source-tree visibility for debug | none | none (PyInstaller-bundled) | full — every `.py` is readable |
| Best for | one-off use, USB sticks, easy hand-off | most Windows users | developers and the AV-paranoid |

## What's new in 0.7.0

- **Three install methods, one source.** v0.7.0 is the first release
  to publish Portable + Compact + Standard side by side.
- **Supreme Master TV download** (Session 11). Paste any
  `/v/<id>.html` episode URL into the Download tab to pull the page's
  HD 1080p / 720p / 396p MP4 or its direct MP3. Multi-part series get
  a "Download all parts" checkbox; the page transcript saves as
  `<base>.txt` next to the media.
- **Per-method clean-machine verification.** Every artefact in this
  release was tested by silent-installing to a clean temp location
  on a Windows machine and running the real-video transcribe smoke
  test from that location.

## How to choose

- **One-off transcription** or running off a USB stick → **Portable**.
- **Daily driver, normal Windows machine** → **Setup-Compact**. Best
  start-up time and disk footprint.
- **Developer machine** or you want to inspect what's actually
  running → **Setup-Standard**. The full Python source tree lives
  on disk under the install dir and is open to read or patch.

## Whisper model

Unchanged from v0.6.0: the 3 GB faster-whisper-large-v3 model is
fetched from a CDN mirror on first launch and cached under
`%LOCALAPPDATA%\WhisperProject\Cache\models\`. No internet needed
for transcription after that.

## Tested on

- Windows 10 x64 (build 19045)
- Windows 11 x64 (assumed equivalent — the build matrix has no
  Windows-version-specific code paths)
- Real-video smoke: `E:\3029-NWN-Daily-Scroll-2m_0002.mp4` (60 s
  English news clip) transcribed end-to-end on all three install
  flavours, producing byte-identical SRT (860 B) and JSON (1117 B).

## Known limitations

- **SmartScreen warning.** None of the three exes are code-signed.
  First-launch shows the standard "Windows protected your PC"
  prompt; click **More info → Run anyway**.
- **First launch is slow on Method A.** Portable unpacks ~190 MB
  to `%TEMP%\_MEI<random>\` on every launch. Methods B and C unpack
  once at install time.
- **Method C uninstall leaves behind any user-edited file under
  the install directory.** The Inno script sweeps `__pycache__` and
  the install subdirectories on uninstall, but it cannot know about
  files a curious user might have added.

## Build and contribute

See [docs/BUILD.md](BUILD.md) for the three build pipelines and
[docs/ROADMAP.md](ROADMAP.md) for where the project is heading.
