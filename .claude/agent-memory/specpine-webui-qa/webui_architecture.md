---
name: WebUI Architecture
description: Pager WebUI accessibility from test environment and known limitations
type: project
---

## WebUI Access Constraint

The Pager WebUI at http://172.16.52.1 is NOT reachable from the Docker-based browser MCP tools (ERR_CONNECTION_REFUSED). The Docker container does not have network routing to the Pager's subnet. All WebUI testing must be done by a human operator on the same network segment, or the browser MCP must be invoked from the host machine directly.

## Waterfall Renderer Architecture

The waterfall renderers do NOT output to WebUI or stdout in the normal run path:
- `spectools_waterfall_pager.py`: reads from an events JSONL file (--events-file arg, default /tmp/spectools_bridge_events.jsonl), tails it with --follow. Does NOT read from stdin.
- `spectools_waterfall_fb.py`: writes RGB565 directly to /dev/fb0 (physical framebuffer). Invisible in WebUI.

The Pager LOG stream (LOG command) is the WebUI-visible output channel. The waterfall ASCII rows are emitted via LOG in payload.sh, not directly by the Python renderer.

## How to Invoke the Pipeline Correctly

```bash
cd /root/payloads/user/reconnaissance/specpine
export LD_LIBRARY_PATH=lib
# Start bridge writing to events file:
python3 bin/spectools_bridge.py --input-command "bin/spectool_raw 0" --events-file /tmp/events.jsonl &
# Start waterfall reading from that events file:
python3 bin/spectools_waterfall_pager.py --events-file /tmp/events.jsonl --follow
```

Pipe bridge stdout -> waterfall stdin does NOT work (waterfall reads file, not stdin).
