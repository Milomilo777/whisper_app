"""Whisper Project (basic) — core package.

All headless logic (config, paths, model lifecycle, worker, writers,
diagnostics) lives here. The ``app`` package owns Tk and depends on
``core``; ``core`` never imports from ``app``.
"""
