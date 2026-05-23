---
name: QA Patterns
description: Test patterns and gotchas discovered across SpecPine QA sessions
type: feedback
---

## Waterfall Proof Pattern

To prove the waterfall is running, use this 3-step verification:

1. Check processes: `ps w | grep -E "spectool|spectools|bridge"`
2. Check events file: `tail -20 /tmp/qa_events.jsonl` (or whatever --events-file was used)
3. Run fresh test: `cd /root/payloads/user/reconnaissance/specpine && export LD_LIBRARY_PATH=lib && timeout 10 python3 bin/spectools_bridge.py --input-command "bin/spectool_raw 0" --events-file /tmp/fresh_test.jsonl`

## Stale Process Gotcha

The bridge+spectool_raw processes may appear in `ps` even after a test run completes if they were started with `&` and not properly killed. Check file mtime vs current time to distinguish live vs stale. A file that stopped growing is a stale run.

## Events File Default

The bridge defaults to `/tmp/spectools_bridge_events.jsonl` if no --events-file is given. The waterfall pager renderer also defaults to the same path. Ad-hoc test runs may use different paths (e.g. /tmp/qa_events.jsonl, /tmp/spp_bridge_events.jsonl).

## sweep Cadence

At 2.4GHz band, 285 bins, 333kHz res: ~1.8 sweeps/second (interval ~550ms). In a 10-second window expect ~10 sweeps.

## spectool_raw stdout is debug lines only

spectool_raw writes human-readable debug lines to stdout: "debug - usb read return 64", etc. The bridge parses these via regex. The debug lines are NOT what the waterfall renders — the bridge converts them to JSONL sweep events.

## No stat command on Pager

The Pager's busybox ash does not have `stat`. Use `ls -la` for file timestamps. File growth can be checked via two `wc -c` calls separated by sleep.
