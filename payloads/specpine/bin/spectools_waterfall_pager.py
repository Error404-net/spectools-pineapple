#!/usr/bin/env python3
"""ASCII block-glyph waterfall renderer for the Hak5 WiFi Pineapple Pager.

Writes colored block characters (░▒▓█) directly to /dev/fb0 with per-character
dBm-based color, matching the graphical waterfall's gradient in a WarGames
phosphor aesthetic. Reuses all framebuffer primitives from spectools_waterfall_fb.py.

Layout (480x222 logical landscape):
  y =   0-27   Header bar (SPECPINE / freq info)
  y =  28-201  Scrolling block-glyph waterfall (174px = 11 rows of 15px)
  y = 202-221  Footer bar (controls hint)
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spectools_waterfall_fb as wf

# ── Extra glyphs (same set as specpine_hud.py) ────────────────────────────────
wf._GLYPHS.update({
    'A': [0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    'E': [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F],
    'F': [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10],
    'G': [0x0F, 0x10, 0x10, 0x17, 0x11, 0x11, 0x0E],
    'I': [0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E],
    'N': [0x11, 0x19, 0x15, 0x15, 0x13, 0x11, 0x11],
    'O': [0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    'R': [0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11],
    'U': [0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    '/': [0x01, 0x02, 0x04, 0x08, 0x10, 0x00, 0x00],
    ':': [0x00, 0x06, 0x06, 0x00, 0x06, 0x06, 0x00],
    # Block shading characters (keyed by control chars to avoid collision)
    '\x01': [0x15, 0x00, 0x15, 0x00, 0x15, 0x00, 0x15],  # ░ sparse checkerboard
    '\x02': [0x1F, 0x00, 0x1F, 0x00, 0x1F, 0x00, 0x1F],  # ▒ horizontal bars
    '\x03': [0x1F, 0x15, 0x1F, 0x15, 0x1F, 0x15, 0x1F],  # ▓ dense with gaps
    '\x04': [0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F],  # █ solid block
})

# ── WarGames palette ──────────────────────────────────────────────────────────
_BG    = wf.rgb565(  0,   8,   4)
_BAR   = wf.rgb565(  0,  20,  10)
_GREEN = wf.rgb565(  0, 220, 100)
_DIM   = wf.rgb565(  0,  80,  40)
_GRID  = wf.rgb565(  0,  35,  18)
_AMBER = wf.rgb565(255, 180,   0)

# ── Layout ────────────────────────────────────────────────────────────────────
HEADER_H = 28
FOOTER_H = 20
WFALL_Y0 = HEADER_H                          # 28
WFALL_Y1 = wf.IMG_H - FOOTER_H - 1          # 201
WFALL_H  = WFALL_Y1 - WFALL_Y0 + 1          # 174

CHAR_SX = 11    # 10px glyph + 1px gap (2x scaled 5-wide glyph)
CHAR_SY = 15    # 14px glyph + 1px gap (2x scaled 7-tall glyph)

CHARS_WIDE   = wf.IMG_W // CHAR_SX           # 43
ROWS_VISIBLE = WFALL_H  // CHAR_SY           # 11

# ── Per-dBm → (block char, RGB565) levels ────────────────────────────────────
# Visual progression: invisible → dim green dots → medium green bars →
#                     bright green dense → amber solid
_LEVELS: list[tuple[float, str, int]] = [
    (-90.0, ' ',    wf.rgb565(  0,   8,   4)),  # noise floor: invisible
    (-80.0, '\x01', wf.rgb565(  0,  40,  20)),  # very low: dim green dots
    (-70.0, '\x01', wf.rgb565(  0,  90,  45)),  # low: medium dim green dots
    (-60.0, '\x02', wf.rgb565(  0, 170,  75)),  # medium-low: cyan-green bars
    (-50.0, '\x02', wf.rgb565(  0, 220, 100)),  # medium: bright green bars
    (-38.0, '\x03', wf.rgb565(200, 200,   0)),  # strong: amber dense
    (999.0, '\x04', wf.rgb565(255, 160,   0)),  # very strong: hot amber solid
]


def _dbm_to_char_color(dbm: float) -> tuple[str, int]:
    for max_d, ch, col in _LEVELS:
        if dbm <= max_d:
            return ch, col
    return _LEVELS[-1][1], _LEVELS[-1][2]


def _glyph2x(fb: bytearray, ch: str, cx: int, cy: int, color: int) -> None:
    """Render glyph at 2× scale: each pixel → 2×2 block."""
    bits_list = wf._GLYPHS.get(ch, wf._GLYPHS[' '])
    for row, bits in enumerate(bits_list):
        for col in range(5):
            if bits & (1 << (4 - col)):
                px, py = cx + col * 2, cy + row * 2
                wf._put(fb, px,     py,     color)
                wf._put(fb, px + 1, py,     color)
                wf._put(fb, px,     py + 1, color)
                wf._put(fb, px + 1, py + 1, color)


def _text2x(fb: bytearray, text: str, x: int, y: int, color: int) -> None:
    for i, ch in enumerate(text):
        _glyph2x(fb, ch.upper(), x + i * 12, y, color)


def _draw_static(fb: bytearray, freq_start_khz: int | None,
                 freq_end_khz: int | None, band: str) -> None:
    """Draw WarGames-style header/footer; leave waterfall area untouched."""
    # Background + grid
    wf._fill(fb, 0, 0, wf.IMG_W, wf.IMG_H, _BG)
    for gy in range(0, wf.IMG_H, 24):
        wf._fill(fb, 0, gy, wf.IMG_W, 1, _GRID)

    # 1-px border
    wf._fill(fb, 0, 0, wf.IMG_W, 1, _DIM)
    wf._fill(fb, 0, wf.IMG_H - 1, wf.IMG_W, 1, _DIM)

    # Header bar
    wf._fill(fb, 0, 0, wf.IMG_W, HEADER_H, _BAR)
    _text2x(fb, "SPECPINE", 8, 7, _AMBER)
    freq_label = ""
    if freq_start_khz and freq_end_khz:
        freq_label = f"{freq_start_khz // 1000}-{freq_end_khz // 1000}MHZ"
    elif band:
        freq_label = f"{band}GHZ"
    if freq_label:
        _text2x(fb, freq_label, wf.IMG_W - len(freq_label) * 12 - 8, 7, _DIM)
    wf._hline(fb, 0, wf.IMG_W - 1, HEADER_H - 1, _GREEN)
    wf._hline(fb, 0, wf.IMG_W - 1, HEADER_H - 2, _GREEN)

    # Waterfall area: solid background
    wf._fill(fb, 0, WFALL_Y0, wf.IMG_W, WFALL_H, _BG)

    # Footer bar
    wf._fill(fb, 0, WFALL_Y1 + 1, wf.IMG_W, FOOTER_H, _BAR)
    wf._hline(fb, 0, wf.IMG_W - 1, WFALL_Y1 + 1, _GREEN)
    wf._hline(fb, 0, wf.IMG_W - 1, WFALL_Y1 + 2, _GREEN)
    hint = "HOLD OK:STOP  HOLD BACK:EXIT"
    _text2x(fb, hint, (wf.IMG_W - len(hint) * 12) // 2, WFALL_Y1 + 5, _DIM)


def _draw_status(fb: bytearray, sweep_count: int, peak: float | None) -> None:
    """Update header right-side info (sweep count + peak dBm)."""
    wf._fill(fb, wf.IMG_W // 2, 0, wf.IMG_W // 2, HEADER_H - 2, _BAR)
    if sweep_count > 0:
        info = f"SW:{sweep_count}"
        if peak is not None:
            info += f"  PK:{int(round(peak))}DB"
        _text2x(fb, info, wf.IMG_W - len(info) * 12 - 8, 7, _DIM)


def _scroll_up(fb: bytearray) -> None:
    """Shift the waterfall area up by CHAR_SY logical pixels (insert new row at bottom).

    In the physical FB (portrait 222×480), logical y maps to physical col via
    phys_col = 221 - ly. Moving data UP (ly decreasing) means physical col
    increases by CHAR_SY. We copy the existing waterfall data rightward in
    physical col space, leaving the lowest CHAR_SY physical cols free for the
    new row.

    Physical waterfall bounds:
      base_col = 221 - WFALL_Y1 = 20  (newest row, bottom of logical display)
      top_col  = 221 - WFALL_Y0 = 193 (oldest row, top of logical display)

    n_keep cols: WFALL_H - CHAR_SY = 159 — the surviving rows after one shift.
    Source: phys cols [base_col .. base_col + n_keep - 1] = [20 .. 178]
    Dest:   phys cols [base_col + CHAR_SY .. base_col + CHAR_SY + n_keep - 1] = [35 .. 193]
    """
    base_col = 221 - WFALL_Y1    # 20
    n_keep   = WFALL_H - CHAR_SY  # 159
    stride   = wf.FB_W            # 222 physical columns per logical row
    for lx in range(wf.IMG_W):
        off = (lx * stride + base_col) * 2
        n   = n_keep * 2
        fb[off + CHAR_SY * 2 : off + CHAR_SY * 2 + n] = fb[off : off + n]


def _draw_new_row(fb: bytearray, sampled: list[float]) -> None:
    """Clear the bottom CHAR_SY rows and render the new sweep's glyph row."""
    new_y0 = WFALL_Y1 - CHAR_SY + 1   # 187
    wf._fill(fb, 0, new_y0, wf.IMG_W, CHAR_SY, _BG)
    for i, dbm in enumerate(sampled):
        ch, col = _dbm_to_char_color(dbm)
        if ch == ' ':
            continue
        cx = 1 + i * CHAR_SX
        if cx + 10 > wf.IMG_W:
            break
        _glyph2x(fb, ch, cx, new_y0, col)


