#!/usr/bin/env python3
"""Dump /dev/fb0 as a viewable 24-bit BMP, no external deps (no Pillow).

The Pager's physical framebuffer is 222x480 RGB565, portrait, row-major;
the logical (on-screen) orientation is 480x222 landscape. Mapping mirrors
spectools_waterfall_fb.py's own rotation:
    fb[lx * 222 + (221 - ly)] = pixel at logical (lx, ly)

Used by graphical_waterfall()'s UP+DOWN combo-press screenshot feature
(funcs_main.sh:check_dpad / funcs_scan.sh:graphical_waterfall) to save a
loot artifact the user can actually open, instead of a raw RGB565 dump.

Usage:
    fb_screenshot.py <output.bmp>
"""
from __future__ import annotations

import struct
import sys

FB_PATH = "/dev/fb0"
FB_W, FB_H = 222, 480    # physical (portrait)
IMG_W, IMG_H = 480, 222  # logical (landscape, as the user sees it)


def _rgb565_to_888(v: int) -> tuple[int, int, int]:
    r = (((v >> 11) & 0x1F) * 255) // 31
    g = (((v >> 5) & 0x3F) * 255) // 63
    b = ((v & 0x1F) * 255) // 31
    return r, g, b


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: fb_screenshot.py <output.bmp>", file=sys.stderr)
        return 2
    out_path = argv[1]

    try:
        with open(FB_PATH, "rb") as f:
            data = f.read(FB_W * FB_H * 2)
    except OSError as exc:
        print(f"error reading {FB_PATH}: {exc}", file=sys.stderr)
        return 1
    if len(data) < FB_W * FB_H * 2:
        print(f"short read from {FB_PATH}: got {len(data)} bytes, "
              f"expected {FB_W * FB_H * 2}", file=sys.stderr)
        return 1

    n = FB_W * FB_H
    pix = struct.unpack(f"<{n}H", data)

    # BMP rows are stored bottom-up; logical row IMG_H-1 (bottom) is written first.
    body = bytearray(IMG_W * IMG_H * 3)
    out_row = bytearray(IMG_W * 3)
    body_off = 0
    for ly in range(IMG_H - 1, -1, -1):
        base = FB_W - 1 - ly
        for lx in range(IMG_W):
            r, g, b = _rgb565_to_888(pix[lx * FB_W + base])
            o = lx * 3
            out_row[o] = b
            out_row[o + 1] = g
            out_row[o + 2] = r
        body[body_off:body_off + len(out_row)] = out_row
        body_off += len(out_row)

    image_size = len(body)
    file_size = 54 + image_size
    file_header = b"BM" + struct.pack("<IHHI", file_size, 0, 0, 54)
    dib_header = struct.pack(
        "<IiiHHIIiiII",
        40,        # DIB header size
        IMG_W, IMG_H,
        1,         # color planes
        24,        # bits per pixel
        0,         # no compression
        image_size,
        0, 0,      # x/y pixels-per-meter (unspecified)
        0, 0,      # colors used / important
    )

    try:
        with open(out_path, "wb") as f:
            f.write(file_header)
            f.write(dib_header)
            f.write(body)
    except OSError as exc:
        print(f"error writing {out_path}: {exc}", file=sys.stderr)
        return 1

    print(f"wrote {out_path} ({file_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
