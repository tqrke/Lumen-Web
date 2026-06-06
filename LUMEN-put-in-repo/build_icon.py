"""Generate luxury LUMEN icon (gold arc on deep charcoal) + Windows .ico."""

from __future__ import annotations

import math
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    raise SystemExit("Install Pillow: pip install Pillow")

ROOT = Path(__file__).resolve().parent
PNG = ROOT / "assets" / "lumen-icon.png"
ICO = ROOT / "assets" / "lumen.ico"
SIZES = [16, 24, 32, 48, 64, 128, 256]


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def render_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size / 2, size / 2
    r = size * 0.44

    # Deep radial background
    for i in range(int(r), 0, -1):
        t = i / r
        col = (
            int(_lerp(18, 32, t)),
            int(_lerp(18, 32, t)),
            int(_lerp(20, 36, t)),
            255,
        )
        draw.ellipse((cx - i, cy - i, cx + i, cy + i), fill=col)

    # Outer ring — Edge blue
    ring = max(1, size // 32)
    draw.ellipse(
        (cx - r, cy - r, cx + r, cy + r),
        outline=(0, 120, 212, 220),
        width=ring,
    )

    # Gold luminous arc (L shape / light beam)
    gold = (184, 149, 106, 255)
    gold_hi = (212, 178, 130, 255)
    sw = max(2, size // 14)
    arc_r = r * 0.62
    bbox = (cx - arc_r, cy - arc_r, cx + arc_r, cy + arc_r)
    draw.arc(bbox, start=200, end=340, fill=gold, width=sw)
    draw.arc(bbox, start=210, end=330, fill=gold_hi, width=max(1, sw - 1))

    # Center gem
    gem_r = size * 0.09
    draw.ellipse(
        (cx - gem_r, cy - gem_r, cx + gem_r, cy + gem_r),
        fill=(0, 120, 212, 255),
    )
    highlight = gem_r * 0.35
    draw.ellipse(
        (cx - gem_r + highlight, cy - gem_r + highlight,
         cx - gem_r + highlight + gem_r * 0.5, cy - gem_r + highlight + gem_r * 0.5),
        fill=(100, 180, 255, 180),
    )

    if size >= 48:
        # Subtle lens flare
        flare = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        fd = ImageDraw.Draw(flare)
        for angle in (35, 145):
            rad = math.radians(angle)
            x2 = cx + math.cos(rad) * r * 0.85
            y2 = cy + math.sin(rad) * r * 0.85
            fd.line((cx, cy, x2, y2), fill=(184, 149, 106, 40), width=max(1, size // 64))
        flare = flare.filter(ImageFilter.GaussianBlur(radius=max(1, size // 48)))
        img = Image.alpha_composite(img, flare)

    return img


def main() -> None:
    PNG.parent.mkdir(parents=True, exist_ok=True)
    master = render_icon(512)
    master.save(PNG, format="PNG")
    print(f"Created {PNG}")

    icons = [render_icon(s) for s in SIZES]
    icons[0].save(
        ICO,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=icons[1:],
    )
    print(f"Created {ICO}")


if __name__ == "__main__":
    main()
