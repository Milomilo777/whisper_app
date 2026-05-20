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
    from core.config import load_config, save_config
    from core.task import TranscriptionTask
    from core.transcriber import load_existing_model, transcribe

    src = os.path.abspath(args.file)
    if not os.path.isfile(src):
        print(f"error: file not found: {src}", file=sys.stderr)
        return 2

    cfg = load_config()
    formats = args.formats or cfg.get("output_formats") or ["srt", "json"]
    cfg["output_formats"] = formats
    if args.language:
        # language code is set per-task, not globally
        pass
    if args.diarization:
        cfg["diarization_enabled"] = True
    save_config(cfg)

    print(f"[cli] loading model...", flush=True)
    if not load_existing_model(lambda m: print(f"[cli] {m}", flush=True)):
        print("error: model not loaded", file=sys.stderr)
        return 3

    task = TranscriptionTask(src)
    if args.language:
        task.language = args.language

    def _on_log(m: str) -> None:
        print(f"[cli] {m}", flush=True)

    def _on_progress(p: int) -> None:
        # one progress line per percentage; flushable.
        pass

    transcribe(task, _on_progress, _on_log, language_cb=None)

    base, _ = os.path.splitext(src)
    print(f"[cli] wrote outputs next to {src}", flush=True)
    for ext in formats:
        candidate = f"{base}.{ext}"
        if os.path.isfile(candidate):
            print(f"  {candidate}", flush=True)
    return 0


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
