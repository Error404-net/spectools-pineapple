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
import sys
import time
from pathlib import Path

# Total payload_log line width
LINE_WIDTH = 50

# Spectrum characters span LINE_WIDTH - 2 pipes - 4 peak = 44
SPECTRUM_COLS = 44

# Emit a freq/scale header every N sweeps
HEADER_EVERY = 15

# dBm thresholds → display char, ordered from lowest to highest
DENSITY: list[tuple[int, str]] = [
    (-90, " "),  # noise floor
    (-80, "."),  # very low signal
    (-70, "-"),  # low signal
    (-65, "="),  # medium signal
    (-55, "+"),  # strong signal
    (999, "#"),  # very strong / saturation
]

SCALE_LINE = "[ ]=<-90 .=-80 -=-70 ==-65 +=-55 #>-55]"[:LINE_WIDTH]


def bin_to_char(dbm: int) -> str:
    for threshold, ch in DENSITY:
        if dbm <= threshold:
            return ch
    return "#"


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


def freq_header(freq_start_khz: int | None, freq_end_khz: int | None) -> str:
    label_l = f"{freq_start_khz // 1000}MHz" if freq_start_khz is not None else "?MHz"
    label_r = f"{freq_end_khz // 1000}MHz" if freq_end_khz is not None else "?MHz"
    inner = SPECTRUM_COLS - len(label_l) - len(label_r)
    dashes = "-" * max(0, inner)
    label = (label_l + dashes + label_r)[:SPECTRUM_COLS].ljust(SPECTRUM_COLS)
    return f"[{label}]"


def truncate(text: str, width: int = LINE_WIDTH) -> str:
    return text[:width]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Pager ASCII waterfall renderer")
    p.add_argument("--events-file", default="/tmp/spectools_bridge_events.jsonl")
    p.add_argument("--follow", action="store_true", help="Tail the events file")
    p.add_argument("--poll-interval", type=float, default=0.05,
                   help="Seconds between polls when following")
    args = p.parse_args(argv)

    events_path = Path(args.events_file)
    sweep_count = 0
    freq_start: int | None = None
    freq_end: int | None = None
    last_header_at = -HEADER_EVERY  # triggers header on first sweep

    def emit(line: str) -> None:
        sys.stdout.write(truncate(line) + "\n")
        sys.stdout.flush()

    emit("SpecTools Waterfall - Wi-Spy DBx")
    emit(SCALE_LINE)

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
                row = "".join(bin_to_char(v) for v in sampled)
                peak = max(bins)
                emit(f"|{row}|{peak:4d}")
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
