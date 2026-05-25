# Whisper Project on macOS

> Status: **groundwork, not yet validated on a real Mac.** The code is
> cross-platform and the scripts follow current best practice for unsigned
> apps, but no one has run them on macOS yet — treat as beta and report back.

The app is plain Python (Tkinter + faster-whisper + yt-dlp + ffmpeg), so it
runs from source on macOS. It is **unsigned** (no paid Apple Developer
certificate), so macOS Gatekeeper needs a one-time nudge — see below.

## Install

You need Python 3.11+ **with Tk**. The easiest is the official installer
from <https://www.python.org/downloads/macos/> (it bundles Tk). With
Homebrew instead: `brew install python python-tk`.

Get the repo **via Terminal** (this matters — see Gatekeeper note), then run
the installer:

```bash
git clone https://github.com/Milomilo777/whisper_project_direct_download_v2.git
cd whisper_project_direct_download_v2
bash platform/macos/install.command
```

The installer makes a `.venv`, installs the deps + `yt-dlp`, gets `ffmpeg`
(Homebrew if present, else a static build into `bin/`), and creates:
- `~/Applications/Whisper Project.command` — double-click to launch the GUI;
- `~/.local/bin/whisper-transcribe` — headless CLI for servers.

## Gatekeeper (unsigned app) — why and how

macOS tags files **downloaded by a browser** with a `com.apple.quarantine`
flag; Gatekeeper then blocks unsigned apps from opening. Three ways through,
cleanest first:

1. **Get the code without quarantine.** Files fetched via `git clone` or
   `curl` are *not* quarantined, so the launchers just work. This is why the
   install steps use `git clone`.
2. **Strip the flag** (if you did download a zip in a browser):
   ```bash
   xattr -dr com.apple.quarantine /path/to/whisper_project_direct_download_v2
   ```
   or just run `bash platform/macos/unblock.command`.
3. **Open Anyway.** Try to open the launcher, dismiss the warning, then
   **System Settings → Privacy & Security → scroll down → "Open Anyway"**.
   (On macOS 15 Sequoia the old right-click→Open shortcut was removed; use
   the Settings route.)

Do **not** disable Gatekeeper globally (`spctl --master-disable`) — it's a
system-wide security downgrade and unnecessary here.

## Headless / server use

```bash
whisper-transcribe /path/to/media.mp4 --formats srt json --language en
```

## Notes / what still needs a real Mac

- The static-ffmpeg fallback uses evermeet.cx; Homebrew's `ffmpeg` is
  preferred when available.
- The embedded VLC preview needs VLC at `/Applications/VLC.app` (the app
  now looks there); without it the transcript viewer is read-only.
- Apple-silicon vs Intel: faster-whisper/ctranslate2 ship arm64 + x86_64
  wheels, so both should work, but neither has been run here yet.
- A signed/notarized `.app` would remove the Gatekeeper step entirely but
  needs a paid Apple Developer account — out of scope for now.

## References (Gatekeeper / unsigned distribution)

- Removing the quarantine attribute (`xattr -dr com.apple.quarantine`) and
  the "Open Anyway" flow — standard, widely documented.
- Distributing via Homebrew, or fetching with `curl`/`git` (no quarantine),
  is the common workaround for unsigned OSS apps.
