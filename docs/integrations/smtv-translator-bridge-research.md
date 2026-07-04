# SMTV docx ↔ machine-translate-docx compatibility research

**Status:** research only — not yet scoped for implementation, no code written.
**Companion project:** `machine-translate-docx` (local sibling repo, same owner, no shared code today). A matching note was left there at `notes/2026-07-04_15-34_whisper-app-smtv-docx-compatibility.md`.

## Why this question came up

whisper_app's SMTV docx writer (`core/writers/smtv_docx_writer.py`) produces a transcript-shaped Word table for Supreme Master TV episodes. `machine-translate-docx` is a separate, mature translation tool that — per its own source comments and error messages — is *already* built around "SMTV-shaped" tables and already has a dedicated SMTV brand lexicon (`prompts/_smtv_locks.txt`) and an "SMTV Robot" output signature. The question: can whisper_app's SMTV docx output feed directly into that tool?

## Exact input contract machine-translate-docx requires (verified from its source)

`src/machine_translate_docx/docx_io/parse.py`:
- Reads only `docxdoc.tables[0]` (the first table).
- Requires `numcols > 2` or hard-exits (code 11, "expected 3").
- Column indices are **hardcoded by position**, never matched by header text:
  - `cells[0]` = row number ("No.")
  - `cells[1]` = source text — its own comments call this "EN text"
  - `cells[2]` = destination text — confirmed by `docx_io/split_input.py` reading `cells[2].paragraphs` back for the `--splitonly` re-distribution path; this is also where the engine writes the translation.
- No header-text validation happens anywhere — a table with the right column *count* but the wrong column *order* is silently misread rather than rejected.

## whisper_app's actual output shape (verified from source)

`core/writers/smtv_docx_writer.py`, 4 columns: `cells[0]`=row number, `cells[1]`=Time Code (`HH:MM:SS.m`), `cells[2]`=Foreign Language transcript text, `cells[3]`=English Translation (left empty for a human to fill in later).

## The mismatch

| Position | whisper_app SMTV docx | machine-translate-docx expects |
|---|---|---|
| 0 | row number | row number |
| 1 | **Time Code** | **EN source text** |
| 2 | Foreign Language transcript | FA destination (empty) |
| 3 | English Translation (empty) | *(table is only 3 columns — doesn't exist)* |

Feeding a whisper_app SMTV docx into machine-translate-docx as-is would pass the column-count gate (4 > 2) and then **silently misread the Time Code column as if it were English source text** — no error, just garbage translations of timestamps. This is not a "just point it at the file" compatibility; the shapes actively disagree at position 1.

## Why the shapes differ

They're solving different stages of the same real pipeline. whisper_app's SMTV docx is the **first hop**: raw audio → transcript in the original spoken language, with an empty English column for a human (or a future automated step) to fill in. machine-translate-docx is the **second hop**: already-correct English → any other target language (Persian is the tuned path; ~140 others use a universal fallback prompt). Today a human presumably bridges the two by hand — transcribe, translate to English, retype into the 3-column shape the translator expects.

## A low-risk bridge, in three tiers (none built — for discussion)

1. **MVP — a standalone converter.** Given a whisper_app SMTV docx whose English Translation column is already filled in, produce a fresh 3-column docx: `cells[0]` = old `cells[0]` (unchanged), `cells[1]` = old `cells[3]` (the now-filled English), `cells[2]` = empty (for the translator to fill). Time Code and the original foreign-language text are dropped from *this specific output* — they still exist in the original whisper_app docx as a reference trail. No change needed to either project's core pipeline; this is a one-shot adapter run between the two tools. Candidate homes: a new `core.convert` target in whisper_app (it already has a `convert_file()` registry for exactly this kind of post-hoc reshaping), a small import adapter in machine-translate-docx's `docx_io/`, or a standalone script belonging to neither package.
2. **Nice-to-have — preserve timing.** The MVP converter loses the Time Code column. If the Double-Lines broadcast output ever needs to re-sync to video, timing could be kept as a docx custom property or a row-number-keyed sidecar JSON, read back after translation without machine-translate-docx's pipeline ever needing to understand it.
3. **Power — skip the human English step.** whisper_app already has two cloud backends (Gemini, Google Cloud STT) that can transcribe *and* translate to English via fewer manual steps. If used for an SMTV job, `cells[3]` could be auto-filled by whisper_app itself, making the pipeline (audio → foreign transcript → English → target language) end-to-end automatic short of a final QA pass. This changes whisper_app's own SMTV writer contract (would need an opt-in flag) and is a separate, larger feature — flagged here, not scoped.

## Open questions for the owner

- Does the human English-translation step (filling whisper_app's empty column 4 today) actually happen in a docx someone edits by hand, or in some other tool/format? This determines whether the MVP converter's *input* shape is exactly as assumed above.
- Where should the MVP converter live — whisper_app's `core.convert`, machine-translate-docx's `docx_io/`, or standalone?
- Is preserving the Time Code (tier 2) actually wanted, or is the translator's output purely for broadcast-caption typing (no machine-readable timing needed at all)?

## Sources (read directly this session, not from memory)

- `machine-translate-docx/src/machine_translate_docx/docx_io/parse.py` — column contract, error messages, the "SMTV-shaped (No. | EN | FA)" phrase
- `machine-translate-docx/src/machine_translate_docx/docx_io/split_input.py` — confirms `cells[2]` is the FA/destination column
- `machine-translate-docx/PROJECT_INDEX.md`, `PROJECT_MEMORY.md` — architecture and hard invariants (C1–C42)
- `whisper_app/core/writers/smtv_docx_writer.py` — full source read, confirms the 4-column output shape
