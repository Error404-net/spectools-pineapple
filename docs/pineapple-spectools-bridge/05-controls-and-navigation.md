# 05 - Controls and Navigation

## Objective

Define consistent gamepad button behavior and mode navigation for live RF viewing.

## Button map (proposed)

- **A**: Confirm / Start / Resume
- **B**: Back / Stop / Exit live view
- **C**: Cycle view mode
- **UP/DOWN**: Move selection or adjust scale
- **LEFT/RIGHT**: Frequency window shift (if supported)

## Screen model

### Screen 1: Setup

- Source selection: USB local or network server
- Device selection
- Range/profile selection
- Start action

### Screen 2: Live waterfall

- Main waterfall pane
- Top status: device, range, FPS, latest peak dBm
- Bottom hints for controls

### Screen 3: Summary/Stats

- Current min/max/avg
- Peak hold frequency and level
- Sweep count and elapsed time

### Screen 4: Export/Save

- Save JSONL session
- Save snapshot
- Save summary CSV

## Navigation rules

1. `B` from Setup exits payload.
2. `B` from Live returns to Setup after stopping capture.
3. `C` only changes visualization mode in Live.
4. Long-running operations should display busy indicator.

## Failure-state UX

- If source fails, show action options:
  - retry
  - change source
  - exit

- On disconnect during live mode:
  - freeze last frame
  - show reconnect countdown/status
