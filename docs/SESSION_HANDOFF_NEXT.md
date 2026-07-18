# Next session — read THIS FIRST

Single-source-of-truth handoff for the next development session on
this repo. Read this file before anything else.

---

## ⭐ Hover-help "(?)" icons added across the whole UI — NOT built/released yet (2026-07-18)

Owner asked for every UI section to get a small hover-help icon
explaining what it does (some sections already had informal grey
inline notes; most had nothing). Added:

- `app/widgets/tooltip.py` — new shared helper (`bind_tooltip`,
  `help_icon`, `add_section_help`). Previously every spot that wanted
  a hover tooltip (only the R3 device badge did) reimplemented its own
  popup; `App._bind_device_badge_tooltip` now calls the shared helper
  instead of duplicating it.
- `app/widgets/tabs.py` — icons on all 5 tabs (Transcribe, Queue,
  Download, Video Tiling, Server). Skipped fields that already had an
  inline grey explanatory note, to avoid clutter.
- `app/dialogs/advanced.py` — section badges on every `LabelFrame` +
  per-field icons on previously-unexplained controls (Batch size,
  Initial prompt, Hotwords, Backend, hallucination "BoH" jargon,
  Demucs, voiceprint, filename template, SponsorBlock). The Google
  Cloud / Cloud STT / NVIDIA Parakeet frames already had full
  paragraphs, left as-is.
- `app/dialogs/transcript_viewer.py` — icons for "Remove fillers" and
  the segment-list colour coding (confidence green/amber/red,
  suspect-row red background), which had zero explanation before.
- `core/server/static/index.html` (the LAN/web UI) — a lightweight
  CSS-only `?` badge on Source / Output formats / Language / Advanced
  options (no JS framework, matches the file's existing vanilla
  style).
- `app/dialogs/hub_setup.py`, `model_download.py`, `model_loading.py`,
  `statistics.py` were checked and left untouched — each already has a
  self-explanatory title/paragraph or is a single-purpose native
  dialog with nothing ambiguous to annotate.

Verified: full `pyright` clean (0/0/0), full hermetic `pytest` suite
green, `gui.py` launches with no traceback. A live-render visual check
was attempted (screenshot of the Advanced dialog) but aborted — it
grabbed an unrelated foreground window on the real desktop instead of
the Tk dialog (focus/z-order issue); the screenshot was deleted
unread rather than risk inspecting unrelated desktop content. Grid
placements were instead manually audited column-by-column (this is
how one real overlap — the SponsorBlock row — was caught and fixed
before commit); no further visual QA was done.

**Same-session follow-up — owner asked for a self-critique pass, which
found and fixed a real bug:**

- Instead of guessing from a screenshot, re-verified layout by
  instantiating the real `App`/`AdvancedDialog`/`TranscriptViewer`
  headlessly and reading `winfo_reqwidth()`/`winfo_width()` directly —
  no screen capture, no privacy risk, and it's exact instead of
  eyeballed.
- **Found:** the Transcribe tab's "quick options" row (Language +
  Identify speakers + Per-word timestamps + Time range), after gaining
  4 new hover icons, required 983px but the app's shipped default
  960px window only gives it 928px. `pack(side="left")` doesn't wrap —
  it clips silently, so on a fresh install some of that row (likely
  the Time-range fields) would have rendered off-screen.
  Fixed by splitting it into two stacked lines (verified back down to
  661px required). See commit `b03796f`.
- Checked the same risk on the Engine-picker row, both Video Tiling
  option rows, and the transcript viewer's toolbar — all comfortably
  under their available width, no changes needed there.
- Also, as part of "make it more readable everywhere": rebuilt the
  Statistics dialog (`app/dialogs/statistics.py`) from a single
  `messagebox.showinfo` text blob into a small labeled-rows Toplevel
  (commit `2b5318f`), and loosened the Advanced dialog's inter-section
  spacing from `pady=(0, 8)` to `(0, 14)` so its 10 stacked sections
  are easier to tell apart now that most carry a corner badge (commit
  `3fae872`).
- Still not built/released — same owner instruction as above.

**Same-session, next round — owner asked "what else could be more
readable" and to go through several layers of reflection myself.**
Investigated with grep/read evidence (not guesses) and proposed 4
options via AskUserQuestion; owner picked all 4:

1. **Friendly errors** — 8 spots (`app.py`, `transcript_viewer.py`,
   `integrations_service.py`, `hardware_wizard.py`) showed a raw
   Python exception string as the entire dialog body. New
   `app/widgets/error_dialog.show_error()` leads with a plain
   sentence, tucks the raw detail behind a collapsible "Show details"
   (still copyable). One spot (`app.py` Convert-transcript,
   `ConvertError`) was left alone — its message was already
   human-authored and specific, not a raw traceback.
2. **Log console colour + theme** — `app/widgets/console.py` was a
   fixed black/lime terminal regardless of the app's own Light/Dark
   toggle, and every line was the same colour (a real failure read
   identically to routine status text). Added `apply_console_theme()`
   (wired into `App.apply_theme()`) and `insert_log_line()`, which
   tags a line red when it matches the "could not / fail / error"
   wording every existing failure-path `self.log(...)` call already
   uses — verified against the real call sites first, so nothing
   needed to change at any of the ~20 existing call sites.
3. **Advanced dialog jump-to-section sidebar** — 10 stacked
   `LabelFrame`s behind one long scroll had no way to jump to one.
   Added a "Jump to" list on the left; verified numerically (not
   visually) against a real running dialog that every link lands on
   its target, including that the last few correctly clamp to the
   bottom of the scroll region instead of landing somewhere invalid.
4. **Two title renames** — `"AI Layer (Phase 2 + 3)"` → `"AI Layer
   (optional)"` (internal phase numbering has no business being
   user-facing) and `"Voice Activity Detection"` → `"... (skip
   silence)"` so the title alone explains the purpose.

Verified the same way as before: real `pyright` (0/0/0), full hermetic
suite green, `gui.py` launch clean, plus the existing
`test_dialogs_open_and_close` smoke test (which opens a real
`AdvancedDialog`) still passes with the new sidebar. Still not
built/released — same owner instruction.

**Same-session, third round — owner asked to critique this round too.**
This one found a real, reproducible bug (not just polish):

- The nav sidebar (170px) tipped the Advanced dialog's "Whisper
  extras" section into a genuine overflow **at the dialog's own
  hard-coded 1100px floor** — which a common 1366x768 laptop actually
  hits (`screen_w*0.75=1024` clamps up to the 1100 floor there), not
  an exotic edge case. Forced the dialog to exactly 1100px against a
  real running instance and measured `winfo_reqwidth()` to confirm:
  1133px needed vs 918px available. Isolated the cause precisely by
  removing the new hover icons in-memory and re-measuring — they
  contributed ~0px; the real driver was two pre-existing
  no-wraplength explanatory Labels plus a hard-coded `wraplength=820`
  repeated 9x across the Google Cloud / Cloud STT / NVIDIA frames
  (all pre-dating this session, just newly exposed by the sidebar
  eating 170px). Fixed the actual wraplengths (820→680, plus two
  missing wraplengths added), shrank the sidebar a bit more, and
  shortened one long button label. Re-verified after each change:
  all 10 sections now fit with real margin at the 1100px floor.
- Matched the nav sidebar's link colour to the dialog's own
  pre-existing link colour (was accidentally using the tooltip-icon
  blue instead).
- The log-console colour heuristic (`could not`/`fail`/`error`
  substring) could have false-positived on a routine line that merely
  *mentions* a filename containing one of those words (e.g. `f"Saved
  {otr_path}"` where the user named their source
  `my_failsafe_video.mp4`). Tightened to a word-boundary regex on the
  exact forms the real call sites use, verified against 9 cases
  including that exact trap.
- Added a scrollbar to the error dialog's collapsible detail box
  (defensive — current call sites only ever pass a short `str(e)`,
  but nothing should silently truncate a longer one later).

Verified with real running Tk instances each time (not visual
guessing): forced-width measurements, an in-memory icon-removal
isolation test, all 10 nav-jump targets re-checked land in view, the
9 console false-positive/true-positive cases, and the error dialog's
toggle actually growing the window. Still not built/released.

**Same-session, fourth round — owner asked to loop the critique until
no more issues turn up.** This round's headline finding: the earlier
place()-based corner badges (`add_section_help`) had a real,
systematic collision bug, not just a width problem.

- Wrote a pixel-level collision checker (compares every badge's actual
  rendered bounding box against every sibling's, across all 5 tabs +
  the Advanced dialog at 2 sizes) instead of guessing. Found 5 real
  overlaps: the Transcribe hero drop-zone's title label, the Download
  tab's time-range slider, the Server tab's Options row, and the
  Advanced dialog's VAD + Whisper-extras sections all had a badge
  sitting on top of real content. The root cause: `add_section_help`
  assumed the top-right corner is always empty, which is only true
  when a section's first row doesn't already reach the right edge.
- Fixed at the root: `app/widgets/tooltip.section_labelframe()` puts
  the help icon in the LabelFrame's own title bar via `labelwidget=`
  instead of floating a badge over the content — Tk keeps that
  structurally separate from grid/pack content, so this bug class
  can't recur. Migrated all 11 real sections to it; the one true
  exception (the drop-zone, which deliberately has no title) got its
  icon moved inline next to the Browse button instead.
