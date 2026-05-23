"""Per-site download integrations.

Each submodule wraps one external site whose download flow is awkward
enough (custom JS player, no public extractor, etc.) that we can't
just hand the URL to yt-dlp.

Currently shipped:
  * :mod:`core.integrations.smtv` — Supreme Master TV scraper.
"""
from __future__ import annotations
