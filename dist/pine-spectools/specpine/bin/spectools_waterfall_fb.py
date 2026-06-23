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
import atexit
import json
import os
import signal
import sys
import time
from collections import deque
from pathlib import Path

# ── Hardware / layout constants ───────────────────────────────────────────────
FB_PATH   = "/dev/fb0"
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

def _lut_lookup(lut: list[int], dbm: float) -> int:
    # rssi_bins from spectool_raw / mock_sweep are floats (e.g. -78.3); the LUT
    # is indexed by integer dBm, so round before indexing. Without this cast,
    # any non-integer bin value raises "TypeError: list indices must be
    # integers or slices, not float" the moment real sweep data arrives --
    # the ASCII renderer (spectools_waterfall_pager.py) has the equivalent
    # int(round(...)) cast for the same reason.
    return lut[max(0, min(255, int(round(dbm)) + 128))]

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

# ── Wi-Fi channel positions (2.4 GHz and 5 GHz) ──────────────────────────────
# The Wi-Spy DBx is a single-radio swept analyzer — it sweeps one fixed range
# at a time (see band_to_range_index() in funcs_main.sh / wispy_hw_dbx.c's
# wispydbx_add_supportedranges()). Whichever range is active arrives here via
# the "device_config" event's freq_start_khz/freq_end_khz, so the tick marks
# below must be computed against the *actual* current sweep range, not a
# hardcoded 2.4GHz assumption — otherwise 5GHz sweeps render with channel
# ticks computed against the wrong axis (or none visible at all).

def _freq_to_x(freq_mhz: float, start_mhz: float = 2400.0,
               end_mhz: float = 2483.5) -> int:
    if end_mhz <= start_mhz:
        return 0
    return int((freq_mhz - start_mhz) / (end_mhz - start_mhz) * (IMG_W - 1))

# Non-overlapping channels for 2.4 GHz (MHz centres)
_WIFI_CHANNELS_24 = {1: 2412, 6: 2437, 11: 2462}
# UNII-1 / UNII-3 channels for 5 GHz (MHz centres) — matches the marker set
# already used by the ASCII renderer (spectools_waterfall_pager.py _CH_5G)
_WIFI_CHANNELS_5 = {
    36: 5180, 40: 5200, 44: 5220, 48: 5240,
    149: 5745, 153: 5765, 157: 5785, 161: 5805,
}

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

    # Wi-Fi channel tick marks and dotted guide lines.
    # Select the 2.4GHz or 5GHz marker set based on the *actual* current
    # sweep range (device_config/sweep events), not a hardcoded assumption --
    # mirrors spectools_waterfall_pager.py's freq_header() ch_map selection.
    teal = rgb565(*C_TEAL)
    gray = rgb565(*C_GRAY)
    start_mhz = freq_start_khz / 1000.0 if freq_start_khz else 2400.0
    end_mhz = freq_end_khz / 1000.0 if freq_end_khz else 2483.5
    channels = _WIFI_CHANNELS_5 if (freq_start_khz and freq_start_khz >= 3_000_000) \
        else _WIFI_CHANNELS_24
    for ch_num, ch_mhz in channels.items():
        if not (start_mhz <= ch_mhz <= end_mhz):
            continue
        cx = _freq_to_x(ch_mhz, start_mhz, end_mhz)
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

def draw_new_sweep(fb: bytearray, row: list[int], ring_len: int) -> None:
    """Scroll the waterfall right by one column and insert `row` (the newest
    sweep) at the left edge of the waterfall region.

    This replaces what used to be a full O(IMG_W * WFALL_ROWS) Python-level
    rebuild on *every* frame (up to 480*162 = 77,760 plain-Python iterations)
    with O(IMG_W) bytearray slice shifts -- each shift is a single C-level
    memmove instead of an inner Python loop. That rebuild-every-frame cost
    was the dominant reason the renderer measured ~1.5-2s/frame on this
    device's MIPS CPU. Call this once per incoming sweep (cheap, unthrottled);
    `flush_fb()`/`draw_status()` remain the only fps-gated, I/O-bound steps.

    `ring_len` is the ring's length *after* appending this sweep (the caller
    uses a deque(maxlen=WFALL_ROWS), so this naturally caps at WFALL_ROWS
    once the ring is full and older columns silently scroll off the right
    edge of the waterfall).
    """
    base_col = 221 - WFALL_Y1   # = 40, newest column within each physical row
    n_after = min(ring_len, WFALL_ROWS)
    shift_n = n_after - 1        # existing columns that need to shift right by one

    for lx in range(IMG_W):
        off = (lx * FB_W + base_col) * 2
        if shift_n > 0:
            fb[off + 2 : off + 2 + shift_n * 2] = fb[off : off + shift_n * 2]
        packed = row[lx]
        fb[off]     = packed & 0xFF
        fb[off + 1] = packed >> 8


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