- Also found (same audit): the main App window, `AdvancedDialog`, and
  `TranscriptViewer` were all resizable with **no `minsize()`** —
  nothing stopped a user, a stale saved `window_geometry`, or a script
  from shrinking any of them below the width every fix in this session
  assumed held. Added a matching `minsize()` to all three (screen-aware
  for `AdvancedDialog`, so it can't force a genuinely small screen's
  window wider than it can display). Verified end-to-end with the
  dialog's own screen-size calls monkey-patched to simulate a real
  1366x768 laptop (not this dev machine's much wider display): it
  opens at exactly the 1100px floor, every section fits, and trying to
  shrink it further is correctly refused by Tk.
- Also fixed a raw-exception dump the earlier error-message sweep
  missed (`app/widgets/platform.py`'s `open_folder()`) — found by
  re-running that search in multiline mode, since the original
  single-line regex couldn't have caught this one anyway.

Re-verified everything after each fix: pyright 0/0/0, full hermetic +
smoke suite green, zero badge/content overlaps on a fresh sweep, nav
jumps still land correctly post-migration. Still not built/released.

**Same-session, fifth/sixth rounds — convergence check.** Two more
passes looking for anything the above missed:

- Round 5: `ruff --select F401,F811,F821` across every file touched
  this session. 5 findings, all confirmed pre-existing (checked
  against the original pre-session commit `389fae2` directly) — none
  introduced this session, so left untouched (out of scope).
- Round 6: fresh line-by-line re-read of `tooltip.py`, `error_dialog.py`,
  `console.py`; grepped for any leftover structural assumption the
  `section_labelframe` migration could have broken (`.winfo_children()`
  iteration, `.cget("text")` assertions in tests — none found). Did
  find that `add_section_help` was now dead code (zero callers anywhere
  after the migration) — deleted it rather than keep a "might be
  useful later" shim, per this project's own stated convention against
  that. Also did an end-to-end open/close sweep of `TranscriptViewer`
  (via its real `open_viewer` entry point), `HardwareWizard`, and
  `Statistics` — all three open and close cleanly with no exception.

Both rounds turned up nothing new beyond that one dead-code removal —
treating this as convergence for now. Re-verified once more: pyright
0/0/0, full hermetic + smoke suite green. Still not built/released.

**Owner explicitly said (same session): do NOT rebuild or bump the
version for this — it rides along with the next release's changes.**
So the 6 commits above are source-only; no installer/exe was rebuilt
and no `gh release` touched. Next session that *does* cut a release
should fold this in (Setup-Standard + Portable + macOS, per the
"Release assets must track every bug fix" rule below — this one is an
exception only because the owner opted out of it for now).

---

## ⭐ macOS build replaced with a colleague's build — Claude's build did not work (2026-07-15)

The macOS `arm64`/`x86_64` `.dmg`s that Claude built and uploaded to
the v1.5.0 release on 2026-07-04 (see entry below) did not work when
the owner tried them. No repro details were captured — the failure
mode and root cause are unknown.

A colleague built a working replacement independently and shared it
as a single universal `.dmg` at a private URL
(`https://smch.ir/binaries/WhisperProject1.5.0.dmg`, said to cover
both `arm64` and `x86_64`). Downloaded and uploaded to the v1.5.0
release:

- Added: `WhisperProject-v1.5.0-macOS-universal.dmg` (~400 MB).
- Removed: `WhisperProject-v1.5.0-macOS-arm64.dmg`,
  `WhisperProject-v1.5.0-macOS-x86_64.dmg`.

**Provenance caveat**: this asset was downloaded from a third-party
URL and published to the public release **without checksum or build
provenance verification** — the owner explicitly accepted that risk
and asked for it to be published as-is. It was **not** built from
this repo's own pipeline (`docs/BUILD.md` Step 4b), so it is not
reproducible from source control the way the other three release
assets are.

Follow-up for a future session: get repro/root-cause details from the
colleague for what was actually broken in Claude's build, and once
fixed, rebuild macOS through the repo's own pipeline so the shipped
macOS asset is source-traceable again like the Windows ones.

**Same-session investigation (owner reported the size difference
looked suspicious — "definitely something is missing" — but declined
to answer any diagnostic questions, e.g. the exact macOS error, so
this is as far as it got):**

- Downloaded the actual CI artifact from the run that produced
  Claude's broken build (`gh run view 28699783814`, workflow
  `macos-app.yml`, 2026-07-04) and inspected its contents directly.
  Core libraries were all present and correctly bundled:
  `libctranslate2.4.8.1.dylib` (57 MB), `libopenblas64_.dylib`
  (69 MB), `onnxruntime` (~37+31 MB), `sherpa_onnx`, `ffmpeg`/`ffprobe`
  in `Contents/Frameworks/bin/`, and the main PyInstaller binary
  (26 MB). No obviously-missing component was found this way.
- The size comparison the owner flagged is not apples-to-apples:
  Claude's old `x86_64` `.dmg` was single-arch (152 MB, measured
  directly from the CI artifact zip), while the colleague's
  replacement is a universal `.dmg` covering both `arm64` and
  `x86_64` (399 MB / 418,211,880 bytes). `.dmg` (UDZO/zlib) and `.zip`
  also don't necessarily compress this binary content at the same
  ratio, which could account for part of the gap on its own.
  - Note: the CI run's boot-smoke step (a hard, non-continue-on-error
    requirement) already exercises the numpy → ctranslate2 →
    faster-whisper import chain inside the frozen `.app` and passed
    for both arches on that run — so a basic import/packaging failure
    in the pre-`.dmg` `.app` is unlikely, though the pipeline never
    smoke-tests the final `.dmg` itself (mount → drag to Applications
    → launch), which is the actual end-user flow.
- Bottom line: no hard evidence of a missing component was found by
  static inspection from Windows (no Mac available to mount/launch
  either build). Root cause remains unconfirmed. If this comes up
  again, the fastest path is the exact macOS error text/screenshot
  from whoever hit it, or reproducing on a real Mac.

---

## ⭐ REAL BUG FOUND BY A COLLEAGUE, FIXED + REBUILT (2026-07-04, later still) — macOS not yet rebuilt with this fix

A colleague testing the published v1.5.0 Setup-Standard installer reported
the SMTV docx output "sometimes" landing under an unexpected name. Root
cause found and fixed: `core.transcriber._write_outputs` shared one
collision-avoidance index across every requested format including
`smtv_docx`, so a pre-existing `.srt`/`.json` from an earlier run of the
same source pushed the SMTV team's file to a `(1)`/`(2)` suffix on its
very first write — even when no `smtv_docx` had ever been written for
that source before. Reproduced directly, fixed (excluded `smtv_docx`
from the shared index; it now always resolves to its documented fixed
filename), and added a regression test
(`tests/core/test_output_indexing.py::test_smtv_docx_filename_stays_fixed_even_when_other_formats_are_indexed`).
Full detail in `docs/CHANGELOG.md` `[1.5.0]`.

Also confirmed for the colleague (they asked): yes, the `.otr`
(oTranscribe) writer added earlier today really is wired into both the
Advanced-settings output-format checkboxes AND the Convert-transcript
picker — both pull from the same `core.writers.supported_formats()`
registry, so no separate wiring was needed once the writer itself was
registered.

Rebuilt and re-uploaded to the v1.5.0 release on all 4 platforms:
Windows `Setup-Standard.exe` + `Portable.zip` (07:52 UTC) and macOS
`arm64`/`x86_64` `.dmg` (08:12 UTC) — all built after this fix landed.

Also this session: researched (not built) a compatibility bridge
between our SMTV docx writer and the sibling `machine-translate-docx`
project — see `docs/integrations/smtv-translator-bridge-research.md`.

---

## ⭐ REPO-WIDE SWEEP (2026-07-04, same day, after the "everything resolved" entry below) — nothing pending

Owner asked, broadly, whether anything was left to do in the whole
repo (not just the handoff list) and to just fix it directly. Did a
fresh sweep: `git status` (clean), CI health (`gh run list` — all
green), open issues (only the 3 deliberately-seeded good-first-issues
existed beyond what's below), and a `TODO|FIXME|XXX|HACK` grep across
`app/`/`core/` (nothing). Two of the three were genuine gaps, not just
contributor bait, so fixed them directly:

- **Issue #3** (no test file for `app/services/transcription_service.py`)
  — added `tests/app/test_transcription_service.py` (11 tests) covering
  `_derive_transcript_stats` across every fallback path, including the
  actual SRT-only scenario that shipped the word_count=0 bug, and
  `_post_usage_stats`'s payload shape + a real no-op proof when
  telemetry is off. Proved the key test isn't tautological by
  simulating the pre-fix code path (forced the fallback parse to fail)
  and confirming it reproduces the exact shipped bug. Closed by commit
  message (`cc5e710`).
- **Issue #5** (`docs/COMPETITIVE_ANALYSIS_2026.md` re-verification) —
  same evidence method as the `GAPS_AGAINST_PEERS_2026.md` fix, scoped
  to just the document's claims about OUR OWN capabilities (Section 1's
  15-row table + the Section 3 backend recommendation; external-tool
  descriptions untouched). Result: 5/15 fully shipped since May
  (forced alignment, diarization, the pluggable-backend seam — realized
  almost exactly as the doc sketched, down to the file layout), 6
  partial, 4 still absent. Best find: `core/llm.py` (local Qwen2.5-1.5B
  summarize/action-items/Q&A/translate) and `core/chapters.py`
  (auto-chapter detection) are BOTH fully built and wired into the
  transcription pipeline, but neither has any UI a user could find —
  same "built the engine, forgot the doorway" shape as `core/search.py`
  from the earlier GAPS audit. Closed by commit message (`2f52b4a`).
- **Issue #4** (coverage badge) — only partially closeable from here.
  Added the missing half of the CI wiring (a tokenless
  `codecov/codecov-action@v5` upload step — `coverage.xml` was already
  being generated, just never published) and the README badge
  (`78fb8a1`). Left OPEN and un-closed on purpose: the badge will read
  "unknown" until the repo is actually activated on codecov.io, which
  probably needs the owner to sign in there once with their GitHub
  account — an external-account action that shouldn't be taken on
  someone's behalf without them being present for it.

Verification: pyright `app/ core/` 0/0/0; full hermetic suite green
(re-run after adding the new test file). All 3 commits pushed to
`master`. `git status` clean.

---

## ⭐ EVERYTHING RESOLVED (2026-07-04, later same day, continued after the 5h-cap stop) — nothing pending

The prior "STOPPING MID-TASK" note (below, kept for history — see the
git history of this file if you need the exact prose) listed 3 loose
ends. All 3 are now done, committed, and pushed to `master`:

- **`docs/GAPS_AGAINST_PEERS_2026.md` re-audit fully applied.** Both
  subagents' findings (`docs/history/GAPS_AUDIT_2026-07-04_findings.md`)
  are now reflected in the doc: the 2 flagged-uncertain rows were
  spot-checked directly (per-machine/per-user install — confirmed both
  `.iss` files hardcode `PrivilegesRequired=admin`, no per-user mode
  exists; cold start — measured for real against `embed_build/`:
  ~1.9 s warm, ~4.7 s cold disk cache), then every remaining row across
  sections A/B/C/D/E/F/H got its correction applied, Section J's "top 5
  gaps" was rewritten (the real remaining gaps are now: system-wide
  dictation hotkey, true streaming live mic, word-level click-to-jump +
  re-export editing, code-signing/notarisation, translation exposure),
  and the stale "164 tests" became 1701.
- **`stats_url` hyphen/underscore mismatch fixed** (closed GitHub #2).
  Confirmed live via a direct HTTP check which filename is real (the
  underscore one, 200; the hyphen one, 404). Fixed `configuration.json`
  to match `core/config.py`'s `DEFAULT_CONFIG`, added a regression test
  (`tests/core/test_config.py::test_repo_configuration_json_agrees_with_default_stats_url`).
- **3 stale untracked QA screenshots deleted** (`online_startup.png` +
  2 others, leftover from v1.3.8-era testing, unreferenced anywhere).

**Also done this session, beyond the original 3 items** (owner asked to
finish everything, including rebuilding both platforms if stale):

- **Windows installers verified already up to date** — no rebuild
  needed. Local `dist_installer/` hashes matched the live `v1.5.0`
  GitHub release assets exactly, and the local build timestamp
  (10:54 local) postdates every code commit that session (otr writer,
  Convert-picker UX, macOS script fix) and predates only doc-only
  commits. The "rebuild + update release assets in place" instruction
  from the entry below this one had, in fact, already been completed
  before the 5h-cap stop.
- **macOS build produced for the first time since v1.3.9.** The last
  full `macos-app.yml` run (2026-06-16) had failed, and no macOS
  artifact existed for v1.4.0 or v1.5.0. Dispatched it fresh
  (`gh workflow run macos-app.yml --ref master`, run id
  `28697230557`) — both matrix legs (arm64, x86_64) succeeded this
  time. Downloaded the two `.dmg`s and uploaded them to the existing
  `v1.5.0` release (`gh release upload v1.5.0 ... --clobber`), same
  version, no new tag. `v1.5.0` now ships 4 assets: Setup-Standard.exe,
  Portable.zip, macOS-arm64.dmg, macOS-x86_64.dmg. Recipe documented in
  `docs/BUILD.md` ("Step 4b") + `docs/RELEASE_PROCESS.md` so it doesn't
  need re-deriving next time.
- **Verification (REAL):** pyright `app/ core/` 0/0/0 (re-confirmed);
  full hermetic suite green (re-confirmed twice — once via the new
  `test_repo_configuration_json_agrees_with_default_stats_url` test
  specifically, once via a full `pytest tests/ --ignore=tests/smoke`
  run). `docs/CHANGELOG.md` `[1.5.0]` updated with the stats_url fix,
  the otr-writer/Convert-picker entries, and the new macOS assets.

**Known, deliberately NOT touched (pre-existing, out of this session's
scope):** `docs/MANUAL_STEPS.md` and `docs/architecture-diagrams.md`
are both artifacts from the ~v0.5.0 era (3-tab app, 137 tests) and
read as very stale against the current v1.5.0 reality. Discovered
while grepping for stale test counts; a full rewrite is a separate,
larger undertaking than this session's scope (finishing last session's
specific leftover items) — flagging for a future session rather than
scope-creeping into it now. Also NOT touched, on purpose: GitHub issues
#3-#5, seeded intentionally as `good first issue` bait for outside
contributors, not leftover work.

