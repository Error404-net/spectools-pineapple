#!/usr/bin/env python3
"""Spectools bridge: spectool_raw text -> JSONL canonical events."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import shlex
import signal
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, TextIO

FREQ_RE = re.compile(r"(?P<kind>start|end|low|high|min|max)[^0-9-]*(?P<freq>-?\d+)", re.IGNORECASE)
BIN_RE = re.compile(r"(?:samples|bins|points)[^0-9]*(\d+)", re.IGNORECASE)
RES_RE = re.compile(r"(?:res|resolution)[^0-9]*(\d+)", re.IGNORECASE)
INT_RE = re.compile(r"-?\d+")
SWEEP_RE = re.compile(r"^([^:]+):\s+(.+)$")


@dataclass
class DeviceConfig:
    device_name: str
    device_id: Optional[int]
    freq_start_khz: Optional[int] = None
    freq_end_khz: Optional[int] = None
    bin_count: Optional[int] = None
    res_hz: Optional[int] = None


class Bridge:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.stop = False
        self.device_configs: Dict[str, DeviceConfig] = {}
        self.last_line_ts: Optional[float] = None
        self.last_stall_emit: float = 0
        self.sweep_count = 0
        self.csv_rows: List[dict] = []
        self.events_fp: Optional[TextIO] = None
        self.metadata = {
            "started_at": self.ts(),
            "source": "spectool_raw",
            "mode": "replay" if args.replay_file else "command",
            "input": args.replay_file or args.input_command,
        }

    @staticmethod
    def ts() -> str:
        return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")

    def emit(self, event: dict) -> None:
        line = json.dumps(event, separators=(",", ":"))
        print(line, flush=True)
        if self.events_fp is not None:
            self.events_fp.write(line + "\n")
            self.events_fp.flush()

    def status(self, message: str, level: str = "info") -> None:
        self.emit({"type": "status", "timestamp": self.ts(), "level": level, "message": message})

    def error(self, code: str, message: str, recoverable: bool = True) -> None:
        self.emit(
            {
                "type": "error",
                "timestamp": self.ts(),
                "code": code,
                "message": message,
                "recoverable": recoverable,
            }
        )

    def parse_line(self, line: str) -> None:
        now = time.time()
        self.last_line_ts = now

        raw = line.strip()
        if not raw:
            return

        sweep_m = SWEEP_RE.match(raw)
        if sweep_m:
            device_name = sweep_m.group(1).strip()
            bins_text = sweep_m.group(2).strip()
            try:
                bins = [int(v) for v in bins_text.split()]
            except ValueError:
                self.error("MALFORMED_SWEEP", f"Invalid sweep bins for '{device_name}'", recoverable=True)
                return
            if not bins:
                self.error("MALFORMED_SWEEP", f"Empty sweep for '{device_name}'", recoverable=True)
                return
            cfg = self.device_configs.get(device_name)
            if cfg is None:
                cfg = DeviceConfig(device_name=device_name, device_id=None, bin_count=len(bins))
                self.device_configs[device_name] = cfg
                self.status(f"Discovered device from sweep stream: {device_name}")

            if cfg.bin_count and cfg.bin_count != len(bins):
                self.status(
                    f"Sweep bin count changed for {device_name}: {cfg.bin_count} -> {len(bins)}",
                    level="warning",
                )
            cfg.bin_count = len(bins)

            stats = {
                "min": min(bins),
                "max": max(bins),
                "avg": round(statistics.fmean(bins), 2),
            }
            event = {
                "type": "sweep",
                "timestamp": self.ts(),
                "device_id": cfg.device_id,
                "device_name": cfg.device_name,
                "freq_start_khz": cfg.freq_start_khz,
                "freq_end_khz": cfg.freq_end_khz,
                "bin_count": cfg.bin_count,
                "rssi_bins": bins,
                "stats": stats,
                "source": "spectool_raw",
            }
            self.emit(event)
            self.sweep_count += 1
            self.csv_rows.append(
                {
                    "timestamp": event["timestamp"],
                    "device_name": cfg.device_name,
                    "min": stats["min"],
                    "max": stats["max"],
                    "avg": stats["avg"],
                    "bin_count": cfg.bin_count,
                }
            )
            return

        lowered = raw.lower()
        if "error" in lowered or "fail" in lowered:
            self.error("SOURCE_MESSAGE", raw, recoverable=True)
            return

        if any(k in lowered for k in ["freq", "samples", "bins", "resolution", "range", "device"]):
            self._parse_configish_line(raw)
            return

        # Unknown line: ignore but surface as debug status.
        if self.args.verbose_unknown:
            self.status(f"Ignored line: {raw}", level="debug")

    def _parse_configish_line(self, line: str) -> None:
        device_name = "Unknown"
        if ":" in line:
            maybe_name = line.split(":", 1)[0].strip()
            if maybe_name and not INT_RE.fullmatch(maybe_name):
                device_name = maybe_name

        cfg = self.device_configs.get(device_name)
        if cfg is None:
            cfg = DeviceConfig(device_name=device_name, device_id=None)
            self.device_configs[device_name] = cfg

        for match in FREQ_RE.finditer(line):
            val = int(match.group("freq"))
            kind = match.group("kind").lower()
            if kind in {"start", "low", "min"}:
                cfg.freq_start_khz = val
            elif kind in {"end", "high", "max"}:
                cfg.freq_end_khz = val

        bin_m = BIN_RE.search(line)
        if bin_m:
            cfg.bin_count = int(bin_m.group(1))

        res_m = RES_RE.search(line)
        if res_m:
            cfg.res_hz = int(res_m.group(1))

        if any(v is not None for v in [cfg.freq_start_khz, cfg.freq_end_khz, cfg.bin_count, cfg.res_hz]):
            self.emit(
                {
                    "type": "device_config",
                    "timestamp": self.ts(),
                    "device_id": cfg.device_id,
                    "device_name": cfg.device_name,
                    "freq_start_khz": cfg.freq_start_khz,
                    "freq_end_khz": cfg.freq_end_khz,
                    "bin_count": cfg.bin_count,
                    "res_hz": cfg.res_hz,
                    "source": "spectool_raw",
                }
            )
            self.status(f"Configured device {cfg.device_name}")

    def _iter_replay(self, path: Path) -> Iterable[str]:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                yield line
                if self.args.replay_delay_ms > 0:
                    time.sleep(self.args.replay_delay_ms / 1000.0)

    def _iter_command(self, command: str) -> Iterable[str]:
        retries = 0
        while not self.stop:
            self.status(f"Starting command: {command}")
            proc = subprocess.Popen(
                shlex.split(command),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                if self.stop:
                    break
                yield line
            rc = proc.wait()
            if self.stop:
                return
            self.status(f"Source process exited with code {rc}", level="warning")
            if retries >= self.args.max_restarts:
                self.error("SOURCE_EXIT", "Source process exited too many times", recoverable=False)
                return
            retries += 1
            self.status(f"Reconnect attempt {retries}/{self.args.max_restarts}", level="warning")
            time.sleep(self.args.restart_delay)

    def check_stall(self) -> None:
        if self.last_line_ts is None:
            return
        elapsed = time.time() - self.last_line_ts
        if elapsed > self.args.stall_timeout and time.time() - self.last_stall_emit > self.args.stall_timeout:
            self.status(f"Source stalled for {elapsed:.1f}s", level="warning")
            self.last_stall_emit = time.time()

    def write_exports(self) -> None:
        if not self.args.export_dir:
            return
        out_dir = Path(self.args.export_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        metadata_path = out_dir / f"session_{ts}.meta.json"
        csv_path = out_dir / f"session_{ts}.summary.csv"
        self.metadata["ended_at"] = self.ts()
        self.metadata["sweep_count"] = self.sweep_count
        metadata_path.write_text(json.dumps(self.metadata, indent=2) + "\n", encoding="utf-8")

        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            fieldnames = ["timestamp", "device_name", "min", "max", "avg", "bin_count"]
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.csv_rows)

        self.status(f"Exported metadata: {metadata_path}")
        self.status(f"Exported summary CSV: {csv_path}")

    def run(self) -> int:
        if self.args.events_file:
            events_path = Path(self.args.events_file)
            events_path.parent.mkdir(parents=True, exist_ok=True)
            self.events_fp = events_path.open("a", encoding="utf-8")

        if self.args.replay_file:
            source_iter = self._iter_replay(Path(self.args.replay_file))
        else:
            source_iter = self._iter_command(self.args.input_command)

        self.status("Bridge initializing")
        saw_line = False
        try:
            for line in source_iter:
                saw_line = True
                self.parse_line(line)
                self.check_stall()
            self.check_stall()
        except Exception as exc:  # noqa: BLE001
            self.error("BRIDGE_EXCEPTION", str(exc), recoverable=False)
            return 2
        finally:
            self.write_exports()

        if not saw_line:
            self.error("NO_DEVICES_FOUND", "No data received from source", recoverable=False)
            if self.events_fp:
                self.events_fp.close()
            return 1

        self.status("Bridge stopped")
        if self.events_fp:
            self.events_fp.close()
        return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Spectools bridge JSONL emitter")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--replay-file", help="Read spectool_raw text from a file")
    src.add_argument("--input-command", default="spectool_raw", help="Command to run for live ingest")
    p.add_argument("--replay-delay-ms", type=int, default=0, help="Delay between replay lines")
    p.add_argument("--events-file", default="/tmp/spectools_bridge_events.jsonl", help="Optional JSONL tee file")
    p.add_argument("--export-dir", default="", help="Optional export directory for metadata + CSV")
    p.add_argument("--stall-timeout", type=float, default=5.0)
    p.add_argument("--max-restarts", type=int, default=3)
    p.add_argument("--restart-delay", type=float, default=1.0)
    p.add_argument("--verbose-unknown", action="store_true")
    return p


def main() -> int:
    args = build_parser().parse_args()
    bridge = Bridge(args)

    def _stop(_sig: int, _frame: object) -> None:
        bridge.stop = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    return bridge.run()


if __name__ == "__main__":
    raise SystemExit(main())
