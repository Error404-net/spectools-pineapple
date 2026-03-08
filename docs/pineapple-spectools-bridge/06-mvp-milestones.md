# 06 - MVP Milestones

## Objective

Provide a concrete incremental plan from parsing to usable Pager experience.

## Milestone 1 - Bridge parser skeleton

Deliverables:

- Bridge process reads `spectool_raw` output.
- Emits validated JSONL events (`status`, `device_config`, `sweep`, `error`).

Acceptance:

- Can parse a captured sample log without crashing.

## Milestone 2 - Payload launcher integration

Deliverables:

- `payload.sh` starts/stops bridge cleanly.
- lock/pid/trap lifecycle implemented.

Acceptance:

- Duplicate launch is blocked and stale lock recovery works.

## Milestone 3 - Basic waterfall renderer

Deliverables:

- Terminal waterfall consuming bridge JSONL.
- Mode toggle: waterfall vs stats.

Acceptance:

- Stable display for sustained scan sessions.

## Milestone 4 - Data export and loot integration

Deliverables:

- JSONL/CSV/session metadata saved into `/root/loot/...`.

Acceptance:

- Export files created with timestamps and non-empty payload.

## Milestone 5 - Resilience hardening

Deliverables:

- reconnect/retry flow
- malformed line handling
- watchdog logging

Acceptance:

- Handles source interruptions without requiring manual cleanup.

## Milestone 6 - Optional net protocol ingestion

Deliverables:

- `spectool_net` decoder path behind configuration switch.

Acceptance:

- Event outputs remain schema-compatible with text-ingest path.
