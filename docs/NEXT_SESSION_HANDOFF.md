# Next session — handoff briefing

You're the eighth architect (or beyond). This file is your two-minute briefing. Read it before anything else. Then choose your scope, then read the corresponding deep-context file.

---

## Where the repo stands

- **Current head:** `master` on `origin`, latest commit visible with `git log --oneline -1`
- **Branches:** exactly one — `master`. Don't make new ones.
- **Tags:** `archive/phase-0-baseline` (historical, on commit `50a4fea`). Don't delete.
- **Latest tested state:** all 137 unit tests pass, 77% coverage on `core/`, PyInstaller `dist/WhisperProject/WhisperProject.exe` builds and smoke-launches for ≥ 5 s.
- **What's done (high-level):** Phases 0 + 1a + 1b + 2a + 2-oTranscribe + 3a + final compile + research notes + architecture diagrams. See `docs/SESSION_LOG.md` for the full narrative of seven prior sessions.
- **No release tag yet.** User has parked the `v0.5.0` decision; don't tag without asking.

---

## First 60 seconds — orient yourself

```bash
cd "C:/Users/Owner/Desktop/whisper_project_claude/whisper_project_direct_download_v2"
git status                                  # must be clean
git log --oneline -10                       # see the recent sessions
git remote -v                               # origin should be the only remote
python -m pytest tests/ -q                  # 137 pass, no failures
test -f docs/PHASE_NEXT_BRIEF.md && echo "OLD BRIEF STILL THERE"   # may be stale; OK
```

Then open these in this order:

1. `README.md` — project orientation
2. `docs/architecture-diagrams.md` — visual system overview (Mermaid + SVG)
3. `docs/SESSION_LOG.md` — narrative of what every prior session did and decided
4. `docs/ROADMAP.md` — Progress snapshot table at the top
5. `docs/COMPETITIVE_ANALYSIS_2026.md` — what 2026 STT looks like, what we should add

If you want the prose architecture: `docs/ARCHITECTURE.md`. If you want the audit findings: `docs/AUDIT.md`. If you want the build pipeline: `docs/BUILD.md`. Each acceptance plan lives at `docs/PHASE_<N>_ACCEPTANCE.md`.

---

## What the user has not yet decided

The user has been asked to pick the next implementation phase. The candidates, ranked by impact-per-effort:

| Phase | Effort | Why it matters now |
|---|---|---|
| **6.2 Chinese punctuation post-processor** | S | 94% of the user's audio is Chinese; current output is wall-of-text. Biggest single CJK quality lift. |
| **6.3 CJK-aware line splitting** | S | 42-char Latin default is wrong for Chinese; Netflix style is ~16 zh-Hans / ~20 zh-Hant glyphs. Small change, immediate readability win. |
| **6.4 Simplified ↔ Traditional via OpenCC** | XS | One dependency, one setting, one post-processor. Fixes mid-file drift. |
| **6.1 Pluggable transcription backends** | L | Unlocks SenseVoice (CJK) and Parakeet-TDT (EU langs) without losing faster-whisper baseline. Bigger commitment but highest ceiling. |
| **4.1 In-app transcript editor** | L | Unique competitive position (Descript-style click-word → audio). |
| **5.1 Diarization via pyannote** | L | Prerequisite for editor's speaker-rename feature (4.4). |
| **6.7 stable-ts integration** | S | Word-perfect timestamps for free as a drop-in for faster-whisper. Enables 4.1. |

The brief for each phase has not been written yet. When the user picks, draft a `docs/PHASE_<N.M>_BRIEF.md` modeled on `docs/PHASE_NEXT_BRIEF.md` (Phase 1b+2a+3a) or `docs/integrations/otranscribe-brief.md` (single-feature), then run it.

---

## Hard rules you must respect

