# Contributing — Whisper Project (basic)

This is the basic edition. Its whole reason to exist is to be
small, clear, and tested. Every change should leave it that way.

## The maintainability bar

Before you commit, the following must all be true:

| Rule | How to check |
|---|---|
| Pyright clean — 0 errors, 0 warnings, 0 informations | `python -m pyright app/ core/` |
| Full unit suite passes | `python -m pytest tests/ --ignore=tests/smoke` |
| Every `def` has return type annotations | `grep -rE "^(    )?def \w+\([^)]*\):$" app/ core/` returns nothing |
| Every module starts with a one-paragraph docstring | first non-comment line is `"""..."""` |
| No bare `except` and no `except Exception: pass` | every `except` either re-raises, logs via `logger`, or maps through `core/error_messages.py` |
| No walrus operators, no nested comprehensions deeper than one level, no lambdas longer than one line | grep + eyeball |
| No file in `app/` or `core/` exceeds 500 lines | `wc -l app/*.py core/**/*.py` — currently only `app/app.py` (840 lines) is over, and it's flagged for a future split |

## Style

- Type hints on every public function. Module-private helpers
  (`_underscore_prefix`) may skip return annotations if the return
  is obvious from the body.
- Comments answer *why*, not *what*. Code that does an obvious
  thing should not have a comment paraphrasing it.
- When you add a comment, prefer multiple short lines over one
  long line, so a future maintainer can scan it.
- Imports: stdlib first, then third-party, then local, separated
  by blank lines.
- Strings: `"double quotes"` everywhere.
- Errors with user-facing impact: map through `core/error_messages.py`
  so the message says **what to try**, not just **what failed**.

## When you add a new feature

1. Write the test first when you can. It documents the behaviour
   for the next reader.
2. Update `docs/ARCHITECTURE.md` if the feature touches the
   process model, the worker IPC protocol, or the on-disk layout.
3. Update `docs/UML.md` if the component graph changes.
4. Add an entry to `CHANGELOG.md` under `## [Unreleased]`.

## When you remove a feature

The basic edition is the place where features come to die in
favour of clarity. If you're about to delete something the
collaborator wanted, ask first. Otherwise — if it's a stale path
nobody uses — go ahead, and call it out in the commit message
so a future revert is one click away.

## The full-fat fork

If a feature request belongs upstream rather than here, point
the contributor at
https://github.com/Milomilo777/whisper_project_direct_download_v2
and explain why this edition is a clean slate.
