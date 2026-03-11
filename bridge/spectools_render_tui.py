#!/usr/bin/env python3
"""Terminal waterfall renderer for bridge JSONL events."""

from __future__ import annotations

import argparse
import json
import os
import select
import sys
import termios
import time
import tty
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional

PALETTE = [
    (-95, "\x1b[48;5;232m "),
    (-85, "\x1b[48;5;18m "),
    (-75, "\x1b[48;5;37m "),
    (-65, "\x1b[48;5;226m "),
    (999, "\x1b[48;5;196m "),
]
RESET = "\x1b[0m"


class Renderer:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.mode = args.start_mode
        self.state = "INITIALIZING"
        self.rows: Deque[List[int]] = deque(maxlen=args.ring_depth)
        self.latest: Optional[dict] = None
        self.sweep_count = 0
        self.start_ts = time.time()
        self.disconnected_since: Optional[float] = None
        self.fd = sys.stdin.fileno() if sys.stdin.isatty() else None
        self._old_tty = None

    def _color_for(self, v: int) -> str:
        for threshold, code in PALETTE:
            if v <= threshold:
                return code
        return PALETTE[-1][1]

    def _sample_bins(self, bins: List[int]) -> List[int]:
        width = self.args.columns
        if len(bins) == width:
            return bins
        if len(bins) > width:
            chunk = len(bins) / width
            sampled = []
            for i in range(width):
                s = int(i * chunk)
                e = int((i + 1) * chunk)
                seg = bins[s : max(e, s + 1)]
                sampled.append(max(seg) if self.args.downsample == "max" else int(sum(seg) / len(seg)))
            return sampled
        out = []
        for i in range(width):
            idx = int(i * len(bins) / width)
            out.append(bins[min(idx, len(bins) - 1)])
        return out

    def _draw(self) -> None:
        os.write(1, b"\x1b[2J\x1b[H")
        elapsed = time.time() - self.start_ts
        fps = self.sweep_count / elapsed if elapsed > 0 else 0
        peak = self.latest["stats"]["max"] if self.latest else "n/a"
        head = f"Spectools Waterfall | state={self.state} | mode={self.mode} | sweeps={self.sweep_count} | fps={fps:.1f} | peak={peak} dBm\n"
        os.write(1, head.encode())

        if self.mode == "stats":
            if self.latest:
                s = self.latest["stats"]
                text = (
                    f"device={self.latest.get('device_name')} bins={self.latest.get('bin_count')}\n"
                    f"min={s['min']} max={s['max']} avg={s['avg']}\n"
                    f"controls: c=cycle mode, p=pause/resume, s=snapshot, q=quit\n"
                )
            else:
                text = "No sweep data yet\n"
            os.write(1, text.encode())
            return

        for row in list(self.rows)[-self.args.height :]:
            mapped = self._sample_bins(row)
            line = "".join(self._color_for(v) for v in mapped) + RESET + "\n"
            os.write(1, line.encode())
        os.write(1, b"controls: c=cycle mode, p=pause/resume, s=snapshot, q=quit\n")

    def _snapshot(self) -> None:
        if not self.args.snapshot_dir:
            return
        out = Path(self.args.snapshot_dir)
        out.mkdir(parents=True, exist_ok=True)
        snap = out / f"snapshot_{int(time.time())}.txt"
        with snap.open("w", encoding="utf-8") as fh:
            fh.write(f"state={self.state} mode={self.mode} sweeps={self.sweep_count}\n")
            if self.latest:
                fh.write(json.dumps(self.latest) + "\n")
        self.state = "PAUSED"

    def _read_key(self) -> Optional[str]:
        if self.fd is None:
            return None
        r, _, _ = select.select([self.fd], [], [], 0)
        if not r:
            return None
        return os.read(self.fd, 1).decode(errors="ignore")

    def _handle_key(self, key: str) -> bool:
        if key in {"q", "b"}:
            return False
        if key == "c":
            self.mode = "stats" if self.mode == "waterfall" else "waterfall"
        elif key == "p":
            self.state = "PAUSED" if self.state == "SCANNING" else "SCANNING"
        elif key == "s":
            self._snapshot()
        return True

    def _iter_lines(self):
        if self.args.input_file:
            with open(self.args.input_file, "r", encoding="utf-8") as fh:
                for line in fh:
                    yield line
                    if self.args.replay_delay_ms > 0:
                        time.sleep(self.args.replay_delay_ms / 1000.0)
        else:
            while True:
                line = sys.stdin.readline()
                if not line:
                    return
                yield line

    def run(self) -> int:
        if self.fd is not None:
            self._old_tty = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
        try:
            self.state = "NO_DATA"
            last_draw = 0.0
            for line in self._iter_lines():
                key = self._read_key()
                if key and not self._handle_key(key):
                    break

                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if evt.get("type") == "error":
                    self.state = "ERROR"
                elif evt.get("type") == "status":
                    if "stall" in str(evt.get("message", "")).lower():
                        self.state = "DISCONNECTED"
                        self.disconnected_since = time.time()
                elif evt.get("type") == "sweep" and self.state != "PAUSED":
                    self.latest = evt
                    self.rows.append(evt.get("rssi_bins", []))
                    self.sweep_count += 1
                    self.state = "SCANNING"

                now = time.time()
                if now - last_draw >= 1.0 / max(self.args.fps, 1):
                    self._draw()
                    last_draw = now

            self.state = "DISCONNECTED" if self.sweep_count else "NO_DATA"
            self._draw()
            return 0
        finally:
            if self.fd is not None and self._old_tty is not None:
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self._old_tty)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Render bridge JSONL waterfall in terminal")
    p.add_argument("--input-file", help="Replay from JSONL file instead of stdin")
    p.add_argument("--replay-delay-ms", type=int, default=50)
    p.add_argument("--columns", type=int, default=80)
    p.add_argument("--height", type=int, default=20)
    p.add_argument("--ring-depth", type=int, default=200)
    p.add_argument("--fps", type=int, default=6)
    p.add_argument("--downsample", choices=["max", "avg"], default="max")
    p.add_argument("--snapshot-dir", default="")
    p.add_argument("--start-mode", choices=["waterfall", "stats"], default="waterfall")
    return p


if __name__ == "__main__":
    args = parser().parse_args()
    raise SystemExit(Renderer(args).run())
