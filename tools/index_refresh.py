#!/usr/bin/env python3
"""Zero-token structural refresher for PROJECT_INDEX.md.

Runs deterministically (no LLM, no network). Intended to be fired automatically
by a Claude Code SessionStart hook, and also by the `project-index` skill right
after it (re)writes the semantic sections.

Behaviour
---------
* Target dir = argv[1] if given, else the current working directory.
* If <target>/PROJECT_INDEX.md does NOT exist -> silent no-op, exit 0.
  (This makes a single global hook safe in every project: it only does work
   where someone opted in by creating an index.)
* Otherwise: walk the source tree, regenerate the block between the
  AUTO-INDEX:STRUCTURE markers (file/dir map + language histogram + freshness
  stamp + drift vs the last DEEP index), and rewrite PROJECT_INDEX.md in place.
* Drift = files added / removed / changed since the last deep (semantic) index.
  When drift crosses a threshold, a "STALE" banner tells the user to run
  /project-index to regenerate the semantic sections (that step costs tokens;
  this script never does).

Flags
-----
  --set-baseline   Record the current tree as the deep-index baseline
                   (deep_index_at = now). The skill calls this after a deep run.

The script always exits 0 and never raises into the hook.
"""
from __future__ import annotations

import sys
import os
import json
import hashlib
from datetime import datetime

MARK_START = "<!-- AUTO-INDEX:STRUCTURE:START -->"
MARK_END = "<!-- AUTO-INDEX:STRUCTURE:END -->"
INDEX_NAME = "PROJECT_INDEX.md"
MANIFEST_NAME = ".project_index.json"

# Drift banner thresholds (whichever trips first).
DRIFT_RATIO = 0.15
DRIFT_ABS = 25

EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".venv-build", "env", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".idea", ".vscode", "dist", "build", "dist_installer", "dist_onedir",
    "dist_onefile", "embed_build", "build_logs", ".tox", ".cache",
    "site-packages", ".next", ".turbo", ".coverage", "_yt_subs",
}
EXCLUDE_PREFIXES = ("dist", "build", ".venv")

# Files we treat as "source" for drift/hash/histogram.
TRACK_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".java", ".go",
    ".rs", ".rb", ".c", ".h", ".hpp", ".cpp", ".cc", ".cs", ".html", ".ejs",
    ".css", ".scss", ".sass", ".less", ".vue", ".svelte", ".sh", ".bash",
    ".bat", ".cmd", ".ps1", ".psm1", ".toml", ".ini", ".cfg", ".conf",
    ".yaml", ".yml", ".json", ".json5", ".md", ".rst", ".txt", ".spec",
    ".iss", ".bas", ".vba", ".sql", ".ejs", ".jinja", ".j2", ".tmpl",
    ".make", ".mk", ".gradle", ".kt", ".swift", ".m", ".r", ".jl",
}


def _is_excluded_dir(name: str) -> bool:
    if name in EXCLUDE_DIRS:
        return True
    low = name.lower()
    return any(low.startswith(p) for p in EXCLUDE_PREFIXES)


def scan(root: str) -> dict:
    """Return {relpath: 'size:mtime'} for every tracked source file."""
    out: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _is_excluded_dir(d)]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in TRACK_EXTS:
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            if rel in (INDEX_NAME, MANIFEST_NAME):
                continue
            try:
                st = os.stat(full)
            except OSError:
                continue
            out[rel] = f"{st.st_size}:{int(st.st_mtime)}"
    return out


def tree_summary(files: dict) -> str:
    """Compact top-level map + per-extension histogram."""
    top: dict[str, int] = {}
    exts: dict[str, int] = {}
    for rel in files:
        head = rel.split("/", 1)[0] if "/" in rel else "(root)"
        top[head] = top.get(head, 0) + 1
        e = os.path.splitext(rel)[1].lower() or "(none)"
        exts[e] = exts.get(e, 0) + 1
    lines = ["| Top-level | Source files |", "|---|---|"]
    for k in sorted(top, key=lambda x: (-top[x], x)):
        lines.append(f"| `{k}` | {top[k]} |")
    hist = "  ".join(
        f"`{e}`×{exts[e]}" for e in sorted(exts, key=lambda x: -exts[x])[:14]
    )
    return "\n".join(lines) + "\n\n**By type:** " + hist + "\n"


