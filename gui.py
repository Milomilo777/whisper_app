"""Entry point. Two modes:

  python gui.py            -> launch the Tk app (default)
  python gui.py --worker   -> spawn the JSON-stdio worker subprocess

The --worker shape is the spawn-contract the App uses to start its
own worker; do NOT rename or remove it.
"""
from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--worker":
        # Strip --worker so any future sub-args parse cleanly.
        sys.argv.pop(1)
        from core.worker import main as worker_main
        return worker_main()

    from app.app import main as app_main
    return app_main()


if __name__ == "__main__":
    raise SystemExit(main())
