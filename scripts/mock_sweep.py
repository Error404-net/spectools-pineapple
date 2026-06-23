#!/usr/bin/env python3
"""
SpecPine mock sweep generator.

Writes fake Wi-Spy DBx JSONL events to a file so the HTTP waterfall
(and other renderers) can be tested without a physical Wi-Spy device.

Usage:
  python3 scripts/mock_sweep.py [--output /tmp/specpine_events.jsonl] \
                                [--band 2.4|5] [--duration 60] [--rate 3]

The sweep data simulates:
  - 2.4 GHz: 3 busy Wi-Fi APs on channels 1, 6, 11 with noise floor ~ -92 dBm
  - 5 GHz:   bursty traffic on channels 36, 40, 149
  - Random environmental noise on all bins
  - Occasional jamming/anomaly burst
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path


# ── 2.4 GHz band ─────────────────────────────────────────────────────────────
BAND_24 = {
    "freq_start_khz": 2400000,
    "freq_end_khz":   2495000,
    "bin_count":       285,
    "res_hz":         333000,
    "device":         "Wi-Spy DBx [mock]",
}

# ── 5 GHz band ────────────────────────────────────────────────────────────────
BAND_5 = {
    "freq_start_khz": 5170000,
    "freq_end_khz":   5835000,
    "bin_count":       554,
    "res_hz":        1200000,
    "device":         "Wi-Spy DBx [mock]",
}


def _channel_centre_bin(band: dict, freq_mhz: float) -> int:
    fs = band["freq_start_khz"]
    fe = band["freq_end_khz"]
    nb = band["bin_count"]
    freq_khz = freq_mhz * 1000
    return int((freq_khz - fs) / (fe - fs) * nb)


_NOISE_FLOOR = -92.0

def _gaussian_blob(bins: list[float], centre: int, width: int, peak_dbm: float) -> None:
    """Add a Gaussian bump to bins (simulates an AP channel).

    Models excess dB above the noise floor as a Gaussian so that bins far from
    the AP centre fall back to the noise floor rather than to 0 dBm.
    """
    excess = peak_dbm - _NOISE_FLOOR   # positive number (e.g. 40 dB)
    for i in range(len(bins)):
        d = (i - centre)
        v = _NOISE_FLOOR + excess * math.exp(-(d * d) / (2.0 * width * width))
        if v > bins[i]:
            bins[i] = v


def generate_sweep(band: dict, t: float, aps: list[dict]) -> list[float]:
    nb = band["bin_count"]
    # Noise floor with slight per-bin variation
    bins = [-92.0 + random.gauss(0, 1.5) for _ in range(nb)]

    for ap in aps:
        cb  = _channel_centre_bin(band, ap["freq_mhz"])
        bw  = ap["width_bins"]
        # amplitude modulates gently over time (simulates traffic bursts)
        amp = ap["peak_dbm"] + 8 * math.sin(t * ap["burst_hz"] * 2 * math.pi) \
              + random.gauss(0, 2)
        amp = min(amp, -30.0)
        _gaussian_blob(bins, cb, bw, amp)

    # Occasional wide-band jammer burst
    if random.random() < 0.02:
        jammer_centre = random.randint(nb // 4, 3 * nb // 4)
        _gaussian_blob(bins, jammer_centre, nb // 8, -45.0)

    return [round(v, 1) for v in bins]


def build_aps(band: dict, band_name: str) -> list[dict]:
    if band_name == "2.4":
        return [
            {"freq_mhz": 2412, "width_bins": 12, "peak_dbm": -52, "burst_hz": 0.7},   # Ch1
            {"freq_mhz": 2437, "width_bins": 12, "peak_dbm": -61, "burst_hz": 1.1},   # Ch6
            {"freq_mhz": 2462, "width_bins": 12, "peak_dbm": -48, "burst_hz": 0.5},   # Ch11
            {"freq_mhz": 2422, "width_bins":  8, "peak_dbm": -78, "burst_hz": 2.3},   # Ch3 (weak)
        ]
    else:
        return [
            {"freq_mhz": 5180, "width_bins": 10, "peak_dbm": -55, "burst_hz": 0.9},   # Ch36
            {"freq_mhz": 5200, "width_bins": 10, "peak_dbm": -68, "burst_hz": 1.4},   # Ch40
            {"freq_mhz": 5745, "width_bins": 10, "peak_dbm": -50, "burst_hz": 0.6},   # Ch149
        ]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="SpecPine mock sweep generator")
    p.add_argument("--output",   default="/tmp/specpine_events.jsonl",
                   help="Events file path (default: /tmp/specpine_events.jsonl)")
    p.add_argument("--band",     choices=["2.4", "5"], default="2.4",
                   help="Simulated band (default: 2.4)")
    p.add_argument("--duration", type=float, default=0,
                   help="Seconds to run; 0 = run until killed (default: 0)")
    p.add_argument("--rate",     type=float, default=3.0,
                   help="Sweeps per second (default: 3.0)")
    p.add_argument("--append",   action="store_true",
                   help="Append to existing file instead of overwriting")
    args = p.parse_args(argv)

    band = BAND_24 if args.band == "2.4" else BAND_5
    aps  = build_aps(band, args.band)
    out  = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    mode = "a" if args.append else "w"
    interval = 1.0 / max(args.rate, 0.1)
    deadline = time.monotonic() + args.duration if args.duration > 0 else float("inf")

    with out.open(mode, encoding="utf-8") as fh:
        # Emit device_config first
        cfg = {
            "type":           "device_config",
            "timestamp":      time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "device":         band["device"],
            "freq_start_khz": band["freq_start_khz"],
            "freq_end_khz":   band["freq_end_khz"],
            "bin_count":      band["bin_count"],
            "res_hz":         band["res_hz"],
        }
        fh.write(json.dumps(cfg) + "\n")
        fh.flush()
        print(f"[mock] wrote device_config ({band['device']})", file=sys.stderr)

        sweep_n = 0
        t0 = time.monotonic()
        try:
            while time.monotonic() < deadline:
                t = time.monotonic() - t0
                bins = generate_sweep(band, t, aps)
                mn, mx, av = min(bins), max(bins), sum(bins) / len(bins)
                evt = {
                    "type":           "sweep",
                    "timestamp":      time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "seq":            sweep_n,
                    "freq_start_khz": band["freq_start_khz"],
                    "freq_end_khz":   band["freq_end_khz"],
                    "rssi_bins":      bins,
                    "stats":          {"min": mn, "max": round(mx, 1), "avg": round(av, 1)},
                }
                fh.write(json.dumps(evt) + "\n")
                fh.flush()
                sweep_n += 1
                if sweep_n % 30 == 0:
                    print(f"[mock] {sweep_n} sweeps  peak={mx:.0f} dBm", file=sys.stderr)
                time.sleep(interval)
        except KeyboardInterrupt:
            pass

    print(f"[mock] done — {sweep_n} sweeps written to {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
