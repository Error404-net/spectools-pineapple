#!/usr/bin/env python3
"""
SpecPine framebuffer boot splash.

WarGames-flavoured ~2.5 s animation drawn directly to /dev/fb0.
  Physical framebuffer : 222 x 480 (portrait, row-major)
  Logical display      : 480 x 222 (landscape)
  Rotation             : fb[lx * 222 + (221 - ly)] = pixel at logical (lx, ly)

Skips silently if /dev/fb0 is missing or cannot be opened. Re-binds
/sys/class/vtconsole/vtcon1/bind on exit if the path exists.
"""
from __future__ import annotations

import os
import signal
import sys
import time

FB_PATH = "/dev/fb0"
VTCON   = "/sys/class/vtconsole/vtcon1/bind"
IMG_W, IMG_H = 480, 222
FB_W,  FB_H  = 222, 480
FB_BYTES = FB_W * FB_H * 2

# WarGames CRT phosphor green on near-black
C_BG     = (0,   8,   4)
C_GREEN  = (0,   220, 100)
C_DIM    = (0,   80,  40)
C_GRID   = (0,   40,  20)
C_AMBER  = (255, 180, 0)
C_WHITE  = (220, 255, 220)


def rgb565(r: int, g: int, b: int) -> int:
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def _put(fb: bytearray, lx: int, ly: int, packed: int) -> None:
    if 0 <= lx < IMG_W and 0 <= ly < IMG_H:
        off = (lx * 222 + (221 - ly)) * 2
        fb[off]     = packed & 0xFF
        fb[off + 1] = packed >> 8


def _fill(fb: bytearray, x: int, y: int, w: int, h: int, packed: int) -> None:
    lo, hi = packed & 0xFF, packed >> 8
    h_clamped = max(0, min(h, IMG_H - y))
    if h_clamped <= 0:
        return
    tile = bytes([lo, hi]) * h_clamped
    col_lo = 221 - (y + h_clamped - 1)
    for lx in range(max(0, x), min(IMG_W, x + w)):
        base = (lx * 222 + col_lo) * 2
        fb[base : base + h_clamped * 2] = tile