**Repo state right now:** `git status` clean, `master` pushed, no
version bump (still 1.5.0 everywhere), `v1.5.0` GitHub release has all
4 platform assets current with `HEAD`. Nothing pending for the next
session to pick up — it can start fresh on whatever's next.

---

## ⭐ CURRENT STATE (2026-07-04) — still v1.5.0 (no version bump): otr writer + Convert-picker UX pass

- **`core/writers/otr.py`** (new) registers `otr` in `core.writers.WRITERS`,
  backed by a new public `core.integrations.otranscribe.segments_to_otr()`.
  `.otr` was importable via `core.convert` before but never offered as an
  EMIT target in File → Convert transcript — now it is (and it also shows
  up as a transcription-output checkbox in the Advanced dialog, since both
  pull from the same `supported_formats()` registry).
- **Human-simulation UX pass on the Convert-transcript dialog** (real
  running app, real screenshots, not just source-reading): the format
  combobox showed bare internal registry keys (`elan`, `smtv_docx`, `otr`,
  …) in plain alphabetical order with no hint of the real output extension.
  Fixed via a new `core.convert.output_extension_for()` — the picker now
  shows `name (.ext)` and lists the four common formats
  (srt/vtt/txt/json) first.
- **macOS DMG script fixed + verified on a real macOS runner**:
  `platform/macos/pyinstaller/compileall-whisper-mac.sh` had a
  copy-paste bug duplicating the pyinstaller invocation; fixed, hardened
  (cd to repo root, `set -euo pipefail`, create-dmg check), and a
  dedicated `macos-compileall-script-test.yml` workflow proved it
  actually produces a `.dmg` end to end. The repo is now **public**, so
  the earlier "macOS CI minutes cost 10x" constraint no longer applies here.
- **Verification (REAL)**: pyright `app/ core/` 0/0/0; hermetic suite
  green; the otr writer + the picker fix were both driven through the
  real running `App` (not just pytest) with real screenshots and a real
  `.otr` file produced and round-tripped.
- **Release status**: `v1.5.0` was already published (both
  `WhisperProject-v1.5.0-Setup-Standard.exe` and
  `WhisperProject-v1.5.0-Portable.zip` are on the GitHub release) — the
  previous handoff's uncertainty about this is resolved, it did ship.
- **NEXT**: per explicit owner instruction this session, rebuild the
  Windows installers with these changes included but **without** bumping
  the version (stay on 1.5.0), then update (not replace/re-tag) the
  existing `v1.5.0` GitHub release's assets in place. See whether this
  session finished that or left it for you.

---

## ⭐ CURRENT STATE (2026-07-03) — v1.5.0: SMTV language fill, convert target, stats fixes, renamed to whisper_app

- **Project renamed** `whisper_project_direct_download_v2` -> `whisper_app`
  (both the GitHub repo and the local checkout folder name; the GitHub
  rename leaves the old URL redirecting). `core/updates.py`'s
  `GITHUB_REPO` constant, `pyproject.toml` urls, the READMEs/install
  docs, and the Homebrew formula were all updated to match.
- **`core/writers/smtv_docx_writer.py`**: the docx header row (row 2,
  col 3) now shows the detected language instead of always reading the
  literal "Foreign Language" -- it reuses the same `lang_label` the
  title row and the "[... starts]" cue already fill.
- **`core/convert.py`**: `smtv_docx` is now a valid `convert_file()`
  target (new `CONVERT_TARGETS` tuple, wired into `app.app`'s File ->
  Convert transcript picker). No language metadata survives a generic
  transcript file, so it's filled the same way the writer treats "no
  language detected."
- **Fixed a real bug**: `app/services/transcription_service.py`'s
  `_derive_transcript_stats` only recovered `word_count` from a `.json`
  sidecar. Anyone whose `output_formats` didn't include `"json"` always
  got `word_count=0` in both history and the opt-in usage-stats POST,
  no matter how much was actually transcribed. It now falls back to
  `core.convert.parse_to_segments` on whatever else was produced.
- **`core/stats.py`** `build_stats_payload` gained `program_version`
  plus host/hardware facts (`platform_system/_node/_release/_version/
  _machine/_processor`, `cpu_count`, `mem_total` via the new `psutil`
  dependency). `stats/transcription_stats.php` gained matching columns
  with an `ALTER TABLE` migration for already-deployed DBs.
- **Verification (REAL)**: pyright `app/ core/` 0/0/0; full hermetic
  suite green (1 pre-existing skip, unrelated).
- Version bumped to **1.5.0** everywhere (`core/__init__.py`,
  `pyproject.toml`, both `.iss` files, the mac spec for parity though
  macOS isn't being built this release). `docs/CHANGELOG.md` +
  `docs/RELEASE_NOTES_v1.5.0.md` updated.
- **Known gap**: `app/services/transcription_service.py` has no
  dedicated test file at all (`_derive_transcript_stats` /
  `_post_usage_stats` are untested in isolation -- exactly how the
  word_count bug shipped unnoticed). The fix reuses well-tested pure
  functions (`core.convert.parse_to_segments`,
  `core.stats.count_words_in_segments`) but the wiring itself still
  has no regression test. Worth a `tests/app/test_transcription_service.py`
  in a future session.
- **NEXT**: build artifacts (Setup-Standard + Portable, built without
  the personal `creds/gcloud_stt.json`) and the actual GitHub release
  (tag `v1.5.0`, prune the old `v1.4.0` release per policy) — see
  whether this session finished them or left them for you.

---

## ⭐ CURRENT STATE (2026-06-22) — v1.4.0: one Parakeet engine, leaner config, clean upgrades

A colleague reported the Transcribe-tab "Parakeet — offline, NVIDIA" engine
permanently warning about missing `encoder.onnx`/`decoder.onnx`/`joiner.onnx`/
`tokens.txt`. Root cause: TWO Parakeet engines existed side by side —
`core/backends/parakeet.py` (sherpa-onnx, never got a model downloader) and
`core/backends/nvidia_asr.py` (transformers, fully working, added 2026-06-21).
The colleague had picked the broken one.

- **Removed `core/backends/parakeet.py`** (sherpa-onnx) entirely, with the
  owner's explicit sign-off (AskUserQuestion → "حذف گزینه‌ی ناقص"): deleted the
  module + its test, and every registration (`core/backends/__init__.py`,
  `core/backends/availability.py` ENGINE_CHOICES/`_PROBES`,
  `app/dialogs/advanced.py` `_BACKEND_CHOICES`, all 3 PyInstaller spec
  hidden-import lists, stray comments/About text). `nvidia_asr` is now the
  only Parakeet engine.
- **Added a "Prepare Parakeet model now..." button** in Advanced settings
  (`app/dialogs/advanced.py::_prepare_nvidia_asr_model`) — runs
  `NvidiaAsrBackend().load()` in a background thread so the deps + model
  download can happen ahead of time instead of mid-transcription. Mirrors the
  existing whisper.cpp download button. New `nvidia_asr` extras group in
  `pyproject.toml` for source checkouts.
- **`core.config.save_config` strips 5 keys** before writing `config.json`
  (`_NON_PERSISTED_KEYS`): `telemetry_opt_in`, `config_url`, `stats_url`,
  `ffplay_downloads`, `latest_version` — all re-derived from `DEFAULT_CONFIG`
  / the online config fetch on every load, so persisting them only risked
  pinning a stale value across an upgrade. Cleans up any config.json that
  already has them too.
- **`installer.iss` / `installer_embed.iss`**: `InitializeSetup` now looks up
  the previous version's uninstaller via the registry (same `AppId`) and runs
  it silently before installing, so files removed/renamed between versions
  don't linger after an in-place upgrade. `CurUninstallStepChanged` skips the
  hub-folder deletion MsgBox when `UninstallSilent()` is true, so this never
  risks silently deleting a multi-GB model hub during the automatic step.
- **`core/writers/smtv_docx_writer.py`**: `document.core_properties.modified`
  is now stamped to "now" before saving — it used to carry the bundled
  template's own modified date straight through to every generated docx.
- **Verification (REAL):** pyright `app/ core/` **0/0/0**; full hermetic
  suite green (was already green pre-change; added regression tests for the
  config-key strip and the docx modified-timestamp fix). `installer.iss` /
  `installer_embed.iss` Pascal sections syntax-checked by compiling their
  `[Code]` sections standalone with the real Inno Setup 6 ISCC compiler.
- Version bumped to **1.4.0** everywhere (`core/__init__.py`, `pyproject.toml`,
  both `.iss` files, the mac spec for parity even though macOS isn't being
  built this release). `docs/CHANGELOG.md` + `docs/RELEASE_NOTES_v1.4.0.md`
  updated. **Windows-only release** — no macOS build this time (owner scope).
- **Caught at push time:** a colleague pushed `167ccf8` directly to
  `origin/master` (delete `config.json` on uninstall, via an unconditional
  `[UninstallDelete]` entry in `installer_embed.iss`) while this session's
  silent-pre-install-uninstall change was in flight. Combined, every silent
  upgrade would have wiped the user's `hub_folder`/API keys/preferences.
  Fixed by merging, then moving that deletion into `CurUninstallStepChanged`
  behind the same `UninstallSilent()` guard as the hub-folder prompt (reading
  `hub_folder` out of config.json BEFORE deleting it). Rebuilt
  Setup-Standard after the fix; this is the version actually released.

---

## CURRENT STATE (2026-06-21) — LOCAL NVIDIA Parakeet ASR engine

A new local transcription engine `nvidia_asr`, on `master` and **pushed**.

History (important): this started as a *cloud* gRPC engine (commits `fa91eaa` +
`7f4d3d5`) because "NVIDIA Nemotron 3.5 ASR" was assumed to be the hosted API.
The owner clarified they wanted it **LOCAL** (model downloaded from Hugging
Face), and a colleague's `transcribe_nemotron.py` showed the transformers
approach. So the cloud engine was **replaced** by a local transformers engine.

- **`nvidia_asr` = local, fully offline** transformers `automatic-speech-recognition`
  pipeline (no audio leaves the machine). Default model
  `nvidia/parakeet-tdt-0.6b-v3` (transformers-native multilingual FastConformer);
  configurable via `nvidia_asr_model_id` to any transformers ASR model id / local
  dir. New module `core/backends/nvidia_asr.py` — pure seams `resolve_device`,
  `resolve_dtype`, `chunks_to_segments`, `text_to_segment`, `friendly_load_error`;
  decodes each window to a 16 kHz mono float32 array with the bundled ffmpeg and
  runs the pipeline window-by-window (progress + cancel); reuses
  `cloud_stt.plan_chunks` + `offset_segments`.
- **Why parakeet, not the literal Nemotron-3.5:** NVIDIA's
  `nemotron-3.5-asr-streaming-0.6b` (and the `-en` variant) HF repos ship ONLY a
  NeMo `.nemo` checkpoint (`library_name: nemo`, no transformers config/weights),
  so `transformers.pipeline` cannot load them — that exact model needs the heavy
  NeMo toolkit. `parakeet-tdt-0.6b-v3` is the transformers-native sibling and the
  owner approved it (AskUserQuestion → "transformers + Parakeet v3").
- **Timestamp reality:** parakeet via transformers 5.12 raises on
  `return_timestamps="word"` / `chunk_length_s` and returns text only. So the
  engine tries word timestamps once, then falls back to ONE segment per window
  timed to the window bounds — hence the small default `nvidia_asr_chunk_seconds`
  = 30 (smaller = finer subtitles). If a future model/transformers supports word
  timestamps, they're used automatically. (Gotcha fixed: the pipeline mutates the
  input dict in preprocess, so each call builds a FRESH `{"raw":…}` dict.)
