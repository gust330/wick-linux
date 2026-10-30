"""Composes brand/board.png and docs/hero.png from the real assets.
Run: python3 brand/src/board.py <snapshots dir> <icon.png> <coal.png> <Geist-Regular.ttf> <Geist-Medium.ttf>
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

snapshots, icon_png, coal_png, regular, medium = map(Path, sys.argv[1:6])
SCALE = 2
tmp = Path(tempfile.mkdtemp())


def font(size, heavy=False):
    return ImageFont.truetype(str(medium if heavy else regular), size * SCALE)


def svg(path, height):
    out = tmp / (Path(path).stem + f"-{height}.png")
    subprocess.run(["rsvg-convert", "-h", str(height * SCALE), "--keep-aspect-ratio", str(path), "-o", str(out)], check=True)
    return Image.open(out).convert("RGBA")


def rounded(size, radius, fill):
    mask = Image.new("L", (size[0] * 2, size[1] * 2), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] * 2 - 1, size[1] * 2 - 1), radius * 2, fill=255)
    mask = mask.resize(size, Image.LANCZOS)
    tile = Image.new("RGBA", size, fill) if isinstance(fill, tuple) else fill.convert("RGBA").resize(size)
    tile.putalpha(mask)
    return tile


def cover(image, size):
    ratio = max(size[0] / image.width, size[1] / image.height)
    scaled = image.resize((round(image.width * ratio), round(image.height * ratio)), Image.LANCZOS)
    # Anchored to the bottom, where the coal is.
    left = (scaled.width - size[0]) // 2
    top = scaled.height - size[1]
    return scaled.crop((left, top, left + size[0], top + size[1]))


def panel(name, width):
    """The real window capture, shadow included. `width` is the width of the panel itself, which is 340pt."""
    image = Image.open(snapshots / f"{name}.png").convert("RGBA")
    image = image.crop((0, 0, image.width, image.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()[3]))
    scale = width * SCALE / (340 * 2)
    return image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)


def at(value):
    return value * SCALE


INK = (245, 242, 238)
MUTED = (245, 242, 238, 150)
BG = (12, 10, 9, 255)
glow = Image.open(coal_png).convert("RGBA")
icon = Image.open(icon_png).convert("RGBA")

# Board
W, H = 1600, 1040
board = Image.new("RGBA", (at(W), at(H)), BG)
draw = ImageDraw.Draw(board)
GAP = 16
M = 40


def label(x, y, text, target=None):
    (target or draw).text((at(x), at(y)), text, font=font(13), fill=MUTED)


# Icon, on the darkest field, with room around it.
tile = rounded((at(520), at(520)), 28, (20, 18, 17, 255))
board.alpha_composite(tile, (at(M), at(M)))
board.alpha_composite(icon.resize((at(340), at(340)), Image.LANCZOS), (at(M + 90), at(M + 90)))
label(M + 24, M + 484, "App icon. Liquid Glass layers from Icon Composer, the light rendered in Blender")

# Lockup on the brand's light.
x2 = M + 520 + GAP
tile = rounded((at(520), at(252)), 28, cover(glow, (at(520), at(252))))
board.alpha_composite(tile, (at(x2), at(M)))
lockup = svg("brand/logo/lockup-light.svg", 74)
board.alpha_composite(lockup, (at(x2) + (at(520) - lockup.width) // 2, at(M) + (at(252) - lockup.height) // 2))

# Lockup on paper.
tile = rounded((at(520), at(252)), 28, (245, 242, 238, 255))
board.alpha_composite(tile, (at(x2), at(M + 252 + GAP)))
lockup = svg("brand/logo/lockup-dark.svg", 74)
board.alpha_composite(lockup, (at(x2) + (at(520) - lockup.width) // 2, at(M + 252 + GAP) + (at(252) - lockup.height) // 2))

# The panel.
x3 = x2 + 520 + GAP
column = (W - M - x3, H - 2 * M)
tile = rounded((at(column[0]), at(column[1])), 28, cover(glow, (at(column[0]), at(column[1]))))
board.alpha_composite(tile, (at(x3), at(M)))
awake = panel("real-awake", 360)
board.alpha_composite(awake, (at(x3) + (at(column[0]) - awake.width) // 2, at(M + 60)))

# Menu bar states.
y2 = M + 520 + GAP
tile = rounded((at(520), at(220)), 28, (20, 18, 17, 255))
board.alpha_composite(tile, (at(M), at(y2)))
label(M + 24, y2 + 20, "Menu bar. A template glyph, so it follows the bar's colour")
for index, (dark, awake_state, text) in enumerate(((True, False, ""), (True, True, "1h 42m"), (False, True, "1h 42m"))):
    bx, bw = M + 24 + index * 160, 148
    bar = rounded((at(bw), at(52)), 12, (0, 0, 0, 255) if dark else (245, 242, 238, 255))
    board.alpha_composite(bar, (at(bx), at(y2 + 96)))
    ink = "#F5F2EE" if dark else "#141211"
    source = Path(tmp / f"glyph-{index}.svg")
    ember = (
        '<circle cx="15.8" cy="11.9" r="2.25" fill="%s"/>' % ink
        if awake_state
        else '<circle cx="15.8" cy="11.9" r="1.5" fill="none" stroke="%s" stroke-width="1.5"/>' % ink
    )
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M20.5 16.3H4.87A1 1 0 0 1 4.3 14.48L14 7.7" '
        f'fill="none" stroke="{ink}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>{ember}</svg>'
    )
    glyph = svg(source, 28)
    gx = bx + (bw - 28) // 2 if not text else bx + 16
    board.alpha_composite(glyph, (at(gx), at(y2 + 108)))
    if text:
        ImageDraw.Draw(board).text(
            (at(bx + 50), at(y2 + 113)), text, font=font(16, True), fill=(245, 242, 238) if dark else (20, 18, 17)
        )

# Palette.
tile = rounded((at(520), at(220)), 28, (20, 18, 17, 255))
board.alpha_composite(tile, (at(x2), at(y2)))
label(x2 + 24, y2 + 20, "Colour. Ember only ever means awake")
swatches = [
    ("Ember", "#FF8A3D"), ("Hot", "#FFC27A"), ("Deep", "#D9421A"), ("Paper", "#F5F2EE"), ("Canvas", "#141211"),
]
for index, (name, value) in enumerate(swatches):
    sx = x2 + 24 + index * 95
    fill = tuple(int(value[i:i + 2], 16) for i in (1, 3, 5)) + (255,)
    swatch = rounded((at(84), at(84)), 42, fill)
    board.alpha_composite(swatch, (at(sx), at(y2 + 56)))
    if name == "Canvas":
        ImageDraw.Draw(board).ellipse(
            (at(sx), at(y2 + 56), at(sx + 84) - 1, at(y2 + 140) - 1), outline=(255, 255, 255, 40), width=2
        )
    draw = ImageDraw.Draw(board)
    draw.text((at(sx), at(y2 + 150)), name, font=font(13, True), fill=INK)
    draw.text((at(sx), at(y2 + 170)), value, font=font(12), fill=MUTED)

# Type, along the bottom.
y3 = y2 + 220 + GAP
tile = rounded((at(1056), at(200)), 28, (20, 18, 17, 255))
board.alpha_composite(tile, (at(M), at(y3)))
draw = ImageDraw.Draw(board)
label(M + 24, y3 + 20, "Type. Geist Medium for the name, San Francisco inside the app")
draw.text((at(M + 24), at(y3 + 56)), "Wick", font=font(84, True), fill=INK)
draw.text((at(M + 280), at(y3 + 60)), "Stays lit with the lid closed.", font=font(32), fill=INK)
draw.text(
    (at(M + 280), at(y3 + 112)),
    "The name is a candle's wick: small, patient, and still burning\nwhen everything else has gone quiet.",
    font=font(16),
    fill=MUTED,
    spacing=at(4),
)
board.convert("RGB").save("brand/board.png", optimize=True)

# README hero
W, H = 1280, 720
hero = cover(glow, (at(W), at(H))).convert("RGBA")
idle = panel("real-idle", 400)
awake = panel("real-awake", 400)
# The captures carry wide transparent margins for their shadows, so they may overlap.
gap = -60
total = idle.width + awake.width + at(gap)
left = (at(W) - total) // 2
top = at(150)
lockup = svg("brand/logo/lockup-light.svg", 44)
hero.alpha_composite(lockup, ((at(W) - lockup.width) // 2, at(40)))
hero.alpha_composite(idle, (left, top))
hero.alpha_composite(awake, (left + idle.width + at(gap), top))
Path("docs").mkdir(exist_ok=True)
hero.convert("RGB").save("docs/hero.png", optimize=True)
