---
name: Known Bugs
description: Confirmed defects from QA sessions with reproduction steps
type: project
---

## Lingering Processes from Previous Sessions

Observed 2026-05-17: PIDs 31665/31667/31669 were alive from a May 16 test run. The ash orchestrator script (PID 31665) left bridge+spectool_raw running in the background after the 6-second timed test completed. The events file (/tmp/qa_events.jsonl) stopped growing after the initial 3 sweeps because the parent's kill was issued but the second backgrounded invocation was still attached to the same events file with fd 3 open.

Workaround: `pkill -f spectool_raw; pkill -f spectools_bridge` before fresh test runs.

## WebUI Browser Unreachable from Docker MCP

The Docker MCP browser container does not have network routing to 172.16.52.1. ERR_CONNECTION_REFUSED on all WebUI navigation attempts. WebUI screenshots can only be taken from a host machine on the same network as the Pager.