- **Config keys** (replaced the old cloud keys): `nvidia_asr_model_id` /
  `_device` ("auto"|"cpu"|"cuda") / `_dtype` ("auto"|"float32"|"float16") /
  `_chunk_seconds` (30). `optional_deps.FEATURES["nvidia_asr"]` installs
  `transformers` + `torch` + `librosa` on first use (NOT bundled, NOT in
  requirements.txt — librosa is required by the ParakeetFeatureExtractor).
- **Verification (REAL):** pyright `app/ core/` **0/0/0**; full hermetic suite
  **green**. Installed `transformers 5.12.1` + `torch 2.12.0+cpu` + `librosa` and
  ran the actual `NvidiaAsrBackend` end-to-end on 25 s of real speech (the test
  video) — it downloaded `parakeet-tdt-0.6b-v3`, transcribed correctly, and
  produced window-timed segments. `tests/core/test_nvidia_asr.py` (pure seams +
  factory + availability + registry sync) passes.
- **OPEN (owner):** first selection of the engine triggers a multi-GB one-time
  download of torch/transformers + the model — warn friends. GPU users get
  float16/CUDA automatically. The exact Nemotron-3.5 `.nemo` is still NOT
  supported (would need a NeMo integration — separate, heavy task).
- Specs: `core.backends.nvidia_asr` is in all three PyInstaller hiddenimports
  (module name unchanged from the cloud version). No version bump, no exe/mac
  build (owner scope). Pre-existing uncommitted `.project_index.json` /
  `PROJECT_INDEX.md` / `online_*.png` left untouched.

---

## ⭐ CURRENT STATE (2026-06-08) — read this FIRST (supersedes the 06-07 note below)

Branch `frontend-stability-fix` (off `master`/`a2fd666`). Two new LOCAL commits — **NOT
pushed, NO GitHub release** (owner asked for a local build only this session):

1. `feat(transcribe): engine picker on the tab + Google Cloud default` — a new **Engine**
   row on the Transcribe tab (offline Faster-Whisper / whisper.cpp / Parakeet / Gemini /
   Google Cloud) with a Ready / needs-setup status line. The shared engine list + cheap
   availability probes live in the new `core/backends/availability.py` (used by both the tab
   and the Advanced dialog). **Google Cloud STT is now the DEFAULT engine** when a build ships
   the bundled key (`creds/gcloud_stt.json`), else offline faster-whisper. The Advanced dialog
   now shows the bundled key is loaded and auto-runs the connection test on open. Switching the
   engine now `stop_all()`s the worker — the dispatch preferred the stale spawn-time backend, so
   a switch never took effect without a restart. Also folds in the verified Codex frontend
   stability fixes (worker stdin `readline`, checkpoint probe, non-crossing download sliders,
   CLI `--formats` registry + real paths/progress).
2. `build(release): bundle gcloud key, bump to v1.3.9` — version 1.3.9 everywhere
   (`core/__init__.py`, `pyproject.toml`, both `.iss`); `build_embed_installer.bat` now copies
   `creds/gcloud_stt.json` into `embed_build/creds/`; the 3 PyInstaller specs mirror the optional
   creds bundling + the new `core.backends.availability` hidden-import.

Verification: pyright `app/ core/` 0/0/0; full hermetic suite green (minus the 3 GPU/cuDNN-flaky
real-ML files, which pass in isolation); Tk-construction smoke of the tab OK; the embed build
resolves `default=google_cloud_stt` and finds its bundled key. **Standard installer built LOCALLY**
at `dist_installer/WhisperProject-v1.3.9-Setup-Standard.exe` for owner testing.

