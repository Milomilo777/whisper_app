"""Regression test for core.optional_deps install()-rollback over-deletion.

Defect: install()'s failed-merge rollback deleted EVERY staged top-level
name from the extras dir, including dirs SHARED with an already-installed
feature. Installing 'whisper_backend' after 'alignment' (both pull
torch/numpy): if the torch/ merge fails (e.g. a locked .pyd), the rollback
used to delete the torch/ that 'alignment' still needs — silently breaking
the previously-working feature.

Fix: snapshot the pre-existing top-level names before the merge and roll
back only the names THIS install newly created, leaving shared pre-existing
dirs untouched.
"""
from __future__ import annotations

import os
import shutil
import subprocess

from core import optional_deps


class _FakeDoneProc:
    """A pip process that has already finished cleanly (returncode 0) so
    install() proceeds straight to the staging -> extras_dir merge."""

    def __init__(self):
        self.stdout = iter(())  # pump thread exits immediately
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):  # pragma: no cover - not reached on a clean exit
        pass

    def kill(self):  # pragma: no cover - not reached on a clean exit
        pass


def test_rollback_keeps_preexisting_shared_dir(monkeypatch, tmp_path):
    """A failed torch/ merge while installing a second feature must NOT
    delete the torch/ a previously-installed feature already put there."""
    final = tmp_path / "pylibs"
    final.mkdir()

    # A prior feature ('alignment') already installed a shared dependency
    # tree. Mark it so we can prove it survives an unrelated rollback.
    pre_torch = final / "torch"
    pre_torch.mkdir()
    (pre_torch / "__init__.py").write_text("# installed by alignment\n")
    sentinel = pre_torch / "PRE_EXISTING.txt"
    sentinel.write_text("do not delete me\n")

    monkeypatch.setattr(optional_deps, "extras_dir", lambda: str(final))
    # Not yet importable, so install() runs the full merge path.
    monkeypatch.setattr(optional_deps, "is_available", lambda feat: False)

    # Build the pip --target staging tree this install would produce: a NEW
    # top-level package plus a re-staged copy of the shared torch/ dep.
    def fake_mkdtemp(*a, **k):
        stage = tmp_path / "stage"
        stage.mkdir()
        new_pkg = stage / "whisper"
        new_pkg.mkdir()
        (new_pkg / "__init__.py").write_text("# new feature\n")
        staged_torch = stage / "torch"
        staged_torch.mkdir()
        (staged_torch / "__init__.py").write_text("# torch from pip\n")
        return str(stage)

    monkeypatch.setattr(optional_deps.tempfile, "mkdtemp", fake_mkdtemp)
    monkeypatch.setattr(
        optional_deps.subprocess, "Popen", lambda *a, **k: _FakeDoneProc()
    )

    # Force the torch/ merge to fail (simulating a locked .pyd / AV lock):
    # the staging copy of torch/ fails BEFORE the pre-existing dst is
    # touched, so the only thing that can delete the pre-existing torch/ is
    # the rollback loop — exactly the code under test.
    real_copytree = shutil.copytree

    def flaky_copytree(src, dst, *a, **k):
        if os.path.basename(src) == "torch":
            raise OSError(13, "simulated locked torch/.pyd")
        return real_copytree(src, dst, *a, **k)

    monkeypatch.setattr(optional_deps.shutil, "copytree", flaky_copytree)

    ok = optional_deps.install("whisper_backend")

    # Install reports failure...
    assert ok is False
    # ...but the pre-existing shared torch/ tree (and its sentinel) survive.
    assert pre_torch.is_dir(), "rollback must not delete a pre-existing shared dir"
    assert sentinel.exists(), "pre-existing shared dir contents must be intact"
    assert sentinel.read_text() == "do not delete me\n"


def test_rollback_removes_newly_created_entry(monkeypatch, tmp_path):
    """The other half of the invariant: an entry this install NEWLY created
    is still rolled back on a merge failure (no partial tree left behind)."""
    final = tmp_path / "pylibs"
    final.mkdir()
    # torch/ already present from a prior feature, but the NEW package is not.
    (final / "torch").mkdir()

    monkeypatch.setattr(optional_deps, "extras_dir", lambda: str(final))
    monkeypatch.setattr(optional_deps, "is_available", lambda feat: False)

    def fake_mkdtemp(*a, **k):
        stage = tmp_path / "stage"
        stage.mkdir()
        # Order the new package BEFORE torch/ so it is fully merged in before
        # the torch/ merge fails, then must be rolled back.
        new_pkg = stage / "aaa_new_pkg"
        new_pkg.mkdir()
        (new_pkg / "__init__.py").write_text("# new\n")
        staged_torch = stage / "torch"
        staged_torch.mkdir()
        (staged_torch / "__init__.py").write_text("# torch\n")
        return str(stage)

    monkeypatch.setattr(optional_deps.tempfile, "mkdtemp", fake_mkdtemp)
    monkeypatch.setattr(
        optional_deps.subprocess, "Popen", lambda *a, **k: _FakeDoneProc()
    )

    real_copytree = shutil.copytree

    def flaky_copytree(src, dst, *a, **k):
        if os.path.basename(src) == "torch":
            raise OSError(13, "simulated locked torch/.pyd")
        return real_copytree(src, dst, *a, **k)

    monkeypatch.setattr(optional_deps.shutil, "copytree", flaky_copytree)

    ok = optional_deps.install("whisper_backend")

    assert ok is False
    # The newly created package was merged then rolled back: no partial tree.
    assert not (final / "aaa_new_pkg").exists(), "newly created entry must roll back"
    # The pre-existing shared dir is still there.
    assert (final / "torch").is_dir()
