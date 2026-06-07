"""The Google Cloud STT backend can fall back to a build-bundled service-account
JSON (creds/gcloud_stt.json next to the app) when no key is configured, so a
trusted-distribution build works out of the box. The bundled file is never in
the repo, so a normal checkout resolves to '' and an explicit key stays required.
"""
from __future__ import annotations

import core.paths as paths
from core.backends.google_cloud_stt import bundled_credentials_path


def test_returns_empty_when_no_bundled_creds(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "resource_base", lambda: str(tmp_path))
    assert bundled_credentials_path() == ""


def test_returns_path_when_bundled_creds_present(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "resource_base", lambda: str(tmp_path))
    creds_dir = tmp_path / "creds"
    creds_dir.mkdir()
    keyfile = creds_dir / "gcloud_stt.json"
    keyfile.write_text("{}", encoding="utf-8")
    assert bundled_credentials_path() == str(keyfile)


def test_directory_without_the_file_is_not_used(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "resource_base", lambda: str(tmp_path))
    (tmp_path / "creds").mkdir()  # dir exists but no gcloud_stt.json
    assert bundled_credentials_path() == ""
