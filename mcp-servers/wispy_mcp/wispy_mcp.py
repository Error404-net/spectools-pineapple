#!/usr/bin/env python3
"""
wispy_mcp — MCP server for the Wi-Spy DBx USB spectrum analyzer.

The dongle moves between two contexts:
  - "remote": plugged into the WiFi Pineapple Pager's USB port. This server
    SSHes into the Pager and runs spectool_raw there (the same MIPS binary
    SpecPine ships, resolved the same way payload.sh resolves it).
  - "local": plugged directly into this machine. This server shells out to a
    locally-built, native spectool_raw on PATH (or WISPY_LOCAL_BIN).

Call wispy_set_target whenever the dongle physically moves between machines —
there is no way to auto-detect this, so the caller (you, or the human you're
working with) has to say which mode is active.

Config (env vars, all optional):
    WISPY_TARGET_MODE      "local" or "remote", default "remote"
    PAGER_HOST             default "172.16.52.1"     (remote mode)
    PAGER_PORT             default 22
    PAGER_USER             default "root"
    PAGER_PASSWORD         default "qwerty"
    PAGER_SPECTOOL_BIN     default "/root/payloads/user/reconnaissance/specpine/bin/spectool_raw"
    PAGER_SPECTOOL_FALLBACK default "/opt/spectools/bin/spectool_raw"
    WISPY_LOCAL_BIN        default "spectool_raw"    (local mode, must be on PATH or absolute)

Persisted state: target mode/config is written to ~/.wispy_mcp/config.json so
it survives server restarts — you don't have to re-tell it where the dongle is
every session, only when it actually moves.

Requires: paramiko
    pip install paramiko --break-system-packages   (or in a venv)

Note on local mode: spectool_raw as shipped in this repo is cross-compiled for
mipsel (the Pager's CPU) and will NOT run on a Mac. Local mode requires a
*separately built* native binary — run `./configure && make` (no
--host=mipsel...) inside `spectool sourcecode/` on the Mac itself, with
libusb installed (e.g. `brew install libusb`).

Run:
    python3 wispy_mcp.py
"""

from __future__ import annotations

import json
import os
import re
import shlex
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import paramiko
from pydantic import BaseModel, ConfigDict, Field
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("wispy_mcp")

CONFIG_PATH = Path.home() / ".wispy_mcp" / "config.json"

DEFAULTS = {
    "mode": os.environ.get("WISPY_TARGET_MODE", "remote"),
    "pager_host": os.environ.get("PAGER_HOST", "172.16.52.1"),
    "pager_port": int(os.environ.get("PAGER_PORT", "22")),
    "pager_user": os.environ.get("PAGER_USER", "root"),
    "pager_password": os.environ.get("PAGER_PASSWORD", "qwerty"),
    "pager_spectool_bin": os.environ.get(
        "PAGER_SPECTOOL_BIN", "/root/payloads/user/reconnaissance/specpine/bin/spectool_raw"
    ),
    "pager_spectool_fallback": os.environ.get("PAGER_SPECTOOL_FALLBACK", "/opt/spectools/bin/spectool_raw"),
    "local_bin": os.environ.get("WISPY_LOCAL_BIN", "spectool_raw"),
}


def _load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text())
            merged = {**DEFAULTS, **cfg}
            return merged
        except Exception:
            pass
    return dict(DEFAULTS)


