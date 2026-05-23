# SpecPine Waterfall — Proof of Operation

**Date**: 2026-05-17  
**Time**: 12:07–12:09 UTC  
**Device**: WiFi Pineapple Pager at 172.16.52.1 (Linux pager 6.6.86, up 14 days)  
**Test runner**: specpine-webui-qa agent

---

## 1. Hardware Enumerated

`lsusb` output from the Pager:

```
Bus 001 Device 001: ID 1d6b:0002 Linux 6.6.86 ehci_hcd EHCI Host Controller
Bus 001 Device 002: ID 1a40:0101  USB 2.0 Hub
Bus 001 Device 003: ID 1a86:55de wch.cn UART+SPI+I2C+JTAG
Bus 001 Device 004: ID 0e8d:7961 MediaTek Inc. Wireless_Device
Bus 001 Device 005: ID 1dd5:5002 MetaGeek Wi-Spy DBx3
```

Wi-Spy DBx3 (`1dd5:5002`) is present and enumerated.

---

## 2. Processes Running

```
31665 root      1424 S    ash -c cd /root/payloads/user/reconnaissance/specpine ...
31667 root     12684 S    python3 bin/spectools_bridge.py --input-command bin/spectool_raw 0 --events-file /tmp/qa_events.jsonl
31669 root      1812 S    bin/spectool_raw 0
```

`spectool_raw` (PID 31669) and the bridge (PID 31667) are both running. PID 31669's parent is PID 31667 — the bridge spawned it as a subprocess. `spectool_raw` is in `futex_wait_queue`, blocked on a USB poll between sweeps — correct state for a live USB device reader.

---

## 3. spectool_raw Actively Producing Output

Reading directly from spectool_raw's stdout pipe in real time:

```
debug - usb read return 64
debug - about to enter blocking select
debug - blocking select completed
debug - usb_interrupt_read
debug - dbx_usb_poll
```

The USB read/poll cycle is running continuously.

---

## 4. Bridge JSONL Events — Fresh 10-Second Test Run

Clean test run at `2026-05-17T12:07:36–12:07:42 UTC`. Bridge produced 15 lines: 2 status, 1 device_config, 10 sweeps, 1 stop.

**device_config event** (device enumerated and configured by bridge):

```json
{"type":"device_config","timestamp":"2026-05-17T12:07:37.475+00:00","device_id":"2417295654","device_name":"Wi-Spy DBx USB 2417295654","freq_start_khz":2400000,"freq_end_khz":2495000,"bin_count":285,"res_hz":333000,"source":"spectool_raw"}
```

**Sweep stats summary** (10 sweeps in 5.15 seconds = ~1.94 sweeps/sec):

```
sweep  1: ts=2026-05-17T12:07:37.492  min=-116  max=-35  avg=-91.19  bins=285
sweep  2: ts=2026-05-17T12:07:38.037  min=-117  max=-32  avg=-91.42  bins=285
sweep  3: ts=2026-05-17T12:07:38.609  min=-118  max=-32  avg=-85.07  bins=285
sweep  4: ts=2026-05-17T12:07:39.190  min=-117  max=-32  avg=-78.66  bins=285
sweep  5: ts=2026-05-17T12:07:39.776  min=-115  max=-33  avg=-84.19  bins=285
sweep  6: ts=2026-05-17T12:07:40.353  min=-103  max=-31  avg=-79.60  bins=285
sweep  7: ts=2026-05-17T12:07:40.928  min=-116  max=-34  avg=-88.60  bins=285
sweep  8: ts=2026-05-17T12:07:41.503  min=-115  max=-34  avg=-89.75  bins=285
sweep  9: ts=2026-05-17T12:07:42.068  min=-117  max=-31  avg=-88.00  bins=285
sweep 10: ts=2026-05-17T12:07:42.642  min=-118  max=-33  avg=-90.05  bins=285
```

All 10 sweeps: 285 bins each, noise floor -103 to -118 dBm, peaks -31 to -35 dBm (real 2.4 GHz activity detected).

**Raw sweep event #1** (first/last 10 bins):

```json
{"type":"sweep","timestamp":"2026-05-17T12:07:37.492+00:00","device_id":"2417295654","device_name":"Wi-Spy DBx USB 2417295654","freq_start_khz":2400000,"freq_end_khz":2495000,"bin_count":285,"rssi_bins":[-116,-101,-100,-103,-102,-102,-101,-98,-102,-101, ... -92,-101,-99,-102],"stats":{"min":-116,"max":-35,"avg":-91.19},"source":"spectool_raw"}
```

---

## 5. ASCII Waterfall Renderer Output

Full pipeline run for ~12 seconds. The waterfall pager renderer produced:

```
SpecTools Waterfall - Wi-Spy DBx
[ ]=<-90 .=-80 -=-70 ==-65 +=-55 #>-55]
[2400MHz----------------------------2495MHz]
R:|  --. .#- -=. =#.    +=+##   .#+ - =  .-. | -31
R:| #####.  = =- . .=.#+    -##     .++-   . | -33
R:|# . +##.=-   +#=-- #--==  #  ##+++++-..   | -32
R:| #   #-...+=. ..= = .   #####   .+= .    .| -32
R:|- - .##.   =++-- ..#++=+#  -.##    - .=.  | -36
R:|-.#=.#    ..  .==-#=    -##=   .=+++-.=-. | -34
R:|    ### -.=+ ..-=. . +     ####+==..-     | -30
R:|# + -.+ #.+   .= . #  =+#####  .=  .   ...| -31
R:| .  #-..-..+ .  ..-++++  =- #     # --    | -34
R:|#..    #..+  . =.-#    -##=   #++++=   .. | -33
```

Each `R:` row = one 285-bin sweep resampled to 42 display columns. Trailing number = peak dBm. `#` clusters in center-band correspond to 2.4 GHz Wi-Fi channels.

---

## 6. Data Pipeline Summary

```
Wi-Spy DBx3 (USB 1dd5:5002)
  -> spectool_raw (PID 31669, MIPS binary, ~1.94 sweeps/sec)
  -> spectools_bridge.py (PID 31667, native text -> JSONL)
  -> /tmp/*.jsonl (285 bins/sweep, timestamped)
  -> spectools_waterfall_pager.py (42-col ASCII rows)
```

The full pipeline is verified end-to-end. The `#` density in the 2400–2495 MHz band is consistent with live 2.4 GHz Wi-Fi traffic.

---

## 7. Notes on WebUI Visibility

The Docker MCP browser had no route to the Pager subnet (172.16.52.1), so WebUI screenshots could not be captured. This is a network isolation limitation of the test runner, not a device issue.

The waterfall's graphical output renders to `/dev/fb0` (the physical screen on the device) — this is not visible in any browser by design. During a running scan, the Pager LOG stream (visible in the WebUI) would show the `R:|...|` rows above, but only from a host on the same network segment as the device.

**No screenshots captured** — see notes above. All evidence is from SSH/shell output.

