# Next session — read THIS FIRST

Single-source-of-truth handoff for the next Claude Code session on
this repo. Read this file before anything else.

---

## 1. Current state (2026-05-21, end of v0.8 Phase 1 session)

| Item | Value |
|---|---|
| Branch | `release/v0.7.0-installer-3-options` |
| Last commit | `fb45094` — v0.8 Shard B (hardware autodetect wizard) |
| Pushed | ✅ everything is on origin |
| Working tree | clean |
| Release tag | `v0.7.1` on GitHub (three EXEs uploaded) |
| Unit suite | 337 passing (+62 from v0.8 Phase 1) |
| Pyright basic | 0 errors, 0 warnings |
| Smoke | 7/7 PASS against real SMTV clip (last verified end of Phase 1) |

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

The user has approved a 3-phase v0.8 roadmap. Phase 1 LANDED in
this session (commits `dbe7de9` + `fb45094`). The detailed plan +
library / model / effort estimates for Phases 2 + 3 are in
**`docs/V08_FEATURE_RESEARCH.md`** — read that file second.

### Phase 1 — DONE this session ✅

**Shard A — `dbe7de9`** (hallucination detector + multi-model picker)
  - `core/hallucination.py` — BoH + 1/2/3-gram repetition + optional
    VAD-disagreement; wires into `_run_post_pipeline`; toggleable via
    `config["hallucination_detect_enabled"]` (default ON).
  - Transcript viewer highlights suspect rows with a light-red row
    background (`tag_configure("suspect", background="#ffe0e0")`).
  - `core/model_manager.MODEL_REGISTRY` — Large v3 (default), Large
    v3 Turbo, Distil Large v3.5. `whisper_model` config key.
  - Advanced dialog gains a model dropdown + hallucination checkbox.
  - 60 new unit tests; all 320 (Shard A) passing at this commit.

**Shard B — `fb45094`** (hardware autodetect wizard)
  - `core/hardware.py` — Tk-free probe layer (CUDA → QNN → OpenVINO
    NPU/GPU → DirectML → CPU int8) + atomic `hardware.json` round
    trip + CUDA re-validation at load.
  - `app/widgets/hardware_wizard.py` — modal Treeview UI with
    Re-probe + Run-5s-benchmark + Save-and-use buttons.
  - `core.transcriber.detect_device` reads `hardware.json` first
    when `device == "auto"`.
  - "Re-detect hardware…" button in Advanced dialog.
  - 17 new unit tests; all 337 passing at this commit.

End-of-Phase-1 verification (this session):
  - pyright app/ core/ → 0 errors, 0 warnings.
  - pytest tests/ (excl. smoke) → 337/337.
  - pytest test_transcribe_smoke + test_transcribe_end_to_end → 7/7
    (real Whisper model + real audio).

### Phase 2 — pick this up next

Live + capture (M effort, opt-in download for the AI layer model).
See `docs/V08_FEATURE_RESEARCH.md` § "Track 1 — Live & Capture" and
§ "Track 2 — AI Layer".

Headline features:
  - **Live mic streaming** via RealtimeSTT (MIT) on top of the
    existing `WhisperModel` instance + Silero/WebRTC VAD.
  - **System audio capture** via WASAPI loopback (`soundcard` or
    `pyaudiowpatch`).
  - **Local LLM panel** — llama-cpp-python + Qwen2.5-1.5B-Instruct
    Q4_K_M with download-on-first-use (don't bundle, keeps Portable
    at ~450 MB instead of growing to 1.45 GB). GBNF for guaranteed
    JSON output.
  - **Vocal separation pre-processing** — Demucs htdemucs toggle.

### Phase 3 — deferred until Phase 2 lands

See `docs/V08_FEATURE_RESEARCH.md` § "Track 3" + the worth-investigating
table. Includes Parakeet adapter (sherpa-onnx), semantic search across
history.db, auto-chapter markers, cross-file speaker fingerprint.

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
Read docs/SESSION_HANDOFF_NEXT.md first, then start Phase 2 of v0.8 (live mic + WASAPI loopback + local LLM panel) per docs/V08_FEATURE_RESEARCH.md Tracks 1 and 2.
```