def _save_config(cfg: Dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


_config: Dict[str, Any] = _load_config()


# ── spectool_raw output parsing (mirrors payloads/specpine/bin/spectools_bridge.py) ──

RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*MHz\s*-\s*(\d+(?:\.\d+)?)\s*MHz", re.IGNORECASE)
NSAMP_RE = re.compile(r"(\d+)\s*samples?\b", re.IGNORECASE)
NRES_RE = re.compile(r"@\s*(\d+(?:\.\d+)?)\s*(KHz|MHz|Hz)", re.IGNORECASE)
DEVCFG_RE = re.compile(r"^\s*Configured\s+device\s+(\d+)\s*\(([^)]+)\)", re.IGNORECASE)
SWEEP_RE = re.compile(r"^([^:]+):\s+(.+)$")


def _to_khz(value: float, unit: str) -> int:
    u = unit.lower()
    if u == "mhz":
        return int(value * 1000)
    if u == "khz":
        return int(value)
    return int(value / 1000)


def _parse_spectool_output(text: str) -> Dict[str, Any]:
    """Condense raw spectool_raw stdout into a summary: device config plus
    aggregate sweep stats. Same line shapes spectools_bridge.py handles
    ("Configured device N (name)", "<lo>MHz-<hi>MHz @ <res>KHz, <N> samples",
    "<device name>: <bin> <bin> <bin> ..."), but collapsed to a summary instead
    of a JSONL stream since MCP tool results should stay compact.
    """
    device_name: Optional[str] = None
    device_id: Optional[str] = None
    freq_start_khz: Optional[int] = None
    freq_end_khz: Optional[int] = None
    bin_count: Optional[int] = None
    res_hz: Optional[int] = None

    sweep_count = 0
    all_mins: List[float] = []
    all_maxes: List[float] = []
    all_avgs: List[float] = []
    peak_value = float("-inf")
    peak_bin_index: Optional[int] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("debug -") or line.startswith("debug:"):
            continue

        devcfg_m = DEVCFG_RE.match(line)
        if devcfg_m:
            device_id, device_name = devcfg_m.group(1), devcfg_m.group(2).strip()
            continue

        rng_m = RANGE_RE.search(line)
        if rng_m and ("mhz" in line.lower()):
            freq_start_khz = _to_khz(float(rng_m.group(1)), "MHz")
            freq_end_khz = _to_khz(float(rng_m.group(2)), "MHz")
            nsamp_m = NSAMP_RE.search(line)
            if nsamp_m:
                bin_count = int(nsamp_m.group(1))
            nres_m = NRES_RE.search(line)
            if nres_m:
                res_hz = int(_to_khz(float(nres_m.group(1)), nres_m.group(2)) * 1000)
            continue

        sweep_m = SWEEP_RE.match(line)
        if sweep_m:
            bins_text = sweep_m.group(2).strip()
            try:
                bins = [float(v) for v in bins_text.split()]
            except ValueError:
                continue
            if not bins:
                continue
            sweep_count += 1
            all_mins.append(min(bins))
            all_maxes.append(max(bins))
            all_avgs.append(statistics.fmean(bins))
            local_max = max(bins)
            if local_max > peak_value:
                peak_value = local_max
                peak_bin_index = bins.index(local_max)

    peak_freq_khz = None
    if peak_bin_index is not None and freq_start_khz is not None and freq_end_khz is not None and bin_count:
        span = freq_end_khz - freq_start_khz
        peak_freq_khz = freq_start_khz + int(span * (peak_bin_index / max(bin_count - 1, 1)))

    return {
        "device_name": device_name,
        "device_id": device_id,
        "freq_start_khz": freq_start_khz,
        "freq_end_khz": freq_end_khz,
        "bin_count": bin_count,
        "res_hz": res_hz,
        "sweep_count": sweep_count,
        "overall_min": min(all_mins) if all_mins else None,
        "overall_max": max(all_maxes) if all_maxes else None,
        "overall_avg": round(statistics.fmean(all_avgs), 2) if all_avgs else None,
        "peak_value": peak_value if peak_bin_index is not None else None,
        "peak_freq_khz": peak_freq_khz,
    }


# ── Target resolution ────────────────────────────────────────────────────────


def _connect_ssh() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=_config["pager_host"],
        port=_config["pager_port"],
        username=_config["pager_user"],
        password=_config["pager_password"],
        timeout=10,
        banner_timeout=10,
        auth_timeout=10,
        look_for_keys=False,
        allow_agent=False,
    )
    return client


def _remote_bin_resolution_cmd() -> str:
    """Shell snippet that picks the payload-local spectool_raw if present,
    else falls back — same precedence payload.sh documents (SPECTOOL_SOURCE)."""
    primary = _config["pager_spectool_bin"]
    fallback = _config["pager_spectool_fallback"]
    return (
        f"if [ -x {shlex.quote(primary)} ]; then echo {shlex.quote(primary)}; "
        f"elif [ -x {shlex.quote(fallback)} ]; then echo {shlex.quote(fallback)}; "
        f"else echo __NOT_FOUND__; fi"
    )


def _run_remote(command: str, timeout_s: int) -> Dict[str, Any]:
    wrapped = f"timeout -s KILL {int(timeout_s)} sh -c {shlex.quote(command)}"
    client = _connect_ssh()
    try:
        stdin, stdout, stderr = client.exec_command(wrapped, timeout=timeout_s + 5)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        exit_code = stdout.channel.recv_exit_status()
        return {"exit_code": exit_code, "stdout": out, "stderr": err}
    finally:
        client.close()


