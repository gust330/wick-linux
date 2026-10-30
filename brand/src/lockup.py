"""Writes the Wick logotype and lockups as outlined SVGs, so they need no font installed.
Run: python3 brand/src/lockup.py <Geist-Medium.ttf> <out dir>

Geist (SIL Open Font License), Medium, tracked in slightly. The word is set once and never retyped.
"""
import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

font = TTFont(sys.argv[1])
out = Path(sys.argv[2])
glyphs = font.getGlyphSet()
cmap = font.getBestCmap()
kern_em = -0.022
upem = font["head"].unitsPerEm
cap = font["OS/2"].sCapHeight


def word_path(text, size):
    scale = size / upem
    x = 0.0
    pen = SVGPathPen(glyphs, lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
    for char in text:
        name = cmap[ord(char)]
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, cap * scale)))
        x += (glyphs[name].width + kern_em * upem) * scale
    return pen.getCommands(), x - kern_em * upem * scale, cap * scale


FOLD = "M20.5 16.3H4.87A1 1 0 0 1 4.3 14.48L14 7.7"


def mark(color, ember, unit, x, y):
    return (
        f'<g transform="translate({x} {y}) scale({unit})" fill="none">'
        f'<path d="{FOLD}" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<circle cx="15.8" cy="11.9" r="2.25" fill="{ember}"/></g>'
    )


def lockup(name, ink, ember):
    # The mark's ink is about 10.6 of its 24 units tall. This scale makes that match the word's cap height.
    size = 96
    path, width, height = word_path("Wick", size)
    unit = height * 2.3 / 24
    box = 24 * unit
    # Ink runs from about x=3.4 to x=21.5 on the grid. One ember width separates mark and word.
    mark_x = -2.9 * unit
    word_x = mark_x + 21.5 * unit + 5.5 * unit
    w = word_x + width + 2
    y = (box - height) / 2
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.1f} {box:.1f}" width="{w:.1f}" height="{box:.1f}">'
        + mark(ink, ember, unit, mark_x, 0)
        + f'<path transform="translate({word_x:.2f} {y:.2f})" d="{path}" fill="{ink}"/></svg>'
    )
    (out / f"{name}.svg").write_text(svg)


lockup("lockup-dark", "#141211", "#FF8A3D")
lockup("lockup-light", "#F5F2EE", "#FF8A3D")
lockup("lockup-mono-dark", "#141211", "#141211")
lockup("lockup-mono-light", "#F5F2EE", "#F5F2EE")

for name, ink, ember in (
    ("mark-dark", "#141211", "#FF8A3D"),
    ("mark-light", "#F5F2EE", "#FF8A3D"),
    ("mark-mono", "#000000", "#000000"),
):
    (out / f"{name}.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">'
        + mark(ink, ember, 1, 0, 0)
        + "</svg>"
    )

path, width, height = word_path("Wick", 400)
(out / "wordmark-light.svg").write_text(
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.1f} {height:.1f}">'
    f'<path d="{path}" fill="#F5F2EE"/></svg>'
)
