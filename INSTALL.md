# SpecPine — Installation Guide

RF spectrum analysis app for the Hak5 WiFi Pineapple Pager, driving a Wi-Spy DBx USB spectrum analyzer. ASCII and full-colour framebuffer waterfall modes, persistent settings, and loot capture — all in a single self-contained payload.

---

## What's in the ZIP

```text
pine-spectools.zip
├── pine-spectools/
│   ├── specpine/               ← the main payload
│   │   ├── payload.sh
│   │   ├── bin/                (spectool_raw, spectool_net, python helpers)
│   │   ├── lib/                (libusb — bundled, no /opt install needed)
│   │   ├── include/
│   │   └── data/
│   ├── specpine_installer/     ← one-shot installer payload
│   │   └── payload.sh
│   └── INSTALL.md
```

The MIPS binaries and libusb ship inside the ZIP. No system-wide install required.

---

## Prerequisites

- Hak5 WiFi Pineapple Pager (firmware 24.10.1, mipsel_24kc / ramips/mt76x8)
- Wi-Spy DBx connected via USB
- SSH/SCP access to the Pager (`root@172.16.42.1`, default password `hak5pineapple`)
- Internet on the Pager for first-run opkg install of `python3` and `evtest` (one-time)

---

## Install

### Step 1 — Copy the ZIP to the Pager

```bash
scp pine-spectools.zip root@172.16.42.1:/root/
```

### Step 2 — Bootstrap the installer payload

```bash
ssh root@172.16.42.1 'cd /tmp && \
  unzip -o /root/pine-spectools.zip "pine-spectools/specpine_installer/payload.sh" && \
  mkdir -p /root/payloads/user/utils/specpine_installer && \
  cp pine-spectools/specpine_installer/payload.sh \
     /root/payloads/user/utils/specpine_installer/payload.sh && \
  chmod 755 /root/payloads/user/utils/specpine_installer/payload.sh'
```

### Step 3 — Run the installer from the Pager UI

On the Pager: **Payloads → utils → SpecPine Installer**

The installer will:

1. Detect and install missing dependencies (`python3`, `evtest`) via opkg — prompts once, needs internet
2. Extract and install SpecPine to `payloads/user/reconnaissance/specpine`
3. Set all permissions

SpecPine will then appear under **Payloads → reconnaissance**.

---

## Updating

Drop a new `pine-spectools.zip` at `/root/pine-spectools.zip` via SCP, then run the installer again from the Pager UI. No SSH beyond the file copy.

---

## Usage

Plug in the Wi-Spy DBx, then launch **SpecPine** from the Pager.

The boot splash plays, then the main menu appears:

| Menu item         | What it does                                                               |
| ----------------- | -------------------------------------------------------------------------- |
| 2.4GHz Waterfall  | Full-color 480×222 RGB565 waterfall on `/dev/fb0`, 2.4 GHz band.          |
| 5GHz Waterfall    | Full-color 480×222 RGB565 waterfall on `/dev/fb0`, 5 GHz band.            |
| SYS/CONFIG        | Settings, diagnostics, about, reset to defaults.                           |

Scans launch immediately with no pre-run prompts. Sessions are saved automatically to `/root/loot/specpine/` unless No-loot mode is on.

### Controls

| Input          | Action                                 |
| -------------- | -------------------------------------- |
| Hold OK ≥0.8s  | Stop scan, return to menu              |
| Hold Back ≥2s  | Exit SpecPine                          |
| Hold DOWN ≥2s  | Save framebuffer screenshot            |

### Settings

Accessible from **SYS/CONFIG**:

| Setting             | Default  | Description                                       |
| ------------------- | -------- | ------------------------------------------------- |
| Stall Timeout       | 8s       | Seconds of no data before feed recovery attempt   |
| Max Restarts        | 5        | Max bridge restart attempts before giving up      |
| Mute                | off      | Suppress all ringtones                            |
| No-loot Mode        | off      | Store sessions in `/tmp` and wipe on exit         |
| Skip Ringtone Check | off      | Skip the ringtone installer prompt at launch      |

### Loot

```text
/root/loot/specpine/session_YYYYMMDD_HHMMSS_text/
├── meta.json           # band, device, freq range, settings snapshot
├── events.jsonl        # full bridge stream
├── sweep_summary.csv   # per-sweep min/max/avg dBm
└── screenshot_*.bmp    # framebuffer screenshots (if taken)
```

Retrieve loot:

```bash
scp -r root@172.16.42.1:/root/loot/specpine ./loot/
```

---

## Troubleshooting

**"spectool_raw not found"** — Re-run the installer payload. The binary ships in the ZIP and should be at `bin/spectool_raw` inside the payload directory.

**"Bridge exited — check Wi-Spy USB"** — Wi-Spy not detected:

```bash
ssh root@172.16.42.1 "lsusb"   # expect 0x1781 or 0x1dd5 (MetaGeek)
PAYLOAD=/root/payloads/user/reconnaissance/specpine
ssh root@172.16.42.1 "LD_LIBRARY_PATH=${PAYLOAD}/lib ${PAYLOAD}/bin/spectool_raw --list"
```

**Graphical waterfall leaves a blank screen** — the virtual console should rebind automatically on exit. If it doesn't:

```bash
ssh root@172.16.42.1 "echo 1 > /sys/class/vtconsole/vtcon1/bind"
```

**No ringtones / tone on screenshot** — Settings → Skip Ringtone Check → off, then re-launch SpecPine to trigger the ringtone installer. Or enable Mute for silence.

**Display shows only noise** — Normal for a swept analyzer in a quiet environment. Bring an active 2.4 GHz source close, or switch to 5 GHz via Settings → Default Band.

---

## Rebuilding from Source

```bash
bash scripts/package.sh
```

Produces `pine-spectools.zip` from `payloads/specpine/` and `spectools-pineapple-build/`. Cross-compiled MIPS binaries live in `spectools-pineapple-build/bin/` — only rebuild those if you're changing the upstream `spectool sourcecode/`.