# 5x7 bitmap font — only the characters we use. Bit 4 = leftmost.
_GLYPHS = {
    ' ': [0x00,0x00,0x00,0x00,0x00,0x00,0x00],
    '.': [0x00,0x00,0x00,0x00,0x00,0x06,0x06],
    '-': [0x00,0x00,0x00,0x0E,0x00,0x00,0x00],
    '/': [0x01,0x02,0x02,0x04,0x08,0x08,0x10],
    'A': [0x0E,0x11,0x11,0x1F,0x11,0x11,0x11],
    'B': [0x1E,0x11,0x11,0x1E,0x11,0x11,0x1E],
    'C': [0x0E,0x11,0x10,0x10,0x10,0x11,0x0E],
    'D': [0x1C,0x12,0x11,0x11,0x11,0x12,0x1C],
    'E': [0x1F,0x10,0x10,0x1E,0x10,0x10,0x1F],
    'F': [0x1F,0x10,0x10,0x1E,0x10,0x10,0x10],
    'G': [0x0E,0x11,0x10,0x17,0x11,0x11,0x0E],
    'H': [0x11,0x11,0x11,0x1F,0x11,0x11,0x11],
    'I': [0x0E,0x04,0x04,0x04,0x04,0x04,0x0E],
    'L': [0x10,0x10,0x10,0x10,0x10,0x10,0x1F],
    'M': [0x11,0x1B,0x15,0x15,0x11,0x11,0x11],
    'N': [0x11,0x19,0x15,0x13,0x11,0x11,0x11],
    'O': [0x0E,0x11,0x11,0x11,0x11,0x11,0x0E],
    'P': [0x1E,0x11,0x11,0x1E,0x10,0x10,0x10],
    'R': [0x1E,0x11,0x11,0x1E,0x14,0x12,0x11],
    'S': [0x0E,0x11,0x10,0x0E,0x01,0x11,0x0E],
    'T': [0x1F,0x04,0x04,0x04,0x04,0x04,0x04],
    'U': [0x11,0x11,0x11,0x11,0x11,0x11,0x0E],
    'V': [0x11,0x11,0x11,0x11,0x11,0x0A,0x04],
    'W': [0x11,0x11,0x11,0x15,0x15,0x1B,0x11],
    'X': [0x11,0x0A,0x04,0x04,0x04,0x0A,0x11],
    'Y': [0x11,0x11,0x0A,0x04,0x04,0x04,0x04],
    '0': [0x0E,0x11,0x13,0x15,0x19,0x11,0x0E],
    '1': [0x04,0x0C,0x04,0x04,0x04,0x04,0x0E],
    '2': [0x0E,0x11,0x01,0x06,0x08,0x10,0x1F],
    '3': [0x1F,0x02,0x04,0x02,0x01,0x11,0x0E],
    '4': [0x02,0x06,0x0A,0x12,0x1F,0x02,0x02],
    '5': [0x1F,0x10,0x1E,0x01,0x01,0x11,0x0E],
    '6': [0x06,0x08,0x10,0x1E,0x11,0x11,0x0E],
    '7': [0x1F,0x01,0x02,0x04,0x08,0x08,0x08],
    '8': [0x0E,0x11,0x11,0x0E,0x11,0x11,0x0E],
    '9': [0x0E,0x11,0x11,0x0F,0x01,0x01,0x06],
    ':': [0x00,0x06,0x06,0x00,0x06,0x06,0x00],
    '?': [0x0E,0x11,0x01,0x06,0x04,0x00,0x04],
    '|': [0x04,0x04,0x04,0x04,0x04,0x04,0x04],
}


def _glyph(fb: bytearray, ch: str, cx: int, cy: int, packed: int, scale: int = 1) -> None:
    bits_list = _GLYPHS.get(ch.upper(), _GLYPHS[' '])
    for row, bits in enumerate(bits_list):
        for col in range(5):
            if bits & (1 << (4 - col)):
                _fill(fb, cx + col * scale, cy + row * scale, scale, scale, packed)


def _text(fb: bytearray, s: str, cx: int, cy: int, packed: int, scale: int = 1) -> None:
    for ch in s:
        _glyph(fb, ch, cx, cy, packed, scale)
        cx += (5 + 1) * scale


def _grid(fb: bytearray, packed: int, step: int = 16) -> None:
    for x in range(0, IMG_W, step):
        for y in range(0, IMG_H):
            _put(fb, x, y, packed)
    for y in range(0, IMG_H, step):
        for x in range(0, IMG_W):
            _put(fb, x, y, packed)


def _border(fb: bytearray, packed: int) -> None:
    _fill(fb, 0, 0, IMG_W, 1, packed)
    _fill(fb, 0, IMG_H - 1, IMG_W, 1, packed)
    _fill(fb, 0, 0, 1, IMG_H, packed)
    _fill(fb, IMG_W - 1, 0, 1, IMG_H, packed)


def _restore_vtcon() -> None:
    if os.path.exists(VTCON):
        try:
            with open(VTCON, "w") as f:
                f.write("1")
        except OSError:
            pass


def _disable_vtcon() -> None:
    if os.path.exists(VTCON):
        try:
            with open(VTCON, "w") as f:
                f.write("0")
        except OSError:
            pass


