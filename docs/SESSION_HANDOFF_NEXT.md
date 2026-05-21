# Next session — read THIS FIRST

Single-source-of-truth handoff for the next Claude Code session on
this repo. Read this file before anything else.

---

## 1. Current state (2026-05-21)

| Item | Value |
|---|---|
| Branch | `release/v0.7.0-installer-3-options` |
| Last commit | `941b89f` — timer freeze + auto-switch to Transcribe on finish |
| Pushed | ✅ everything is on origin |
| Working tree | clean |
| Release tag | `v0.7.1` on GitHub (three EXEs uploaded) |
| Unit suite | 275 passing |
| Pyright basic | 0 errors, 0 warnings |
| Smoke | 5/5 PASS against real SMTV clip (last verified) |

## 2. What just happened this session (chronological)

1. Two-audit-pass deep debug — 11 blockers + 22 serious issues fixed
   across HistoryDB cross-thread, FolderWatcher RLock, drag-and-drop
   bind, parallel `.part` collision, stop_worker stdin hang,
   writers crashing on numeric speaker, stable-ts shape bug,
   pywhispercpp / stable-ts not bundled, …
2. Released v0.7.1 with bundled pywhispercpp + stable-ts (portable
   grew 262 → 447 MB).
3. UI overhaul of the Transcribe tab — researched MacWhisper / Buzz /
   Aiko / Vibe / OpenWhispr / WhisperUI and rebuilt around a hero
   drop-zone + 3 visible controls + big accent CTA + everything else
   behind "Advanced settings…". Vocabulary cleanup: VAD / compute /
   hotwords / device no longer visible on the main tab.
4. Download tab CTA upgraded to the same Accent + larger pattern.
5. Timer-freeze bug fixed — `task.end_time` field added, wired into
   every terminal transition (finish_task, cancel, cancel_download,
   download finish, error). app.fmt_time freezes the Elapsed column.
6. Auto-switch tabs: Transcribe → Queue on start, Queue → Transcribe
   on finish (so user lands on the Last Result card with file
   paths + Open buttons).

All of the above are committed + pushed.

## 3. What's pending — pick this up first

The user has approved a 3-phase v0.8 roadmap (6 features). The
detailed plan + library / model / effort estimates are in
**`docs/V08_FEATURE_RESEARCH.md`** — read that file second.

### Phase 1 — start HERE in the next session

Light features, no heavy deps. The user wants **2 parallel shards**:

**Shard A** — covers two features that both touch transcriber + UI:
  - **Hallucination detector flag** (S effort)
    * New `core/hallucination.py` — regex repetition + BoH wordlist
      + VAD-disagreement
    * Integrate into `_run_post_pipeline` in `core/transcriber.py`
    * Annotate segments with `seg["suspect"] = True` + reason
    * Make the viewer (`app/dialogs/transcript_viewer.py`) highlight
      suspect rows in red
    * Tests: `tests/core/test_hallucination.py`
  - **Multi-model picker** — turbo + distil-v3.5 only (S effort)
    * Modify `app/dialogs/advanced.py` to add a model dropdown
    * Modify `core/model_manager.py` to handle multiple model paths
    * Add `whisper_model` config key (default: `large-v3` to preserve
      current behavior)
    * faster-whisper supports all three natively — no new adapter
    * Tests: `tests/core/test_model_picker.py`
    * **Parakeet defers to Phase 3** (needs new sherpa-onnx adapter)

**Shard B** — a single self-contained feature:
  - **Hardware autodetect wizard** (M effort)
    * New `app/widgets/hardware_wizard.py` — probe CUDA → QNN/NPU →
      Intel-NPU → OpenVINO → DirectML → CPU int8
    * 5-second benchmark on a bundled clip → real RTF
    * Persist choice in `%LOCALAPPDATA%\WhisperProject\hardware.json`
    * Modify `core/transcriber.py::detect_device` to read that file
    * "Re-detect" button in Advanced dialog
    * Tests: `tests/core/test_hardware_wizard.py`

