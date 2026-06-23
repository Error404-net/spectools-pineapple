# mcp-servers

Two local MCP servers for working with the WiFi Pineapple Pager and its
Wi-Spy DBx dongle without manual ad hoc SSH/browser-click sessions (one of
which previously hung the device and required a reboot).

- `pager_mcp/` — SSH-based control of the Pager itself: run commands, capture
  the LCD as a PNG, attempt button-press injection (experimental), and
  list/launch/stop/check payloads.
- `wispy_mcp/` — Wi-Spy DBx control, switchable between "remote" (dongle in
  the Pager's USB port, driven via SSH) and "local" (dongle plugged into this
  Mac directly).

## One-time setup

```bash
cd mcp-servers/pager_mcp  && pip install -r requirements.txt --break-system-packages
cd ../wispy_mcp           && pip install -r requirements.txt --break-system-packages
```

(Drop `--break-system-packages` if you're using a venv instead — recommended
if you'd rather not touch system Python.)

## Registering with Claude

Add both to your MCP client config (e.g. `claude_desktop_config.json`, or
wherever Cowork/Claude Code reads MCP server definitions):

```json
{
  "mcpServers": {
    "pager": {
      "command": "python3",
      "args": ["/Users/Jesse/GitHub/spectools-pineapple/mcp-servers/pager_mcp/pager_mcp.py"],
      "env": {
        "PAGER_HOST": "172.16.52.1",
        "PAGER_PASSWORD": "qwerty"
      }
    },
    "wispy": {
      "command": "python3",
      "args": ["/Users/Jesse/GitHub/spectools-pineapple/mcp-servers/wispy_mcp/wispy_mcp.py"],
      "env": {
        "PAGER_HOST": "172.16.52.1",
        "PAGER_PASSWORD": "qwerty",
        "WISPY_TARGET_MODE": "remote"
      }
    }
  }
}
```

Restart Claude Desktop (or reload the Cowork session) after editing the
config for the new servers to be picked up.

## Day-to-day use

- **Pager**: just use `pager_run_command`, `pager_capture_screen`,
  `pager_list_payloads` / `pager_launch_payload` / `pager_stop_payload` /
  `pager_payload_status` directly — no setup needed beyond the env vars above.
- **Wi-Spy**: tell it where the dongle is whenever it moves:
  - "the Wi-Spy is in the Pager" → `wispy_set_target(mode="remote")` (also the default)
  - "I moved the Wi-Spy to my Mac" → `wispy_set_target(mode="local")`
  - Local mode needs a **native** (not MIPS) `spectool_raw` built on the Mac —
    see the note at the top of `wispy_mcp.py` for the build command.

## Safety notes

- Every remote shell command `pager_mcp` and `wispy_mcp` (remote mode) run is
  wrapped in the device's own `timeout -s KILL <n>`, so a stuck remote process
  (the exact failure mode that hung the Pager before) gets force-killed
  instead of hanging the SSH session or the device.
- `pager_press_button` is explicitly experimental — the real button-injection
  mechanism on this hardware hasn't been confirmed yet (see task: "Investigate
  real button-press mechanism on Pager hardware"). It runs under a 3s kill
  timeout for the same reason. Verify any button-press attempt with
  `pager_capture_screen` before/after rather than trusting exit_code 0.
- `pager_launch_payload` launches payload.sh over SSH directly, which is NOT
  the same code path as launching it from the Pager's own menu (menu-driven
  payloads often block on real button-press events). This is intentional —
  it's the tool for reproducing/diagnosing the "SpecPine runs but never shows
  on screen" bug, not a guaranteed equivalent of a real launch.