Why not released: the installer contains the bundled key; publishing it as a GitHub release asset
would expose it whenever the repo is later made public (the owner's macOS-CI plan). So this build
stays local-only until the owner decides.

Pending / next: owner tests the local Standard build; if OK, update the macOS build to match. The
macOS CI checkout has NO `creds/`, so cloud STT on mac needs the key injected (GH secret → write
`creds/gcloud_stt.json` in the workflow, or drop it into the mac build tree). `google-cloud-speech`
still installs on-first-use into `user_cache_dir()/pylibs` (slim-embed design) — already cached on
the owner's machine from prior gcloud use, so the cloud default works immediately there; a fresh
machine installs it the first time Advanced settings opens (auto-test) or shows a clear
"open Advanced to install" message on a direct Transcribe.

---

## ⭐ CURRENT STATE (2026-06-07, end of the completeness push)

- **Unified branch is `macos-ci`** (tip ~`5a632c3`). It carries EVERYTHING: this
  session's Windows-side work + the macOS session's commits (convert/config/spec/CI/QA
  + their tiny-model E2E). Local `master` was reset to equal `origin/macos-ci`, so they
  are reconverged — future commits go on `master` and push as a fast-forward to `macos-ci`.
  `origin/master` is still `53fc8b2` ON PURPOSE (never pushed — it fires the costly ci.yml
  matrix; the macos-ci → master merge + the v1.3.8 release are the OWNER's call).
- **Bug state:** a find-until-dry adversarial sweep ran to convergence — 6 rounds fixed
  ~20 real bugs (5+4+3+3+3+2), severity collapsing HIGH/security/data-loss → all-LOW → dry.
  Plus the earlier 44-bug fixpack + the macОS 88-candidate triage. Every fix has a hermetic
  regression test. pyright `app/ core/` = 0/0/0. Hermetic suite green (the only non-green is a
  Python-3.14 multi-Tk-root dev-env flake that passes in isolation; the shipped 3.11 runtime +
  the macOS CI 3.11/3.12 don't have it). **macOS CI build is GREEN on real hardware.**
- **Artifacts:** `dist_installer/WhisperProject-v1.3.8-Setup-Standard.exe` + `-Portable.zip`,
  rebuilt from the unified tree, launch-smoke verified (window "Whisper Project v1.3.8").
- **Bundled Google Cloud key (owner-authorized, trusted-distribution):** both Windows builds
  bundle the service-account JSON at `creds/gcloud_stt.json`; the backend
  (`bundled_credentials_path()` in `core/backends/google_cloud_stt.py`) auto-uses it when no
  user key is set, so a friend can pick "Google Cloud STT" without pasting a key. Default
  backend stays **offline** (faster_whisper). **SECURITY: the key file is NEVER committed**
  (gitignored: `creds/` + `gcloud_stt.json`); it lives ONLY in the local build tree
  `embed_build/creds/`. So the macOS `.app` built on CI does NOT carry the key (the CI checkout
  has no `creds/`) — if friends need cloud STT on macOS too, the macOS session must drop the
  same JSON into its build. The key is revocable: rotate the SA in GCP if any build leaks; scope
  the SA to Speech-to-Text only + set a GCP budget cap.

---

## 0b. Post-1.3.8 fixes (2026-06-07) — found by live end-to-end testing, on `macos-ci`

Two real defects surfaced by a real offline+online+network E2E run on a 30s clip, a 3-hour
file, and the LAN server — both fixed, tested, and pushed to `macos-ci` (NOT master):
- **Server download of non-ASCII output names** (`core/server/httpd.py`): downloading the SMTV
  `.docx` (en-dash in the name) over `/api/jobs/<id>/result` crashed the handler (http.server
  latin-1 header encoding). Fixed with RFC 6266 `filename*` + ASCII fallback
  (`content_disposition_attachment`) + test. Verified: the `.docx` now downloads (valid 4-col table).
- **Offline time-range on huge files** (`core/transcriber.py`): a time range was passed as
  faster_whisper `clip_timestamps`, which decodes the WHOLE file — a 3h file hung. Now the
  offline path PRE-SLICES `[clip_start, clip_end]` via `_slice_audio_from` (fast ffmpeg seek),
  transcribes only the slice, deletes it, and shifts timestamps back to the original timeline
  (`_shift_segments`). Whole-file + resume paths untouched. Tests in
  `tests/core/test_fixpack_timerange_slice.py`. Verified live: a [5,15] range emits an SRT
  starting at 00:00:05. E2E test inputs live in `%TEMP%\wp_e2e_*`; drivers in `.claude/e2e_*.py`.

These are committed on local `master` too. Remember: push only to `macos-ci` (fetch+rebase via a
temp branch, never force-push) until the macOS build is green and we merge `macos-ci` → `master` once.

### Round 2 (2026-06-07) — frontend edge-case hunt + macOS-report triage (on `macos-ci`)
A 50-agent frontend edge-case hunt (16 confirmed) + a 6-cluster triage of the macOS session's
`BUG_CANDIDATES_for_feature_session.md` (88 candidates, their auto-voting was unreliable so each was
re-verified against CURRENT code). FIXED + tested + pushed:
- **Frontend (HIGH):** re-run/resume of a CLIPPED transcription dropped clip_start/clip_end →
  transcribed the whole file (now preserved in _rerun_task/resume_task/_bulk_rerun/_bulk_resume);
  App.cancel() now ignores a terminal task; worker_exit marks a PAUSED task as error (was stranded).
- **Time-range hardening:** start ≥ media duration now errors clearly; pre-slice temp file removed via try/finally.
- **Security/privacy:** Gemini API key moved from the `?key=` URL into the `x-goog-api-key` header
  (was leaking into logs); uploaded Gemini Files-API blobs now DELETED after use.
- **Cloud accounting:** usage minutes no longer billed on cancel / over-counted (bills actual transcribed seconds).
- **Concurrency:** worker `emit()` now serialises stdout writes (was interleaving/corrupting the frozen
  JSON protocol); the stdin reader enforces the 1 MB cap WHILE reading (OOM guard was defeated).
- **LAN server:** multipart text fields placed AFTER the file part were dropped (every upload silently
  fell back to [srt]+auto) — now re-scanned; a trailing-CRLF appended 2 junk bytes to saved media — fixed.
- **Data loss:** Recorder.stop() no longer truncates the WAV a still-alive capture thread is writing.
- **POSIX:** kill_process_tree(force=False) now escalates SIGTERM→SIGKILL (only Windows did before);
  checkpoint key is now case-folded so resume works on case-insensitive FS.
Tests in tests/core/test_fixpack_{frontend_edges,cloud,gcloud,worker,server,recorder,proc_ckpt}.py.
`macos-ci` tip after this round: ~4697e3a. pyright app core 0/0/0.

**REMAINING BACKLOG (lower priority — verified-real but not yet fixed):**
- Frontend mediums/lows from the hunt (full list in the wf_c7cb6f91-7a6 run output): duplicate concurrent
  re-run of the same file; stale SMTV episode reused for a different URL; tiling grid size not persisted;
  server port out-of-range not clamped on Start; directory/empty/non-http/multi-URL drop = silent no-op;
  download slider knobs can cross; Advanced "Download now" leaks the mousewheel bind; LAN-IP-detect-fail
  status wording.
- macOS-report mediums/lows (41+26) NOT triaged this round — e.g. _checkpoint language-validation (needs a
  signature change), config UNC `.exists()` startup hang, smtv CDN filename sanitize, history lastrowid=0,
  tiling lock/zombie reaping, writers/base time formatting. Triage each against CURRENT code (lines are stale)
  before fixing; many may already be guarded.

## 0. Latest session — Phases 1–6 + 44-bug audit fixpack → v1.3.8 (2026-06-06)

**Current state: v1.3.8.** On top of the v1.3.7 baseline: Phase 1 (9
changes) + Phase 2 (cloud + web/LAN) + Phase 3 (bug fixes + features) +
Phase 4 (config / multi-model / convert / stats / ffplay) + Phase 5
(frontend bug-hunt fixes) + Phase 6 (macOS support) + a **44-finding
adversarial audit fixpack** (each finding skeptic-verified and covered by
a hermetic regression test). Version bumped to **1.3.8** in the 4 knobs.
pyright `app/ core/` is 0/0/0 and the FULL hermetic suite is green in
deterministic order (the two `test_resume_from_cancellation` tests were
fixed — they now capture the checkpoint fingerprint in-scope, so they pass
mid-suite and no longer need deselecting).

**Branch / push status (2026-06-06):**
- All work lives on local `master`. The owner authorised publishing it to
  the `macos-ci` branch (NOT `master`) so a sibling macOS-CI session can
  build/test the `.app` on real Apple hardware via GitHub Actions.
- `macos-ci` was pushed (first at 9c5f1db, then updated with the fixpack +
  v1.3.8). Pushing `macos-ci` does NOT fire `ci.yml` (its push triggers are
  master / release/** / feature/** / chore/**), so it does not burn the
  Windows+Ubuntu Actions minutes. Do NOT push to `master` until the macOS
  build is green; `macos-ci` → `master` is merged ONCE at the end.
- Coordination: fetch + rebase onto `macos-ci`'s tip before pushing; never
  force-push / clobber the macOS session's commits (it owns
  `.github/workflows/macos-build.yml` and any Mac runtime fixes).

**Artifacts:** rebuild the Setup-Standard + Portable as **v1.3.8** from the
embed tree (the v1.3.7 artifacts under `dist_installer\` predate the
fixpack). Incremental rebuild = re-copy HEAD `app/`+`core/`+`gui.py` over
the tested `embed_build\` runtime → sanity import → ISCC `installer_embed.iss`
→ `shutil.make_archive` Portable → launch smoke. Helper: `.claude\rebuild_137.ps1`
(update the version strings to 1.3.8 first, or use a 1.3.8 copy).

> **Reiterate (do not skip):** everything in §0 (Phases 1–3) is **local
> only** — committed on `master`, **not pushed**, **no version bump / tag**.
> A release would still need the version bump in the **4 usual places**
> (`core/__init__.py` `__version__`, `pyproject.toml`, `installer.iss`,
> `installer_embed.iss` `#define MyAppVersion`) — see §3 — and is only cut
> when the owner authorises it.

The Phase-1 9 changes (grouped):

- **Model hub default → `%LOCALAPPDATA%\WhisperProject\Cache\models`**
  (was the install dir → "access is denied" for non-admin users). Added a
  typed `ModelDestinationNotWritable` + a re-pick flow in the
  model-download dialog, a writability probe in the hub picker, and aligned
  the default hub with `model_folder_for`'s empty-hub fallback
  (`HUB_SUBFOLDER_NAME = "models"`) so an existing `Cache\models` model is
  **reused, not re-downloaded** (~3 GB). Verified with a real
  `load_config()` probe on this machine.
- **GPU/CPU autodetect hardening** — a cheap cuDNN/cuBLAS runtime-load gate
  (CUDA only when usable); a self-healing model load that falls back to CPU
  int8 instead of crashing the worker (or falsely prompting a ~3 GB
  re-download); the effective device reported additively on the worker
  `ready` event; a live GPU/CPU badge + a one-time "running on CPU (slower)"
  warning gated to the GPU-detected-but-unusable case (`cpu_warning_shown`).
- **Always-visible per-task action bars** under both Queue tabs
  (Pause / Resume / Cancel / Re-run / Remove) + a status-cell click toggle;
  right-click menu + Esc kept. Download "pause" is stop-and-continue (keeps
  the `.part`, resumes via yt-dlp `-c`/`--continue`); disabled for SMTV
  downloads (no resume point).
- **Network / UNC drag-and-drop fix** — a backslash-preserving, brace-aware
  splitter so a `\\server\share\file` drop is no longer silently dropped
  (`tk.splitlist` was collapsing the leading `\\`).
- **Optional LAN/web server** — `python gui.py serve [--port] [--host]
  [--lan] [--token] [--max-upload-mb]`. Loopback by default (no firewall
  prompt); `--lan` is the explicit opt-in. Browser page + JSON API
  (upload OR URL jobs, progress poll, result download); in-process
  sequential transcription keeps the model hot; bounded queue + upload cap
  + optional token; jobs recorded to history. New Tk-free `core/server/`
  package; new keys `server_port` / `server_max_upload_mb`. Verified live
  here (`/api/health`, `/api/formats`, `/` all 200).
- **Multi-monitor Video Tiling rewrite** — a Tk-free engine (ported from
  the maintainer's `video-tiler` v1.1): one download fanned out to one
  `ffplay` per selected monitor, `poll()` liveness, exponential-backoff
  reconnect, self-heal `yt-dlp -U`, robust extraction, http(s) validation,
  clean teardown via `core._proc.kill_process_tree`. New `core/monitors.py`
  (screeninfo → ctypes Win32 → single-monitor fallback). New keys
  `tiling_quality` / `tiling_mute` / `tiling_multi_monitor` /
  `tiling_selected_monitors` / `tiling_auto_restart`. New optional dep:
  **screeninfo**.
- **Optional Google Gemini cloud STT backend** (`cloud_stt`) — paste a free
  AI Studio API key, transcribe via the Gemini API over stdlib REST
  (default `gemini-3.5-flash`, configurable), chunked upload via the Files
  API. Honest *local* minutes counter + a billing-console link. Loud
  privacy opt-in (uploads audio to Google → breaks the offline guarantee).
  New keys `cloud_stt_api_key` / `_model` / `_minutes_used` /
  `_free_minutes_cap` / `_chunk_seconds`.
- **Opt-in GitHub update check** (notify-only, never auto-installs) in
  `core/updates.py` + a Help-menu "Check for updates" + a throttled quiet
  launch check; silent on private-repo/offline/up-to-date. Documented that
  the Standard installer already upgrades **in place** (stable Inno
  `AppId`). New keys `update_check_enabled` / `last_update_check`.
- **Docs-only** — `docs/evaluations/GEMMA4_EVALUATION_2026-06.md`:
  recommends SKIP of Gemma 4 12B for transcription (30 s cap,
  torch/BF16/~24 GB VRAM, no word timestamps, no WER win), with a
  future-adjunct path + hardware-gate sketch.

### Phase 2 — real Google Cloud STT + one-click Web/LAN (same 2026-06-06 batch)

Committed locally on top of the Phase-1 nine (see the `git log` tail:
`9fd5b3b` … `a2d05f9`). Still LOCAL ONLY, still 1.3.7-labelled.

- **Real Google Cloud Speech-to-Text backend** (`google_cloud_stt`, new
  `core/backends/google_cloud_stt.py`) — a second, more capable cloud
  option next to the simple Gemini one. Authenticates with a
  **service-account JSON file** (NOT a pasted key) via the official
  `google-cloud-speech` **v2** client, installed **on demand on first use**
  (`core/optional_deps.py`) — NOT bundled. Two modes: (a) Standard/online —
  decode via ffmpeg, chunk the local file into ≤ ~55 s pieces, `recognize()`
  inline per chunk, offset + stitch timestamps, no Cloud Storage (~$0.016/min);
  (b) Batch — v2 `BatchRecognize` via a user-supplied GCS bucket (`gs://`),
  `DYNAMIC_BATCHING`, ~$0.004/min (~75 % cheaper) but up to ~24 h turnaround.
  Word-level timestamps + speaker diarization supported. The earlier Gemini
  backend (`cloud_stt`) is KEPT as the simple paste-a-key alternative; both
  labelled in the UI.
- **Cloud STT settings UI** (`app/dialogs/advanced.py`) — backend dropdown
  with human labels for both cloud options; a Google Cloud section with a
  service-account JSON picker, a "How do I get this file?" step-by-step help
  dialog (clickable links to the exact console pages), a non-blocking
  **Test connection** button (installs the libs on demand + validates the
  JSON/auth), a Batch-mode toggle + GCS bucket field, a diarization toggle,
  and a LIVE usage display.
- **Free-tier usage tracking** — a LOCAL **monthly** minutes counter (resets
  each calendar month) + an honest estimated-cost line ("X / 60 free minutes
  this month; estimated $Y of the $300 credit"), labelled a local estimate
  with a billing-console link (the real remaining credit is NOT readable
  from the key). New keys `gcloud_stt_minutes_used` /
  `gcloud_stt_minutes_month` / `gcloud_stt_free_minutes_cap`.
- **One-click Web / LAN access** (`app/app.py` + `app/widgets/tabs.py`, a
  `core/server` `ServerHandle`) — a new **Web / LAN access** tab with a
  single Start/Stop toggle, a port field (free-port fallback when busy), a
  **Share on local network** checkbox (loopback default vs `0.0.0.0` with a
  plain firewall note), an optional access password (token), the reachable
  URL(s) incl. LAN IP, an **Open in browser** button, non-blocking
  start/stop, and auto-stop on exit. New keys `server_share_lan` /
  `server_token` (`server_port` / `server_max_upload_mb` already existed).
- **About dialog enriched** (`app/app.py` `_show_about`) — a "What's new"
  section + plain-language descriptions of all the cloud options, Web/LAN
  access, per-task controls, multi-monitor tiling, and the update check /
  in-place upgrade, with clickable helpful links.
- **New docs** — `docs/CLOUD_STT_GOOGLE.md` (service-account setup + batch +
  honest usage note); `docs/SERVER.md` updated for the one-click toggle. All
  new `gcloud_stt_*` / `server_*` keys documented in `docs/CONFIG.md`.

### Phase 3 — bug fixes + features + live-verified Google Cloud STT (same 2026-06-06 batch)

Committed locally on top of Phase 2. Still LOCAL ONLY, still 1.3.7-labelled,
NOT pushed, NO version bump. From a reported-issues list + a deep
adversarial review. Full user-facing bullets in `docs/CHANGELOG.md`
`[Unreleased]` (`#### Phase 3` blocks under Added / Changed / Fixed / Docs).

Bug fixes:
- **Web / LAN: every job crashed** with `'_CancelledTask' object has no
  attribute 'paused'` — the server task object now mirrors the engine's
  read contract (renamed `_ServerTask`); test fakes hardened.
- **"View transcript" closed the whole app** — libvlc `set_hwnd` on an
  unrealized Tk window (a native crash that bypassed `try`/`except`). Fixed
  by deferring the HWND bind until the window is mapped + a graceful
  fallback; the viewer now opens the actual transcript `.json` (no spurious
  file-picker).
- **"Re-detect hardware" froze the UI** — the probe ran on the Tk main
  thread (+ an unbounded cuDNN/cuBLAS `ctypes.CDLL` probe). Fixed: runs
  off-thread behind a generation-token guard + a timeout-bounded DLL probe.
- **Queue per-task action bar was unusable** — the 500 ms `refresh()`
  rebuilt the tree and wiped the selection; selection is now preserved
  across the rebuild.
- **Off-thread Tk writes fixed** — the Video Tiling log callback + 4
  Advanced-dialog worker handlers now marshal through the main thread (new
  `App.log_threadsafe`); tiling status colour now applied.
- **Smaller** — status-cell click defers via `after_idle`; `start_tiling`
  guards a bad grid spinbox; `pause_download` only pauses a running
  download; theme + download-folder `save_config` guarded;
  `minimise_to_tray` / `telemetry_opt_in` added to `DEFAULT_CONFIG`;
  multi-file enqueue gates the model once; Advanced mouse-wheel binding
  released on close; server handle registered before `start()`.

Features:
- **VLC transcript preview seek/scrub transport bar** — draggable position,
  `MM:SS` readout, ±5 s / ±10 s skip, keyboard; degrades gracefully without
  VLC.
- **Web / LAN feature parity** — per-job advanced options (VAD, word
  timestamps, diarization, clip range, …) via a per-job
  `.whisperproject.json` override; `GET /api/jobs` list; pause / resume
  routes; outputs from the engine's `task.output_paths`; a 3-view browser
  UI (Submit / Jobs / Result with inline transcript); streaming uploads (no
  full-RAM buffering); HTTP hardening (body-drain on early reject,
  constant-time token compare). Cloud / alt backends are NOT per-job
  switchable over the web (security boundary).
- **"SMTV transcription" docx output format** (registry key `smtv_docx`, UI
  label "SMTV transcription") — fills the bundled template
  `core/writers/templates/smtv_template.docx`: a 4-column table (auto row #;
  `Time Code` `HH:MM:SS.m`; `Foreign Language` = transcript; `English
  Translation` empty for the human), title line
  `"<work title> -Transcription in <language> – Translation in English"`,
  filename matched; grows the table past 31 rows; forces a `.docx` extension.
- **Google Cloud STT fixes — LIVE-VERIFIED** with the owner's
  service-account JSON (project `crucial-context-297802`): default
  model/location is now `chirp_2` / `us-central1` (supports auto-detect +
  multilingual; the old `long` / `global` rejected `"auto"`); language codes
  mapped ISO → BCP-47 (Google v2 rejects a bare `"en"`); word time offsets
  always requested + words re-segmented into properly-timed phrases (a real
  run produced 5 correctly-timed subtitle segments instead of one 0–30 s
  blob). `config.py` `gcloud_stt_model` / `gcloud_stt_location` defaults
  updated; `docs/CONFIG.md` + `docs/CLOUD_STT_GOOGLE.md` updated.
- **Installer Video-Tiling opt-out** — a "do NOT include Video Tiling" task
  in `installer_embed.iss` drops a `{app}\no_tiling.flag` marker; the app
  hides the Video Tiling tab when present (`core.hub.tiling_tab_enabled()`).

**SETUP NOTE — the app now DEFAULTS to Google Cloud transcription
(uploads audio to Google):** the owner's service-account JSON at
`C:\Users\Owner\Desktop\whisper_project_claude\crucial-context-297802-71bbe43c6f33.json`
is set as the app default in the user config
(`transcribe_backend = google_cloud_stt` + `gcloud_stt_credentials_json` +
`gcloud_stt_model = chirp_2` / `gcloud_stt_location = us-central1`). This is
the **dev machine's** config, not a shipped default — but be aware the app
here uploads audio to Google by default. **To switch back to offline:**
Advanced > Backend → `faster_whisper`. `google-cloud-speech` installs on
first use (on demand); **batch mode** additionally needs a GCS bucket +
**Storage Object Admin**.

### P4 BACKLOG — planned, NOT yet implemented

New requests from
`C:\Users\Owner\Desktop\new jobs\claude_request_v1.38.txt`. Recorded as
planned for a future session; nothing below is built yet.

- **P4-1 — three-level merged configuration** (hard-coded → online-URL →
  local-file) so model URLs / the usage-stats URL / latest-version /
  ffplay links can change **without redistributing** the app.
- **P4-2 — config-driven multi-model + an Advanced model selector** — add
  `faster-whisper-medium`, `large-v3-turbo`, `distil-large-v3.5`;
  `large-v3` stays the default.
- **P4-3 — transcription format CONVERSION** — JSON ↔ SRT / VTT / TSV / TXT
  (+ `.otr` import), with the faster-whisper JSON as the middle format.
- **P4-4 — usage stats** — a "word count" column in the sqlite
  transcription table + a PHP online stats tracker (IP / geoip via
  `smch.ir`, filename, model, language, duration, AI time, status) + the
  app POSTing stats.
- **P4-5 — ffplay download links in config** for auto-fetch on Windows /
  macOS.

**Build/spec bookkeeping done:** the PyInstaller hidden-import lists in
both `whisper_project_onefile.spec` and `whisper_project_onedir.spec` carry
all the new modules — Phase-1 (`core.server.*`, `core.monitors`,
`core.backends.cloud_stt`, `core.updates`) + **screeninfo** AND the Phase-2
backend (`core.backends.google_cloud_stt`) — both verified present this
session. The `google-cloud-speech` / `google-cloud-storage` libs install on
demand at runtime, so they are deliberately NOT bundled (only the backend
module that imports them lazily is).

**OPEN caveats for the next session (re-check; don't assume done):**
- **R6 Gemini path is UNTESTED end-to-end** — no API key in this
  environment. The owner must live-test with their own key: paste key →
  "Test key" → run one file → confirm a transcript lands and the local
  minutes counter advances.
- **The real Google Cloud STT (`google_cloud_stt`) network path is UNTESTED
  here** — no service-account JSON in the dev environment. The owner must
  live-test: in **Advanced > Backend** pick the JSON file → click **Test
  connection** → run a file. **Standard mode** needs only the JSON + the
  **Cloud Speech-to-Text User** role + the Speech-to-Text API enabled.
  **Batch mode** additionally needs a GCS bucket + **Storage Object Admin**
  on it. The `google-cloud-speech` (+ `google-cloud-storage` for batch) libs
  install on **first use** (on demand), NOT bundled — so the first run with
  this backend will pause to pip-install them.
- **screeninfo is a NEW optional dependency** — multi-monitor tiling
  degrades to single-monitor without it; it's pruned/absent in some build
  trees, so confirm the Monitors chooser behaves when it's missing.

**A build was produced this session** (the build path is appended
separately) — still **v1.3.7-labelled, unreleased, local only**.

**PRE-EXISTING test issues (NOT introduced this session — present at the
baseline commit `53fc8b2`, so not a regression):**
- `tests/core/test_resume_from_cancellation.py` is **order-dependent** —
  it fails in isolation even at baseline `53fc8b2`; passes under the full
  suite ordering.
- `tests/core/test_v08_real_file_e2e.py` is a **real-model E2E** that
  ERRORs under full-suite session ordering (needs the real model + a
  hot worker; not hermetic).
- A Tk-root **"Can't find a usable tk.tcl"** flake on the local Python
  3.14 box (environment quirk, not our code).
- These are why the deferred test-gap items (§0.1 below) still need a
  heavier harness; do NOT treat their flakes as new breakage.

**A release would still need the version bump in the 4 usual places**
(`core/__init__.py` `__version__`, `pyproject.toml`, `installer.iss`,
`installer_embed.iss` `#define MyAppVersion`) before building — see §3.

---

## 0.1. Earlier session — senior-architect deep audit (2026-05-29)

A read-only audit fanned out 8 parallel shards (concurrency, resource
leaks, security, error-handling, data-integrity, cross-platform,
test-gaps, maintainability) → 53 raw findings → 20 verified-real + 32
P2 + 1 rejected. Fixed in 8 themed commit batches, each gated on
`pyright app/ core/` 0/0/0 + the hermetic suite green, pushed to
`master`. Full list in `docs/CHANGELOG.md` `[1.3.7]` (this batch SHIPPED as
v1.3.7 on 2026-05-29). Method + raw findings: `.claude/audit_findings.md`
(workspace, untracked).

**Shipped behaviour:** no change to Windows spawn flags; the fixes are
teardown/robustness/correctness. **Released as v1.3.7** (this was the batch
deferred at the time; it has since shipped).

**Deferred, with reason (re-check; don't assume done):**
- **Test-gaps not yet covered** (cover already-shipped code, lower risk,
  need heavier harnesses): P2-19 headless ready-timeout teardown; P2-21
  crash-resume `_do_resume` closure (needs a Tk-ish fake or a pure-helper
  refactor); P2-22 SMTV `_apply_smtv_formats` mapping (+ a 'max'-quality
  variant is dropped — worth confirming intent); P2-23 Advanced-settings
  `_save_and_close` var→config round-trip (best after extracting a pure
  `collect_advanced_config` helper).
- **P2-31** `ensure_worker_ready(headless=True)` + `start_standby()` are
  dead in production (only tests call them) and would deadlock if reused
  on the Tk thread. Left in place — tests depend on `headless=True` and a
  runtime "am I on the Tk thread?" guard is unreliable. Already documented
  as deprecated in their docstrings; use `_when_worker_ready` instead.
- **REJ-1 (NOT a bug):** the PDF writer not stripping XML-illegal control
  chars was investigated and is harmless — reportlab 4.x uses a lenient
  HTMLParser, not a strict XML parser, so NUL/ESC/etc. build a valid PDF.
  No fix needed (verified empirically).
- **P2-14 (doc-only):** LRC timestamps render 3-digit minutes past 100 min
  (LRC has no hours field); strict players may mis-seek. Left as-is —
  inherent to the format.
- **macOS [13]/P2-16 + Linux**: the ffmpeg-into-bin symlink + non-fatal
  unzip are `bash -n`-clean and reasoned-correct but UNVERIFIED on a real
  Mac. Class-C yt-dlp/ffprobe items (keyframe snap, etc.) untouched —
  still need a real yt-dlp+ffprobe harness before changing.

**Suggested live re-validation next session** (needs the model + test
video): `python tools/e2e_cancel_pause.py` exercises the real worker's
cooperative cancel/pause/resume — confirms the process-tree-kill +
modal-close changes (batches A/C) didn't disturb the cooperative path.

---

## 1. Current state (2026-05-25)

| Item | Value |
|---|---|
| Branch | `master` — **the single mainline**. Published tip is **v1.3.7** (deep-audit hardening, see §0.1). On top of that sit the **2026-06-06 LOCAL-ONLY changes — Phase 1 (9 changes) + Phase 2 (real Google Cloud STT, one-click Web/LAN, enriched About) (see §0) — committed, NOT pushed, NOT released.** Owner will authorise the push/release later. |
| Version | **unchanged — still 1.3.7** in all 4 places (pyproject, `core.__version__`, both `.iss`). This session deliberately did NOT bump — the Phase-1 + Phase-2 changes are unreleased; bump only when the owner authorises the release. |
| Last PUBLISHED release | **v1.3.7** on GitHub (Standard 219 MB + Portable 325 MB) — the deep-audit security/leak/robustness/correctness pass (§0.1); built + slim past-bug E2E PASS + live cancel/pause E2E PASS + hermetic suite green + pyright 0/0/0; published 2026-05-29. |
| GitHub releases now | `v1.3.7` (latest) + `basic-v0.1.0` (separate edition). **POLICY (2026-05-26 owner): keep ONLY the latest release — prune the rest on each release.** v1.3.6 release object was pruned on the v1.3.7 release; its git tag + the local `dist_installer/WhisperProject-v1.3.6-*` artefacts remain as backup. |
| Installed test copy | none built (validated by `tools/e2e_slim_pastbugs.py` + `tools/e2e_cancel_pause.py` against the real worker). The user installs the published EXE themselves. |
| Default GitHub branch | `master` (now the ONLY branch — origin has just `master`) |
| Working tree | local commits ahead of `origin/master` (the §0 nine-change batch + the docs/test-cleanup); untracked tooling (`.claude/`, `PROJECT_INDEX.md`, `AGENTS.md`, `.cursorrules`, `tools/index_refresh.py`) left as-is |
| Gate | `pyright app core` → **0/0/0** (re-verified this session). Full `run_tests.bat` hermetic suite NOT re-run this session — see the PRE-EXISTING test flakes in §0 before reading any red as a regression. |
| Build prereqs (this PC) | Inno Setup `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` ✓ · test video `E:\3029-NWN-Daily-Scroll-2m_0002.mp4` ✓ · extracted model under `%LOCALAPPDATA%\WhisperProject` ✓ |
| Version source of truth | `core/__init__.py` `__version__` (bundled; About dialog + telemetry read it). Bump it with pyproject + both `.iss` every release. |

### What shipped in v1.3.6 (PUBLISHED 2026-05-26)

Video Tiling tab + Linux/macOS groundwork. Full list: `docs/CHANGELOG.md`
+ `docs/RELEASE_NOTES_v1.3.6.md` + the plan in
`docs/CROSS_PLATFORM_ROADMAP.md`. Headlines: **Video Tiling tab**
(`core/tiling.py` + `build_tiling_tab`) — one live stream filled across the
screen as an N×N grid via `yt-dlp | ffplay -vf tile=NxN` (ports
`translation-robot/video-tiler`); **ffplay is NOT bundled** (would bloat
the build), so the tab detects its absence and tells the user to drop
`ffplay.exe` in `bin/` or put ffmpeg on PATH. **Cross-platform core
hardening** — `yt-dlp`/`ffmpeg`/`ffprobe` resolve per-OS via
`core.paths.bundled_binary` (PATH fallback), `--ffmpeg-location` is only
passed when a bundled ffmpeg exists, VLC discovery covers macOS/Linux; the
Windows build is byte-for-byte the same shape. **`platform/linux/`** (one-
step `install.sh` venv + deps + static-ffmpeg fallback + a headless
`whisper-transcribe` CLI + update/uninstall) and **`platform/macos/`**
(`install.command` + `unblock.command` for Gatekeeper + README). A
`.gitattributes` pins LF on `*.sh`/`*.command`.

**Follow-ups for a future session:**
- Video Tiling needs **ffplay** to actually run. To make it work
  out-of-box on Windows, add `bin/ffplay.exe` (from the full ffmpeg build)
  — either commit it (repo already LFS-warns on the ~97 MB ffmpeg.exe) or,
  cleaner, have `build_embed_installer.bat` fetch ffplay into
  `embed_build/bin` at build time. Deferred to keep the build/repo size
  unchanged this release.
- **macOS is unvalidated** — no Mac was available. The code + scripts
  follow best practice but need a real-device run (see `platform/macos/README.md`).
- Linux scripts are `bash -n`-clean but not run on a real distro here; the
  maintainer confirmed transcription works on their Linux server.

### What shipped in v1.3.5 (PUBLISHED 2026-05-25)

Real Pause/Resume/Cancel + a post-slim hardening pass (five parallel
code-audit shards over everything that changed in v1.3.x). Full list:
`docs/CHANGELOG.md` + `docs/RELEASE_NOTES_v1.3.5.md`. Headlines:
**cooperative pause/resume/cancel (#37)** — the worker now reads control
commands on a dedicated `worker-stdin` reader thread and flips the
in-flight task's `cancelled`/`paused` flags while the main thread is busy
in `transcribe()`; the transcriber already polled those between segments
(and flushes a resumable checkpoint on cancel), so only signal delivery
was missing. `app/app.py` pause/resume/cancel now call
`TranscriptionService.send_control(task, action)` instead of killing the
worker; a per-worker `stdin_lock` serialises the three concurrent writers.
**The worker reports the files it actually wrote** in the `done` event
(`task.output_paths` → `finish_task` history + `show_last_result`), so a
docx/pdf-only run no longer shows "no output files found". Plus the audit
fixes: a "transcribing" download row is cancellable; `_fmt_timecode`
sub-second carry (`1:30.999` → `0:01:31`); per-format writer resilience
(one bad writer no longer discards the good ones); pausing a not-yet-
running task is a no-op; `progress_cell`/`marquee_cell` tolerate a
non-finite percent; on-demand installs are serialised + log on the UI
thread; the slim build drops the orphaned `llvmlite.libs` and its sanity
check imports docx/reportlab to guard the docx-regression class. New
tests: `test_worker_control`, `test_cancel_checkpoint` (deterministic
faked-model cancel→checkpoint), done-event outputs, sub-second timecode;
new live driver `tools/e2e_cancel_pause.py`.

### What shipped in v1.3.4 (PUBLISHED 2026-05-25)

Slim install + on-demand optional deps + the docx fix. Full list:
`docs/CHANGELOG.md` + `docs/RELEASE_NOTES_v1.3.4.md`. Headlines:
**slim ~800 MB install** (was ~1.5 GB) — `build_embed_installer.bat`
now prunes the heavy optional libraries (torch, torchaudio,
openai-whisper, stable-ts, numba, llvmlite, sympy, networkx, mpmath)
after pip install; the Standard installer dropped 348 MB → 219 MB and
the Portable ZIP 557 MB → 326 MB. **On-demand optional features**
(`core/optional_deps.py`) — Word-timestamp alignment (stable-ts) and the
openai-whisper backend now `pip install --target` into a user pylibs dir
(~700 MB, one time) the first time they're used; `app/app.py`
`_offer_optional_install` asks first (askyesno + a threaded Toplevel
progress), then restarts the worker. The core stack (faster-whisper) is
still bundled so transcription/subtitles/diarisation/downloads/the
time-range slider all work out of the box. **DOCX (+ PDF) output fix** —
the worker's config snapshot was stale, so `output_formats` never crossed
the process boundary and docx was silently dropped; `output_formats` is
now threaded transcribe_command → worker → `_write_outputs`.
New: `tools/e2e_slim_pastbugs.py` (slim-build past-bug release gate) +
`tests/core/test_optional_deps.py`.

### What shipped in v1.3.3 (PUBLISHED 2026-05-25; pruned then RESTORED — still on GitHub)

Position slider on the Download tab (#39) + clip/range review fixes, and
the first Portable ZIP of the embed tree. Full list: `docs/CHANGELOG.md`
+ `docs/RELEASE_NOTES_v1.3.3.md`. Headlines: a **draggable Start/End
position slider** on the Download tab (`set_download_duration` /
`_on_download_scale`, guarded by `_suppress_scale_cb` + a
`_download_duration<=0` disable) wired to the time-range fields; review
fixes from three code-review shards — the slider `set()` no longer
clobbers typed values, a clipped run forces `resume=False` (no checkpoint
keyed to the whole file), and `start>=end` is dropped to open-ended.

### What shipped in v1.3.2 (PUBLISHED 2026-05-25, now pruned from GitHub)

Security + features, after a second bug-hunt (4 more parallel shards:
concurrency, resource-leaks, hostile-input, security). Full list:
`docs/CHANGELOG.md` + `docs/RELEASE_NOTES_v1.3.2.md`. Headlines:
**SECURITY** — yt-dlp option injection closed (a "-"-prefixed pasted URL
could hit `--exec`; `"--"` end-of-options added in all 3 yt-dlp argv
builders, regression-tested) + zip-slip guard on model-archive extract;
**Transcribe-tab time range** (#28) — clip_timestamps through the worker,
end-to-end verified (transcribed only 120–180s of a 10-min file, original
timeline, progress→100%); **multi-site download error visibility** — the
queue now shows yt-dlp's real ERROR line + a "Cookies from browser" hint
for login-walled sites (Facebook); **ffprobe "N/A"** tolerated;
**progress %% kept visible** during the startup marquee; a contributed
**hub_folder/model_path** fix (collaborator commit 5b59fbc).

### Still pending (next session)
- **#37 worker cancel/pause/checkpoint — DONE in v1.3.5.** A cooperative
  control channel now delivers cancel/pause/resume to the running worker
  (a `worker-stdin` reader thread flips the in-flight task's flags); pause
  truly halts, resume continues, and cancel flushes a resumable checkpoint
  instead of killing the worker. Proven by `tests/core/test_worker_control.py`
  + `tests/core/test_cancel_checkpoint.py` + `tools/e2e_cancel_pause.py`.
  Residual (NOT addressed): `ensure_worker_ready(headless=True)` could
  still deadlock if ever called on the Tk main thread — low risk (the
  headless path is only invoked off the main thread today).
- **Resource leaks — RESOLVED 2026-05-29 (deep audit, see §0.1).** Worker/
  yt-dlp now tree-killed via `core/_proc.py` (no orphaned ffmpeg/demucs);
  `partials/` swept at startup + cleared on declined crash-resume;
  HistoryDB closed in on_exit; demucs cache bounded; recorder streams to
  disk. Commits `cd402c9` + `7c91285`.
- **#38 selector tuning** — the download selector already falls back to a
  combined stream (`/best`) so it isn't YouTube-locked; the real fix
  shipped is the ERROR SURFACING. Once a user retries Dailymotion on
  v1.3.2 and the queue shows the actual error, fix that specific cause
  (don't change the selector blind — risks the proven YouTube path).
- **burn_subs filter escaping — RESOLVED 2026-05-29 (deep audit, see §0.1).**
  Subtitles now burn from a temp copy with a graph-safe ASCII name, so
  `' [ ] , ;` in a (downloaded) title can't break/inject the ffmpeg filter
  graph; the colon-escape is gated to Windows. New `tests/core/test_burn_subs.py`.
  Commit `0204cc8`.

### What shipped in v1.3.1 (PUBLISHED 2026-05-25, now pruned from GitHub)

Reliability bug-hunt on top of v1.3.0 (traced each UI action through the
code + four parallel audit agents). Full list: `docs/CHANGELOG.md` +
`docs/RELEASE_NOTES_v1.3.1.md`. Headlines: **non-ASCII filename downloads
now transcribe** — yt-dlp stdout forced to UTF-8 (`_utf8_subprocess_env`)
PLUS a self-healing fallback (`DownloadService._recover_saved_path`) that
finds the real downloaded file if the parsed path is wrong; **language
codes normalized on the DEFAULT path** (`_normalize_language` now in
`_build_transcribe_kwargs`, not just the alt-backend call — fixes "en-US"
and multi-value picker codes like "zh-Hans,zh-CN" crashing the worker);
**VLC found via registry/Program Files** with a clear 64-bit hint
(`_locate_vlc_dir`); **download cancel stops the linked transcription** +
**re-run keeps the time-range**; **optional-dep probes catch OSError**
(diarization/parakeet/whisper_cpp no longer crash the app on a bad native
DLL — VLC bug class); Transcribe **path validation**; demucs via
`sys.executable`. Plus the queue **"working" marquee** animation and the
**0:00:00 time-range defaults**. New tests: test_normalize_language,
test_recover_saved_path, test_transcribe_kwargs, test_progress_cell
(+marquee).

### Still pending (next session)
- **#28 — time-range for the Transcribe tab**: let the user transcribe
  only a slice of a long local file. Recommended approach: faster-whisper
  `clip_timestamps` threaded through `_build_transcribe_kwargs` (the
  central kwargs builder), with the per-segment progress % computed
  relative to the clip bounds (transcriber.py:~1123) so the bar still
  fills 0→100. Add Start/End fields to the Transcribe tab + clip_start/end
  on TranscriptionTask.
- **Minor**: `watched_folder` has no `_drive_is_mounted` deferral like
  download_folder/model_path, so a not-yet-mounted/temp watched folder is
  silently dropped at launch (app/app.py watched-folder branch). Low
  urgency (degrades gracefully, just doesn't watch).

### What shipped in v1.3.0 (published 2026-05-25, now pruned from GitHub)

UX + reliability on top of v1.2.0. Full list: `docs/CHANGELOG.md` +
`docs/RELEASE_NOTES_v1.3.0.md`. Headlines: **fixed auto-transcribe after
a merged video+audio download** (the saved-path parser matched the
yt-dlp-deleted audio fragment, so Shorts / reels silently failed to
transcribe — now `select_saved_path` makes the merged file win); per-row
**graphical progress bars** in both queues (`progress_cell`); the
**version is now visible** (window title `_base_title` + a version-stamped
installer shortcut via a `#define MyAppVersion` knob); the **Download row
shows "transcribing" + live progress** after an auto-transcribe (linked
via `TranscriptionTask.source_download` ↔
`VideoDownloadTask.transcription_task`, flipped back in `finish_task`);
the **"Last result" card** no longer expands to fill the Transcribe tab;
and the **language picker resets to "Auto" every launch** (no longer
persisted; other prefs still are).

### What shipped in v1.2.0 (published 2026-05-25, now pruned from GitHub)

UX + accessibility on top of v1.1.0. Full list: `docs/CHANGELOG.md` +
`docs/RELEASE_NOTES_v1.2.0.md`. Headlines: app-wide copy/paste fix
(layout-independent Ctrl+C/V/X/A + right-click menus on every text field
+ a copyable log console), bulk multi-select queue actions (cancel /
re-run / resume / remove), auto-hiding queue scrollbars, model
download-status + a "Download now" button, "Open file" for finished
downloads, output-file de-dup (`name (1).srt`), the About dialog showing
the live version, and a stable installer `AppId` (single Add/Remove
entry that upgrades cleanly).

### v1.1.0 changes (folded into the published v1.2.0; v1.1.0 itself pruned)

Audio-in-downloads fix, the main-thread model-load freezes (download /
crash-resume / watched-folder), model-hub + download-folder persistence,
crash-resume nag, truncated-SMTV-download, About repo-URL removal, and
the opt-in "Cookies from browser" feature. Bug-hunt method + findings:
`docs/AUDIT_2026-05-25_boundary_bugs.md`.

## 2. Shipped deliverables — Standard + Portable (both embed-based)

Two published assets per release, both built from the slim
`embed_build\` tree (embeddable CPython 3.11 + deps):

| Asset | Local path | Size (v1.3.4) | Notes |
|---|---|---|---|
| Setup-Standard | `dist_installer/WhisperProject-v1.3.4-Setup-Standard.exe` | 219 MB | installs to Program Files (admin), shell-extension + shortcuts |
| Portable | `dist_installer/WhisperProject-v1.3.4-Portable.zip` | 326 MB | `shutil.make_archive` of `embed_build\`; extract + run `Run Whisper Project.bat`, no install |

History: v1.0.3 shipped a PyInstaller Portable EXE; 2026-05-24 the policy
was "Standard only"; **the user then asked for Portable back as a ZIP of
the embed tree (v1.3.2+).** Both ship now. The PyInstaller Compact
(`whisper_project_onedir.spec` + `installer.iss`) and onefile Portable
(`whisper_project_onefile.spec`) pipelines remain maintained-but-unshipped
(keep their hidden-import lists current so they don't bit-rot).

Download from:
**[github.com/Milomilo777/whisper_project_direct_download_v2/releases/latest](https://github.com/Milomilo777/whisper_project_direct_download_v2/releases/latest)**

## 3. RELEASES — v1.3.6 latest, DONE (2026-05-26).

**v1.3.6** is live (Video Tiling tab + Linux/macOS groundwork; Standard
219 MB + Portable 326 MB). The step log below is from v1.3.4 and documents
the identical pipeline (bump → build → compile → zip → e2e → publish).

**Release policy (2026-05-26 owner — reverses the 2026-05-25 keep-all):**
- **Keep ONLY the latest release.** After publishing vNEW, DELETE the older
  release objects (`gh release delete vX.Y.Z --yes` — keeps the git tag +
  the local `dist_installer/` installer as backup). Only the latest + the
  separate `basic-v0.1.0` stay on the Releases page. (So step 7 below now
  means "prune the previous release," the opposite of before.)
- **Release LESS often** — batch several features/fixes per version
  (owner: "half or a third the speed"); don't cut a version per small change.
- **Push in batches** — commit locally often, push several commits together.

---

v1.3.4 was live on GitHub (Standard + Portable). Steps that ran:

1. ✅ Gate green: pyright `app/ core/` 0/0/0; hermetic suite (tests/ minus
   tests/smoke) exit 0.
2. ✅ Slim embed rebuild (`build_embed_installer.bat`, now prunes the
   heavy libs) — `embed_build\` = **805 MB** (was 1.6 GB), "embed_import_ok"
   + "build complete". Verified: torch/stable_whisper/whisper absent,
   faster_whisper present, `optional_deps.is_available("alignment"/"whisper_backend")`
   both False (on-demand path live).
3. ✅ Standard installer compiled clean (290 s) →
   `dist_installer\WhisperProject-v1.3.4-Setup-Standard.exe` (**219 MB**,
   size-stable + MZ magic). IMPORTANT: ISCC writes the EXE incrementally —
   wait for the "Successful compile" line / a stable size before publishing
   (a mid-write EXE looks smaller and ships corrupt). Here the background
   task exited 0 AND printed "Successful compile", so the size was final.
4. ✅ Portable ZIP via `embed_build\python\python.exe -c "shutil.make_archive(...)"`
   → `dist_installer\WhisperProject-v1.3.4-Portable.zip` (**326 MB**,
   testzip OK, has `Run Whisper Project.bat` + `gui.py`, no torch).
5. ✅ Past-bug E2E on the slim embed tree (`tools/e2e_slim_pastbugs.py`,
   run with the embed python) — drives the REAL worker over JSON stdin/
   stdout and asserts every output format lands. PASS: docx (36954 B, valid
   PK magic) + srt + json + txt all written; `en-US` normalised to `en` (no
   crash); clip 0–20s produced output (progress→100); apostrophe+space
   filename round-tripped.
6. ✅ Published — `gh release create v1.3.4 <Standard.exe> <Portable.zip>
   --target chore/cleanup-hardening --notes-file docs/RELEASE_NOTES_v1.3.4.md`;
   both assets `state=uploaded`, sizes match local.
7. ✅ Pruned v1.3.3 (`gh release delete v1.3.3 --cleanup-tag --yes`) —
   GitHub now has only `v1.3.4` + `basic-v0.1.0` (archive tags kept).
   **POLICY CHANGE (2026-05-25): this was the LAST prune.** Right after
   v1.3.4 shipped the user said "از این به بعد نسخه‌های قدیمی را پاک نکن" —
   do NOT delete old releases going forward. Future releases publish the
   new version and **leave every prior release + tag in place**. (The
   pruned v1.3.3 local artefacts still sit under `dist_installer/` if the
   user ever wants v1.3.3 re-published.)
8. **GUI-manual checks for the user** (not automatable): pick docx in
   Advanced settings → confirm a .docx lands next to the media; select
   Word-timestamp alignment → confirm the on-demand download prompt appears
   (and works) on a machine without torch; the Download-tab position slider;
   a non-YouTube / login-walled download (the queue shows the real error +
   cookie hint).

**To cut the NEXT release** (vX.Y.Z), bump the version in
`core/__init__.py` + `pyproject.toml` + both `.iss` files (the embed
`.iss` reads `#define MyAppVersion`), then repeat steps 1–7 — and step 7
now means **prune the previous release** (`gh release delete` the old one,
keep only the latest + `basic-v0.1.0`). Use absolute
paths via `cmd.exe` (a background cmd may not inherit cwd); `<REPO>` =
`C:\Users\Owner\Desktop\whisper_project_claude\whisper_project_direct_download_v2`.
Full step-by-step lives in `docs/RELEASE_PROCESS.md`.

### Deferred bug-audit items (`docs/AUDIT_2026-05-25_boundary_bugs.md`)
- SMTV cancel-latency on a stalled socket + no-retry; a site-layout
  change silently empties the article transcript.
- Worker-lifecycle: ~~`_pending_load_*` dangle if the awaited worker
  dies~~ **RESOLVED 2026-05-29** (Batch C [1], commit `f2c2991`): the
  loading modal now closes on startup_error/worker_exit and the pending
  state is cleared. STILL OPEN: `startup_error` still `stop_all()`s ALL
  workers + clears `app.workers`, not just the failing one (low impact —
  usually only one worker exists at first-transcribe; left for a targeted fix).
- Download rows stuck `interrupted` skew `stats()`.
- Hardware-probe stall (async attempt was REVERTED — a real fix needs
  `test_hardware_wizard_constructs_without_crashing` made async-aware).
- **Class C — needs a REAL yt-dlp + ffprobe harness before changing:**
  `--download-sections` keyframe snap (clip starts early), sub-second
  timecode, open-left `*-MM:SS` bound. Do NOT "fix" these blind.
- Older: P1s in `docs/STABILITY_AUDIT_2026-05-23.md`; SMTV server-side
  time-range slicing (limitation in `docs/integrations/smtv-brief.md`).

## 4. Branch + tag map

```
origin/master                       ← THE single branch; HEAD; carries v1.3.5
  tag v1.3.5                        ← the current release commit
  tag v1.3.4, v1.3.3                ← kept (releases are never pruned)
  tag v1.0.3                        ← earlier release commit (7295872)
  tag archive/cleanup-hardening-final ← old chore/cleanup-hardening tip (= master now)
  tag archive/basic-edition         ← old basic-edition tip (998 tests + downloads)
  tag archive/master-pre-merge      ← old (pre-2026-05-25) master Session-9 lineage
  tag archive/release-v0.7-baseline ← pre-orphan snapshot (recovery aid)
  tag v0.7.1, v0.7.0                ← historical releases
```

master's current history is the former `chore/cleanup-hardening` orphan
lineage (a squashed base + the v1.0.3 → v1.3.5 commits) — that's the
preserved project progress. The superseded pre-merge master (Session-9
era) and the deleted branches all live on as the `archive/*` tags above,
so nothing was lost.

## 5. The 1-line restart prompt

```
Read docs/SESSION_HANDOFF_NEXT.md first, then continue on master (the single mainline). Normal pushes to master are fine; don't force-push / rewrite master and don't move or delete published release tags (v1.0.3+ are public) without an explicit ask.
```

## 6. Forbidden actions (durable; mirrors CLAUDE.md)

- Don't `git push --force` / rewrite history on `master` (without an
  explicit ask) — normal pushes are fine now that master is the mainline
- Don't move or delete a **published release tag** (`v1.0.3`+ are public;
  moving them invalidates downloaded artefacts)
- Prune old GitHub releases — keep ONLY the latest + `basic-v0.1.0`
  (2026-05-26 owner; reverses the 2026-05-25 keep-all). Release less often;
  push commits in batches.
- Don't touch `.git/config`
- Don't code-sign the EXE

## 7. Sanity-check commands for the next session

```cmd
cd C:\Users\Owner\Desktop\whisper_project_claude\whisper_project_direct_download_v2
git log --oneline -5
git status
pyright app/ core/
python -m pytest tests/ --ignore=tests/smoke
```

Expected: the full hermetic suite passes (exit 0), pyright 0/0/0,
working tree clean. Optionally re-run the slim-build release gate
`embed_build\python\python.exe tools\e2e_slim_pastbugs.py` (PASS) after a
rebuild.

## 8. Key documents

| Doc | Purpose |
|---|---|
| [README.md](../README.md) | Project overview + install + config |
| [docs/INSTALL.md](INSTALL.md) | End-user install steps |
| [docs/BUILD.md](BUILD.md) | Two shipped build pipelines + the unshipped Compact one |
| [docs/ARCHITECTURE.md](ARCHITECTURE.md) | Process model + threading |
| [docs/CONFIG.md](CONFIG.md) | Every config key documented |
| [docs/history/DEEP_AUDIT_BRIEF.md](history/DEEP_AUDIT_BRIEF.md) | Senior-architect line-by-line audit + fix brief for a fresh session |
| [docs/RELEASE_PROCESS.md](RELEASE_PROCESS.md) | How to ship the next release |
| [docs/release-notes/RELEASE_NOTES_v1.3.5.md](release-notes/RELEASE_NOTES_v1.3.5.md) | v1.3.5 user-facing notes (latest) |
| [docs/CHANGELOG.md](CHANGELOG.md) | Full version history |
| [docs/history/STABILITY_AUDIT_2026-05-23.md](history/STABILITY_AUDIT_2026-05-23.md) | Multi-day stability audit + the P1 punch list |
| [CLAUDE.md](../CLAUDE.md) | Durable rules for any Claude Code session |
