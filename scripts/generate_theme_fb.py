#!/usr/bin/env python3
"""
Render SpecPine on-device framebuffer assets.

Writes raw 480×222 RGB565 frames matching the Pager's logical landscape
orientation (renderer rotates to the physical 222×480 portrait fb):

    fb[lx * 222 + (221 - ly)] = RGB565(lx, ly)

Outputs go into payloads/specpine/data/theme/:
  - splash.fb              (single-frame title shot)
  - boot_animation/frame_1.fb  (4-frame WOPR-style boot sequence)
  - boot_animation/frame_2.fb
  - boot_animation/frame_3.fb
  - boot_animation/frame_4.fb

Each .fb is exactly IMG_W * IMG_H * 2 = 480 * 222 * 2 = 213,120 bytes.

Run from the repo root:
    python3 scripts/generate_theme_fb.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow required: python3 -m pip install --user --break-system-packages Pillow")
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR   = REPO_ROOT / "payloads" / "specpine" / "data" / "theme"
ANIM_DIR  = OUT_DIR / "boot_animation"
ANIM_DIR.mkdir(parents=True, exist_ok=True)

# Logical (landscape) — matches spectools_waterfall_fb.py
IMG_W, IMG_H = 480, 222
FB_W, FB_H = 222, 480
FB_BYTES = FB_W * FB_H * 2

# Palette (mirrors theme.sh THEME_FB_* tokens)
BG       = (8,   12,  8)
BG_DARK  = (3,   6,   3)
GREEN    = (0,   220, 100)
GREEN_D  = (0,   140, 60)
GREEN_DD = (0,   70,  30)
AMBER    = (255, 180, 40)
CYAN     = (60,  220, 220)
WHITE    = (220, 255, 220)


def rgb565(r: int, g: int, b: int) -> int:
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def find_mono_font(size: int) -> "ImageFont.ImageFont":
    candidates = [
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Monaco.dfont",
        "/Library/Fonts/Andale Mono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
        "/Library/Fonts/Courier New Bold.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def pil_to_fb(img: "Image.Image") -> bytes:
    """PIL RGB → raw RGB565 bytes with logical→physical rotation."""
    if img.size != (IMG_W, IMG_H):
        img = img.resize((IMG_W, IMG_H))
    px = img.convert("RGB").load()
    out = bytearray(FB_BYTES)
    for lx in range(IMG_W):
        for ly in range(IMG_H):
            r, g, b = px[lx, ly]
            v = rgb565(r, g, b)
            off = (lx * 222 + (221 - ly)) * 2
            out[off]     = v & 0xFF
            out[off + 1] = v >> 8
    return bytes(out)


def base_canvas(grid: bool = True) -> "Image.Image":
    img = Image.new("RGB", (IMG_W, IMG_H), BG)
    d = ImageDraw.Draw(img)
    if grid:
        for x in range(0, IMG_W, 16):
            d.line([(x, 0), (x, IMG_H)], fill=GREEN_DD, width=1)
        for y in range(0, IMG_H, 16):
            d.line([(0, y), (IMG_W, y)], fill=GREEN_DD, width=1)
    # 3-px scanlines
    for y in range(0, IMG_H, 3):
        d.line([(0, y), (IMG_W, y)], fill=BG_DARK, width=1)
    # corner brackets
    pad = 6
    notch = 12
    for cx, cy in [(pad, pad), (IMG_W - pad - 1, pad),
                   (pad, IMG_H - pad - 1), (IMG_W - pad - 1, IMG_H - pad - 1)]:
        d.line([(cx - notch, cy), (cx + notch, cy)], fill=GREEN_D, width=1)
        d.line([(cx, cy - notch), (cx, cy + notch)], fill=GREEN_D, width=1)
    return img


def render_splash(out_path: Path) -> None:
    img = base_canvas()
    d   = ImageDraw.Draw(img)
    title_font = find_mono_font(56)
    sub_font   = find_mono_font(18)
    body_font  = find_mono_font(16)
    d.text((34, 38),  "SpecPine",                  font=title_font, fill=GREEN)
    d.text((34, 102), "RF INTEL . WI-SPY DBX",     font=sub_font,   fill=GREEN_D)
    d.text((34, 130), "> bridge online",           font=body_font,  fill=AMBER)
    d.text((34, 152), "> waterfall ready",         font=body_font,  fill=AMBER)
    d.text((34, 188), "shall we play a game?",     font=body_font,  fill=CYAN)
    out_path.write_bytes(pil_to_fb(img))
    print(f"  wrote {out_path.relative_to(REPO_ROOT)} ({out_path.stat().st_size} B)")


def render_boot_frame(idx: int, total: int) -> "Image.Image":
    """Frame `idx` of `total`. Progressively fills, ends with READY."""
    img = base_canvas()
    d   = ImageDraw.Draw(img)
    title_font = find_mono_font(48)
    body_font  = find_mono_font(16)
    ready_font = find_mono_font(28)

    d.text((34, 30), "SpecPine", font=title_font, fill=GREEN)

    # Loading bar — fills with each frame.
    bar_x, bar_y, bar_w, bar_h = 34, 110, 412, 14
    d.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], outline=GREEN_D, width=1)
    fill_w = int((bar_w - 4) * (idx / total))
    if fill_w > 0:
        d.rectangle([bar_x + 2, bar_y + 2, bar_x + 2 + fill_w, bar_y + bar_h - 2],
                    fill=GREEN)

    captions = [
        "> probing usb . . .",
        "> bridge initializing . . .",
        "> bridge online",
        "> READY",
    ]
    for i in range(min(idx, len(captions))):
        d.text((34, 138 + i * 18), captions[i], font=body_font,
               fill=AMBER if i < len(captions) - 1 else GREEN)

    if idx >= total:
        d.text((180, 180), "READY", font=ready_font, fill=AMBER)
    return img


def render_animation() -> None:
    total = 4
    for i in range(1, total + 1):
        img = render_boot_frame(i, total)
        out = ANIM_DIR / f"frame_{i}.fb"
        out.write_bytes(pil_to_fb(img))
        print(f"  wrote {out.relative_to(REPO_ROOT)} ({out.stat().st_size} B)")


def main() -> None:
    print(f"Rendering SpecPine framebuffer assets → {OUT_DIR.relative_to(REPO_ROOT)}")
    render_splash(OUT_DIR / "splash.fb")
    render_animation()
    print("Done.")


if __name__ == "__main__":
    main()
