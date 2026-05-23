---
name: Device Facts
description: Hardware, firmware, Wi-Spy USB ID, binary details, and verified pipeline facts
type: project
---

## Pager Device

- SSH: root@172.16.52.1, password: qwerty
- OS: Linux pager 6.6.86, mips, WiFi Pineapple Pager (OpenWrt)
- Firmware: 24.10.1 (mipsel_24kc / ramips/mt76x8)
- WebUI: http://172.16.52.1 — NOT reachable from Docker browser container (ERR_CONNECTION_REFUSED); all WebUI interaction must be done from a host with network access to 172.16.52.1

## Wi-Spy Hardware

- USB ID: 1dd5:5002 (MetaGeek Wi-Spy DBx3)
- Device name in events: "Wi-Spy DBx USB 2417295654"
- Device ID: 2417295654
- Frequency range: 2400000–2495000 kHz (2.4 GHz band)
- Bin count: 285 bins
- Resolution: 333 Hz (333000 Hz)
- Sweep cadence: ~1.8 sweeps/second (sweep interval ~550ms)

## Payload Location

- Deployed at: /root/payloads/user/reconnaissance/specpine/
- Not at /root/specpine/ (that path does not exist)
- LD_LIBRARY_PATH for execution: lib (relative, when cd'd into payload dir)

## Binary Verification

- spectool_raw confirmed working: MIPS binary, runs against plugged Wi-Spy DBx3
- spectool_raw stdout produces debug lines: "debug - usb read return 64", "debug - about to enter blocking select", etc.
- Bridge (spectools_bridge.py) correctly parses spectool_raw native output and emits JSONL

## Pipeline Verified (2026-05-17)

Full data flow confirmed:
  spectool_raw 0 → spectools_bridge.py → /tmp/*.jsonl → spectools_waterfall_pager.py → ASCII rows

Fresh 10-second test produced 10 sweep events with plausible 2.4GHz RSSI values:
  min: -103 to -118 dBm (noise floor)
  max: -31 to -35 dBm (signals detected)
  avg: -78 to -91 dBm
  all 285 bins populated per sweep
