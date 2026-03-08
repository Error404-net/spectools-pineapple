# 01 - Spectools Data Contract

## Objective

Define a stable, device-agnostic event schema for a bridge layer that ingests Spectools data and emits Pager-friendly records.

## Source inputs

### A) `spectool_raw` text stream (MVP)

Current `spectool_raw` emits line-oriented output such as:

- Device/range/config lines
- Sweep lines: `<device_name>: <rssi_0> <rssi_1> ...`

This source is easiest to adopt immediately, because it requires no Spectools code changes.

### B) `spectool_net` frames (future)

The network protocol provides structured frames for:

- device descriptors
- sweep blocks
- command/messages

This source is more robust but requires frame decoding.

## Canonical internal event schema

All bridge output should normalize into one of these event types:

### `device_config`

```json
{
  "type": "device_config",
  "timestamp": "2026-01-01T12:00:00.123Z",
  "device_id": "optional-int-or-null",
  "device_name": "WiSPY 24x",
  "freq_start_khz": 2400000,
  "freq_end_khz": 2483500,
  "bin_count": 83,
  "res_hz": 1000000,
  "source": "spectool_raw"
}
```

### `sweep`

```json
{
  "type": "sweep",
  "timestamp": "2026-01-01T12:00:00.456Z",
  "device_id": "optional-int-or-null",
  "device_name": "WiSPY 24x",
  "freq_start_khz": 2400000,
  "freq_end_khz": 2483500,
  "bin_count": 83,
  "rssi_bins": [-91, -89, -90, -88],
  "stats": {
    "min": -97,
    "max": -49,
    "avg": -82.4
  },
  "source": "spectool_raw"
}
```

### `status`

```json
{
  "type": "status",
  "timestamp": "2026-01-01T12:00:00.789Z",
  "level": "info",
  "message": "Configured device WiSPY 24x"
}
```

### `error`

```json
{
  "type": "error",
  "timestamp": "2026-01-01T12:00:01.000Z",
  "code": "DEVICE_DISCONNECTED",
  "message": "Error polling spectool device",
  "recoverable": true
}
```

## Transport from bridge to renderer/UI

## MVP choice

- **JSONL (line-delimited JSON)** over stdout.
- Optional tee to file for debug replay:
  - `/tmp/spectools_bridge_events.jsonl`

## Optional runtime transports (later)

- Unix domain socket for local subscribers
- lightweight HTTP stream endpoint (if needed by Virtual Pager extension)

## Parsing and reliability rules

1. Ignore unknown non-sweep lines unless they map to `status`/`error`.
2. Track the latest known config per device; attach config to sweep events.
3. If sample count changes unexpectedly, emit `status` + adapt bin mapping.
4. On malformed sweep lines, emit `error` and continue (do not crash).
5. If data source stalls past timeout threshold, emit `status` level `warning`.

## Edge-case handling

- **No devices found**: emit terminal `error` and non-zero exit.
- **Partial lines**: buffer until newline or timeout.
- **Reconnect**: emit `status` reconnect attempt events.
- **High-rate sweeps**: allow renderer-side decimation while preserving raw events.
