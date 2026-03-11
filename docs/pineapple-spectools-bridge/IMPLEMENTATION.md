# Spectools Bridge Implementation Notes

## Added components

- `bridge/spectools_bridge.py`
  - Parses `spectool_raw` text into JSONL events: `status`, `device_config`, `sweep`, and `error`.
  - Supports replay mode (`--replay-file`) and live command mode (`--input-command`).
  - Includes watchdog-style stall warnings, restart attempts, malformed-line tolerance, and optional exports.
- `bridge/spectools_render_tui.py`
  - Consumes bridge JSONL and renders an ANSI waterfall (or stats mode).
  - Includes decimation/downsampling and runtime controls (`c`, `p`, `s`, `q`).
- `payloads/spectools_waterfall/payload.sh`
  - Pager-compatible launcher with lock/pid/trap lifecycle handling.
  - Performs preflight checks, source selection, and start/stop orchestration.
  - Streams live bridge output to the renderer via FIFO so the waterfall is shown in real time (waterfall/stats modes).
- `bridge/fixtures/spectool_raw_sample.log`
  - Replay fixture for local testing.
- `config/spectools_bridge.conf`
  - Optional runtime overrides.

## Quick usage

Replay the bridge against fixture data:

```bash
./bridge/spectools_bridge.py --replay-file bridge/fixtures/spectool_raw_sample.log
```

Write events and exports:

```bash
./bridge/spectools_bridge.py \
  --replay-file bridge/fixtures/spectool_raw_sample.log \
  --events-file /tmp/spectools_bridge_events.jsonl \
  --export-dir /tmp/spectools_loot
```

Render waterfall from generated events:

```bash
./bridge/spectools_render_tui.py --input-file /tmp/spectools_bridge_events.jsonl
```

Run payload launcher directly:

```bash
./payloads/spectools_waterfall/payload.sh
```

## Live waterfall behavior

From the payload, pressing **A** now starts the bridge and opens the renderer in the foreground so you can see a live ANSI waterfall. Exit live view with `q`/`b` in the renderer, then the payload returns to setup controls.