def manifest_hash(files: dict) -> str:
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode("utf-8", "replace"))
        h.update(files[rel].encode("ascii", "replace"))
    return h.hexdigest()[:16]


def diff(current: dict, baseline: dict):
    cur, base = set(current), set(baseline)
    added = cur - base
    removed = base - cur
    changed = {f for f in (cur & base) if current[f] != baseline[f]}
    return added, removed, changed


def build_block(files: dict, manifest: dict) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    total = len(files)
    base_list = manifest.get("deep_index_list") or {}
    deep_at = manifest.get("deep_index_at") or "never (run /project-index)"

    parts = [MARK_START,
             "## Structure (auto-refreshed — do not hand-edit this block)",
             "",
             f"- **Source files tracked:** {total}",
             f"- **Structure refreshed:** {now}",
             f"- **Semantic sections last built:** {deep_at}"]

    if base_list:
        added, removed, changed = diff(files, base_list)
        n = len(added) + len(removed) + len(changed)
        parts.append(
            f"- **Drift since semantic build:** +{len(added)} added · "
            f"~{len(changed)} changed · -{len(removed)} removed"
        )
        stale = total > 0 and (n >= DRIFT_ABS or (n / max(total, 1)) >= DRIFT_RATIO)
        if stale:
            sample = sorted(list(added) + list(changed))[:8]
            parts.append("")
            parts.append(
                "> ⚠️ **STALE** — the source tree changed a lot since the "
                "semantic sections were built. Re-run `/project-index` to "
                "regenerate purposes / gotchas / subsystem maps."
            )
            if sample:
                parts.append(">")
                parts.append("> Notable: " + ", ".join(f"`{s}`" for s in sample))
    else:
        parts.append(
            "- **Drift:** baseline not set — run `/project-index` to build the "
            "semantic sections and set the baseline."
        )

    parts.append("")
    parts.append(tree_summary(files))
    parts.append(MARK_END)
    return "\n".join(parts)


def splice(text: str, block: str) -> str:
    if MARK_START in text and MARK_END in text:
        pre = text.split(MARK_START, 1)[0]
        post = text.split(MARK_END, 1)[1]
        return pre + block + post
    sep = "" if text.endswith("\n") else "\n"
    return text + sep + "\n---\n\n" + block + "\n"


def main() -> int:
    args = [a for a in sys.argv[1:]]
    set_baseline = "--set-baseline" in args
    args = [a for a in args if not a.startswith("--")]
    root = os.path.abspath(args[0]) if args else os.getcwd()

    index_path = os.path.join(root, INDEX_NAME)
    if not os.path.isfile(index_path):
        return 0  # opt-in only: silent where there is no index

    manifest_path = os.path.join(root, MANIFEST_NAME)
    manifest = {}
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as fh:
                manifest = json.load(fh)
        except (OSError, ValueError):
            manifest = {}

    files = scan(root)

    if set_baseline:
        manifest["deep_index_at"] = datetime.now().isoformat(timespec="seconds")
        manifest["deep_index_hash"] = manifest_hash(files)
        manifest["deep_index_list"] = files

    block = build_block(files, manifest)

    try:
        with open(index_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        with open(index_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(splice(text, block))
    except OSError as exc:
        sys.stderr.write(f"[project-index] could not update index: {exc}\n")
        return 0

    manifest["refreshed_at"] = datetime.now().isoformat(timespec="seconds")
    manifest["current_hash"] = manifest_hash(files)
    try:
        with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass

    drift = ""
    base_list = manifest.get("deep_index_list") or {}
    if base_list and not set_baseline:
        a, r, c = diff(files, base_list)
        drift = f" drift +{len(a)} ~{len(c)} -{len(r)}"
    tag = " baseline set" if set_baseline else ""
    sys.stdout.write(
        f"[project-index] refreshed {os.path.basename(root)}/PROJECT_INDEX.md "
        f"({len(files)} files{drift}){tag}\n"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never break the hook
        sys.stderr.write(f"[project-index] non-fatal: {exc}\n")
        sys.exit(0)
