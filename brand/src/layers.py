"""Writes the vector layers of the app icon, and a flat preview. Run: python3 brand/src/layers.py <out dir>"""
import subprocess
import sys
from pathlib import Path

OUT = Path(sys.argv[1])
SIZE = 1024
MARK_SCALE = 0.74
UNIT = SIZE * MARK_SCALE / 24
OFFSET = (SIZE - 24 * UNIT) / 2


def frame(defs, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" viewBox="0 0 {SIZE} {SIZE}">'
        f"<defs>{defs}</defs>"
        f'<g transform="translate({OFFSET} {OFFSET}) scale({UNIT})">{body}</g></svg>'
    )


# Paper at the top, warmed from below by the coal, the way the glass catches light in the real thing.
fold = frame(
    '<linearGradient id="paper" gradientUnits="userSpaceOnUse" x1="12" y1="6.5" x2="12" y2="17.5">'
    '<stop offset="0" stop-color="#FFFFFF"/><stop offset="0.55" stop-color="#FFF6EA"/>'
    '<stop offset="1" stop-color="#FFC48C"/></linearGradient>',
    '<path d="M20.5 16.3H4.87A1 1 0 0 1 4.3 14.48L14 7.7" fill="none" stroke="url(#paper)" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
)
ember = frame(
    '<radialGradient id="core" gradientUnits="userSpaceOnUse" cx="15.8" cy="11.9" r="2.25">'
    '<stop offset="0" stop-color="#FFF8EC"/><stop offset="0.55" stop-color="#FFD9A0"/>'
    '<stop offset="1" stop-color="#FF9A50"/></radialGradient>',
    '<circle cx="15.8" cy="11.9" r="2.25" fill="url(#core)"/>',
)

for name, svg in (("fold", fold), ("ember", ember)):
    path = OUT / f"{name}.svg"
    path.write_text(svg)
    subprocess.run(["rsvg-convert", str(path), "-o", str(OUT / f"{name}.png")], check=True)
