#!/usr/bin/env python3
"""
pager_mcp — MCP server for controlling the Hak5 WiFi Pineapple Pager over SSH.

Gives an LLM client safe, repeatable tools to:
  - run arbitrary shell commands on the Pager
  - capture the current LCD frame as a PNG
  - attempt button/D-pad input injection (experimental, see caveats below)
  - list / launch / stop / check status of payloads (e.g. SpecPine)

Why this exists: manual ad hoc SSH experimentation (long-running foreground
commands, hung scripts) previously froze/crashed the device. Every remote
command this server runs is wrapped in the device's own `timeout` so a stuck
remote process can never hang the SSH session or the Pager indefinitely.

Connection config (env vars, all optional):
    PAGER_HOST      default "172.16.52.1"
    PAGER_PORT      default 22
    PAGER_USER      default "root"
    PAGER_PASSWORD  default "qwerty"   (the Pager's documented dev password)

Requires: paramiko, Pillow
    pip install paramiko pillow --break-system-packages   (or in a venv)

Run:
    python3 pager_mcp.py
"""

from __future__ import annotations

import base64
import json
import os
import posixpath
import shlex
import time
from enum import Enum
from typing import Any, Dict, List, Optional

import paramiko
from pydantic import BaseModel, ConfigDict, Field
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("pager_mcp")

# ── Connection config ────────────────────────────────────────────────────────

PAGER_HOST = os.environ.get("PAGER_HOST", "172.16.52.1")
PAGER_PORT = int(os.environ.get("PAGER_PORT", "22"))
PAGER_USER = os.environ.get("PAGER_USER", "root")
PAGER_PASSWORD = os.environ.get("PAGER_PASSWORD", "qwerty")

DEFAULT_PAYLOAD_ROOT = "/root/payloads/user"
DEFAULT_SSH_TIMEOUT = 10  # seconds, for establishing the connection itself

# ── Shared SSH helpers ───────────────────────────────────────────────────────


