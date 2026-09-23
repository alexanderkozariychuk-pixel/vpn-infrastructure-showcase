#!/usr/bin/env python3
"""
Generate the favicon-weight cut of the Sovereign mark.

    python3 make_favicon.py          # rewrites favicon-{16,32,48,192}.png and favicon.ico

Why a separate cut at all. The app icon (icon-192, icon-512, apple-touch-icon)
is seen at 180 px and up, where fine strokes read as precision. A favicon is
rendered at 16 px in a browser tab and beside a search result, and at that
size the same strokes fall below one pixel and the mark turns into a smudge —
three faint dots with no visible connection between them, which is the one
idea the mark exists to carry.

So this draws the same motif heavier: nodes larger, ring stroke and edges
thicker, the three nodes pushed further apart so the triangle survives. That
is optical sizing, the same reason a typeface ships a caption cut, and not a
rebrand. The app icons are deliberately left alone.

The numbers below were chosen by rendering candidates at 16 px on the light
background a search result uses and looking at them. An earlier attempt made
the nodes so large they merged into a blob with no edges at all — bolder is
not the same as more legible, and only looking tells you where the line is.

Everything is drawn 16x oversized and downscaled, which is what keeps the
diagonals clean.
"""
from pathlib import Path

from PIL import Image, ImageDraw

BG = (8, 12, 15, 255)        # --bg
ACCENT = (0, 212, 255, 255)  # --accent

# Normalised to a unit square, so one set of numbers drives every size.
X = 0.25       # horizontal inset of the two upper nodes
Y_TOP = 0.29
Y_BOTTOM = 0.75
R_RING = 0.120
R_DOT = 0.130
W_RING = 0.060
W_LINE = 0.060

SIZES = (16, 32, 48, 192)
ICO_SIZES = [(16, 16), (32, 32), (48, 48)]


def render(size: int, scale: int = 16) -> Image.Image:
    S = size * scale
    tl, tr, bot = (X, Y_TOP), (1 - X, Y_TOP), (0.5, Y_BOTTOM)

    img = Image.new("RGBA", (S, S), BG)
    d = ImageDraw.Draw(img)
    px = lambda p: (p[0] * S, p[1] * S)  # noqa: E731

    # Edges first — the nodes sit on top of them.
    line_w = max(1, int(W_LINE * S))
    for a, b in ((tl, tr), (tl, bot), (tr, bot)):
        d.line([px(a), px(b)], fill=ACCENT, width=line_w)

    def ring(centre, r, w):
        x, y = px(centre)
        rr, ww = r * S, max(1, int(w * S))
        d.ellipse([x - rr, y - rr, x + rr, y + rr], outline=ACCENT, width=ww)
        # Punch the centre back to the background: at this weight the edge
        # passing underneath would otherwise fill the node in.
        inner = rr - ww
        d.ellipse([x - inner, y - inner, x + inner, y + inner], fill=BG)

    def dot(centre, r):
        x, y = px(centre)
        rr = r * S
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=ACCENT)

    ring(tl, R_RING, W_RING)
    ring(tr, R_RING, W_RING)
    dot(bot, R_DOT)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    here = Path(__file__).parent
    for n in SIZES:
        render(n).save(here / f"favicon-{n}.png", optimize=True)
    render(192).save(here / "favicon.ico", format="ICO", sizes=ICO_SIZES)
    print(f"wrote favicon-{{{','.join(map(str, SIZES))}}}.png and favicon.ico")


if __name__ == "__main__":
    main()
