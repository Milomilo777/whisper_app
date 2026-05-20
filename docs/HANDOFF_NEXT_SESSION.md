# Handoff for the next hands-off session

Branch is `release/v0.7.0-installer-3-options`. Built artifacts on
the v0.7.0 GitHub release are in sync with the branch HEAD.

The previous hands-off session (Session 14) cleared every item in
the original `Remaining work` list. The repo is feature-complete
for v0.7.0; this doc is now a reference for what *was* shipped and
where future work plugs in.

## Where things stand

### Done in Sessions 12 + 13 + 14 + this session

  ✓ Diarization (sherpa-onnx, no HF token)
  ✓ In-app transcript viewer (split-pane + python-vlc fallback)
  ✓ DOCX + Markdown + PDF writers
  ✓ Drag-and-drop (tkinterdnd2)
  ✓ Recent files menu (history.db)
  ✓ Window geometry persistence
  ✓ Multi-file Browse...
  ✓ Keyboard shortcuts (Ctrl+O, Ctrl+Enter, Esc, Ctrl+Q, Ctrl+F, Ctrl+S)
  ✓ Last Result card with View transcript + Burn subtitles +
    Open folder buttons
  ✓ Queue row icons (✓ ▶ ⋯ ⊘ ✗)
  ✓ Queue row double-click → open folder
  ✓ Queue right-click → Burn subtitles
  ✓ Window title shows live progress
  ✓ Chime on completion + View menu toggle
  ✓ About dialog with version + GitHub URL
  ✓ Empty-state hints on Queue + Last Result
  ✓ Friendlier user-facing strings
  ✓ Per-file language picker on Transcribe tab
  ✓ Device picker (auto/cpu/cuda)
  ✓ Compute-type picker (int8/int8_float16/float16/float32)
  ✓ Inline hotwords entry
  ✓ YouTube/HTTP URL detection on Transcribe-tab file field
  ✓ CLI mode (`gui.py transcribe FILE`)
  ✓ Watched-folder watcher class + Advanced-dialog UI wiring
  ✓ ffmpeg burn-subs helper + Queue right-click integration
  ✓ Atomic SRT/JSON writes
  ✓ App typed attribute block (Pyright clean)
  ✓ History-narrowed access pattern
  ✓ Graceful worker shutdown
  ✓ JSON-stdio worker defensive emit fallback
  ✓ SMTV E2E live-network test
  ✓ Live SMTV download test
  ✓ GitHub Actions CI (Win + Ubuntu × py3.11+3.12, xvfb on Linux)
  ✓ CODE_OF_CONDUCT.md + issue templates + PR template
  ✓ tests/fixtures/sample.wav (1 s 16 kHz silence, generator
    script committed too)
  ✓ Coverage + CI badges in README
  ✓ English-only scope correction

### Session-14 deliveries (this hands-off run)

  ✓ A1 — Filename templating (`{base} {ext} {lang} {date} {speaker_count}`)
  ✓ A2 — whisper.cpp backend via pywhispercpp (opt-in)
  ✓ A3 — stable-ts word-level alignment (opt-in post-process)
  ✓ B1 — Viewer: find/replace, speaker rename, confidence colour
    coding, filler-word removal, save-changes via JSON writer
  ✓ B2 — Karaoke-style word highlight follows VLC playhead
  ✓ C1 — System tray + minimise-to-tray + idle/active icon flip
  ✓ C2 — Native toast on completion via pystray.Icon.notify
  ✓ C3 — High-DPI scaling computed from system DPI
  ✓ C4 — Sentry crash reporting + launch ping (both opt-in)
  ✓ D1 — Auto-resume after crash (history.db `interrupted` rows)
  ✓ D2 — Per-folder `.whisperproject.json` overrides
  ✓ E1 — Windows Explorer right-click "Transcribe with Whisper Project"
  ✓ Watched-folder UI wiring (G4 leftover)
  ✓ Specs hiddenimports updated; deliverables rebuilt
  ✓ Release v0.7.0 refreshed

