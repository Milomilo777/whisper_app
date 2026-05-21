# Next session — read THIS FIRST

Single-source-of-truth handoff for the next Claude Code session on
this repo. Read this file before anything else.

---

## 1. Current state (2026-05-21, end of v0.8 Phase 1 + 2 + 3 session)

| Item | Value |
|---|---|
| Branch | `release/v0.7.0-installer-3-options` |
| Last commit | `99af9bf` — v0.8 Phase 2 + 3 wiring + real-file E2E |
| Pushed | ✅ everything is on origin (after push step below) |
| Working tree | clean |
| Release tag | `v0.7.1` on GitHub (three EXEs uploaded) |
| Unit suite | 438 passing (+163 from baseline 275) |
| Real-file E2E | 10/10 PASS (`tests/core/test_v08_real_file_e2e.py`) |
| Pyright basic | 0 errors, 0 warnings |
| Smoke | 7/7 PASS against real SMTV clip (re-verified end of Phase 3) |

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

### Phase 2 — DONE this session ✅ (`commit 99af9bf modules + wiring`)

* `core/recorder.py` — sounddevice (mic) + pyaudiowpatch (Windows
  WASAPI loopback) recorder writing 16-kHz mono WAV. Graceful
  fallback when deps missing.
* `core/llm.py` — local LLM panel: Qwen2.5-1.5B-Instruct Q4_K_M via
  llama-cpp-python with download-on-first-use to
  `user_cache_dir()/llm/`. LLMRunner.summarise / action_items /
  ask / translate. Atomic download (.part + os.replace) with
  cancel-aware cleanup.
* `core/separator.py` — Demucs htdemucs vocal-separation pre-process
  with file size+mtime+model cache key. `separate_vocals()` is
  safe to always call (no-op when off / dep missing).

### Phase 3 — DONE this session ✅ (`commit 99af9bf`)

* `core/backends/parakeet.py` — sherpa-onnx Parakeet TDT v3 adapter.
  `sherpa_onnx` is already bundled (diarisation dep) so zero new
  wheel cost. Requires four model files under
  `user_cache_dir()/parakeet/`. Token-to-segment grouping cuts on
  gap > 0.8s. Registered under backend slug `"parakeet"`.
* `core/search.py` — semantic search across `history.db` with
  sentence-transformers/all-MiniLM-L6-v2 when installed +
  sqlite FTS5 keyword fallback. Sidecar `search.db` carries
  per-segment FTS5 + optional float32 embedding BLOBs.
* `core/chapters.py` — auto-chapter markers via long-silence
  heuristic, optional LLM titler when AI Layer on. Outputs land
  as `<base>.chapters.json` sidecar — writers untouched.
* `core/voiceprint.py` — cross-file speaker fingerprint DB via
  pyannote/embedding. Enrol once → matching SPEAKER_NN clusters
  get relabelled on every future transcript. Storage: sqlite
  with float32 BLOB packing.

### Phase 2 + 3 wiring

* `core/config.py` — `ai_enabled`, `ai_model_path`, `demucs_enabled`,
  `auto_chapters_enabled`, `chapter_min_seconds`, `chapter_gap_seconds`,
  `voiceprint_enabled` keys with sensible defaults (Demucs +
  LLM off; chapters + voiceprint on).
* `core/transcriber.py` — Demucs pre-process hook + auto-chapter
  build + `_write_chapter_sidecar()` + `_maybe_get_llm_runner()`.
* `app/dialogs/advanced.py` — new "AI Layer (Phase 2 + 3)" frame
  with toggles + "Install AI model…" worker. Backend dropdown
  now includes `parakeet`.
* `core/backends/__init__.py` — Parakeet registered in dispatcher.
* Both PyInstaller specs — hidden imports updated for all 7 new
  modules.

### Real-file E2E ✅

`tests/core/test_v08_real_file_e2e.py` — 10 tests that load the
real Whisper model and transcribe the SMTV clip, then verify
every v0.8 feature end-to-end on real audio: JSON / SRT output
shape, hallucination detector flags, chapters sidecar
(sequential indices + full time coverage), search index +
keyword recovery, voiceprint relabel no-op, pipeline log
markers. Auto-skips when the fixture is missing. ~3 minutes
wall time on a cold cache.

### What's NOT done (Phase 2 follow-ups)

* Live mic recording UI — module is ready, but a "Live" tab
  hasn't been added yet. The Phase-2 module can be exercised
  programmatically; UI work in a follow-up.
* RealtimeSTT streaming integration — out of scope for the
  recorder module (record-then-transcribe is enough for MVP).
  Add when the user asks for low-latency live transcription.
* Local LLM panel UI — `_install_ai_model` button is wired and
  the four LLMRunner entry points (summarise / ask / etc.) are
  callable, but the viewer-level "Summarize transcript" /
  "Ask question" panel is a follow-up.
* Voiceprint enrolment UI — `enrol_with_vector` works, full
  pipeline including pyannote embedding extraction + a
  "Enrol speaker…" button in the viewer is a follow-up.

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
Read docs/SESSION_HANDOFF_NEXT.md first, then build the v0.8 user-facing UIs that were deferred at the end of Phase 3: Live tab using core/recorder.py, AI Layer panel using core/llm.py.LLMRunner from the transcript viewer, and a Voice enrol dialog using core/voiceprint.py. Bundle whichever heavy deps the user wants shipped.
```
