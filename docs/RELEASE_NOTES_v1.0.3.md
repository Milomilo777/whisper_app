# Whisper Project v1.0.3

A small UX + memory release. Two collaborator-driven changes:

1. **Time-range video download** — grab only the slice you need.
2. **Lazy Whisper-model load** — no more ~2 GB of RAM held idle
   from the moment the app opens.

This release continues to skip the Setup-Compact installer.
Portable + Setup-Standard between them cover every install
scenario.

---

## What's new

### Download only the slice you need

A new "Time range (optional)" panel on the Download tab. Fill
**Start** and **End** in `H:MM:SS`, `MM:SS`, or seconds, and
yt-dlp's `--download-sections` fetches only that segment.

Example: paste a 2-hour talk, type `Start = 0:00:51` and
`End = 0:01:25`, hit Download — you get a 34-second MP4. The
auto-transcribe pass (if enabled) then runs on that 34-second
file, not the full 2 hours. The savings are mostly on the
transcription side: Whisper on a 34-second slice finishes in
seconds, even on CPU.

Leave the fields blank for the previous full-video behaviour.
The Queue row shows a `trim 0:51 → 1:25` badge when a range is
active, so you can tell the partial jobs from the full ones at a
glance.

Supreme Master TV URLs are **not** sliced in this release. The
SMTV scraper downloads via plain HTTP and has no slicing path;
if you enter a range against an SMTV URL, the app logs a clear
warning and downloads the full clip. Adding ffmpeg-based range
download for SMTV is on the next-session list.

### The app no longer preloads the model on launch

**Old:** every launch immediately spawned a worker subprocess
and loaded the 3 GB Whisper model in the background, so the
first transcribe was instant. Cost: ~2 GB of RAM held idle from
the moment the window opened — whether or not you ever clicked
Transcribe.

**New:** the worker spawn is deferred to the first transcribe
request. You click Transcribe, a small modal "Loading Whisper
model…" dialog appears with an indeterminate progressbar, the
worker loads the model (a few seconds on SSD + decent CPU),
the dialog dismisses, the transcribe runs. Subsequent
transcribes in the same session are instant — only the first
one pays the load.

The modal explicitly grabs focus (the app "freezes" while it's
up) so you know something's happening rather than wondering if
the click registered. You can Cancel the load; nothing else is
affected.

Crash-resume and watched-folder enqueues go through the same
gate without showing a modal — they wait headless with a 120-
second timeout, so a background auto-dispatch doesn't pop a
dialog in your face.

---

## Upgrade notes

No migration required. Config schema unchanged. The first
transcribe of every session now takes a few extra seconds — the
trade for ~2 GB of RAM you weren't using.

---

## Quality bar

| Metric | Result |
|---|---|
| pyright `app/ core/` | 0 errors, 0 warnings, 0 informations |
| Unit + integration suite | 578 tests passing |
| Real-file end-to-end (SMTV clip) | 10/10 |
| Smoke + end-to-end (Whisper model) | 7/7 |

---

## Deliverables

| Asset | Size | Best for |
|---|---|---|
| `WhisperProject-v1.0.3-Portable.exe` | ~447 MB | one file, no install |
| `WhisperProject-v1.0.3-Setup-Standard.exe` | ~349 MB | proper installer — Python visible on disk |

Setup-Compact is intentionally skipped — between Portable and
Setup-Standard there is no audience Compact uniquely served.

Step-by-step install: [INSTALL.md](INSTALL.md).
