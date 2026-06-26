#!/usr/bin/env python3
"""Pager-optimized ASCII waterfall renderer for SpecTools bridge JSONL events.

Outputs one LOG-compatible tagged line per sweep to stdout. The shell wrapper
(text_waterfall() in funcs_scan.sh) reads each line and routes it to the
appropriate LOG color command.

Line tag prefixes:
  B:  → LOG blue    (peak dBm < -80 — noise floor)
  C:  → LOG cyan    (peak dBm -80 to -70 — low signal)
  G:  → LOG green   (peak dBm -70 to -60 — medium signal)
  Y:  → LOG yellow  (peak dBm -60 to -50 — strong signal)
  R:  → LOG red     (peak dBm > -50 — very strong / peak)
  (no tag) → LOG default (headers, legends, status lines)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

LINE_WIDTH    = 50
SPECTRUM_COLS = 42      # LINE_WIDTH - 2 (tag) - 2 pipes - 4 peak
HEADER_EVERY  = 10      # print freq + scale header every N sweeps

# Block-shading glyphs (Unicode; ASCII fallback if locale not UTF-8)
_DENSITY_UNICODE: list[tuple[float, str]] = [
    (-88.0, " "),   # noise floor — invisible
    (-78.0, "░"),   # very low
    (-68.0, "▒"),   # low
    (-55.0, "▓"),   # medium
    (999.0, "█"),   # strong / peak
]
_DENSITY_ASCII: list[tuple[float, str]] = [
    (-88.0, " "),
    (-78.0, "."),
    (-68.0, "-"),
    (-55.0, "="),
    (999.0, "#"),
]

_SCALE_UNICODE = "[░<-78  ▒<-68  ▓<-55  █>-55   (dBm)]"
_SCALE_ASCII   = "[.<-78  -<-68  =<-55  #>-55   (dBm)]"

# Wi-Fi channel centre frequencies (kHz) → display marker
_CH_2G: dict[int, str] = {
    2412000: "1", 2437000: "6", 2462000: ">",
}
_CH_5G: dict[int, str] = {
    5180000: "a", 5200000: "b", 5220000: "c", 5240000: "d",
    5745000: "e", 5765000: "f", 5785000: "g", 5805000: "h",
}

# 5-tier dBm → LOG tag mapping (based on row peak)
_TAGS: list[tuple[float, str]] = [
    (-80.0, "B:"),  # blue   — noise floor
    (-70.0, "C:"),  # cyan   — low
    (-60.0, "G:"),  # green  — medium
    (-50.0, "Y:"),  # yellow — strong
    (999.0, "R:"),  # red    — very strong
]


def _unicode_ok() -> bool:
    enc = getattr(sys.stdout, "encoding", None) or ""
    if "utf" in enc.lower():
        return True
    for var in ("LC_ALL", "LC_CTYPE", "LANG"):
        if "utf" in os.environ.get(var, "").lower():
            return True
    return False


def _bin_char(dbm: float, density: list[tuple[float, str]]) -> str:
    for threshold, ch in density:
        if dbm <= threshold:
            return ch
    return density[-1][1]


def _peak_tag(peak: float) -> str:
    for threshold, tag in _TAGS:
        if peak <= threshold:
            return tag
    return _TAGS[-1][1]


def resample(bins: list[float], width: int) -> list[float]:
    n = len(bins)
    if n == width:
        return list(bins)
    chunk = n / width
    if n > width:
        return [max(bins[int(i * chunk) : max(int((i + 1) * chunk), int(i * chunk) + 1)])
                for i in range(width)]
    return [bins[min(int(i * n / width), n - 1)] for i in range(width)]


def freq_header(freq_start_khz: int | None, freq_end_khz: int | None,
                cols: int = SPECTRUM_COLS) -> str:
    label_l = f"{freq_start_khz // 1000}MHz" if freq_start_khz else "?MHz"
    label_r = f"{freq_end_khz // 1000}MHz" if freq_end_khz else "?MHz"
    buf = ["-"] * cols
    for i, c in enumerate(label_l[:cols]):
        buf[i] = c
    for i, c in enumerate(label_r):
        pos = cols - len(label_r) + i
        if 0 <= pos < cols:
            buf[pos] = c
    if freq_start_khz and freq_end_khz:
        span = freq_end_khz - freq_start_khz
        ch_map = _CH_2G if freq_start_khz < 3_000_000 else _CH_5G
        for freq_khz, mark in ch_map.items():
            if freq_start_khz <= freq_khz <= freq_end_khz and span > 0:
                pos = int((freq_khz - freq_start_khz) / span * cols)
                if 0 <= pos < cols and buf[pos] == "-":
                    buf[pos] = mark
    return f"[{''.join(buf)[:cols].ljust(cols)}]"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Pager ASCII waterfall renderer")
    p.add_argument("--events-file", default="/tmp/spectools_bridge_events.jsonl")
    p.add_argument("--follow", action="store_true")
    p.add_argument("--poll-interval", type=float, default=0.05)
    p.add_argument("--band", default="", help="Band label for header (e.g. 2.4)")
    p.add_argument("--unicode", action="store_true", default=None)
    p.add_argument("--no-unicode", dest="unicode", action="store_false")
    args = p.parse_args(argv)

    use_unicode = _unicode_ok() if args.unicode is None else args.unicode
    density  = _DENSITY_UNICODE if use_unicode else _DENSITY_ASCII
    scale_ln = (_SCALE_UNICODE  if use_unicode else _SCALE_ASCII)[:LINE_WIDTH]

    events_path = Path(args.events_file)
    sweep_count = 0
    freq_start: int | None = None
    freq_end:   int | None = None
    last_header_at = -HEADER_EVERY

    def emit(line: str) -> None:
        sys.stdout.write(line[:LINE_WIDTH] + "\n")
        sys.stdout.flush()

    # ── Opening header ────────────────────────────────────────────────────────
    band_label = f"  {args.band}GHz" if args.band else ""
    emit(f"── SPECPINE ASCII WATERFALL{band_label} ──")
    emit(scale_ln)
    emit("tap OK=pause  hold OK=stop")

    if not events_path.exists():
        emit("Waiting for device...")
        while not events_path.exists():
            time.sleep(0.5)
        emit("Device connected.")

    with events_path.open("r", encoding="utf-8") as fh:
        while True:
            raw = fh.readline()
            if not raw:
                if args.follow:
                    time.sleep(args.poll_interval)
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

            elif etype == "sweep":
                if evt.get("freq_start_khz") is not None:
                    freq_start = evt["freq_start_khz"]
                if evt.get("freq_end_khz") is not None:
                    freq_end = evt["freq_end_khz"]

                bins: list[float] = evt.get("rssi_bins", [])
                if not bins:
                    continue

                if sweep_count - last_header_at >= HEADER_EVERY:
                    emit(freq_header(freq_start, freq_end))
                    emit(scale_ln)
                    last_header_at = sweep_count

                sampled = resample(bins, SPECTRUM_COLS)
                row  = "".join(_bin_char(v, density) for v in sampled)
                peak = max(bins)
                tag  = _peak_tag(peak)
                emit(f"{tag}|{row}|{int(round(peak)):4d}")
                sweep_count += 1

            elif etype == "error":
                msg = evt.get("message", "unknown error")
                emit(f"ERR:{msg}"[:LINE_WIDTH])

            elif etype == "status":
                if evt.get("level") == "warning":
                    emit(f"[!]{evt.get('message', '')}"[:LINE_WIDTH])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
