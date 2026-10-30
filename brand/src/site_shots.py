"""Crops panel snapshots for the website, removing the stage they were rendered on.
Run: python3 brand/src/site_shots.py <snapshots dir> <out dir>
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

snapshots, out = Path(sys.argv[1]), Path(sys.argv[2])
STAGE_PADDING = 72  # 36pt at 2x, from wick-snapshots
RADIUS = 48

for source, target in (("idle", "shot-idle"), ("needs-access", "shot-access")):
    image = Image.open(snapshots / f"{source}.png").convert("RGBA")
    panel = image.crop((STAGE_PADDING, STAGE_PADDING, image.width - STAGE_PADDING, image.height - STAGE_PADDING))
    scale = 4
    mask = Image.new("L", (panel.width * scale, panel.height * scale), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, mask.width - 1, mask.height - 1), RADIUS * scale, fill=255)
    panel.putalpha(mask.resize(panel.size, Image.LANCZOS))
    panel.save(out / f"{target}.webp", quality=90, method=6)
    print(target, panel.size)
