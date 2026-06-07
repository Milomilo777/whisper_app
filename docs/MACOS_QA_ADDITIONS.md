# macOS QA additions — KEEP THESE WHEN MERGING `macos-ci` INTO `master`

This branch carries macOS build/test/health work, validated on real Apple-silicon
GitHub Actions runners by the macOS QA session. Everything below is **committed (not
gitignored)** and is meant for ongoing use in future releases. **When you merge
`macos-ci` → `master`, preserve all of it** — do not drop it in the merge/rebase.

## Code fixes (real bugs, verified GREEN on macOS)
- `core/convert.py` — `_same_file` uses `os.path.samefile` (POSIX-correct case-insensitive
  detection) and `convert_file` writes with `newline="\n"` (no CRLF rewrite on Windows).
- `core/config.py` — `fetch_online_config` refuses non-http(s) `config_url` (SSRF / file://
  guard); `_persistable_model_path` POSIX-correct dedup (samefile + normcase fallback).
- `tests/core/test_project_overrides.py` — `@pytest.mark.skipif(os.name != 'nt')` on the UNC
  test (its `os.name='nt'` monkeypatch crashed pytest on py3.11/POSIX).
- `tests/core/test_config.py`, `test_hub.py`, `test_stats.py` — 3 Windows-path tests made
  cross-platform.
- `platform/macos/pyinstaller/whisper_project_mac.spec` — repo paths resolved via `SPECPATH`
  so the `.app` actually builds (previously failed: "gui.py not found").

## Tests added (keep — reusable health gate, runs in the normal hermetic suite)
- `tests/core/test_health_invariants.py` — core-is-Tk-free, shipped-version consistency
  (`pyproject` == `core.__version__`), and onefile/onedir spec hidden-import sync.

## CI workflows added (`.github/workflows/`, keep — each also has `workflow_dispatch`)
- `macos-build.yml`       — deps + pyright + hermetic suite on macos-15.
- `macos-test-matrix.yml` — macos-15 + macos-15-intel × py3.11/3.12/3.13 + atomic per-file isolation.
- `macos-app.yml`         — builds `.app`/`.dmg` (PyInstaller) + smoke + uploads the artifact;
  also runs `install.command` and lints the Homebrew formula.
- `macos-harsh.yml`       — randomized-order ×5 seeds, repeat-stress ×3, coverage, ruff/bandit/pip-audit/vulture.
- `macos-health.yml`      — ruff(extended)/mypy/vulture/radon+xenon/interrogate/deptry + the invariant tests.
- `macos-py311.yml`       — one-off py3.11 failure-pinner (the bug it found is fixed; keep or drop).
- `macos-e2e.yml` + `tools/e2e_tiny_macos.py` — REAL transcription E2E: macOS `say` speech →
  faster-whisper `tiny` model → the project's output writers. Proves inference + output work on
  Apple Silicon without the 3 GB shipped model. VERIFIED green (100% word accuracy on the say clip).

Triggering: these fire on a push to a dedicated throwaway branch
(`macos-app-build` / `macos-test` / `macos-harsh` / `macos-health` / `macos-py311`) OR via the
Actions "Run workflow" button (`workflow_dispatch`). On `master`, use `workflow_dispatch`
(the push-branch triggers won't fire there). The throwaway trigger branches are NOT needed
on `master` — only these workflow FILES are.

## Current status
macOS is GREEN on BOTH Apple arches × py3.11/3.12/3.13 + atomic isolation; all 3 install
methods build; the `.app`/`.dmg` artifact is downloadable from a `macos-app.yml` run.