def _connect() -> paramiko.SSHClient:
    """Open a fresh SSH connection. Callers are responsible for closing it.

    A fresh connection per call (rather than a pooled/persistent one) is
    intentional: the Pager is a flaky embedded device and we'd rather pay a
    small reconnect cost than silently operate over a half-dead session.
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=PAGER_HOST,
        port=PAGER_PORT,
        username=PAGER_USER,
        password=PAGER_PASSWORD,
        timeout=DEFAULT_SSH_TIMEOUT,
        banner_timeout=DEFAULT_SSH_TIMEOUT,
        auth_timeout=DEFAULT_SSH_TIMEOUT,
        look_for_keys=False,
        allow_agent=False,
    )
    return client


def _run_remote(command: str, timeout_s: int) -> Dict[str, Any]:
    """Run `command` on the Pager, hard-bounded by the device's own `timeout`
    utility so a stuck remote process can never hang this call or leak past
    its budget. Returns exit_code/stdout/stderr; never raises for a command
    that ran (only for connection failures).
    """
    wrapped = f"timeout -s KILL {int(timeout_s)} sh -c {shlex.quote(command)}"
    client = _connect()
    try:
        stdin, stdout, stderr = client.exec_command(wrapped, timeout=timeout_s + 5)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        exit_code = stdout.channel.recv_exit_status()
        return {"exit_code": exit_code, "stdout": out, "stderr": err, "timed_out": exit_code == 137}
    finally:
        client.close()


def _connection_error(e: Exception) -> str:
    return (
        f"Error: could not reach the Pager at {PAGER_USER}@{PAGER_HOST}:{PAGER_PORT} "
        f"({type(e).__name__}: {e}). Check that the Pager is powered on, on the same "
        f"network, and that PAGER_HOST/PAGER_PASSWORD env vars are correct."
    )


# ── pager_run_command ────────────────────────────────────────────────────────


class RunCommandInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    command: str = Field(
        ...,
        description="Shell command to run on the Pager, e.g. 'pgrep -fa specpine' or 'cat /tmp/specpine.log'.",
        min_length=1,
        max_length=4000,
    )
    timeout_seconds: int = Field(
        default=15,
        description="Hard kill timeout in seconds. The command is always wrapped in the device's `timeout` "
        "utility so it cannot hang the Pager or this call. Keep this short for anything that might block "
        "(e.g. reading an input device) — see pager_press_button's caveats.",
        ge=1,
        le=120,
    )


@mcp.tool(
    name="pager_run_command",
    annotations={
        "title": "Run a shell command on the Pager",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def pager_run_command(params: RunCommandInput) -> str:
    """Run an arbitrary shell command on the Pager over SSH and return its output.

    The command always runs under the device's own `timeout -s KILL <n>` so it is
    force-killed if it doesn't finish in time — this cannot hang the Pager or this
    tool call the way a raw `ssh ... long-running-thing` could.

    Args:
        params (RunCommandInput): command to run, and a timeout budget.

    Returns:
        str: JSON object: {"exit_code": int, "stdout": str, "stderr": str, "timed_out": bool}.
        exit_code 137 / timed_out=true means the command was killed for exceeding timeout_seconds.

    Examples:
        - Use when: "what's running on the pager right now" -> command="ps | grep -i specpine"
        - Use when: "show me the last specpine log lines" -> command="tail -n 50 /tmp/specpine.log"
        - Don't use when: you want a screenshot of the LCD (use pager_capture_screen)
        - Don't use when: you want to launch/stop a payload (use pager_launch_payload / pager_stop_payload,
          which already build safe detached commands for you)
    """
    try:
        result = _run_remote(params.command, params.timeout_seconds)
        return json.dumps(result, indent=2)
    except Exception as e:  # noqa: BLE001
        return _connection_error(e)


# ── pager_capture_screen ─────────────────────────────────────────────────────


class CaptureScreenInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    save_path: Optional[str] = Field(
        default=None,
        description="Local filesystem path to save the PNG to. If omitted, saves to "
        "/tmp/pager_screen_<timestamp>.png and that path is returned.",
    )
    rotate: bool = Field(
        default=True,
        description="Rotate the raw portrait framebuffer (222x480) into the landscape "
        "orientation (480x222) the Pager actually displays. Set False to debug raw fb0 bytes.",
    )


@mcp.tool(
    name="pager_capture_screen",
    annotations={
        "title": "Capture the Pager's current LCD frame",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def pager_capture_screen(params: CaptureScreenInput) -> str:
    """Capture whatever is currently on the Pager's physical LCD and save it as a PNG.

    Reads the raw /dev/fb0 framebuffer over SSH (RGB565, physical 222x480 portrait
    buffer; the Pager renders it as 480x222 landscape) and decodes it locally with
    Pillow. This is read-only and safe to call at any time, including while another
    process (SpecPine, a renderer, the native pineapple UI) owns the display.

    Args:
        params (CaptureScreenInput): optional save_path, and whether to rotate to landscape.

    Returns:
        str: JSON {"saved_to": str, "width": int, "height": int} on success, or
        "Error: <message>" on failure (e.g. device unreachable, fb0 unreadable).

    Examples:
        - Use when: "what does the screen show right now" -> call with defaults, then
          read the resulting PNG file.
        - Use when: confirming whether pager_press_button or pager_launch_payload had
          any visible effect — capture before and after and compare.
    """
    try:
        # Mirrors the read pattern already proven in scripts/fb_waterfall_smoketest.sh:
        # cat the fixed-size fb0 region directly, base64 it for safe transport over SSH.
        w, h = 222, 480
        size = w * h * 2
        cmd = (
            "python3 -c \"import sys,base64; "
            f"d=open('/dev/fb0','rb').read({size}); "
            "sys.stdout.write(base64.b64encode(d).decode())\""
        )
        result = _run_remote(cmd, timeout_s=10)
        if result["exit_code"] != 0:
            return (
                f"Error: failed to read /dev/fb0 (exit {result['exit_code']}). "
                f"stderr: {result['stderr'].strip()[:500]}"
            )
        raw = base64.b64decode(result["stdout"].strip())
        if len(raw) < size:
            return (
                f"Error: only got {len(raw)} of {size} expected bytes from /dev/fb0 — "
                "the framebuffer may not be the size CLAUDE.md documents, or fb0 is missing."
            )

        from PIL import Image

        pixels: List[tuple] = []
        for i in range(0, size, 2):
            val = raw[i] | (raw[i + 1] << 8)
            r5 = (val >> 11) & 0x1F
            g6 = (val >> 5) & 0x3F
            b5 = val & 0x1F
            pixels.append(((r5 * 255) // 31, (g6 * 255) // 63, (b5 * 255) // 31))

        img = Image.new("RGB", (w, h))
        img.putdata(pixels)

        out_w, out_h = w, h
        if params.rotate:
            img = img.rotate(-90, expand=True)
            out_w, out_h = h, w

        save_path = params.save_path or f"/tmp/pager_screen_{int(time.time())}.png"
        img.save(save_path)
        return json.dumps({"saved_to": save_path, "width": out_w, "height": out_h})
    except Exception as e:  # noqa: BLE001
        return _connection_error(e) if isinstance(e, (paramiko.SSHException, OSError)) else f"Error: {type(e).__name__}: {e}"


# ── pager_list_input_devices (diagnostic, for button-press research) ────────


@mcp.tool(
    name="pager_list_input_devices",
    annotations={
        "title": "List the Pager's input devices",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def pager_list_input_devices() -> str:
    """List /proc/bus/input/devices and /dev/input/* on the Pager.

    Diagnostic helper for figuring out exactly which device node the physical
    D-pad/buttons appear on and what event codes they emit (the actual button
    keycodes are not yet confirmed — see pager_press_button's caveats). Run this
    first, then physically press a button and run it again or tail an `evtest`
    capture via pager_run_command to see which device reacts.

    Returns:
        str: JSON {"proc_bus_input_devices": str, "dev_input_listing": str}.
    """
    try:
        devices = _run_remote("cat /proc/bus/input/devices", timeout_s=5)
        listing = _run_remote("ls -la /dev/input/ 2>&1", timeout_s=5)
        return json.dumps(
            {
                "proc_bus_input_devices": devices["stdout"],
                "dev_input_listing": listing["stdout"],
            },
            indent=2,
        )
    except Exception as e:  # noqa: BLE001
        return _connection_error(e)


# ── pager_press_button (EXPERIMENTAL) ────────────────────────────────────────


class PagerButton(str, Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    OK = "ok"
    BACK = "back"


# Best-guess Linux evdev keycodes for a typical 5-way D-pad + back button.
# UNVERIFIED against this specific device's input driver — see docstring caveats.
_BUTTON_KEYCODES = {
    PagerButton.UP: 103,    # KEY_UP
    PagerButton.DOWN: 108,  # KEY_DOWN
    PagerButton.LEFT: 105,  # KEY_LEFT
    PagerButton.RIGHT: 106, # KEY_RIGHT
    PagerButton.OK: 28,     # KEY_ENTER
    PagerButton.BACK: 1,    # KEY_ESC
}


class PressButtonInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    button: PagerButton = Field(..., description="Which button to simulate: up, down, left, right, ok, back.")
    event_device: str = Field(
        default="/dev/input/event0",
        description="Input device node to write to. funcs_main.sh's start_evtest reads /dev/input/event0 "
        "for the real D-pad, so that's the default — confirm with pager_list_input_devices if unsure.",
    )


@mcp.tool(
    name="pager_press_button",
    annotations={
        "title": "Simulate a Pager button press (EXPERIMENTAL)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def pager_press_button(params: PressButtonInput) -> str:
    """Attempt to simulate a D-pad/button press by writing a synthetic evdev EV_KEY event
    directly to the Pager's input device node.

    *** EXPERIMENTAL — the exact keycodes and whether the kernel driver behind
    /dev/input/event0 even accepts writes are UNVERIFIED on this hardware. ***
    Many embedded GPIO-keypad drivers expose a read-only event node — writes may
    fail harmlessly (ENOTTY/EINVAL, which this tool reports as an error), or may
    silently do nothing. This tool deliberately runs under a 3-second hard kill
    timeout so a bad write attempt cannot hang the device or this call the way the
    earlier manual `specpine_splash.py` SSH invocation reportedly did.

    Recommended usage: call pager_capture_screen before and after to see whether
    anything actually changed. If nothing changes, the real button input is most
    likely injected by hardware/kernel means this tool can't reach, and physical
    presses (or the Virtual Pager simulator's own UI) remain the reliable path —
    use pager_list_input_devices to keep investigating the real mechanism.

    Args:
        params (PressButtonInput): which logical button, and which device node to target.

    Returns:
        str: JSON {"attempted": str, "keycode": int, "exit_code": int, "stderr": str}
        on completion (exit_code 0 does NOT guarantee the press registered — only
        that the write syscall didn't error), or "Error: <message>" on connection failure.
    """
    keycode = _BUTTON_KEYCODES[params.button]
    # Two EV_KEY events (press + release) followed by an EV_SYN report, per the
    # standard Linux `struct input_event { tv_sec, tv_usec, type, code, value }`
    # layout (16 bytes on most 32-bit embedded targets: 2x int32 time + 3x int16... ).
    # mipsel_24kc is 32-bit, so we use the 32-bit timeval layout (4+4+2+2+4 = 16 bytes).
    py = f"""
import struct, time
def ev(t, c, v):
    sec = int(time.time())
    usec = 0
    return struct.pack('iiHHi', sec, usec, t, c, v)
EV_KEY, EV_SYN = 1, 0
SYN_REPORT = 0
data = ev(EV_KEY, {keycode}, 1) + ev(EV_SYN, SYN_REPORT, 0)
data += ev(EV_KEY, {keycode}, 0) + ev(EV_SYN, SYN_REPORT, 0)
with open({params.event_device!r}, 'wb') as f:
    f.write(data)
"""
    cmd = f"python3 -c {shlex.quote(py)}"
    try:
        result = _run_remote(cmd, timeout_s=3)
        return json.dumps(
            {
                "attempted": params.button.value,
                "device": params.event_device,
                "keycode": keycode,
                "exit_code": result["exit_code"],
                "stderr": result["stderr"].strip(),
                "note": "exit_code 0 means the write syscall succeeded, not that the press registered. "
                "Verify visually with pager_capture_screen.",
            },
            indent=2,
        )
    except Exception as e:  # noqa: BLE001
        return _connection_error(e)


# ── Payload management ───────────────────────────────────────────────────────


class ListPayloadsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload_root: str = Field(
        default=DEFAULT_PAYLOAD_ROOT,
        description="Root directory to search for payload.sh files.",
    )


@mcp.tool(
    name="pager_list_payloads",
    annotations={
        "title": "List installed payloads",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def pager_list_payloads(params: ListPayloadsInput) -> str:
    """List installed payloads on the Pager (anything with a payload.sh under payload_root),
    along with whether each currently appears to be running.

    Args:
        params (ListPayloadsInput): payload_root, default /root/payloads/user.

    Returns:
        str: JSON {"payloads": [{"name": str, "path": str, "running": bool, "pid": int|null}, ...]}
        or "Error: <message>" on failure.
    """
    try:
        find_cmd = f"find {shlex.quote(params.payload_root)} -maxdepth 3 -name payload.sh 2>/dev/null"
        result = _run_remote(find_cmd, timeout_s=10)
        paths = [p for p in result["stdout"].splitlines() if p.strip()]
        payloads = []
        for path in paths:
            name = posixpath.basename(posixpath.dirname(path))
            pgrep = _run_remote(f"pgrep -f {shlex.quote(path)}", timeout_s=5)
            pids = [int(p) for p in pgrep["stdout"].split() if p.strip().isdigit()]
            payloads.append(
                {
                    "name": name,
                    "path": path,
                    "running": len(pids) > 0,
                    "pid": pids[0] if pids else None,
                }
            )
        return json.dumps({"payloads": payloads}, indent=2)
    except Exception as e:  # noqa: BLE001
        return _connection_error(e)


class LaunchPayloadInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    payload_path: str = Field(
        ...,
        description="Full path to the payload.sh to launch, e.g. "
        "'/root/payloads/user/reconnaissance/specpine/payload.sh' (get this from pager_list_payloads).",
        min_length=1,
    )


@mcp.tool(
    name="pager_launch_payload",
    annotations={
        "title": "Launch a payload",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def pager_launch_payload(params: LaunchPayloadInput) -> str:
    """Launch a payload.sh in the background (detached, survives the SSH session ending).

    IMPORTANT CAVEAT: this runs the script over SSH, NOT through the Pager's own
    payload launcher UI. Real menu-driven payloads typically block on button-press
    events (LIST_PICKER, WAIT_FOR_BUTTON_PRESS) — those will hang waiting for input
    that an SSH-launched, non-interactive session may never deliver the way the real
    launcher does. This is a known open question for SpecPine specifically (it runs
    to completion over SSH but historically never visibly updates the LCD). Use this
    tool to reproduce/diagnose that, not as a guaranteed equivalent of a real launch.

    Args:
        params (LaunchPayloadInput): full path to payload.sh.

    Returns:
        str: JSON {"pid": int, "log_file": str} on success, "Error: <message>" on failure.
    """
    try:
        name = posixpath.basename(posixpath.dirname(params.payload_path))
        log_file = f"/tmp/pager_mcp_launch_{name}.log"
        cmd = f"nohup bash {shlex.quote(params.payload_path)} > {shlex.quote(log_file)} 2>&1 & echo $!"
        # No outer timeout here — the launched process is detached (backgrounded with
        # nohup + &), so the *launching* shell returns almost immediately regardless.
        client = _connect()
        try:
            stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
            out = stdout.read().decode("utf-8", "replace").strip()
            err = stderr.read().decode("utf-8", "replace").strip()
        finally:
            client.close()
        if not out.isdigit():
            return f"Error: launch did not return a PID. stdout={out!r} stderr={err!r}"
        return json.dumps({"pid": int(out), "log_file": log_file})
    except Exception as e:  # noqa: BLE001
        return _connection_error(e)


class StopPayloadInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    payload_path: Optional[str] = Field(
        default=None, description="Full path to the payload.sh to stop (matched via pkill -f)."
    )
    pid: Optional[int] = Field(default=None, description="Specific PID to kill instead of matching by path.")


@mcp.tool(
    name="pager_stop_payload",
    annotations={
        "title": "Stop a running payload",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def pager_stop_payload(params: StopPayloadInput) -> str:
    """Stop a running payload by PID or by path (pkill -f match).

    Sends SIGTERM first; this does not force-kill (-9) so the payload's own
    `cleanup` trap (config restore, lock release, loot finalization) gets a
    chance to run, matching how SpecPine and similar payloads expect to exit.

    Args:
        params (StopPayloadInput): exactly one of pid or payload_path.

    Returns:
        str: JSON {"signaled": bool, "method": str} or "Error: <message>".
    """
    if not params.pid and not params.payload_path:
        return "Error: provide either pid or payload_path."
    try:
        if params.pid:
            result = _run_remote(f"kill -TERM {int(params.pid)}", timeout_s=5)
            method = f"kill -TERM {params.pid}"
        else:
            result = _run_remote(f"pkill -TERM -f {shlex.quote(params.payload_path)}", timeout_s=5)
            method = f"pkill -TERM -f {params.payload_path}"
        return json.dumps({"signaled": result["exit_code"] == 0, "method": method, "exit_code": result["exit_code"]})
    except Exception as e:  # noqa: BLE001
        return _connection_error(e)


class PayloadStatusInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    payload_path: str = Field(..., description="Full path to the payload's payload.sh.", min_length=1)
    log_tail_lines: int = Field(default=40, description="How many lines of the launch log / specpine.log to include.", ge=1, le=500)


@mcp.tool(
    name="pager_payload_status",
    annotations={
        "title": "Check a payload's run status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def pager_payload_status(params: PayloadStatusInput) -> str:
    """Check whether a payload is currently running and pull recent log context.

    Args:
        params (PayloadStatusInput): payload path and how many log lines to include.

    Returns:
        str: JSON {"running": bool, "pids": [int], "log_tail": str} or "Error: <message>".
        log_tail concatenates /tmp/pager_mcp_launch_<name>.log and /tmp/specpine.log
        (whichever exist) since most payloads log to one of those.
    """
    try:
        name = posixpath.basename(posixpath.dirname(params.payload_path))
        pgrep = _run_remote(f"pgrep -f {shlex.quote(params.payload_path)}", timeout_s=5)
        pids = [int(p) for p in pgrep["stdout"].split() if p.strip().isdigit()]
        log_cmd = (
            f"for f in /tmp/pager_mcp_launch_{shlex.quote(name)}.log /tmp/specpine.log; do "
            f"[ -f \"$f\" ] && echo \"--- $f ---\" && tail -n {params.log_tail_lines} \"$f\"; done"
        )
        logs = _run_remote(log_cmd, timeout_s=10)
        return json.dumps({"running": len(pids) > 0, "pids": pids, "log_tail": logs["stdout"]}, indent=2)
    except Exception as e:  # noqa: BLE001
        return _connection_error(e)


if __name__ == "__main__":
    mcp.run()
