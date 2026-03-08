# 07 - Prompt Sequence

Use these prompts in order to implement the bridge safely and incrementally.

## Prompt 1 - Build parser MVP

"Create a bridge script that reads `spectool_raw` lines from stdin and emits JSONL events (`status`, `device_config`, `sweep`, `error`) matching `docs/pineapple-spectools-bridge/01-spectools-data-contract.md`. Include a replay mode that reads from a logfile for local testing."

Expected outputs:

- `bridge/spectools_bridge.py` (or shell equivalent)
- sample input fixture
- quick usage notes

Acceptance:

- Replay mode outputs parseable JSONL.

## Prompt 2 - Build payload launcher

"Create a Pager-compatible `payload.sh` that manages start/stop/status of the bridge using lockfile + pid + trap cleanup as defined in `02-pager-payload-contract.md`."

Expected outputs:

- `payloads/spectools_waterfall/payload.sh`

Acceptance:

- Start/stop works and duplicate runs are blocked.

## Prompt 3 - Build waterfall renderer

"Create a lightweight terminal waterfall renderer consuming bridge JSONL and implement color mapping + decimation from `04-waterfall-rendering-plan.md`."

Expected outputs:

- `bridge/spectools_render_tui.py`

Acceptance:

- Live or replay mode displays stable waterfall.

## Prompt 4 - Add controls/navigation

"Implement control flow and mode switching per `05-controls-and-navigation.md`, including setup/live/stats/export screens and button mapping notes for Pager integration."

Expected outputs:

- updated launcher + renderer docs/code

Acceptance:

- Modes switch cleanly and stop/exit behavior is deterministic.

## Prompt 5 - Add exports and loot wiring

"Add JSONL + CSV + snapshot export to `/root/loot/spectools_waterfall/` and include runtime metadata in each session."

Expected outputs:

- export helpers
- documented output filenames

Acceptance:

- Export files appear and contain valid data.

## Prompt 6 - Harden error/reconnect logic

"Add robust error handling for malformed lines, stalled source, disconnect/reconnect, and unexpected process exit. Ensure graceful cleanup in all cases."

Expected outputs:

- improved bridge resiliency
- troubleshooting notes

Acceptance:

- Restart/recovery path functions without manual file cleanup.
