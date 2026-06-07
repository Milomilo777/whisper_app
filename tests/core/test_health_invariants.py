"""Code-health invariants (added by the macOS QA session).

Tool-free, deterministic checks that catch real regression classes:
- core/ must stay Tk-free (it runs inside the headless worker subprocess).
- the shipped version stays consistent across its canonical Python sources.
- the two Windows PyInstaller specs keep identical app.*/core.* hidden-import sets
  (the project's documented bit-rot trap).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]


def test_core_stays_tk_free():
    """Importing the engine-layer core modules must NOT pull in tkinter — core
    runs in the headless worker subprocess where tkinter may be absent/unusable.
    Done in a fresh subprocess so the test runner's own tkinter import can't mask
    a real violation."""
    code = (
        "import sys\n"
        "import core, core.config, core.paths, core.hardware, core.convert, "
        "core.task, core.writers, core.history, core.hub, core._proc, core._checkpoint\n"
        "tk = sorted(m for m in sys.modules if m == 'tkinter' or m.startswith('tkinter.'))\n"
        "assert not tk, 'core transitively imported tkinter: %r' % tk\n"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, "core is not Tk-free:\n" + r.stdout + "\n" + r.stderr


def test_shipped_version_is_consistent():
    """pyproject.toml version must equal core.__version__ (the runtime source of
    truth). The project's 'version trap' is exactly these two drifting apart."""
    import core

    pyproject = (_REPO / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"', pyproject)
    assert m, "no version found in pyproject.toml"
    assert m.group(1) == core.__version__, (
        f"version drift: pyproject={m.group(1)} core.__version__={core.__version__}"
    )


def _spec_module_tokens(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r"""["']((?:app|core)\.[\w.]+)["']""", text))


def test_pyinstaller_specs_hiddenimports_in_sync():
    """The onefile and onedir Windows specs must carry identical app.*/core.*
    hidden-import sets so the unshipped pipelines don't bit-rot."""
    onefile = _REPO / "whisper_project_onefile.spec"
    onedir = _REPO / "whisper_project_onedir.spec"
    if not (onefile.exists() and onedir.exists()):
        pytest.skip("PyInstaller spec files not present in this checkout")
    a, b = _spec_module_tokens(onefile), _spec_module_tokens(onedir)
    assert a == b, (
        "spec hidden-import drift:\n"
        f"  only in onefile: {sorted(a - b)}\n"
        f"  only in onedir:  {sorted(b - a)}"
    )
