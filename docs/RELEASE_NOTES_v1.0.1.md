# Whisper Project v1.0.1

Single-fix patch release. No new features, no behaviour changes,
no migration required for existing v1.0.0 users — only the
first-run path is affected.

## What's fixed

**Fresh installs no longer re-download the 3 GB Whisper model on
the launch after the first-run hub picker.**

The first-run "Choose Model Hub Folder" dialog used to be
asynchronous: it opened and immediately let the rest of startup
continue. The transcription worker spawned with an empty
`hub_folder` and downloaded the model into
`%LOCALAPPDATA%\WhisperProject\Cache\models\`. When the user
accepted the dialog's default (`<install-dir>\hub`), the choice
was saved — but the next launch resolved `model_path` to a
folder the model had never been extracted into, hit a startup
error, opened the model-download dialog, and pulled the full
3 GB archive again.

The patch makes the dialog default and the empty-hub fallback
agree on the same path, and defers the worker spawn until the
dialog has fired its on-done callback. Accepting the default is
now a no-op; picking a custom folder routes the first download
straight to the right place.

Verified by a `load_config()` simulation of the fresh-install path
plus a regression test (`tests/core/test_hub.py`).

## Who should upgrade

- **You've already installed v1.0.0 and the model is loading
  fine?** You don't need to upgrade. The bug only triggers when
  `model_path` was first computed under one hub and `hub_folder`
  was later saved as a different path.
- **You're about to install on a fresh machine?** Use v1.0.1.
- **A user reported the "downloads the model every time I open
  the app" symptom?** v1.0.1 fixes it.

## Verification

- pyright `app/ core/`: 0 errors, 0 warnings, 0 informations.
- Unit suite: 535 passed (one new regression test).
- Real-file E2E: unchanged from v1.0.0 (no transcription path
  touched).

## Deliverables

| Asset | Local path | Size |
|---|---|---|
| Portable | `dist/WhisperProject-v1.0.1-Portable.exe` | ~447 MB |
| Setup-Compact | `dist_installer/WhisperProject-v1.0.1-Setup-Compact.exe` | ~326 MB |
| Setup-Standard | `dist_installer/WhisperProject-v1.0.1-Setup-Standard.exe` | ~349 MB |

## What changed under the hood

Two files, ~50 lines total. See commit `c419b6e` on the
`chore/cleanup-hardening` branch:

- `core/config.py:_apply_runtime_fallbacks` — empty `hub_folder`
  now falls back to `core.hub.default_hub_folder()` instead of
  `user_cache_dir()/models/`.
- `app/app.py:_on_start` — defers `start_standby()` until the
  hub-setup dialog answers.