**Sharding rules**:
  - Each shard has its own test + Pyright + smoke
  - Both shards commit independently (atomic commits per feature)
  - User wants push at the end, not after every commit (this is
    different from the durable rule in CLAUDE.md — confirm with the
    user if doubtful, but the current explicit instruction in
    Phase 1 is "commit, but don't push until the user OKs the UI"
    pattern was for UI work specifically; for Phase 1 functional
    features the standing rule of commit-and-push-immediately may
    apply — ASK IF UNSURE).

### Phase 2 + 3 — deferred

After Phase 1 lands, decide with the user whether to continue in
the same session or spawn a fresh one (context is the deciding
factor). Phase 2 and Phase 3 details are in
`docs/V08_FEATURE_RESEARCH.md`.

## 4. User preferences learned this session (durable)

These should inform every UI / dev decision:

- **Persian responses, English code / docs / comments.** The
  CLAUDE.md global rule already covers this — never write Persian
  in any committed file.
- **Don't push UI-touching commits without explicit user OK.** The
  user wants to test UI changes locally first. (Functional /
  backend changes can push immediately per the durable rule.)
- **Hates jargon in user-facing strings.** VAD / compute_type /
  hotwords / int8_float16 / cuda / device all banned from the
  main canvas. Move them to Advanced dialog or remove entirely.
- **Wants accent-blue (sv_ttk Accent.TButton) for primary CTAs**,
  larger than secondary buttons (ipady=8, ipadx=24).
- **Wants tabs to auto-switch** based on user intent (start → Queue,
  finish → Transcribe). Don't be shy about programmatic tab
  changes.
- **Wants the timer to freeze when a task is done.** `task.end_time`
  is the field; set it on every terminal transition.
- **Hero drop-zone pattern** for file pickers — MacWhisper / Aiko
  style, not the Browse-button-on-a-form style.
- **Likes parallel shards** for substantial work. 2-3 shards in
  parallel is the standing pattern. Always research → implement →
  test → commit per shard.
- **Trusts reflective reasoning.** When asked to think hard, use
  4-layer reflective passes (research → map → design → implement).
- **CI badge URL has `release/v0.7.0-installer-3-options` in it —
  that's the branch name, NOT a stale version reference. Don't
  "fix" it.**

## 5. Key files to know about

| File | Why |
|---|---|
| `CLAUDE.md` | Durable rules for any session (auto-loaded) |
| `docs/V08_FEATURE_RESEARCH.md` | Full v0.8 roadmap with library / model / effort |
| `docs/V09_REMOTE_MODE_RESEARCH.md` | Separate v0.9 cloud-GPU plan (after v0.8) |
| `docs/HANDOFF_NEXT_SESSION.md` | Older general handoff (less specific than this file) |
| `docs/RELEASE_NOTES_v0.7.1.md` | What's in v0.7.1 + audit history |
| `docs/CHANGELOG.md` | Standard changelog (update on release bumps) |

## 6. Sanity-check commands for the next session's first turn

```cmd
cd C:\Users\Owner\Desktop\whisper_project_claude\whisper_project_direct_download_v2
git log --oneline -5
git status
python -m pytest tests/ --ignore=tests/smoke -q | tail -3
pyright app/ core/ | tail -3
```

Expected: branch on `941b89f`, working tree clean, 275 passing,
pyright 0 errors. If anything diverges, something happened between
sessions — pause and investigate.

## 7. The smoke clip that matters

```
tests/fixtures/smtv_clip/AD-The-Most-Powerful-Daily-Prayer-max.mp3
```

91-second English narration. Gitignored but present on disk.
This is the canonical real-audio test for any feature that
touches transcription. Don't re-download unless missing.

## 8. The portable EXE path

```
dist/WhisperProject-v0.7.1-Portable.exe
```

447 MB. Bundles stable-ts + pywhispercpp + faster-whisper + sherpa-onnx
diarization. If you rebuild with PyInstaller, the filename stays the
same (overwrites in place).

## 9. Forbidden actions (from CLAUDE.md, repeated for safety)

- Don't merge to master
- Don't checkout master
- Don't push master
- Don't touch `.git/config`
- Don't run code-signing
- English-only product (no Persian / Arabic / RTL in the UI)

## 10. The 1-line restart prompt

Paste this verbatim to start the next session:

```
Read docs/SESSION_HANDOFF_NEXT.md first, then start Phase 1 of v0.8 with 2 parallel shards as described there.
```