# ── Pager UI suspend/resume ───────────────────────────────────────────────────
# The Pager's /pineapple/pineapple process owns /dev/fb0 and repaints every
# ~750ms.  SIGSTOP it before writing frames; SIGCONT on exit to restore the UI.
# evtest reads /dev/input/event0 directly from the kernel — button input
# continues to work while pineapple is stopped.

def _pineapple_pid() -> int | None:
    import subprocess
    for cmd in (["pidof", "pineapple"], ["pgrep", "-x", "pineapple"],
                ["pgrep", "-f", "/pineapple/pineapple"]):
        try:
            out = subprocess.check_output(cmd, text=True).strip()
            first = out.split()[0]
            return int(first)
        except Exception:
            continue
    # Fallback: pidof/pgrep may be missing from PATH, or behave differently,
    # depending on the process tree the renderer was launched from (real menu
    # launch vs. an interactive SSH shell). Scan /proc directly as a last
    # resort instead of silently giving up.
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                with open(f"/proc/{entry}/comm", "r") as f:
                    comm = f.read().strip()
            except OSError:
                continue
            if comm == "pineapple":
                return int(entry)
    except OSError:
        pass
    return None

def pineapple_stop() -> None:
    pid = _pineapple_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGSTOP)
            print(f"[fb] pineapple (pid {pid}) SIGSTOPped", file=sys.stderr)
        except OSError as e:
            print(f"[fb] pineapple (pid {pid}) SIGSTOP failed: {e}", file=sys.stderr)
    else:
        print("[fb] WARNING: pineapple process not found via pidof/pgrep/proc scan -- "
              "the native UI may keep repainting over our frames and nothing will "
              "appear to change on screen", file=sys.stderr)

def pineapple_cont() -> None:
    pid = _pineapple_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGCONT)
            print(f"[fb] pineapple (pid {pid}) SIGCONTinued", file=sys.stderr)
        except OSError as e:
            print(f"[fb] pineapple (pid {pid}) SIGCONT failed: {e}", file=sys.stderr)

# ── Main ──────────────────────────────────────────────────────────────────────

