"""The microphone icon, drawn in code (no asset files), one colour per state."""
from __future__ import annotations

from PIL import Image, ImageDraw

COLORS = {
    "idle": (32, 122, 96),  # the PCB green
    "recording": (214, 48, 49),
    "processing": (230, 145, 20),
    "loading": (110, 120, 130),
    "error": (110, 120, 130),
}


def mic_image(state: str = "idle", size: int = 64) -> Image.Image:
    s = size / 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(14 * s), fill=COLORS.get(state, COLORS["idle"]))
    white = (255, 255, 255, 255)
    # capsule
    d.rounded_rectangle([24 * s, 10 * s, 40 * s, 38 * s], radius=int(8 * s), fill=white)
    # cradle
    d.arc([16 * s, 20 * s, 48 * s, 46 * s], start=0, end=180, fill=white, width=max(2, int(4 * s)))
    # stand and base
    d.line([32 * s, 46 * s, 32 * s, 53 * s], fill=white, width=max(2, int(4 * s)))
    d.line([23 * s, 54 * s, 41 * s, 54 * s], fill=white, width=max(2, int(4 * s)))
    if state == "error":
        d.line([12 * s, 12 * s, 52 * s, 52 * s], fill=(255, 255, 255, 255), width=max(2, int(5 * s)))
    return img


def write_ico(path) -> None:
    img = mic_image("idle", 256)
    img.save(path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
