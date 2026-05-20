# v0.7.1 — Hands-off polish push

Packages the Session-14 hands-off polish push as a tagged release.
Same three install methods, same single source on
`release/v0.7.0-installer-3-options`, every "Remaining work" item
from `docs/HANDOFF_NEXT_SESSION.md` now landed.

## Pick one

| | **Portable** | **Setup-Compact** | **Setup-Standard** |
|---|---|---|---|
| Asset | `WhisperProject-v0.7.1-Portable.exe` | `WhisperProject-v0.7.1-Setup-Compact.exe` | `WhisperProject-v0.7.1-Setup-Standard.exe` |
| Install step | none — double-click | silent ~20 s | silent ~45 s |
| Start-up | ~6 s (every launch unpacks) | ~3 s | ~3 s |
| AV exposure | onefile binaries trigger more false positives | lower | lowest (real CPython on disk) |
| Source-tree visibility for debug | none | none (PyInstaller-bundled) | full — every `.py` is readable |
| Best for | one-off use, USB sticks, easy hand-off | most Windows users | developers and the AV-paranoid |

## What's new in 0.7.1

Twelve high-impact additions land in one tagged release:

- **Filename templating** — `output_filename_template` honoured by every
  writer. Tokens `{base}`, `{ext}`, `{lang}`, `{date}`,
  `{speaker_count}` resolve at write time. Templates may include
  sibling subdirectories (`transcripts/{base}.{ext}`); those folders
  are created on the fly. Malformed templates fall back to the legacy
  layout.

- **Pluggable Whisper backends** — `core/backends/` houses an ABC +
  two implementations. `faster_whisper` (default) preserves the
  CTranslate2 path; `whisper_cpp` (opt-in) drives pywhispercpp on
  quantised ggml models (~1.1 GB for large-v3-q5_0). The Advanced
  dialog grows a backend picker + a "Download whisper.cpp
  model..." button.

- **Word-level alignment refinement (stable-ts)** — opt-in DTW pass
  after the main transcribe. Tightens word boundaries to ±50 ms.
  Available via the Advanced dialog's "Word alignment" dropdown.

- **Transcript viewer enhancements** — `Ctrl+F` Find-and-Replace,
  right-click "Rename speaker (everywhere)", word-confidence colour
  coding (green ≥ 0.85 / amber / red), one-click "Remove fillers"
  (uh / um / er / …), `Ctrl+S` atomic save via the JSON writer.

- **Karaoke-style word highlight** — when VLC is playing, the
  active word in the segment panel is bracketed and the active
  segment row glows. Follows the playhead at 250 ms tick rate.

- **System tray + minimise-to-tray + native toast** — pystray +
  Pillow on a daemon thread. Right-click menu Show / Hide / Exit.
  Icon flips between hollow blue (idle) and red dot (active).
  `config["minimise_to_tray"]` (Advanced dialog) makes
  WM_DELETE_WINDOW hide instead of exit. Completed jobs raise a
  native toast.

- **High-DPI scaling** — Tk scaling now computed from
  `winfo_fpixels('1i')` on launch. Fonts and paddings stop
  shrinking on 125 % / 150 % Windows displays.

- **Anonymous opt-in telemetry** — `config["telemetry_opt_in"]`
  gates both Sentry crash reporting (needs `$SENTRY_DSN`) and a
  one-shot launch ping (needs `$WHISPER_TELEMETRY_URL`). Ping
  carries `{os, version, python, anonymised_id}` only;
  anonymised_id is a SHA-256 of a one-shot UUID4 stashed under
  `user_cache_dir()/telemetry_id`.

- **Auto-resume after crash** — rows the `history.db` flagged
  `interrupted` on the previous run get re-enqueued when their
  source files still exist.

- **Per-folder `.whisperproject.json` overrides** — drop a JSON
  next to (or above) a media file to override the global config
  for that folder. Dict-valued keys (`model`, …) deep-merge one
  level. Bad JSON / non-object roots are silently ignored.

- **Watched-folder UI wiring** — `core.watcher.FolderWatcher` is
  exposed through the Advanced dialog. New media files dropped in
  are stability-checked (size stable for 1.2 s) then auto-enqueued.

- **Windows Explorer "Transcribe with Whisper Project"** — both
  installers ship an optional `shellext` task that registers
  `HKCR\*\shell\WhisperProjectTranscribe`. Right-click any file →
  the existing CLI mode (`WhisperProject.exe transcribe "%1"`)
  picks it up.

## Test coverage

Hermetic unit suite: **237 passing** (was 191 at start of session).
Smoke suite: 3 passes against the freshly built portable exe with
a real 60 s news clip. Pyright clean on `app/` + `core/`.

## Known limitations

- **SmartScreen warning.** None of the three exes are code-signed.
  First-launch shows the standard "Windows protected your PC"
  prompt; click **More info → Run anyway**.
- **First launch is slow on Method A.** Portable unpacks ~260 MB
  to `%TEMP%\_MEI<random>\` on every launch. Methods B and C
  unpack once at install time.
- **stable-ts ships torch.** Enabling word alignment loads a tiny
  Whisper model via stable-ts which transitively pulls torch
  (~125 MB), shipped in Setup-Standard for completeness even when
  the user keeps the default `none` alignment.

## Build and contribute

See [docs/BUILD.md](BUILD.md) for the three build pipelines and
[docs/ROADMAP.md](ROADMAP.md) for where the project is heading.

The full Session-14 narrative + design notes live in
[docs/RELEASE_NOTES_v0.7.0.md](RELEASE_NOTES_v0.7.0.md) under
"Hands-off polish push" — same content, slightly more prose.