def _run_session(events_path: Path, args, lut: list[int], fb: bytearray,
                  flush_fb, running: list[bool], reload_flag: list[bool]) -> None:
    """One band/session's worth of rendering: wait for the events file, then
    tail it and incrementally draw sweeps until told to stop (`running[0]`
    goes False) or reload (`reload_flag[0]` goes True, e.g. a live band
    switch from the LEFT/RIGHT buttons -- see check_dpad()/graphical_waterfall()
    in funcs_main.sh/funcs_scan.sh). Returning here without exiting the
    process lets main() loop back and pick up a freshly-restarted bridge's
    events file without paying this device's ~8-10s Python startup cost on
    every band switch.
    """
    ring: deque[list[int]] = deque(maxlen=WFALL_ROWS)
    freq_start: int | None = None
    freq_end:   int | None = None
    sweep_count = 0
    peak: int | None = None
    state = "INIT"

    build_static(fb, freq_start, freq_end)
    _fill(fb, 0, WFALL_Y0, IMG_W, WFALL_ROWS, rgb565(*C_BLACK))
    draw_status(fb, sweep_count, peak, state)
    flush_fb(fb)

    if not events_path.exists():
        state = "WAITING"
        draw_status(fb, sweep_count, peak, state)
        flush_fb(fb)
        while not events_path.exists() and running[0] and not reload_flag[0]:
            time.sleep(0.5)

    if not running[0] or reload_flag[0]:
        return

    frame_interval = 1.0 / max(args.fps, 1)
    last_draw = 0.0
    dirty = False

    with events_path.open("r", encoding="utf-8") as fh:
        while running[0] and not reload_flag[0]:
            raw = fh.readline()
            if not raw:
                if args.follow:
                    time.sleep(args.poll_interval)
                    now = time.time()
                    if dirty and now - last_draw >= frame_interval:
                        draw_status(fb, sweep_count, peak, state)
                        flush_fb(fb)
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
                _fill(fb, 0, WFALL_Y0, IMG_W, WFALL_ROWS, rgb565(*C_BLACK))
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
                    draw_new_sweep(fb, row, len(ring))   # cheap; unthrottled
                    sweep_count += 1
                    peak = max(bins)
                    state = "SCANNING"
                    dirty = True

            elif etype == "error":
                state = "ERROR"
                dirty = True

            elif etype == "status":
                if "stall" in str(evt.get("message", "")).lower():
                    state = "STALLED"
                    dirty = True

            now = time.time()
            if dirty and now - last_draw >= frame_interval:
                draw_status(fb, sweep_count, peak, state)
                flush_fb(fb)
                last_draw = now
                dirty = False


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Pager framebuffer spectrum waterfall")
    p.add_argument("--events-file", default="/tmp/spectools_bridge_events.jsonl")
    p.add_argument("--follow", action="store_true", help="Tail events file")
    p.add_argument("--poll-interval", type=float, default=0.05)
    p.add_argument("--fps",  type=int, default=6, help="Target display refresh rate")
    p.add_argument("--no-ui-stop", action="store_true",
                   help="Skip SIGSTOP of pineapple UI (useful for testing)")
    args = p.parse_args(argv)

    # Graceful shutdown on signals — always resume the Pager UI on exit
    running = [True]
    def _stop(*_):
        running[0] = False
        if not args.no_ui_stop:
            pineapple_cont()
    signal.signal(signal.SIGINT,  _stop)
    signal.signal(signal.SIGTERM, _stop)

    # SIGUSR1 = live band switch (sent by graphical_waterfall() after it has
    # restarted the bridge with a new --range). Doesn't exit the interpreter —
    # just unwinds the current _run_session() so main() can start a fresh one
    # against the new events file, avoiding this device's ~8-10s Python/import
    # startup cost on every LEFT/RIGHT band switch.
    reload_flag = [False]
    def _reload(*_):
        reload_flag[0] = True
    signal.signal(signal.SIGUSR1, _reload)

    lut = _build_lut()
    fb  = bytearray(FB_W * FB_H * 2)

    if not args.no_ui_stop:
        pineapple_stop()
        # Belt-and-suspenders: atexit fires on *any* interpreter shutdown path —
        # normal return, sys.exit(), or an uncaught exception unwinding out of
        # main() — not just the SIGINT/SIGTERM cases the signal handler above
        # covers. pineapple_cont() is idempotent (SIGCONT to an already-running
        # process is a no-op), so registering it here is safe even though the
        # explicit calls below will often also fire. This does NOT protect
        # against SIGKILL/-9 or OOM-kill, since the process never gets to run
        # exit handlers in that case — that's covered by the independent
        # pineapple_ensure_running() shell-level check in funcs_main.sh, called
        # from payload.sh's cleanup trap and from graphical_waterfall().
        atexit.register(pineapple_cont)

    def flush_fb(buf: bytearray) -> None:
        try:
            with open(FB_PATH, "r+b", buffering=0) as dev:
                dev.seek(0)
                dev.write(buf)
        except OSError as exc:
            # Fall back to LOG-style stderr message so the shell wrapper can log it
            print(f"[fb] write error: {exc}", file=sys.stderr, flush=True)

    events_path = Path(args.events_file)

    while running[0]:
        reload_flag[0] = False
        _run_session(events_path, args, lut, fb, flush_fb, running, reload_flag)

    if not args.no_ui_stop:
        pineapple_cont()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
