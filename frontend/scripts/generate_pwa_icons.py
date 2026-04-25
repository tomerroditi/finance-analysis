"""Generate PWA icon assets for the Finance Analysis dashboard.

Produces app icons in the sizes expected by the manifest plus an Apple
touch icon and the SVG used as `icon` in `index.html`. Re-run this script
whenever the brand colors (in `frontend/src/index.css`) change.

Usage::

    python scripts/generate_pwa_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

PUBLIC_DIR = Path(__file__).resolve().parent.parent / "public"
ICONS_DIR = PUBLIC_DIR / "icons"

BG = (15, 23, 42)            # --background  #0f172a
SURFACE = (30, 41, 59)       # --surface     #1e293b
PRIMARY = (59, 130, 246)     # --primary     #3b82f6
SECONDARY = (16, 185, 129)   # --secondary   #10b981
TEXT = (248, 250, 252)       # --text        #f8fafc


def _draw_chart(draw: ImageDraw.ImageDraw, size: int, inset: float) -> None:
    """Draw a simple upward-trending line chart inside a square canvas.

    Parameters
    ----------
    draw:
        Pillow drawing context.
    size:
        Canvas edge length in pixels.
    inset:
        Fraction of the canvas to leave as a margin around the chart
        (0.18 = standard, 0.28 = maskable safe zone).
    """
    margin = int(size * inset)
    box = (margin, margin, size - margin, size - margin)
    inner_w = box[2] - box[0]
    inner_h = box[3] - box[1]

    baseline_y = box[1] + int(inner_h * 0.78)
    draw.line([(box[0], baseline_y), (box[2], baseline_y)],
              fill=SURFACE, width=max(2, size // 96))

    bar_w = inner_w // 7
    gap = inner_w // 14
    heights = [0.30, 0.42, 0.36, 0.55, 0.62, 0.78]
    cursor = box[0] + gap
    for ratio in heights:
        bar_h = int(inner_h * ratio)
        bar_top = baseline_y - bar_h
        radius = max(1, bar_w // 4)
        draw.rounded_rectangle(
            (cursor, bar_top, cursor + bar_w, baseline_y),
            radius=radius,
            fill=SURFACE,
        )
        cursor += bar_w + gap

    points = [
        (box[0] + int(inner_w * 0.05), box[1] + int(inner_h * 0.70)),
        (box[0] + int(inner_w * 0.25), box[1] + int(inner_h * 0.55)),
        (box[0] + int(inner_w * 0.50), box[1] + int(inner_h * 0.40)),
        (box[0] + int(inner_w * 0.78), box[1] + int(inner_h * 0.20)),
        (box[0] + int(inner_w * 0.95), box[1] + int(inner_h * 0.08)),
    ]
    line_w = max(3, size // 48)
    draw.line(points, fill=PRIMARY, width=line_w, joint="curve")

    dot_r = max(3, size // 36)
    for px, py in points:
        draw.ellipse(
            (px - dot_r, py - dot_r, px + dot_r, py + dot_r),
            fill=PRIMARY,
            outline=TEXT,
            width=max(1, size // 128),
        )

    arrow_x, arrow_y = points[-1]
    arrow_size = max(8, size // 16)
    draw.polygon(
        [
            (arrow_x + arrow_size, arrow_y - arrow_size),
            (arrow_x + arrow_size // 4, arrow_y - arrow_size),
            (arrow_x + arrow_size, arrow_y - arrow_size // 4),
        ],
        fill=SECONDARY,
    )


def _make_icon(size: int, *, maskable: bool = False, rounded: bool = True) -> Image.Image:
    img = Image.new("RGBA", (size, size), BG + (255,))
    draw = ImageDraw.Draw(img)

    if rounded and not maskable:
        radius = int(size * 0.22)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, size, size), radius=radius, fill=255)
        bg = Image.new("RGBA", (size, size), BG + (255,))
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        img.paste(bg, (0, 0), mask)
        draw = ImageDraw.Draw(img)

    inset = 0.28 if maskable else 0.18
    _draw_chart(draw, size, inset)
    return img


def _write_svg() -> None:
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="14" fill="#0f172a"/>
  <line x1="10" y1="48" x2="54" y2="48" stroke="#1e293b" stroke-width="2"/>
  <g fill="#1e293b">
    <rect x="11" y="34" width="5" height="14" rx="1"/>
    <rect x="18" y="29" width="5" height="19" rx="1"/>
    <rect x="25" y="32" width="5" height="16" rx="1"/>
    <rect x="32" y="24" width="5" height="24" rx="1"/>
    <rect x="39" y="20" width="5" height="28" rx="1"/>
    <rect x="46" y="14" width="5" height="34" rx="1"/>
  </g>
  <polyline points="11,40 22,34 36,28 49,18 56,13"
            fill="none" stroke="#3b82f6" stroke-width="3"
            stroke-linecap="round" stroke-linejoin="round"/>
  <g fill="#3b82f6" stroke="#f8fafc" stroke-width="0.6">
    <circle cx="11" cy="40" r="2"/>
    <circle cx="22" cy="34" r="2"/>
    <circle cx="36" cy="28" r="2"/>
    <circle cx="49" cy="18" r="2"/>
    <circle cx="56" cy="13" r="2"/>
  </g>
  <polygon points="58,11 52,11 58,17" fill="#10b981"/>
</svg>
"""
    (PUBLIC_DIR / "favicon.svg").write_text(svg, encoding="utf-8")


def main() -> None:
    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    _make_icon(192).save(ICONS_DIR / "icon-192.png", optimize=True)
    _make_icon(512).save(ICONS_DIR / "icon-512.png", optimize=True)
    _make_icon(512, maskable=True, rounded=False).save(
        ICONS_DIR / "icon-512-maskable.png", optimize=True
    )
    _make_icon(180).save(ICONS_DIR / "apple-touch-icon.png", optimize=True)

    _write_svg()

    print(f"Wrote PWA icons to {ICONS_DIR}")


if __name__ == "__main__":
    main()
