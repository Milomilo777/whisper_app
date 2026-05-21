"""Language tables shared across the UI and download services."""
from __future__ import annotations

# Display name → comma-separated yt-dlp subtitle language codes.
# Order: Automatic, English, then alphabetical. Multi-variant entries
# collapse the codes YouTube actually uses (e.g. zh-Hans + zh-CN).
SUBTITLE_LANGUAGES: list[tuple[str, str]] = [
    ("Automatic", ""),
    ("English", "en"),
    ("Arabic", "ar"),
    ("Chinese (Simplified)", "zh-Hans,zh-CN"),
    ("Chinese (Traditional)", "zh-Hant,zh-TW"),
    ("Czech", "cs"),
    ("Danish", "da"),
    ("Dutch", "nl"),
    ("Finnish", "fi"),
    ("French", "fr"),
    ("German", "de"),
    ("Greek", "el"),
    ("Hebrew", "he,iw"),
    ("Hindi", "hi"),
    ("Hungarian", "hu"),
    ("Indonesian", "id,in"),
    ("Italian", "it"),
    ("Japanese", "ja"),
    ("Korean", "ko"),
    ("Norwegian", "no,nb"),
    ("Persian", "fa"),
    ("Polish", "pl"),
    ("Portuguese", "pt,pt-BR,pt-PT"),
    ("Romanian", "ro"),
    ("Russian", "ru"),
    ("Spanish", "es,es-419"),
    ("Swedish", "sv"),
    ("Thai", "th"),
    ("Turkish", "tr"),
    ("Ukrainian", "uk"),
    ("Vietnamese", "vi"),
]


def subtitle_lang_args(lang: str) -> str:
    """Convert a comma-separated lang spec to the form yt-dlp's ``--sub-langs`` accepts.

    Trims whitespace and drops empty entries. Returns the empty string if
    nothing is left.
    """
    codes = [c.strip() for c in (lang or "").split(",") if c.strip()]
    return ",".join(codes)
