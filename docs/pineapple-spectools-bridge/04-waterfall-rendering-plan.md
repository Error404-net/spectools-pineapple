# 04 - Waterfall Rendering Plan

## Objective

Define a practical waterfall rendering approach suitable for Pineapple Pager constraints while still feeling modern.

## Rendering modes

### Mode 1: Text/ANSI waterfall (MVP)

- Render each sweep as a heatmap row in terminal-friendly output.
- Use fixed-width bins mapped to color blocks.
- Keep dependencies near-zero.

### Mode 2: Lightweight web/virtual pager view (Phase 2)

- Consume bridge JSONL stream and draw canvas-based waterfall.
- Add richer overlays (peak trace, channel markers, cursor readout).

## Visual mapping

- RSSI to color bands (example):
  - `<= -95`: dark/black
  - `-94..-85`: blue
  - `-84..-75`: cyan/green
  - `-74..-65`: yellow
  - `>= -64`: red/white hot

- Bin-to-column mapping:
  - If source bins > display columns: downsample by max/avg chunk
  - If source bins < display columns: duplicate/interpolate bins

## Performance envelope

- Target UI update rate: **4–10 FPS**.
- Ring buffer depth: **100–300 rows** depending on mode.
- Decimation policy:
  - Preserve latest sweep always.
  - Drop intermediate sweeps when renderer lags.

## UI states

- `INITIALIZING`
- `SCANNING`
- `PAUSED`
- `NO_DATA`
- `DISCONNECTED`
- `ERROR`

Each state should have a clear banner/status line.

## Export and diagnostics

- Save snapshot image/text frame to loot path.
- Export raw bridge JSONL session.
- Export summarized CSV with timestamped min/max/avg per sweep.

## Accessibility and usability

- High-contrast palette default.
- Optional monochrome mode.
- Optional reduced-motion mode (lower refresh, less blinking).
