"""Entry point. Three modes:

  python gui.py                  → launch the Tk app (default)
  python gui.py --worker         → spawn the JSON-stdio worker
  python gui.py transcribe FILE  → CLI transcription
  python gui.py --help           → usage

The worker mode is invoked by the App spawning its own exe; do
NOT remove or rename the ``--worker`` shape — it's the
spawn-contract every method of the deliverables uses.
"""
import argparse
import sys


def _cli_transcribe(args: argparse.Namespace) -> int:
    """Run a one-shot transcription from the command line."""
    import os
    import time
    from core.config import load_config, save_config
    from core.task import TranscriptionTask
    from core import transcriber as _trans

    src = os.path.abspath(args.file)
    if not os.path.isfile(src):
        print(f"error: file not found: {src}", file=sys.stderr)
        return 2

    cfg = load_config()
    formats = args.formats or cfg.get("output_formats") or ["srt", "json"]
    cfg["output_formats"] = formats
    # Mirror the explicit CLI flags onto cfg so save_config writes
    # them through AND the module-level _trans.config snapshot is
    # refreshed to match — the worker module was originally read
    # once at import time and never re-read non-diarization keys
    # like output_formats, so the FIRST CLI run with new --formats
    # / --diarization silently fell back to whatever was on disk
    # at import time.
    if args.diarization:
        cfg["diarization_enabled"] = True
    save_config(cfg)
    # CRITICAL — _trans.config was loaded at import time. Refresh it
    # so the writer sees the just-saved values on this very run.
    _trans.config.update(cfg)

    print("[cli] loading model...", flush=True)
    if not _trans.load_existing_model(lambda m: print(f"[cli] {m}", flush=True)):
        print("error: model not loaded", file=sys.stderr)
        return 3

    task = TranscriptionTask(src)
    if args.language:
        task.language = args.language

    # History entry — match the GUI path so CLI usage doesn't
    # silently bypass the recent-files / statistics surfaces.
    history_db = None
    history_id = None
    try:
        from core.history import HistoryDB
        history_db = HistoryDB()
        history_id = history_db.insert_transcription(
            src,
            model=(cfg.get("model") or {}).get("name", ""),
            language=args.language or "",
        )
    except Exception as e:  # noqa: BLE001
        print(f"[cli] history.db unavailable: {e}", flush=True)
        history_db = None

    def _on_log(m: str) -> None:
        print(f"[cli] {m}", flush=True)

    def _on_progress(p: int) -> None:
        # one progress line per percentage; flushable.
        pass

    started = time.time()
    status = "finished"
    error_msg = ""
    try:
        _trans.transcribe(task, _on_progress, _on_log, language_cb=None)
    except Exception as e:  # noqa: BLE001
        status = "error"
        error_msg = str(e)
        print(f"[cli] ERROR: {e}", file=sys.stderr, flush=True)
    duration_s = time.time() - started

    base, _ = os.path.splitext(src)
    written: list[str] = []
    for ext in formats:
        candidate = f"{base}.{ext}"
        if os.path.isfile(candidate):
            written.append(candidate)
    if status == "finished":
        print(f"[cli] wrote {len(written)} output(s) next to {src}", flush=True)
        for p in written:
            print(f"  {p}", flush=True)

    if history_db is not None and history_id is not None:
        try:
            history_db.finish_transcription(
                history_id, status,
                output_paths=written,
                duration_seconds=duration_s,
                language=getattr(task, "detected_language", "") or args.language or "",
                error=error_msg,
            )
        except Exception as e:  # noqa: BLE001
            print(f"[cli] could not finish history row: {e}", flush=True)
        try:
            history_db.close()
        except Exception:  # noqa: BLE001
            pass

    return 0 if status == "finished" else 4


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="WhisperProject",
        description="Offline transcription + downloader. Run without arguments to launch the desktop app.",
    )
    sub = p.add_subparsers(dest="command")

    tr = sub.add_parser("transcribe", help="Transcribe a file and exit (no UI)")
    tr.add_argument("file", help="audio/video file to transcribe")
    tr.add_argument(
        "--language", "-l", default="",
        help="force a language code (en, es, fa, …); empty = auto-detect",
    )
    tr.add_argument(
        "--formats", "-f", nargs="+",
        choices=("srt", "vtt", "tsv", "txt", "json", "lrc", "md", "docx", "pdf"),
        help="output formats (default: from config.json)",
    )
    tr.add_argument(
        "--diarization", action="store_true",
        help="enable speaker diarization for this transcription",
    )
    return p


def main() -> int:
    # Worker mode is a special early branch — bypasses argparse so
    # we never break the spawn-contract.
    if "--worker" in sys.argv:
        from core.worker import main as _worker_main
        return _worker_main()

    parser = _build_argparser()
    args = parser.parse_args()

    if args.command == "transcribe":
        return _cli_transcribe(args)

    # Default: launch the Tk app.
    from app import run
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
