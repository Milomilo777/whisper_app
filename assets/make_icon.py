"""Generate the app icon.

Run once (manually, not part of the build pipeline) to produce
``assets/whisper.ico`` — a multi-resolution Windows icon. The
shipped ``.ico`` is committed; this script is here so the design
is reproducible from source rather than landing as a mystery
binary.

Design:
  A rounded-square teal background with a stylized white "W" and
  three sound-wave arcs to its right. Two contrasts so it reads
  against both the light and dark Windows themes.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUTPUT = Path(__file__).resolve().parent / "whisper.ico"

BG = (32, 122, 128)         # teal
FG = (255, 255, 255)        # white W + waves
SIZES = [256, 128, 64, 48, 32, 16]


def _draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Rounded-square background.
    radius = max(2, size // 8)
    d.rounded_rectangle(
        [(0, 0), (size - 1, size - 1)],
        radius=radius,
        fill=BG,
    )

    # The "W" — drawn as four line segments so it scales to any
    # size without relying on font availability at build time.
    pad = size * 0.18
    cx_left = pad
    cx_right = size * 0.58
    top = size * 0.30
    bottom = size * 0.70
    middle_high = size * 0.45
    stroke = max(2, size // 12)
    # Left dip + right dip of the W.
    d.line(
        [
            (cx_left, top),
            ((cx_left + cx_right) / 3, bottom),
            (size * 0.35, middle_high),
            (cx_right - (cx_right - cx_left) / 6, bottom),
            (cx_right, top),
        ],
        fill=FG,
        width=stroke,
        joint="curve",
    )

    # Three concentric arcs to the right of the W — sound waves.
    if size >= 32:
        cx = size * 0.78
        cy = size * 0.50
        for frac in (0.08, 0.14, 0.20):
            r = size * frac
            arc_stroke = max(1, size // 24)
            d.arc(
                [(cx - r, cy - r), (cx + r, cy + r)],
                start=-50,
                end=50,
                fill=FG,
                width=arc_stroke,
            )

    return img


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    layers = [_draw_icon(s) for s in SIZES]
    # Save as a single .ico that holds all sizes. Pillow's
    # ``sizes=`` arg controls the embedded resolutions.
    layers[0].save(
        OUTPUT,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=layers[1:],
    )
    # Also write a PNG sidecar — used by the About dialog and
    # anything else that prefers a flat image.
    layers[0].save(OUTPUT.with_suffix(".png"))
    print(f"wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes)")
    print(f"wrote {OUTPUT.with_suffix('.png')}")


if __name__ == "__main__":
    main()