### Out of scope for v0.7.0 — recorded in ROADMAP §5–6

The following deferred items already had their design notes in
the previous handoff. Pull them into a v0.8.0 plan when the
priorities surface again. Each is XL-effort and warrants its own
session.

  - **A4 / whisper-stack experiments**: WhisperX (700 MB PyTorch +
    pyannote), Insanely-Fast-Whisper (GPU-only, BetterTransformer +
    FlashAttention-2), NeMo Parakeet / Canary (600 MB NVIDIA NeMo),
    SenseVoice (Chinese-focused, out of scope for English-only),
    Demucs voice separation (heavy PyTorch dep, only useful on
    noisy / music-heavy content).
  - **E2 niche video site scrapers**: mirror the
    `core/integrations/smtv.py` pattern when a new target site is
    requested.
  - **F1 live mic transcription**: ROADMAP §5.1c sketches the
    system-wide dictation hotkey version. Simpler "click a button
    and talk for 30 s" version is also captured there.

If you take on F1, the smallest viable change is `sounddevice`
dep + a single "Live transcribe" button on the Transcribe tab
that spawns a fixed-duration recording, then runs Whisper on the
saved WAV.

## Build pipeline reminders

Three deliverables, all rebuilt by:

```
pyinstaller --noconfirm --clean whisper_project_onefile.spec
pyinstaller --noconfirm --clean --distpath dist_onedir whisper_project_onedir.spec
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer.iss
build_embed_installer.bat
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer_embed.iss
```

Both specs need every new module added to `hiddenimports`. The
embed installer pulls dependencies via the bundled pip-install
step in `build_embed_installer.bat`.

The diarization ONNX models live in `bin/diarization/`
(gitignored). Use `tools/download_diarization_models.bat`
to fetch them on a fresh dev machine before building.

## Tests

  - Unit suite: 246 passing. Run with
    `python -m pytest tests/ --ignore=tests/smoke`.
  - Smoke suite uses real local resources (Whisper model,
    test video at `E:\3029-NWN-Daily-Scroll-2m_0002.mp4`).
    Skip on machines without them.
  - Live SMTV smokes hit the real CDN; skip via
    `WHISPER_OFFLINE_TESTS=1`.

## Release management

The v0.7.0 tag has been force-moved multiple times this and
last session as the underlying bytes evolved. Don't be afraid
to move it again — the user explicitly authorised it. The
process is:

```
git tag -fa v0.7.0 -m "..."
git push --force origin refs/tags/v0.7.0
gh release upload v0.7.0 dist/*.exe dist_installer/*.exe --clobber
gh release edit v0.7.0 --notes-file docs/RELEASE_NOTES_v0.7.0.md
```

### Alternative release strategy (deferred)

We currently ship a NEW tag + NEW GitHub release per version bump
(v0.7.0 stays, v0.7.1 is a fresh release). A future session may
prefer the GitHub-only force-move strategy: keep a single moving
tag and force-update the same GitHub release on every refresh —
simpler asset URLs, cleaner Releases page, but loses version
history. Not done yet; record the trade-off here so the next
session has the choice in front of them.

## Forbidden actions (still hold from earlier prompts)

  - Don't merge to master.
  - Don't checkout master.
  - Don't push master.
  - Don't touch `.git/config`.
  - Don't run code-signing.
  - English-only — no i18n, no RTL, no Persian section in
    INSTALL.md.

## The 2-line restart prompt

Paste this verbatim to start the next session:

```
ادامه برنچ release/v0.7.0-installer-3-options را پیش ببر طبق docs/HANDOFF_NEXT_SESSION.md — همه آیتم‌های "Remaining work" را به ترتیب با کیفیت بالا پیاده کن، تست واقعی بگیر، کامیت و پوش کن، رلیز را آپدیت کن. هیچ سوالی از من نپرس، تا انتها هندزفری پیش برو.
```