def _connection_error(e: Exception) -> str:
    mode = _config["mode"]
    if mode == "remote":
        return (
            f"Error: could not reach the Pager at {_config['pager_user']}@{_config['pager_host']} "
            f"({type(e).__name__}: {e}). Current target mode is 'remote' — if the Wi-Spy is actually "
            f"plugged into your Mac right now, call wispy_set_target(mode='local') first."
        )
    return f"Error: {type(e).__name__}: {e}"


def _capture(duration_seconds: int, extra_args: str = "") -> Dict[str, Any]:
    """Run spectool_raw for ~duration_seconds and return its raw stdout, regardless
    of target mode. Always hard-bounded by `timeout` (remote) or subprocess timeout
    (local) so this can never hang."""
    mode = _config["mode"]
    if mode == "local":
        bin_path = _config["local_bin"]
        cmd = f"{shlex.quote(bin_path)} {extra_args}".strip()
        try:
            proc = subprocess.run(
                shlex.split(cmd), capture_output=True, text=True, timeout=duration_seconds + 3
            )
            return {"exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
        except FileNotFoundError:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": (
                    f"'{bin_path}' not found on PATH. Local mode requires a NATIVE build of spectool_raw "
                    "(not the MIPS one in this repo) — build it from `spectool sourcecode/` on this machine "
                    "with `./configure && make`, then set WISPY_LOCAL_BIN to its path, or call "
                    "wispy_set_target(local_bin='/path/to/spectool_raw')."
                ),
            }
        except subprocess.TimeoutExpired as e:
            return {"exit_code": 124, "stdout": e.stdout or "", "stderr": "local capture timed out and was killed"}
    else:
        resolve = _remote_bin_resolution_cmd()
        full_cmd = (
            f"BIN=$({resolve}); "
            f'if [ "$BIN" = "__NOT_FOUND__" ]; then echo "NO_SPECTOOL_BIN_FOUND" >&2; exit 127; fi; '
            f'export LD_LIBRARY_PATH="$(dirname "$BIN")/../lib"; '
            f'"$BIN" {extra_args}'.strip()
        )
        return _run_remote(full_cmd, timeout_s=duration_seconds + 3)


# ── wispy_get_target / wispy_set_target ──────────────────────────────────────