def _resample(bins: list[float], n: int) -> list[float]:
    if not bins:
        return [float('-inf')] * n
    nb = len(bins)
    if nb == n:
        return list(bins)
    chunk = nb / n
    if nb > n:
        return [max(bins[int(i * chunk) : max(int((i + 1) * chunk), int(i * chunk) + 1)])
                for i in range(n)]
    return [bins[min(int(i * nb / n), nb - 1)] for i in range(n)]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Pager ASCII block-glyph waterfall")
    p.add_argument("--events-file", default="/tmp/spectools_bridge_events.jsonl")
    p.add_argument("--follow", action="store_true")
    p.add_argument("--poll-interval", type=float, default=0.05)
    p.add_argument("--fps",  type=int, default=6)
    p.add_argument("--btn-file", default="/tmp/specpine_btn_evt")
    p.add_argument("--no-ui-stop", action="store_true")
    args = p.parse_args(argv)

    running = [True]

    def _stop(*_):
        running[0] = False
        if not args.no_ui_stop:
            wf.pineapple_cont()

    signal.signal(signal.SIGINT,  _stop)
    signal.signal(signal.SIGTERM, _stop)

    if not args.no_ui_stop:
        wf.pineapple_stop()
        atexit.register(wf.pineapple_cont)

    fb = bytearray(wf.FB_W * wf.FB_H * 2)

    def flush() -> None:
        try:
            with open(wf.FB_PATH, "r+b", buffering=0) as dev:
                dev.seek(0)
                dev.write(fb)
        except OSError as exc:
            print(f"[pager] fb write: {exc}", file=sys.stderr, flush=True)

    btn_path = Path(args.btn_file)
    events_path = Path(args.events_file)

    freq_start: int | None = None
    freq_end:   int | None = None
    band = ""
    sweep_count = 0
    peak: float | None = None
    frame_interval = 1.0 / max(args.fps, 1)
    last_draw = 0.0
    dirty = False

    _draw_static(fb, freq_start, freq_end, band)
    flush()

    if not events_path.exists():
        _text2x(fb, "WAITING FOR DEVICE...", 8, WFALL_Y0 + 8, _DIM)
        flush()
        while not events_path.exists() and running[0]:
            # Check for stop via btn_file
            try:
                if "stop" in btn_path.read_text():
                    running[0] = False
            except OSError:
                pass
            time.sleep(0.5)

    if not running[0]:
        return 0

    with events_path.open("r", encoding="utf-8") as fh:
        while running[0]:
            raw = fh.readline()
            if not raw:
                if args.follow:
                    time.sleep(args.poll_interval)
                    # Check stop flag
                    try:
                        if "stop" in btn_path.read_text():
                            running[0] = False
                            break
                    except OSError:
                        pass
                    now = time.time()
                    if dirty and now - last_draw >= frame_interval:
                        _draw_status(fb, sweep_count, peak)
                        flush()
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
                _draw_static(fb, freq_start, freq_end, band)
                dirty = True

            elif etype == "sweep":
                if evt.get("freq_start_khz") is not None:
                    freq_start = evt["freq_start_khz"]
                if evt.get("freq_end_khz") is not None:
                    freq_end = evt["freq_end_khz"]

                bins: list[float] = evt.get("rssi_bins", [])
                if bins:
                    sampled = _resample(bins, CHARS_WIDE)
                    _scroll_up(fb)
                    _draw_new_row(fb, sampled)
                    sweep_count += 1
                    peak = max(bins)
                    dirty = True

            elif etype == "error":
                dirty = True

            now = time.time()
            if dirty and now - last_draw >= frame_interval:
                _draw_status(fb, sweep_count, peak)
                flush()
                last_draw = now
                dirty = False

    if not args.no_ui_stop:
        wf.pineapple_cont()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
