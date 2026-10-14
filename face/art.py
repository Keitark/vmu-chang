#!/usr/bin/env python3
"""Deterministic 48x32 LCD adaptation of ebazchan's neutral avatar face.

The procedural source geometry is a 240x240 field: eye centres (50,93),
(190,96), radius 8; mouth centred at (123,148), 90x4. This is the neutral
M5Stack-Avatar geometry used by ebazchan. Copyright (c) 2018 Shinya Ishikawa,
MIT License; see the distributed THIRD_PARTY_NOTICES.txt.

Crop unused rows 0..39 and 200..239, then uniformly scale by 1/5. Pixel
coverage uses an 8x8 deterministic sample grid with a 50-percent threshold.
Subpixel horizontal strokes retain one pixel of height. No body or text is
drawn. In returned mode-1 images, a nonzero bit means a *dark LCD pixel*;
the clear eyes and mouth are zero. PNG previews invert this semantic mask
to display dark as black. Preview GIF speed is illustrative, not measured
VMU timing.
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image

W, H = 48, 32
SCALE = 5
VIEWPORT = (0, 40, 240, 200)
EYES = ((50, 93), (190, 96))
EYE_RADIUS = 8
MOUTH = (123, 148, 90, 4)
SAMPLES = 8
SOURCE_GEOMETRY = {
    "source_size": [240, 240],
    "viewport_xyxy": list(VIEWPORT),
    "scale": "1/5 uniform",
    "eye_centres": [list(p) for p in EYES],
    "eye_radius": EYE_RADIUS,
    "mouth_centre": list(MOUTH[:2]),
    "mouth_size": list(MOUTH[2:]),
    "pixel_coverage_samples_per_axis": SAMPLES,
    "pixel_coverage_threshold": "1/2",
    "minimum_horizontal_stroke_height_pixels": 1,
    "blink_stroke_size_pixels": [3, 1],
}


def _coverage(predicate, x: int, y: int) -> bool:
    """Whether at least half of the deterministic samples are in a feature."""
    inside = sum(
        predicate(x + (sx + 0.5) / SAMPLES, y + (sy + 0.5) / SAMPLES)
        for sy in range(SAMPLES) for sx in range(SAMPLES)
    )
    return inside * 2 >= SAMPLES * SAMPLES


def _clear_rectangle(image: Image.Image, cx: float, cy: float,
                     width: float, height: float) -> None:
    # Preserve at least one raster row for the source's 4/5-pixel mouth.
    raster_height = max(height, 1.0)
    row = int(cy)
    for y in range(H):
        for x in range(W):
            covered = _coverage(
                lambda px, py: (abs(px-cx) <= width/2 and
                                abs(py-cy) <= raster_height/2), x, y)
            # A one-row line centred between rows must not disappear.
            if covered or (height <= 1 and y == row and
                           abs(x + 0.5 - cx) < width/2):
                image.putpixel((x, y), 0)


def render_face(closed: bool = False) -> Image.Image:
    """Return a 48x32 binary semantic LCD mask (1=dark, 0=clear)."""
    image = Image.new("1", (W, H), 1)
    radius = EYE_RADIUS / SCALE
    for source_x, source_y in EYES:
        cx, cy = source_x / SCALE, (source_y - VIEWPORT[1]) / SCALE
        if closed:
            # Rasterise the collapsed eyelid as exactly three clear pixels;
            # a half-pixel threshold tie must not reduce it to two pixels.
            for x in range(int(cx)-1, int(cx)+2):
                image.putpixel((x, int(cy)), 0)
        else:
            for y in range(H):
                for x in range(W):
                    if _coverage(lambda px, py: ((px-cx)**2 + (py-cy)**2
                                                <= radius**2), x, y):
                        image.putpixel((x, y), 0)
    cx, cy, width, height = MOUTH
    _clear_rectangle(image, cx/SCALE, (cy-VIEWPORT[1])/SCALE,
                     width/SCALE, height/SCALE)
    return image


def as_vram(image: Image.Image) -> bytes:
    """Pack a semantic 48x32 image row-major, MSB on the left (192 bytes)."""
    if image.size != (W, H) or image.mode != "1":
        raise ValueError("Expected a 48x32 mode-1 semantic LCD mask")
    return bytes(
        sum(bool(image.getpixel((x + bit, y))) << (7-bit) for bit in range(8))
        for y in range(H) for x in range(0, W, 8)
    )


def display_image(mask: Image.Image) -> Image.Image:
    """Convert 1=dark LCD semantics to ordinary black/white image colours."""
    return mask.convert("L").point(lambda value: 0 if value else 255)


def generate(output_dir: Path | str) -> dict:
    """Generate only face assets into an existing staging directory."""
    output_dir = Path(output_dir)
    neutral, blink = render_face(), render_face(True)
    (output_dir / "frames.bin").write_bytes(as_vram(neutral) + as_vram(blink))
    neutral_display, blink_display = display_image(neutral), display_image(blink)
    neutral_display.save(output_dir / "neutral.png")
    blink_display.save(output_dir / "blink.png")
    neutral_display.resize((480, 320), Image.Resampling.NEAREST).save(
        output_dir / "face.png")
    neutral_display.resize((480, 320), Image.Resampling.NEAREST).save(
        output_dir / "preview.gif", save_all=True,
        append_images=[blink_display.resize((480, 320), Image.Resampling.NEAREST)],
        duration=[1400, 200], loop=0, optimize=False, disposal=2)
    # A centred 32x32 crop preserves the LCD face's aspect ratio in the VMU
    # file-manager icon; it is the same face, with no legacy robot drawing.
    icon = neutral.crop((8, 0, 40, 32))
    display_image(icon).save(output_dir / "icon.png")
    icon_bytes = bytes(
        (0 if icon.getpixel((x, y)) else 1) << 4 |
        (0 if icon.getpixel((x+1, y)) else 1)
        for y in range(32) for x in range(0, 32, 2)
    )
    (output_dir / "icon.bin").write_bytes(icon_bytes)
    return {"geometry": SOURCE_GEOMETRY,
            "frame_count": 2, "bytes_per_frame": 192,
            "lcd_bit_semantics": "1=dark, 0=clear; MSB-left, row-major",
            "icon": "centre crop x=8..39 of neutral face; palette 0=black, 1=white",
            "preview": "illustrative 14:2 open:closed ratio; not measured hardware timing"}
