#!/usr/bin/env python3
"""
Graphical spectrum waterfall for the Hak5 WiFi Pineapple Pager.

Writes RGB565 pixels directly to /dev/fb0.
  Physical framebuffer : 222 × 480 pixels (portrait, row-major)
  Logical display      : 480 × 222 pixels (landscape, as user sees)
  Rotation mapping     : fb[lx * 222 + (221 - ly)] = pixel at logical (lx, ly)

Screen layout (logical coordinates, origin = top-left):
  y =   0-14   Title bar
  y =  15-19   Wi-Fi channel tick marks
  y =  20-181  Waterfall  (162 rows of sweep history)
  y = 182-191  dBm colour-scale legend bar
  y = 192-204  Frequency labels
  y = 205-221  Status bar
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from collections import deque
from pathlib import Path

# ── Hardware / layout constants ───────────────────────────────────────────────
FB_PATH   = "/dev/fb0"
VTCON     = "/sys/class/vtconsole/vtcon1/bind"
IMG_W, IMG_H = 480, 222   # logical dimensions
FB_W,  FB_H  = 222, 480   # physical framebuffer dimensions

TITLE_Y0,  TITLE_Y1  =   0,  14
TICK_Y0,   TICK_Y1   =  15,  19
WFALL_Y0,  WFALL_Y1  =  20, 181
LEGEND_Y0, LEGEND_Y1 = 182, 191
FREQ_Y0,   FREQ_Y1   = 192, 204
STATUS_Y0, STATUS_Y1 = 205, 221

WFALL_ROWS = WFALL_Y1 - WFALL_Y0 + 1   # 162

# ── Colour palette (dark/teal aesthetic, matching Pager UI themes) ────────────
C_BG       = (10,  16,  28)   # dark navy background
C_BAR      = (18,  30,  52)   # slightly lighter bar
C_TEAL     = ( 0, 200, 160)   # accent / channel markers
C_WHITE    = (255, 255, 255)
C_GRAY     = (100, 110, 120)
C_CYAN     = ( 0, 200, 220)
C_BLACK    = (  0,   0,   0)

# ── Spectrum heat-map gradient ────────────────────────────────────────────────
# (dBm, (R, G, B)) breakpoints — interpolated linearly between them
_GRADIENT = [
    (-100, (  0,   0,   0)),
    ( -88, (  0,   0, 160)),
    ( -78, (  0, 120, 220)),
    ( -70, (  0, 220,  80)),
    ( -60, (200, 220,   0)),
    ( -50, (255, 140,   0)),
    ( -38, (255,  20,   0)),
    (   0, (255, 180, 220)),  # over-saturated: hot pink/white
]

def _build_lut() -> list[int]:
    """Pre-compute RGB565 for dBm -128..+127. Access with lut[dbm + 128]."""
    lut: list[int] = []
    for dbm in range(-128, 128):
        r, g, b = 0, 0, 0
        if dbm <= _GRADIENT[0][0]:
            r, g, b = _GRADIENT[0][1]
        elif dbm >= _GRADIENT[-1][0]:
            r, g, b = _GRADIENT[-1][1]
        else:
            for i in range(len(_GRADIENT) - 1):
                lo_dbm, lo_col = _GRADIENT[i]
                hi_dbm, hi_col = _GRADIENT[i + 1]
                if lo_dbm <= dbm <= hi_dbm:
                    t = (dbm - lo_dbm) / (hi_dbm - lo_dbm)
                    r = int(lo_col[0] + t * (hi_col[0] - lo_col[0]))
                    g = int(lo_col[1] + t * (hi_col[1] - lo_col[1]))
                    b = int(lo_col[2] + t * (hi_col[2] - lo_col[2]))
                    break
        lut.append(rgb565(r, g, b))
    return lut   # len=256; lut[dbm + 128] for any dbm in [-128, 127]

def _lut_lookup(lut: list[int], dbm: int) -> int:
    return lut[max(0, min(255, dbm + 128))]

# ── Bitmap font (5 × 7 px, 1 bit/pixel) ──────────────────────────────────────
# Each glyph = 7 ints; bit 4 = leftmost column, bit 0 = rightmost
_GLYPHS: dict[str, list[int]] = {
    ' ': [0x00,0x00,0x00,0x00,0x00,0x00,0x00],
    '-': [0x00,0x00,0x00,0x0E,0x00,0x00,0x00],
    '.': [0x00,0x00,0x00,0x00,0x00,0x06,0x06],
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
    'B': [0x1E,0x11,0x11,0x1E,0x11,0x11,0x1E],
    'C': [0x0E,0x11,0x10,0x10,0x10,0x11,0x0E],
    'D': [0x1C,0x12,0x11,0x11,0x11,0x12,0x1C],
    'H': [0x11,0x11,0x11,0x1F,0x11,0x11,0x11],
    'M': [0x11,0x1B,0x15,0x15,0x11,0x11,0x11],
    'P': [0x1E,0x11,0x11,0x1E,0x10,0x10,0x10],
    'S': [0x0E,0x11,0x10,0x0E,0x01,0x11,0x0E],
    'T': [0x1F,0x04,0x04,0x04,0x04,0x04,0x04],
    'W': [0x11,0x11,0x11,0x15,0x1B,0x11,0x11],
    'X': [0x11,0x0A,0x04,0x04,0x04,0x0A,0x11],
    'b': [0x10,0x10,0x1E,0x11,0x11,0x11,0x1E],
    'c': [0x00,0x00,0x0E,0x11,0x10,0x11,0x0E],
    'd': [0x01,0x01,0x0F,0x11,0x11,0x11,0x0F],
    'e': [0x00,0x00,0x0E,0x11,0x1F,0x10,0x0E],
    'h': [0x10,0x10,0x16,0x19,0x11,0x11,0x11],
    'i': [0x04,0x00,0x0C,0x04,0x04,0x04,0x0E],
    'k': [0x10,0x10,0x12,0x14,0x18,0x14,0x12],
    'l': [0x0C,0x04,0x04,0x04,0x04,0x04,0x0E],
    'm': [0x00,0x00,0x11,0x1B,0x15,0x11,0x11],
    'n': [0x00,0x00,0x16,0x19,0x11,0x11,0x11],
    'o': [0x00,0x00,0x0E,0x11,0x11,0x11,0x0E],
    'p': [0x00,0x00,0x1E,0x11,0x1E,0x10,0x10],
    'r': [0x00,0x00,0x16,0x19,0x10,0x10,0x10],
    's': [0x00,0x00,0x0E,0x10,0x0E,0x01,0x0E],
    't': [0x04,0x04,0x1F,0x04,0x04,0x04,0x03],
    'w': [0x00,0x00,0x11,0x11,0x15,0x1B,0x11],
    'x': [0x00,0x00,0x11,0x0A,0x04,0x0A,0x11],
    'y': [0x00,0x00,0x11,0x11,0x0F,0x01,0x0E],
    'z': [0x00,0x00,0x1F,0x02,0x04,0x08,0x1F],
    '|': [0x04,0x04,0x04,0x04,0x04,0x04,0x04],
}

# ── Low-level framebuffer helpers ─────────────────────────────────────────────

def rgb565(r: int, g: int, b: int) -> int:
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)

def _off(lx: int, ly: int) -> int:
    """Byte offset in fb bytearray for logical pixel (lx=0..479, ly=0..221)."""
    return (lx * 222 + (221 - ly)) * 2

def _put(fb: bytearray, lx: int, ly: int, packed: int) -> None:
    off = (lx * 222 + (221 - ly)) * 2
    fb[off]     = packed & 0xFF
    fb[off + 1] = packed >> 8

def _fill(fb: bytearray, x: int, y: int, w: int, h: int, packed: int) -> None:
    """Fill rectangle — iterates over FB rows (lx) for cache efficiency."""
    lo, hi = packed & 0xFF, packed >> 8
    tile = bytes([lo, hi]) * h
    col_lo = 221 - (y + h - 1)
    for lx in range(x, x + w):
        base = (lx * 222 + col_lo) * 2
        fb[base : base + h * 2] = tile

def _glyph(fb: bytearray, ch: str, cx: int, cy: int, packed: int) -> None:
    bits_list = _GLYPHS.get(ch, _GLYPHS[' '])
    for row, bits in enumerate(bits_list):
        for col in range(5):
            if bits & (1 << (4 - col)):
                _put(fb, cx + col, cy + row, packed)

def _text(fb: bytearray, text: str, x: int, y: int, packed: int) -> None:
    """Draw text left-justified at (x, y); glyph stride = 6 px."""
    for i, ch in enumerate(text):
        _glyph(fb, ch, x + i * 6, y, packed)

def _hline(fb: bytearray, x0: int, x1: int, ly: int, packed: int) -> None:
    lo, hi = packed & 0xFF, packed >> 8
    col = 221 - ly
    for lx in range(x0, x1 + 1):
        off = (lx * 222 + col) * 2
        fb[off] = lo;  fb[off + 1] = hi

def _vline_dotted(fb: bytearray, lx: int, y0: int, y1: int, packed: int) -> None:
    """Dotted vertical line (every 2 px) — marks Wi-Fi channel centres."""
    for ly in range(y0, y1 + 1, 2):
        _put(fb, lx, ly, packed)

# ── Wi-Fi 2.4 GHz channel positions ──────────────────────────────────────────

def _freq_to_x(freq_mhz: float, start_mhz: float = 2400.0,
               end_mhz: float = 2483.5) -> int:
    return int((freq_mhz - start_mhz) / (end_mhz - start_mhz) * (IMG_W - 1))

# Non-overlapping channels for 2.4 GHz (MHz centres)
_WIFI_CHANNELS = {1: 2412, 6: 2437, 11: 2462}

# ── Static frame builder (title, legend, freq marks, channel ticks) ───────────

def build_static(fb: bytearray, freq_start_khz: int | None,
                 freq_end_khz: int | None) -> None:
    # Full background
    bg = rgb565(*C_BG)
    _fill(fb, 0, 0, IMG_W, IMG_H, bg)

    # Title bar background
    bar = rgb565(*C_BAR)
    _fill(fb, 0, TITLE_Y0, IMG_W, TITLE_Y1 - TITLE_Y0 + 1, bar)

    # Title text
    white = rgb565(*C_WHITE)
    _text(fb, "SpecTools Waterfall", 4, TITLE_Y0 + 4, white)
    _text(fb, "Wi-Spy DBx", 300, TITLE_Y0 + 4, rgb565(*C_TEAL))

    # Thin divider line under title
    _hline(fb, 0, IMG_W - 1, TITLE_Y1, rgb565(*C_TEAL))

    # Wi-Fi channel tick marks and dotted guide lines
    teal = rgb565(*C_TEAL)
    gray = rgb565(*C_GRAY)
    for ch_num, ch_mhz in _WIFI_CHANNELS.items():
        cx = _freq_to_x(ch_mhz)
        # Tick in tick zone
        _fill(fb, cx - 1, TICK_Y0, 3, TICK_Y1 - TICK_Y0 + 1, teal)
        # Dotted guide through waterfall
        _vline_dotted(fb, cx, WFALL_Y0, WFALL_Y1, gray)
        # Channel number label (below waterfall, in freq zone)
        label = str(ch_num)
        lx_label = max(0, cx - len(label) * 3)
        _text(fb, label, lx_label, FREQ_Y0 + 5, teal)

    # dBm gradient legend bar
    for lx in range(IMG_W):
        frac = lx / (IMG_W - 1)
        dbm = int(-100 + frac * 80)   # maps 0..479 → -100..-20 dBm
        r, g, b = 0, 0, 0
        if dbm <= _GRADIENT[0][0]:
            r, g, b = _GRADIENT[0][1]
        elif dbm >= _GRADIENT[-1][0]:
            r, g, b = _GRADIENT[-1][1]
        else:
            for i in range(len(_GRADIENT) - 1):
                lo_d, lo_c = _GRADIENT[i]
                hi_d, hi_c = _GRADIENT[i + 1]
                if lo_d <= dbm <= hi_d:
                    t = (dbm - lo_d) / (hi_d - lo_d)
                    r = int(lo_c[0] + t * (hi_c[0] - lo_c[0]))
                    g = int(lo_c[1] + t * (hi_c[1] - lo_c[1]))
                    b = int(lo_c[2] + t * (hi_c[2] - lo_c[2]))
                    break
        col = rgb565(r, g, b)
        for ly in range(LEGEND_Y0, LEGEND_Y1 + 1):
            _put(fb, lx, ly, col)

    # dBm tick labels under legend bar
    for dbm_label in (-95, -80, -70, -60, -50, -40):
        lx_label = int((dbm_label - (-100)) / 80 * (IMG_W - 1))
        _text(fb, str(dbm_label), lx_label, LEGEND_Y1 + 1, gray)

    # Freq range labels
    if freq_start_khz and freq_end_khz:
        s_mhz = freq_start_khz // 1000
        e_mhz = freq_end_khz // 1000
        _text(fb, f"{s_mhz}MHz", 0, FREQ_Y0, gray)
        e_str = f"{e_mhz}MHz"
        _text(fb, e_str, IMG_W - len(e_str) * 6 - 2, FREQ_Y0, gray)

    # Status bar background
    _fill(fb, 0, STATUS_Y0, IMG_W, STATUS_Y1 - STATUS_Y0 + 1, bar)
    _hline(fb, 0, IMG_W - 1, STATUS_Y0, rgb565(*C_TEAL))

# ── Sweep → colour row ────────────────────────────────────────────────────────

def sweep_to_row(bins: list[int], lut: list[int]) -> list[int]:
    """Resample rssi_bins to IMG_W and convert to packed RGB565 ints."""
    n = len(bins)
    row: list[int] = []
    if n >= IMG_W:
        chunk = n / IMG_W
        for i in range(IMG_W):
            s = int(i * chunk)
            e = int((i + 1) * chunk)
            seg = bins[s : max(e, s + 1)]
            row.append(_lut_lookup(lut, max(seg)))
    else:
        for i in range(IMG_W):
            idx = int(i * n / IMG_W)
            row.append(_lut_lookup(lut, bins[min(idx, n - 1)]))
    return row

# ── Waterfall + status drawing ────────────────────────────────────────────────

def draw_waterfall(fb: bytearray, ring: deque) -> None:
    """Redraw waterfall region from ring buffer (newest sweep at bottom).

    Iterates by FB row (= frequency bin = lx) to use stride-based addressing,
    avoiding repeated multiplication in the inner loop.
    """
    # Blank empty rows at the top when the ring is not yet full
    if len(ring) < WFALL_ROWS:
        _fill(fb, 0, WFALL_Y0, IMG_W, WFALL_ROWS - len(ring), rgb565(*C_BLACK))

    n = len(ring)
    # Pre-materialise ring as a list for fast index access
    ring_list = list(ring)  # ring_list[0] = newest

    # col for newest sweep in the framebuffer: 221 - WFALL_Y1 = 221 - 181 = 40
    # col for oldest sweep in the framebuffer: 221 - (WFALL_Y1 - (n-1)) = 40 + n - 1
    base_col = 221 - WFALL_Y1   # = 40

    for lx in range(IMG_W):
        # FB row = lx; each step along t increments the FB column by 1.
        # Starting byte offset for this row at base_col:
        off = (lx * 222 + base_col) * 2
        for t in range(n):
            packed = ring_list[t][lx]
            fb[off]     = packed & 0xFF
            fb[off + 1] = packed >> 8
            off += 2   # advance one FB column (same row)


def draw_status(fb: bytearray, sweep_count: int, peak: int | None,
                state: str) -> None:
    bar = rgb565(*C_BAR)
    _fill(fb, 0, STATUS_Y0 + 1, IMG_W, STATUS_Y1 - STATUS_Y0, bar)
    white = rgb565(*C_WHITE)
    teal  = rgb565(*C_TEAL)
    gray  = rgb565(*C_GRAY)

    _text(fb, f"Sweeps:{sweep_count}", 4, STATUS_Y0 + 5, white)
    if peak is not None:
        _text(fb, f"Peak:{peak}dBm", 160, STATUS_Y0 + 5, teal)
    _text(fb, state[:12], 340, STATUS_Y0 + 5, gray)

# ── vtconsole control ─────────────────────────────────────────────────────────

def vtcon_disable() -> None:
    try:
        with open(VTCON, "w") as f:
            f.write("0\n")
    except OSError:
        pass

def vtcon_enable() -> None:
    try:
        with open(VTCON, "w") as f:
            f.write("1\n")
    except OSError:
        pass

# ── Main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Pager framebuffer spectrum waterfall")
    p.add_argument("--events-file", default="/tmp/spectools_bridge_events.jsonl")
    p.add_argument("--follow", action="store_true", help="Tail events file")
    p.add_argument("--poll-interval", type=float, default=0.05)
    p.add_argument("--fps",  type=int, default=6, help="Target display refresh rate")
    p.add_argument("--no-vtcon", action="store_true",
                   help="Skip vtconsole disable (useful for testing)")
    args = p.parse_args(argv)

    # Graceful shutdown on signals
    running = [True]
    def _stop(*_):
        running[0] = False
    signal.signal(signal.SIGINT,  _stop)
    signal.signal(signal.SIGTERM, _stop)

    lut = _build_lut()
    fb  = bytearray(FB_W * FB_H * 2)
    ring: deque[list[int]] = deque(maxlen=WFALL_ROWS)

    freq_start: int | None = None
    freq_end:   int | None = None
    sweep_count = 0
    peak: int | None = None
    state = "INIT"

    build_static(fb, freq_start, freq_end)

    if not args.no_vtcon:
        vtcon_disable()

    def flush_fb() -> None:
        try:
            with open(FB_PATH, "wb") as dev:
                dev.write(fb)
        except OSError as exc:
            # Fall back to LOG-style stderr message so the shell wrapper can log it
            print(f"[fb] write error: {exc}", file=sys.stderr, flush=True)

    flush_fb()

    events_path = Path(args.events_file)
    if not events_path.exists():
        state = "WAITING"
        draw_status(fb, 0, None, state)
        flush_fb()
        while not events_path.exists() and running[0]:
            time.sleep(0.5)

    if not running[0]:
        vtcon_enable()
        return 0

    frame_interval = 1.0 / max(args.fps, 1)
    last_draw = 0.0
    dirty = False

    with events_path.open("r", encoding="utf-8") as fh:
        while running[0]:
            raw = fh.readline()
            if not raw:
                if args.follow:
                    time.sleep(args.poll_interval)
                    # Draw if dirty and frame interval elapsed
                    now = time.time()
                    if dirty and now - last_draw >= frame_interval:
                        draw_waterfall(fb, ring)
                        draw_status(fb, sweep_count, peak, state)
                        flush_fb()
                        last_draw = now
                        dirty = False
                    continue
                break

            stripped = raw.strip()
            if not stripped:
                continue
            try:
                evt = json.loads(stripped)
            except json.JSONDecodeError:
                continue

            etype = evt.get("type")

            if etype == "device_config":
                if evt.get("freq_start_khz") is not None:
                    freq_start = evt["freq_start_khz"]
                if evt.get("freq_end_khz") is not None:
                    freq_end = evt["freq_end_khz"]
                build_static(fb, freq_start, freq_end)
                dirty = True

            elif etype == "sweep" and state != "PAUSED":
                if evt.get("freq_start_khz") is not None:
                    freq_start = evt["freq_start_khz"]
                if evt.get("freq_end_khz") is not None:
                    freq_end = evt["freq_end_khz"]

                bins: list[int] = evt.get("rssi_bins", [])
                if bins:
                    row = sweep_to_row(bins, lut)
                    ring.appendleft(row)   # newest first
                    sweep_count += 1
                    peak = max(bins)
                    state = "SCANNING"
                    dirty = True

            elif etype == "error":
                state = "ERROR"
                dirty = True

            elif etype == "status":
                lvl = evt.get("level", "info")
                if "stall" in str(evt.get("message", "")).lower():
                    state = "STALLED"
                    dirty = True

            now = time.time()
            if dirty and now - last_draw >= frame_interval:
                draw_waterfall(fb, ring)
                draw_status(fb, sweep_count, peak, state)
                flush_fb()
                last_draw = now
                dirty = False

    if not args.no_vtcon:
        vtcon_enable()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
