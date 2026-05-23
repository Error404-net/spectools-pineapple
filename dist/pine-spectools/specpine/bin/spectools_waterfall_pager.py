#!/usr/bin/env python3
"""Pager-optimized ASCII waterfall renderer for SpecTools bridge JSONL events.

Outputs one LOG-compatible line per sweep. Designed for the Hak5 WiFi
Pineapple Pager payload_log display (50-char max, plain ASCII, no ANSI).

Line formats:
  waterfall row  : |{44 spectrum chars}|{peak dBm, 4 chars}
  freq header    : [{44 label chars}]
  scale legend   : [{legend text}]
  status/errors  : plain text, truncated to 50 chars
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Total payload_log line width
LINE_WIDTH = 50

# Spectrum characters span LINE_WIDTH - 2 (tag) - 2 pipes - 4 peak = 42
SPECTRUM_COLS = 42

# Emit a freq/scale header every N sweeps
HEADER_EVERY = 10

# ASCII fallback glyph set (always safe)
_DENSITY_ASCII: list[tuple[int, str]] = [
    (-90, " "),  # noise floor
    (-80, "."),  # very low signal
    (-70, "-"),  # low signal
    (-65, "="),  # medium signal
    (-55, "+"),  # strong signal
    (999, "#"),  # very strong / saturation
]

# Unicode block-shading glyphs (used when stdout is UTF-8 capable)
_DENSITY_UNICODE: list[tuple[int, str]] = [
    (-90, " "),       # noise floor
    (-80, "░"),  # ░ very low
    (-70, "▒"),  # ▒ low
    (-65, "▓"),  # ▓ medium
    (-55, "█"),  # █ strong
    (999, "█"),  # █ saturation
]

_SCALE_ASCII   = "[ ]=<-90 .=-80 -=-70 ==-65 +=-55 #>-55]"
_SCALE_UNICODE = "[░<-80 ▒<-70 ▓<-65 █>-55 (dBm) ]"

# 2.4 GHz Wi-Fi channel centres → single-char marker for the freq header
_CH_2G: dict[int, str] = {2437000: "6", 2462000: ">"}
# 5 GHz UNII-1/UNII-3 centres → single-char marker
_CH_5G: dict[int, str] = {
    5180000: "a", 5200000: "b", 5220000: "c", 5240000: "d",
    5745000: "e", 5765000: "f", 5785000: "g", 5805000: "h",
}


def _unicode_ok() -> bool:
    """Return True if stdout encoding and locale both appear to be UTF-8."""
    enc = getattr(sys.stdout, "encoding", None) or ""
    if "utf" in enc.lower():
        return True
    for var in ("LC_ALL", "LC_CTYPE", "LANG"):
        if "utf" in os.environ.get(var, "").lower():
            return True
    return False


def bin_to_char(dbm: int, density: list[tuple[int, str]]) -> str:
    for threshold, ch in density:
        if dbm <= threshold:
            return ch
    return density[-1][1]


def resample(bins: list[int], width: int) -> list[int]:
    """Downsample or upsample bin array to target width, using max for downsampling."""
    if len(bins) == width:
        return bins
    result: list[int] = []
    chunk = len(bins) / width
    if len(bins) > width:
        for i in range(width):
            s = int(i * chunk)
            e = int((i + 1) * chunk)
            seg = bins[s : max(e, s + 1)]
            result.append(max(seg))
    else:
        for i in range(width):
            idx = int(i * len(bins) / width)
            result.append(bins[min(idx, len(bins) - 1)])
    return result


def freq_header(freq_start_khz: int | None, freq_end_khz: int | None,
                cols: int = SPECTRUM_COLS) -> str:
    label_l = f"{freq_start_khz // 1000}MHz" if freq_start_khz is not None else "?MHz"
    label_r = f"{freq_end_khz // 1000}MHz" if freq_end_khz is not None else "?MHz"

    buf = ["-"] * cols
    for i, c in enumerate(label_l[:cols]):
        buf[i] = c
    for i, c in enumerate(label_r):
        pos = cols - len(label_r) + i
        if 0 <= pos < cols:
            buf[pos] = c

    # Overlay channel markers only where a dash still sits
    if freq_start_khz is not None and freq_end_khz is not None:
        span = freq_end_khz - freq_start_khz
        ch_map = _CH_2G if freq_start_khz < 3_000_000 else _CH_5G
        for freq_khz, mark in ch_map.items():
            if freq_start_khz <= freq_khz <= freq_end_khz and span > 0:
                pos = int((freq_khz - freq_start_khz) / span * cols)
                if 0 <= pos < cols and buf[pos] == "-":
                    buf[pos] = mark

    return f"[{''.join(buf)[:cols].ljust(cols)}]"


def truncate(text: str, width: int = LINE_WIDTH) -> str:
    return text[:width]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Pager ASCII waterfall renderer")
    p.add_argument("--events-file", default="/tmp/spectools_bridge_events.jsonl")
    p.add_argument("--follow", action="store_true", help="Tail the events file")
    p.add_argument("--poll-interval", type=float, default=0.05,
                   help="Seconds between polls when following")
    p.add_argument("--banner", default="",
                   help="Optional one-line banner emitted under the scale line")
    p.add_argument("--unicode", action="store_true", default=None,
                   help="Force Unicode block glyphs (auto-detected if omitted)")
    p.add_argument("--no-unicode", dest="unicode", action="store_false",
                   help="Force ASCII glyphs regardless of terminal encoding")
    args = p.parse_args(argv)

    use_unicode = _unicode_ok() if args.unicode is None else args.unicode
    density = _DENSITY_UNICODE if use_unicode else _DENSITY_ASCII
    scale_line = (_SCALE_UNICODE if use_unicode else _SCALE_ASCII)[:LINE_WIDTH]

    events_path = Path(args.events_file)
    sweep_count = 0
    freq_start: int | None = None
    freq_end: int | None = None
    last_header_at = -HEADER_EVERY  # triggers header on first sweep

    def emit(line: str) -> None:
        sys.stdout.write(truncate(line) + "\n")
        sys.stdout.flush()

    emit("SpecTools Waterfall - Wi-Spy DBx")
    emit(scale_line)
    if args.banner:
        emit(truncate(args.banner))

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

                bins: list[int] = evt.get("rssi_bins", [])
                if not bins:
                    continue

                if sweep_count - last_header_at >= HEADER_EVERY:
                    emit(freq_header(freq_start, freq_end))
                    last_header_at = sweep_count

                sampled = resample(bins, SPECTRUM_COLS)
                row = "".join(bin_to_char(v, density) for v in sampled)
                peak = int(round(max(bins)))
                # Tag tier so the bash wrapper can route to LOG red/yellow/green.
                if peak >= -50:
                    tag = "R:"
                elif peak >= -70:
                    tag = "Y:"
                else:
                    tag = "G:"
                emit(f"{tag}|{row}|{peak:4d}")
                sweep_count += 1

            elif etype == "error":
                msg = evt.get("message", "unknown error")
                emit(truncate(f"ERR:{msg}", LINE_WIDTH))

            elif etype == "status":
                level = evt.get("level", "info")
                if level in ("warning",):
                    msg = evt.get("message", "")
                    emit(truncate(f"[!]{msg}", LINE_WIDTH))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