1. **Single branch `master`.** No new branches, no rebases, no force-push, no amends.
2. **No tokens in code, commits, or config.** Use the host credential helper (Windows Credential Manager via GitHub Desktop). The user has had two token leaks already; do not be the source of a third.
3. **`bin/` is gitignored.** Never commit `ffmpeg.exe`, `ffprobe.exe`, `yt-dlp.exe`. They are vendored separately and PyInstaller copies them via `whisper_project.spec` + `build.bat`'s `xcopy` fallback.
4. **`config.json` lives in `%LOCALAPPDATA%\WhisperProject\`**, not next to the executable. Don't ever copy it to `dist/`. Phase 1.2 handled the migration.
5. **Worker `core/worker.py` JSON stdio protocol is sacred.** Add fields freely; never remove or rename. The parent `app/services/transcription_service.py` depends on the event shape.
6. **Tk is single-threaded.** Only the `poll_*` methods on the App may touch widgets. Services produce events; the App polls them. This is documented in `docs/ARCHITECTURE.md` "Threading rules."
7. **Re-run all prior acceptance suites at every phase boundary.** Phase 0, 1, 1b, 2a, 2-oTranscribe, 3a. Fix regressions in a `Phase NX hotfix:` commit before pushing.
8. **Append a new Session N entry to `docs/SESSION_LOG.md`** at the end of your session. Append-only.
9. **Don't release.** The user controls `git tag v*.*.*` and `git push origin v*.*.*`. Recipe is in `MANUAL_STEPS.md` Section B.

---

## What's explicitly out of scope right now

- **Persian / Arabic / RTL.** Removed in Session 6 — user's audience is 94% Chinese plus EN/FR/DE. No bidirectional text features.
- **Cloud LLM calls as default.** "Bring-your-own-key" for Ollama / Claude / GPT is a Phase 7 backlog item, off-by-default.
- **Mobile.** Different problem domain; the Seal Android app owns yt-dlp-on-mobile.
- **Real-time streaming / live-mic.** Backlog Phase 5.3.
- **Cloud transcription.** Project identity is offline. No OpenAI Whisper API toggle.

---

## What you CAN and SHOULD do

- Pick **one phase** from the candidate table above.
- Write a `docs/PHASE_<N.M>_BRIEF.md` for it (modeled on `docs/PHASE_NEXT_BRIEF.md`).
- Implement it incrementally with one commit per logical unit.
- Write tests alongside; aim for the existing 77% coverage target.
- Re-run every prior acceptance suite.
- Push to `origin/master` after acceptance, before declaring done.
- Append a `Session N+1` entry to `docs/SESSION_LOG.md` and update `docs/CHANGELOG.md` Unreleased.
- If you find a new CRITICAL or HIGH issue, add a row to `docs/AUDIT.md` and fix it.

---

## Where to look when something feels weird

| Symptom | First file to open |
|---|---|
| Code doesn't behave like the docs say | `git log --oneline -- <file>` to see what changed |
| Don't know which service does what | `docs/architecture-diagrams.md` Mermaid view |
| Want full file paths and process model | `docs/architecture.svg` |
| Test fails but I didn't change the code | `docs/PHASE_*_ACCEPTANCE.md` for that phase |
| Build fails | `docs/BUILD.md` exit codes |
| Worker subprocess hangs | `core/worker.py` + `app/services/transcription_service.py` |
| Auto-transcribe not enqueuing | `app/services/download_service.py` end-of-job branch + `tests/core/test_auto_transcribe_wiring.py` |
| oTranscribe round-trip breaks | `docs/integrations/otranscribe-research.md` schema section |
| Why we chose subprocess workers (or anything else load-bearing) | `docs/DECISIONS.md` ADRs |

---

## Files you should NOT touch

- `bin/` contents — vendored, gitignored
- `archive/phase-0-baseline` tag — historical pointer
- The four oTranscribe files in `docs/integrations/` unless you're actually extending the integration
- `config.json.migrated.bak` and `config.json.corrupt` — automatic migration / quarantine artifacts, gitignored
- Anything under `dist/`, `build/`, `build_logs/`, `.coverage`, `.pytest_cache/` — all gitignored

---

## One paragraph the user can repeat to start your session

> You are the next architect on the whisper_project_direct_download_v2 repository. Read docs/NEXT_SESSION_HANDOFF.md from start to finish, then docs/SESSION_LOG.md, then docs/ROADMAP.md. Then ask the user which Phase from the candidate table you should ship. Once they pick, draft a docs/PHASE_<N.M>_BRIEF.md and execute it hands-off, on master, with commits per unit, push after acceptance. Append a Session N+1 entry to docs/SESSION_LOG.md. Do not release; do not embed tokens; do not create branches; do not rewrite history.

That's the whole briefing. Good luck.
