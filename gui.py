"""Entry point. Real code lives in the ``app`` package."""
import sys

if "--worker" in sys.argv:
    from core.worker import main as _worker_main
    sys.exit(_worker_main())

from app import run

if __name__ == "__main__":
    run()