def main() -> int:
    if not os.path.exists(FB_PATH):
        return 0   # silent skip

    try:
        fb_file = open(FB_PATH, "r+b", buffering=0)
    except OSError:
        return 0

    fb = bytearray(FB_BYTES)

    def _cleanup(*_a):
        try:
            fb_file.close()
        except OSError:
            pass
        _restore_vtcon()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _cleanup)
    signal.signal(signal.SIGINT,  _cleanup)

    _disable_vtcon()

    # Prefer pre-rendered theme frames if present (much faster on the MIPS
    # CPU than the inline drawing fallback below).
    here = os.path.dirname(os.path.abspath(__file__))
    theme_dir = os.path.join(here, "..", "data", "theme")
    anim_dir  = os.path.join(theme_dir, "boot_animation")
    anim_frames = sorted(
        os.path.join(anim_dir, f)
        for f in (os.listdir(anim_dir) if os.path.isdir(anim_dir) else [])
        if f.startswith("frame_") and f.endswith(".fb")
    )
    if anim_frames:
        for f in anim_frames:
            try:
                with open(f, "rb") as fh:
                    data = fh.read()
                if len(data) == FB_BYTES:
                    fb_file.seek(0); fb_file.write(data)
                    time.sleep(0.45)
            except OSError:
                pass
        # Linger briefly on the last frame.
        time.sleep(0.4)
        fb_file.close()
        _restore_vtcon()
        return 0

    # ── Fallback: inline drawing (original behaviour) ──
    bg = rgb565(*C_BG)
    grid = rgb565(*C_GRID)
    dim = rgb565(*C_DIM)
    green = rgb565(*C_GREEN)
    amber = rgb565(*C_AMBER)
    white = rgb565(*C_WHITE)

    # Frame 1: blank + grid + border (cold start)
    for i in range(FB_BYTES):
        fb[i] = 0
    _fill(fb, 0, 0, IMG_W, IMG_H, bg)
    _grid(fb, grid, step=16)
    _border(fb, dim)
    fb_file.seek(0); fb_file.write(bytes(fb))
    time.sleep(0.35)

    # Frame 2: title appears
    _text(fb, "SPECPINE", 156, 70, green, scale=4)
    fb_file.seek(0); fb_file.write(bytes(fb))
    time.sleep(0.45)

    # Frame 3: subtitle + loading bar frame
    _text(fb, "RF INTEL  WI-SPY DBX", 142, 116, dim, scale=2)
    bar_x, bar_y, bar_w, bar_h = 80, 150, 320, 12
    _fill(fb, bar_x, bar_y, bar_w, 1, dim)
    _fill(fb, bar_x, bar_y + bar_h - 1, bar_w, 1, dim)
    _fill(fb, bar_x, bar_y, 1, bar_h, dim)
    _fill(fb, bar_x + bar_w - 1, bar_y, 1, bar_h, dim)
    fb_file.seek(0); fb_file.write(bytes(fb))
    time.sleep(0.25)

    # Frame 4: progress fills
    steps = 8
    for s in range(1, steps + 1):
        fill_w = int((bar_w - 4) * s / steps)
        _fill(fb, bar_x + 2, bar_y + 2, fill_w, bar_h - 4, green)
        fb_file.seek(0); fb_file.write(bytes(fb))
        time.sleep(0.06)

    # Frame 5: READY
    _text(fb, "READY", 200, 184, amber, scale=2)
    fb_file.seek(0); fb_file.write(bytes(fb))
    time.sleep(0.35)

    # Frame 6: brief flash to white then back
    _text(fb, "READY", 200, 184, white, scale=2)
    fb_file.seek(0); fb_file.write(bytes(fb))
    time.sleep(0.10)
    _text(fb, "READY", 200, 184, amber, scale=2)
    fb_file.seek(0); fb_file.write(bytes(fb))
    time.sleep(0.30)

    fb_file.close()
    _restore_vtcon()
    return 0


if __name__ == "__main__":
    if "--dry-run" in sys.argv:
        # Verify glyph table covers the chars we render. Useful for CI.
        chars = set("SPECPINE RF INTEL  WI-SPY DBX READY")
        missing = [c for c in chars if c.upper() not in _GLYPHS]
        if missing:
            print(f"missing glyphs: {missing}")
            sys.exit(1)
        print("dry-run OK")
        sys.exit(0)
    raise SystemExit(main())
