# 02 - Pager Payload Contract

## Objective

Define exactly how the Spectools bridge is launched, controlled, and surfaced in the Pineapple Pager payload UX.

## Payload metadata requirements

Follow Pager payload header conventions in `payload.sh`:

```bash
#!/bin/bash
# Title: Spectools Waterfall
# Description: Live RF waterfall and spectrum view from Spectools devices
# Author: <you>
# Category: reconnaissance
# Version: 0.1
```

## Runtime placement

Proposed layout on device:

- Payload root: `/root/payloads/user/reconnaissance/spectools_waterfall/`
- Launcher: `payload.sh`
- Bridge executable/script: `bin/spectools_bridge` or `bin/spectools_bridge.py`
- Optional UI renderer: `bin/spectools_render_tui`
- Config file: `config/spectools_bridge.conf`

## Log and loot conventions

- Runtime logs: `/tmp/spectools_waterfall.log`
- PID file: `/tmp/spectools_waterfall.pid`
- Lock file: `/tmp/spectools_waterfall.lock`
- Loot path: `/root/loot/spectools_waterfall/`
  - snapshots
  - exported JSONL
  - optional CSV summaries

## Button and flow contract

### Primary actions

- **A**: Start scan/view
- **B**: Stop scan/view
- **C**: Change mode (waterfall ↔ summary ↔ peak-hold)
- **X/Y (if mapped)**: Range or sensitivity adjustments

### Expected UX flow

1. Preflight checks (binary exists, perms, interface availability).
2. Present mode picker and source picker (local USB vs net host).
3. Start bridge in background + attach renderer.
4. Show live updates until stop/cancel.
5. Cleanup and optionally offer save/export.

## Process management requirements

- Guard against duplicate runs via lock file + PID check.
- Use `trap` cleanup for `EXIT INT TERM`.
- Kill child bridge/renderer processes on exit.
- Remove stale lock/pid files on startup after validation.

## Error reporting contract

Use Pager-native primitives consistently:

- `LOG` for runtime notes
- LED state changes (`SETUP`, `ATTACK`, `FAIL`, `FINISH`)
- Dialogs for fatal/preflight errors

## Security and safety constraints

- No network listener exposed by default.
- If net mode is enabled, bind locally unless explicitly configured.
- Sanitize all user text inputs before shell execution.
