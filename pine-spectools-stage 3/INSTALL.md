# SpecPine — Installation & Usage Guide

A bundled BluePine-style RF spectrum analysis app for the Hak5 WiFi Pineapple Pager, driving a Wi-Spy DBx USB spectrum analyzer. One payload, one menu, every feature inside it: in-app installer, status / device info, quick scan, ASCII waterfall, full-colour framebuffer waterfall, Wi-Fi channel utilization, anomaly / jammer detection, saved sessions browser, persistent settings.

---

## Prerequisites

- Hak5 WiFi Pineapple Pager (24.10.1, mipsel_24kc / ramips/mt76x8)
- Wi-Spy DBx connected via USB
- SSH/SCP access (`root@pineapple` or `root@172.16.42.1`)
- Internet on the Pager for the first-run dependency install (one-time `opkg install python3 evtest`); SpecPine will prompt and install for you

---

## Step 1 — Upload SpecPine

Unzip the package on your computer, then SCP the single `specpine/` directory into the Pager's `reconnaissance` category:

```bash
unzip pine-spectools.zip
scp -r pine-spectools/specpine root@pineapple:/root/payloads/user/reconnaissance/
ssh root@pineapple "chmod 755 \
    /root/payloads/user/reconnaissance/specpine/payload.sh \
    /root/payloads/user/reconnaissance/specpine/bin/*.py \
    /root/payloads/user/reconnaissance/specpine/bin/spectool_raw \
    /root/payloads/user/reconnaissance/specpine/bin/spectool_net"
```

That's the entire upload. SpecTools binaries, libraries, udev rules, the ASCII logo and all helper scripts are inside `specpine/`. The in-app installer wires them into `/opt/spectools/`.

---

## Step 2 — Launch SpecPine

On the Pager, navigate to **Payloads → user → reconnaissance → specpine**, run **payload.sh**.

You'll see:

1. The SpecPine ASCII logo + `Flutter` ringtone.
2. *"Press OK to Start"*. Press OK.
3. The main menu:

   ```
   ================ SpecPine - v1.0 ====
   1: Status
   2: Quick Scan
   3: Text Waterfall
   4: Graphical Waterfall
   5: Channel Analysis
   6: Anomaly Detection
   7: Saved Sessions
   8: Install / Repair
   9: Settings
   10: About
   0: Exit
   ```

If `python3` or `evtest` are missing, SpecPine prompts to install them via `opkg` (one-time, network required).

---

## Step 3 — Install SpecTools binaries (one-time)

From the main menu, pick **Install / Repair → Install**. SpecPine copies:

- `/opt/spectools/bin/spectool_raw` and `spectool_net`
- `/opt/spectools/lib/libusb-{0.1,1.0}.so*` (with versioned symlinks)
- `/etc/spectools/spectools.conf`
- `/etc/udev/rules.d/99-wispy.rules`

LED turns green on success. You only need to do this once per Pager.

---

## Step 4 — Use it

Plug the Wi-Spy DBx in. From the main menu:

| Menu item | What it does |
|---|---|
| **Status** | `spectool_raw --list`, freq range, bin count, settings summary, scan counters |
| **Quick Scan** | ~3-second snapshot, prints min/max/avg dBm |
| **Text Waterfall** | ASCII waterfall on the Pager LOG. Tap OK = pause. Hold OK ≥0.8 s = stop. |
| **Graphical Waterfall** | Full-colour 480×222 RGB565 waterfall on `/dev/fb0`. Same OK semantics. |
| **Channel Analysis** | Captures for N seconds, prints ranked Wi-Fi channel utilization for the chosen band |
| **Anomaly Detection** | Continuous baseline-spike watcher. Red LED + Warning ringtone on breach. |
| **Saved Sessions** | List, view summary, replay (ASCII), delete |
| **Settings** | Default band/mode, stall timeout, max restarts, anomaly thresholds, mute, no-loot mode, GPS tagging, reset to defaults |

Each scan shows a pre-run dialog: pick band (Auto / 2.4 / 5), pick session name, choose whether to save loot.

### Loot

```
/root/loot/specpine/session_YYYYMMDD_HHMMSS_<name>/
├── meta.json           # band, device, freq range, GPS, settings snapshot
├── events.jsonl        # full bridge stream
├── sweep_summary.csv   # per-sweep min/max/avg
├── channel_report.txt  # channel_analysis output
├── anomaly_log.txt     # anomaly_detection hits + GPS
└── gps.txt             # initial GPS_GET (if enabled)
```

In **No-loot mode** (Settings → No-loot Mode), sessions live under `/tmp/specpine/` and are wiped when SpecPine exits.

Retrieve loot:
```bash
scp -r root@pineapple:/root/loot/specpine ./loot/
```

---

## Controls during scans

- **Tap OK** = pause / resume (text waterfall, anomaly detection)
- **Hold OK ≥0.8 s** = stop scan, return to main menu
- **Back** = return to menu without stopping a scan, depending on Pager UI

The button watcher runs `evtest /dev/input/event0` in the background and writes flag values to `/tmp/specpine_btn_evt`. If your Pager numbers input devices differently, SpecPine falls back to the first `/dev/input/event*` it finds.

---

## Troubleshooting

**"spectool_raw not installed"** — Run **Install / Repair → Install** from the main menu.

**"Bridge exited - check Wi-Spy USB"** — Wi-Spy not detected:
```bash
ssh root@pineapple "lsusb"       # expect MetaGeek / 0x1781 or 0x1dd5
ssh root@pineapple "LD_LIBRARY_PATH=/opt/spectools/lib /opt/spectools/bin/spectool_raw --list"
```

**Library errors** —
```bash
ssh root@pineapple "LD_LIBRARY_PATH=/opt/spectools/lib ldd /opt/spectools/bin/spectool_raw"
```

**No ringtones** — Settings → Skip Ringtone Check toggles to no, then re-launch; SpecPine reinstalls the RTTTL files into `/lib/pager/ringtones/`. Or set Mute = on if you just want silence.

**Graphical waterfall leaves a blank screen on exit** — `vtcon1` should auto-rebind. If it doesn't on your firmware:
```bash
ssh root@pineapple "echo 1 > /sys/class/vtconsole/vtcon1/bind"
```

**Display only shows noise** — Bring an active 2.4 GHz emitter close. The Pager's antennas are far less sensitive than a desktop card.

---

## Rebuilding the Package

From the repo root:
```bash
bash scripts/package.sh
```

Produces `pine-spectools.zip`. The legacy three-payload tree is preserved in `payloads/legacy/` for reference but is **not** included in the zip.