@mcp.tool(
    name="wispy_get_target",
    annotations={
        "title": "Show current Wi-Spy target",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def wispy_get_target() -> str:
    """Report which machine this server currently thinks the Wi-Spy DBx is plugged into.

    Returns:
        str: JSON of the current config (mode, and the relevant host/bin path for that mode).
        Secrets (the Pager's SSH password) are redacted.
    """
    safe = dict(_config)
    safe["pager_password"] = "***"
    return json.dumps(safe, indent=2)


class SetTargetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = Field(..., description="'local' (dongle plugged into this machine) or 'remote' (plugged into the Pager).")
    pager_host: Optional[str] = Field(default=None, description="Override the Pager's IP/hostname (remote mode only).")
    pager_password: Optional[str] = Field(default=None, description="Override the Pager's SSH password (remote mode only).")
    local_bin: Optional[str] = Field(default=None, description="Path to a native, locally-built spectool_raw binary (local mode only).")


@mcp.tool(
    name="wispy_set_target",
    annotations={
        "title": "Set where the Wi-Spy DBx is plugged in",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def wispy_set_target(params: SetTargetInput) -> str:
    """Tell this server whether the Wi-Spy DBx is currently plugged into the Pager
    ("remote") or directly into this machine ("local"). There's no way to auto-detect
    this — call it whenever the dongle physically moves. Persists to ~/.wispy_mcp/config.json
    so future sessions remember it until told otherwise.

    Args:
        params (SetTargetInput): mode, plus optional overrides for that mode's connection info.

    Returns:
        str: JSON of the resulting config (password redacted), or "Error: <message>" if mode is invalid.
    """
    if params.mode not in ("local", "remote"):
        return "Error: mode must be 'local' or 'remote'."
    _config["mode"] = params.mode
    if params.pager_host:
        _config["pager_host"] = params.pager_host
    if params.pager_password:
        _config["pager_password"] = params.pager_password
    if params.local_bin:
        _config["local_bin"] = params.local_bin
    _save_config(_config)
    safe = dict(_config)
    safe["pager_password"] = "***"
    return json.dumps(safe, indent=2)


# ── wispy_list_devices ───────────────────────────────────────────────────────


@mcp.tool(
    name="wispy_list_devices",
    annotations={
        "title": "List attached Wi-Spy devices",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def wispy_list_devices() -> str:
    """Run `spectool_raw --list` against the current target to see what Wi-Spy hardware
    is detected (USB enumeration, device name/id). Good first call after wispy_set_target
    or whenever a sweep tool reports no devices found.

    Returns:
        str: raw stdout/stderr from spectool_raw --list, or "Error: <message>" on failure
        (e.g. SSH unreachable in remote mode, binary missing in local mode).
    """
    try:
        result = _capture(duration_seconds=3, extra_args="--list")
        if result["exit_code"] not in (0, None):
            return f"Error: spectool_raw --list exited {result['exit_code']}. stderr: {result['stderr'].strip()[:500]}"
        return result["stdout"] or "(no output — no Wi-Spy device detected)"
    except Exception as e:  # noqa: BLE001
        return _connection_error(e)


# ── wispy_sweep ───────────────────────────────────────────────────────────────


class SweepInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_seconds: int = Field(
        default=5, description="How long to capture sweeps for before summarizing.", ge=1, le=30
    )


@mcp.tool(
    name="wispy_sweep",
    annotations={
        "title": "Capture and summarize a spectrum sweep",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def wispy_sweep(params: SweepInput) -> str:
    """Run spectool_raw against the current target for a fixed duration and return a
    condensed summary (device config + aggregate sweep stats + estimated peak frequency)
    rather than the raw firehose of per-bin sweep lines.

    Args:
        params (SweepInput): how many seconds to capture before summarizing (1-30).

    Returns:
        str: JSON summary with this schema:
        {
            "device_name": str|null, "device_id": str|null,
            "freq_start_khz": int|null, "freq_end_khz": int|null,
            "bin_count": int|null, "res_hz": int|null,
            "sweep_count": int,             # how many full sweeps were captured
            "overall_min": float|null, "overall_max": float|null, "overall_avg": float|null,
            "peak_value": float|null,       # strongest signal seen across all sweeps
            "peak_freq_khz": int|null       # estimated frequency of that peak
        }
        or "Error: <message>" if nothing was captured (no device, wrong target mode, etc.)

    Examples:
        - Use when: "is anything loud on 2.4GHz right now" -> call with default duration,
          check peak_freq_khz/peak_value.
        - Use when: you need raw per-bin data for custom analysis -> use wispy_raw_capture instead.
    """
    try:
        result = _capture(duration_seconds=params.duration_seconds)
        if not result["stdout"].strip():
            err = result["stderr"].strip()[:500]
            return f"Error: no output captured — is the Wi-Spy attached and the target mode correct? stderr: {err}"
        summary = _parse_spectool_output(result["stdout"])
        if summary["sweep_count"] == 0:
            return (
                "Error: spectool_raw ran but produced no parseable sweep lines in "
                f"{params.duration_seconds}s. Raw stderr: {result['stderr'].strip()[:500]}"
            )
        return json.dumps(summary, indent=2)
    except Exception as e:  # noqa: BLE001
        return _connection_error(e)


# ── wispy_raw_capture ─────────────────────────────────────────────────────────


class RawCaptureInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_seconds: int = Field(default=3, description="How long to capture for.", ge=1, le=15)
    max_lines: int = Field(default=200, description="Truncate output to this many lines to keep the response small.", ge=10, le=2000)


@mcp.tool(
    name="wispy_raw_capture",
    annotations={
        "title": "Capture raw spectool_raw output",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def wispy_raw_capture(params: RawCaptureInput) -> str:
    """Capture raw, unparsed spectool_raw text output — useful for debugging the parser
    in wispy_sweep, or inspecting exact device-config lines spectools_bridge.py expects.

    Args:
        params (RawCaptureInput): duration and a line cap to keep the response bounded.

    Returns:
        str: the raw stdout (truncated to max_lines, with a note if truncated), or
        "Error: <message>" on failure.
    """
    try:
        result = _capture(duration_seconds=params.duration_seconds)
        lines = result["stdout"].splitlines()
        truncated = len(lines) > params.max_lines
        shown = "\n".join(lines[: params.max_lines])
        if truncated:
            shown += f"\n... [truncated, {len(lines) - params.max_lines} more lines]"
        if not shown.strip() and result["stderr"].strip():
            return f"Error: no stdout captured. stderr: {result['stderr'].strip()[:1000]}"
        return shown
    except Exception as e:  # noqa: BLE001
        return _connection_error(e)


if __name__ == "__main__":
    mcp.run()
