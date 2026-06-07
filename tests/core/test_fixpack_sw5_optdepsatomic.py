"""Regression test for core.optional_deps.install() atomic per-entry merge.

Defect (cluster optdepsatomic): the per-entry merge was NON-ATOMIC for a
pre-existing shared directory. For a dst that already exists (e.g. ``torch/``
installed by a prior ``whisper_backend`` install), the loop did ``_rm(dst)``
BEFORE ``os.replace(tmp, dst)``. If the replace then failed (a locked .pyd /
antivirus lock / disk-full — the cases the module's own comments cite), the
live ``torch/`` was already destroyed, and the post-loop rollback explicitly
SKIPS pre_existing names, so the shared dep was left gone with no restore
path — silently breaking the previously-installed sibling feature while
``is_available()`` (a cheap ``find_spec``) still reported it present.

The fix moves the live dst aside to a ``.bak`` BEFORE the replace and
restores it on any failure, so a pre-existing shared dir is never left
missing. This test merges an upgraded ``torch/`` over a pre-existing one
where the in-loop replace fails, and asserts the ORIGINAL ``torch/`` survives
intact. It FAILS on the pre-fix code (original torch/ destroyed).

Hermetic: no network, no model, no Tk root, no real pip.
"""
from __future__ import annotations

import os

from core import optional_deps

_ORIGINAL_MARKER = "ORIGINAL-torch-from-prior-install"
_UPGRADED_MARKER = "UPGRADED-torch-being-merged"


class _FakeOkProc:
    """A pip process that 'succeeds' immediately: empty output, exit 0."""

    def __init__(self):
        self.stdout = iter(())  # pump thread exits at once
        self.returncode = 0

    def wait(self, timeout=None):
        return 0

    def terminate(self):
        pass

    def kill(self):
        pass


def _write_tree(root: str, marker_text: str) -> None:
    """Create a torch-like package dir with a top-level + a submodule file."""
    pkg = os.path.join(root, "torch")
    os.makedirs(pkg, exist_ok=True)
    with open(os.path.join(pkg, "__init__.py"), "w", encoding="utf-8") as fh:
        fh.write(f"# {marker_text}\n")
    with open(os.path.join(pkg, "_marker.txt"), "w", encoding="utf-8") as fh:
        fh.write(marker_text)


def test_failed_replace_over_pre_existing_torch_keeps_original_intact(
    monkeypatch, tmp_path
):
    final = tmp_path / "pylibs"
    final.mkdir()
    # A pre-existing shared dir from a prior (sibling) on-demand install.
    _write_tree(str(final), _ORIGINAL_MARKER)

    monkeypatch.setattr(optional_deps, "extras_dir", lambda: str(final))
    # Force install() past its early short-circuit and skip the final import
    # probe path (we return False at the rollback before reaching it anyway).
    monkeypatch.setattr(optional_deps, "is_available", lambda feat: False)

    # When install() makes its staging dir, fill it with the UPGRADED torch/
    # the way a successful pip --target run would have.
    real_mkdtemp = optional_deps.tempfile.mkdtemp
    staged: dict = {}

    def rec_mkdtemp(*a, **k):
        p = real_mkdtemp(*a, **k)
        staged["path"] = p
        _write_tree(p, _UPGRADED_MARKER)
        return p

    monkeypatch.setattr(optional_deps.tempfile, "mkdtemp", rec_mkdtemp)
    monkeypatch.setattr(
        optional_deps.subprocess, "Popen", lambda *a, **k: _FakeOkProc()
    )

    # Make ONLY the in-loop staged->final move of torch fail (locked .pyd /
    # AV / disk-full). All other os.replace calls (notably the move-aside of
    # the live dst to its .bak) delegate to the real implementation.
    real_replace = os.replace
    final_torch = os.path.join(str(final), "torch")

    def flaky_replace(src, dst, *a, **k):
        if os.path.normcase(str(dst)) == os.path.normcase(final_torch) and (
            ".torch.merge-" in os.path.basename(str(src))
        ):
            raise OSError("simulated locked .pyd / AV lock during replace")
        return real_replace(src, dst, *a, **k)

    monkeypatch.setattr(optional_deps.os, "replace", flaky_replace)

    ok = optional_deps.install("whisper_backend")

    assert ok is False, "a failed merge must report failure"

    # The ORIGINAL pre-existing torch/ must still be present and unchanged —
    # the live shared dir must NEVER be left destroyed by a failed replace.
    marker_path = os.path.join(final_torch, "_marker.txt")
    assert os.path.isdir(final_torch), "pre-existing torch/ was destroyed"
    assert os.path.isfile(marker_path), "pre-existing torch/ contents are gone"
    with open(marker_path, encoding="utf-8") as fh:
        assert fh.read() == _ORIGINAL_MARKER, (
            "torch/ must hold the ORIGINAL contents, not a partial/upgraded tree"
        )

    # No leftover .bak / .merge scratch entries in the extras dir.
    leftovers = [
        n
        for n in os.listdir(str(final))
        if n.startswith(".torch.bak-") or n.startswith(".torch.merge-")
    ]
    assert not leftovers, f"merge scratch must be cleaned up, found {leftovers}"

    # The staging tree is removed on the failure path.
    assert "path" in staged
    assert not os.path.exists(staged["path"]), "staging tree must be cleaned up"
