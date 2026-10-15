#!/usr/bin/env python3
"""Deterministic LCD adaptation of ebazchan's full procedural avatar face.

Expression identities, mouth geometry, gaze quirks and integer inverse
rotation follow samples/stackchang_face/src/stackchang_face.v in ebazchan.
Eyes use consistent 4x4 optical glyphs so the two eyes remain readable on
the VMU LCD despite the source eyes' different subpixel positions.
M5Stack-Avatar:
Copyright (c) 2018 Shinya Ishikawa, MIT License; see the distributed
THIRD_PARTY_NOTICES.txt. No reference script is imported or executed.

Source positions use the 240x240 field cropped to y=40..199 and uniformly
scaled by 1/5. Optical eye glyphs are placed at those quantized centres,
then inverse-rotated with the whole face. The mouth retains source-pixel
coverage and formulas; its closed 90x4 source rectangle gets an 18x1 LCD
stroke. In returned mode-1 images,
nonzero means a DARK LCD pixel; clear face features are zero. Preview images
invert that semantic mask. GIF timing illustrates the exact ROM schedule;
it does not claim measured hardware timing. No body or text enters LCD art.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from PIL import GifImagePlugin, Image, ImageDraw

W, H = 48, 32
SCALE = 5
VIEWPORT = (0, 40, 240, 200)
EYES = ((50, 93), (190, 96))
EYE_RADIUS = 8
MOUTH = (123, 148, 90, 4)
EXPRESSIONS = ("neutral", "happy", "angry", "sad", "sleepy", "doubt")
ROT_COS = {-3: 1020, -2: 1022, -1: 1024, 0: 1024, 1: 1024, 2: 1022, 3: 1020}
ROT_SIN = {-3: -89, -2: -60, -1: -30, 0: 0, 1: 30, 2: 60, 3: 89}
OPTICAL_EYES = {
    "neutral": ("0110", "1111", "1111", "0110"),
    "happy": ("0110", "1001", "0000", "0000"),
    "sleepy": ("0000", "0000", "1111", "0110"),
    "angry_left": ("0000", "1100", "1111", "0110"),
    "angry_right": ("0000", "0011", "1111", "0110"),
}
POSES = (
    {"name": "rest", "closed": False, "k": 0, "gaze_v": 0, "gaze_h": 0, "mouth_open": 0},
    {"name": "blink", "closed": True, "k": 0, "gaze_v": 0, "gaze_h": 0, "mouth_open": 0},
    {"name": "lookleft", "closed": False, "k": 25, "gaze_v": -3, "gaze_h": -3, "mouth_open": 0},
    {"name": "lookright", "closed": False, "k": 75, "gaze_v": 3, "gaze_h": 3, "mouth_open": 0},
    {"name": "mouthquarter", "closed": False, "k": 0, "gaze_v": 0, "gaze_h": 0, "mouth_open": 64},
    {"name": "mouthhalf", "closed": False, "k": 0, "gaze_v": 0, "gaze_h": 0, "mouth_open": 128},
    {"name": "mouthfull", "closed": False, "k": 0, "gaze_v": 0, "gaze_h": 0, "mouth_open": 256},
)
SEGMENTS = (
    ("rest", 8), ("blink", 2), ("lookleft", 4), ("lookright", 4),
    ("mouthquarter", 2), ("mouthhalf", 2), ("mouthfull", 2),
    ("mouthhalf", 2), ("mouthquarter", 2), ("rest", 4),
)
PREVIEW_TICK_MS = 100
SOURCE_GEOMETRY = {
    "source_size": [240, 240], "viewport_xyxy": list(VIEWPORT),
    "scale": "1/5 uniform", "eye_centres": [list(p) for p in EYES],
    "eye_radius": EYE_RADIUS, "happy_inner_radius": 5,
    "mouth_centre": list(MOUTH[:2]), "mouth_closed_size": list(MOUTH[2:]),
    "mouth_width_formula": "90 - ((40 * mouth_open) >> 8)",
    "mouth_height_formula": "4 + ((56 * mouth_open) >> 8)",
    "mouth_open_range": [0, 256], "mouth_pixel_coverage_samples_per_pixel": 25,
    "mouth_pixel_coverage_threshold": "13/25 integer source pixels; 10/25 for closed subpixel stroke",
    "closed_mouth_lcd_size": [18, 1],
    "eye_rasterization": "consistent 4x4 optical glyphs, not phase-sensitive 5x5 eye coverage",
    "eye_glyphs": OPTICAL_EYES,
    "eye_origin_formula": "(floor(source_cx/5)-2, floor((source_cy-40)/5)-2)",
    "closed_eye_lcd_size": [3, 1],
    "rotation_pivot": [120, 120], "rotation_scale": 1024,
    "rotation_cos_by_gaze_h": ROT_COS, "rotation_sin_by_gaze_h": ROT_SIN,
}


def _eye_hit(x: int, y: int, cx: int, cy: int, is_left: bool,
             expression: str, closed: bool) -> bool:
    if closed:
        return cx-8 <= x < cx+8 and cy-2 <= y < cy+2
    dx, dy = x-cx, y-cy
    if dx*dx + dy*dy > 64:
        return False
    if expression in ("angry", "sad"):
        lx, ly = x-(cx-8), y-(cy-8)
        apex_right = not (is_left ^ (expression == "sad"))
        if 0 <= lx <= 16 and 0 <= ly <= 8:
            cut = (lx >= 2*ly) if apex_right else (lx <= 16-2*ly)
            if cut:
                return False
    if expression == "sleepy":
        if cx-8 <= x < cx+12 and cy-8 <= y < cy+2:
            return False
    if expression == "happy":
        if dx*dx + dy*dy <= 25 or (cx-8 <= x < cx+12 and cy <= y < cy+10):
            return False
    # The source gives Doubt no special mask; it intentionally equals Neutral.
    return True


def _optical_eyes(eye_centres: tuple, expression: str, closed: bool,
                  gaze_h: int) -> set[int]:
    """Place consistent LCD masks before applying the whole-face tilt."""
    unrotated = set()
    for eye, (cx, cy) in enumerate(eye_centres):
        if closed:
            points = [(cx//5+offset, (cy-40)//5) for offset in (-1, 0, 1)]
        else:
            key = expression
            if expression == "doubt":
                key = "neutral"
            elif expression in ("angry", "sad"):
                use_left = (eye == 0) ^ (expression == "sad")
                key = "angry_left" if use_left else "angry_right"
            glyph = OPTICAL_EYES[key]
            left, top = cx//5-2, (cy-40)//5-2
            points = [(left+x, top+y) for y, row in enumerate(glyph)
                      for x, bit in enumerate(row) if bit == "1"]
        unrotated.update(y*W+x for x, y in points if 0 <= x < W and 0 <= y < H)
    if gaze_h == 0:
        return unrotated
    c, s = ROT_COS[gaze_h], ROT_SIN[gaze_h]
    rotated = set()
    for y in range(H):
        for x in range(W):
            # Sample each optical LCD cell's middle source pixel. The same
            # inverse-rotation pivot and integer table also rotate the mouth.
            dx, dy = x*5+2-120, y*5+42-120
            px, py = ((c*dx+s*dy) >> 10)+120, ((c*dy-s*dx) >> 10)+120
            sx, sy = px//5, (py-40)//5
            if 0 <= sx < W and 0 <= sy < H and sy*W+sx in unrotated:
                rotated.add(y*W+x)
    return rotated


def render_face(closed: bool = False, *, expression: str = "neutral", k: int = 0,
                gaze_v: int = 0, gaze_h: int = 0, mouth_open: int = 0) -> Image.Image:
    """Render a 48x32 semantic LCD mask (1=dark, 0=clear)."""
    if expression not in EXPRESSIONS:
        raise ValueError(f"Unknown expression: {expression}")
    if gaze_h not in ROT_COS or not -3 <= gaze_v <= 3:
        raise ValueError("Gaze must be an integer in -3..3")
    if not 0 <= mouth_open <= 256:
        raise ValueError("mouth_open must be in 0..256")
    breath = math.sin((k % 100) * 2 * math.pi / 100)
    eye_dy = math.floor(3 * breath)
    mouth_dy = eye_dy + math.floor(2 * breath)
    eye_centres = ((50+gaze_v, 93+gaze_v+eye_dy),
                   (190+gaze_h, 96+gaze_v+eye_dy))
    mouth_w, mouth_h = 90-(40*mouth_open >> 8), 4+(56*mouth_open >> 8)
    mouth_left, mouth_top = 123-mouth_w//2, 148+mouth_dy-mouth_h//2
    c, s = ROT_COS[gaze_h], ROT_SIN[gaze_h]
    coverage = [0]*(W*H)
    for y in range(VIEWPORT[1], VIEWPORT[3]):
        for x in range(VIEWPORT[0], VIEWPORT[2]):
            dx, dy = x-120, y-120
            px, py = ((c*dx+s*dy) >> 10)+120, ((c*dy-s*dx) >> 10)+120
            target = ((y-40)//SCALE)*W + x//SCALE
            if (mouth_left <= px < mouth_left+mouth_w and
                    mouth_top <= py < mouth_top+mouth_h):
                coverage[target] += 1
    image = Image.new("1", (W, H), 1)
    features = _optical_eyes(eye_centres, expression, closed, gaze_h)
    threshold = 10 if mouth_h < 5 else 13
    features.update(index for index, count in enumerate(coverage) if count >= threshold)
    for index in features:
        image.putpixel((index % W, index // W), 0)
    return image


def as_vram(image: Image.Image) -> bytes:
    """Pack a semantic 48x32 image row-major, MSB on the left (192 bytes)."""
    if image.size != (W, H) or image.mode != "1":
        raise ValueError("Expected a 48x32 mode-1 semantic LCD mask")
    return bytes(sum(bool(image.getpixel((x+bit, y))) << (7-bit) for bit in range(8))
                 for y in range(H) for x in range(0, W, 8))


def display_image(mask: Image.Image) -> Image.Image:
    """Convert 1=dark LCD semantics to ordinary black/white image colours."""
    return mask.convert("L").point(lambda value: 0 if value else 255)


def _gif_frame(mask: Image.Image) -> Image.Image:
    frame = Image.new("P", mask.size)
    frame.putpalette([0, 0, 0, 255, 255, 255] + [0]*762)
    frame.putdata([0 if value else 1 for value in mask.getdata()])
    return frame.resize((480, 320), Image.Resampling.NEAREST)


def _write_gif(path: Path, sprites: list[Image.Image], frame_ids: list[int]) -> None:
    # Explicit GIF data keeps all 192 ROM ticks, including identical neighbours.
    frames = [_gif_frame(mask) for mask in sprites]
    header, _ = GifImagePlugin.getheader(frames[frame_ids[0]], info={"loop": 0, "duration": PREVIEW_TICK_MS})
    with path.open("wb") as target:
        for block in header:
            target.write(block)
        for frame_id in frame_ids:
            for block in GifImagePlugin.getdata(frames[frame_id], duration=PREVIEW_TICK_MS, disposal=2):
                target.write(block)
        target.write(b";")


def expression_gallery() -> Image.Image:
    """Labelled review sheet; labels never enter the LCD art."""
    gallery = Image.new("RGB", (752, 392), "#303030")
    draw = ImageDraw.Draw(gallery)
    for index, expression in enumerate(EXPRESSIONS):
        x, y = 8+(index % 3)*248, 8+(index//3)*192
        panel = display_image(render_face(expression=expression)).resize((240, 160), Image.Resampling.NEAREST).convert("RGB")
        gallery.paste(panel, (x, y))
        label = expression.upper() + (" (= NEUTRAL)" if expression == "doubt" else "")
        draw.text((x+4, y+166), label, fill="white")
    return gallery


def generate(output_dir: Path | str) -> dict:
    """Generate deduplicated sprites, exact runtime schedule and previews."""
    output_dir = Path(output_dir)
    sprites, sprite_data, sprite_meta, lookup = [], [], [], {}
    by_bytes: dict[bytes, int] = {}
    for expression in EXPRESSIONS:
        for pose in POSES:
            parameters = {name: value for name, value in pose.items() if name != "name"}
            image = render_face(expression=expression, **parameters)
            data = as_vram(image)
            if data not in by_bytes:
                frame_id = len(sprites)
                by_bytes[data] = frame_id
                sprites.append(image)
                sprite_data.append(data)
                sprite_meta.append({"id": frame_id, "sha256": hashlib.sha256(data).hexdigest(), "poses": []})
            frame_id = by_bytes[data]
            lookup[(expression, pose["name"])] = frame_id
            sprite_meta[frame_id]["poses"].append({"expression": expression, "pose": pose["name"], **parameters})
    if len(sprites) > 127:
        raise ValueError("Sprite count exceeds the 8-bit doubled pointer index")
    frame_ids, expression_labels, phase_states = [], [], []
    for expression in EXPRESSIONS:
        for pose, ticks in SEGMENTS:
            frame_ids.extend([lookup[(expression, pose)]]*ticks)
            expression_labels.extend([expression]*ticks)
            phase_states.extend([pose]*ticks)
    if len(frame_ids) != 192:
        raise ValueError("Expected exactly 192 timeline ticks")
    animation = {"schema_version": 1, "expressions": list(EXPRESSIONS),
                 "expression_aliases": {"doubt": "neutral"}, "ticks_per_expression": 32,
                 "frame_count": len(sprites), "timeline_ticks": len(frame_ids),
                 "frame_ids": frame_ids, "expression_labels": expression_labels,
                 "phase_states": phase_states, "sprites": sprite_meta,
                 "poses": list(POSES), "segments": [{"pose": pose, "ticks": ticks} for pose, ticks in SEGMENTS],
                 "preview_tick_ms": PREVIEW_TICK_MS,
                 "preview_timing": "illustrative; physical VMU elapsed timing is unmeasured"}
    (output_dir/"animation.json").write_text(json.dumps(animation, indent=2, sort_keys=True)+"\n", encoding="utf-8", newline="\n")
    (output_dir/"frames.bin").write_bytes(b"".join(sprite_data))
    neutral, blink = sprites[lookup[("neutral", "rest")]], sprites[lookup[("neutral", "blink")]]
    display_image(neutral).save(output_dir/"neutral.png")
    display_image(blink).save(output_dir/"blink.png")
    display_image(neutral).resize((480, 320), Image.Resampling.NEAREST).save(output_dir/"face.png")
    _write_gif(output_dir/"preview.gif", sprites, frame_ids)
    # Labels belong to this external comparison sheet, never to LCD sprites.
    expression_gallery().save(output_dir/"expressions.png")
    icon = neutral.crop((8, 0, 40, 32))
    display_image(icon).save(output_dir/"icon.png")
    (output_dir/"icon.bin").write_bytes(bytes(
        (0 if icon.getpixel((x, y)) else 1) << 4 | (0 if icon.getpixel((x+1, y)) else 1)
        for y in range(32) for x in range(0, 32, 2)))
    return {"geometry": SOURCE_GEOMETRY, "frame_count": len(sprites), "bytes_per_frame": 192,
            "expressions": list(EXPRESSIONS), "poses_per_expression": len(POSES),
            "timeline_ticks": len(frame_ids), "timeline_file": "animation.json",
            "expression_aliases": {"doubt": "neutral"},
            "source_quirks": ["Doubt eye mask equals Neutral",
                              "screen-left eye gaze uses (gaze_v,gaze_v); right uses (gaze_h,gaze_v)",
                              "mouth narrows and grows taller as open increases",
                              "whole face inverse-rotates about (120,120) using integer source tables"],
            "lcd_bit_semantics": "1=dark, 0=clear; MSB-left, row-major",
            "icon": "centre crop x=8..39 of neutral face; palette 0=black, 1=white",
            "preview": "exact 192 ROM ticks at illustrative 100ms/tick; elapsed hardware timing unmeasured"}
