"""Regression: the Google Cloud STT 'Test connection' button must honour the
build-bundled service-account key, the same way real transcription does.

``core.backends.google_cloud_stt.GoogleCloudSttBackend.load()`` falls back to
``bundled_credentials_path()`` when the user hasn't typed/picked an explicit
JSON path (see test_fixpack_bundled_creds.py) -- a trusted-distribution build
works out of the box with no setup. But ``AdvancedDialog._test_gcloud_connection``
checked ONLY the typed path and bailed out with "Pick your service-account
JSON file first (Browse...)" whenever it was empty -- so a user of a build
that ships with the key pre-configured could never use the Test button to
confirm it, and would reasonably conclude the key wasn't connected.

The fix mirrors load()'s fallback in the button handler: an empty field now
probes ``bundled_credentials_path()`` first, and the status text says so
("...using the build-bundled key...") so the user knows which key was tested.

Hermetic: a SimpleNamespace fake dialog, no real Tk root, no network, no
google libraries, no actual JSON file required for the guard-path assertions.
"""
from __future__ import annotations

import types

import app.dialogs.advanced as adv
from core.backends import google_cloud_stt as g


class _V:
    """Minimal stand-in for a Tk *Var."""

    def __init__(self, value: object = ""):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


def _fake_app():
    return types.SimpleNamespace(
        app_config={},
        post_to_main=lambda fn: fn(),
        log_threadsafe=lambda *_a, **_kw: None,
    )


def _fake_dialog():
    return types.SimpleNamespace(
        app=_fake_app(),
        _gcloud_credentials=_V(""),
        _gcloud_batch_mode=_V(False),
        _gcloud_bucket=_V(""),
        _gcloud_test_result=_V(""),
    )


def test_empty_field_with_no_bundled_key_still_asks_to_pick_one(monkeypatch, tmp_path):
    """Genuine checkout (no creds/ dir): the original guard message is kept."""
    import core.paths as paths
    monkeypatch.setattr(paths, "resource_base", lambda: str(tmp_path))
    assert g.bundled_credentials_path() == ""  # sanity: nothing bundled here

    dlg = _fake_dialog()
    adv.AdvancedDialog._test_gcloud_connection(dlg)  # type: ignore[arg-type]

    assert "Pick your service-account JSON file first" in dlg._gcloud_test_result.get()


def test_empty_field_falls_back_to_bundled_key(monkeypatch, tmp_path):
    """Trusted-distribution build (creds/gcloud_stt.json present): the Test
    button must probe the bundled key instead of refusing to run, and the
    status text must say it is testing the bundled key (not a picked file).
    """
    import core.paths as paths
    monkeypatch.setattr(paths, "resource_base", lambda: str(tmp_path))
    creds_dir = tmp_path / "creds"
    creds_dir.mkdir()
    keyfile = creds_dir / "gcloud_stt.json"
    keyfile.write_text("{}", encoding="utf-8")
    bundled = str(keyfile)
    assert g.bundled_credentials_path() == bundled  # sanity

    spawned = []
    monkeypatch.setattr(
        adv, "safe_thread",
        lambda fn, name=None: spawned.append((fn, name)),
        raising=False,
    )
    # The handler imports safe_thread from core._threads at call time --
    # patch it there too so the inline `from core._threads import safe_thread`
    # picks up the stub regardless of which binding resolves first.
    import core._threads as threads_mod
    monkeypatch.setattr(
        threads_mod, "safe_thread",
        lambda fn, name=None: spawned.append((fn, name)),
    )

    dlg = _fake_dialog()
    adv.AdvancedDialog._test_gcloud_connection(dlg)  # type: ignore[arg-type]

    result = dlg._gcloud_test_result.get()
    assert "Pick your service-account JSON file first" not in result
    assert "bundled key" in result
    # The worker thread was scheduled (not skipped) -- the guard let it through.
    assert spawned, "expected the connection-test worker to be scheduled"
