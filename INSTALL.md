# SpecTools Waterfall — Installation & Usage Guide

Live RF spectrum waterfall from a Wi-Spy DBx on the Hak5 WiFi Pineapple Pager.

---

## What You Get

| Payload | Purpose |
|---------|---------|
| `spectools_install` | One-time setup — copies compiled binaries onto the Pager |
| `spectools_waterfall` | Live ASCII waterfall display from the Wi-Spy DBx |

---

## Prerequisites

- Hak5 WiFi Pineapple Pager (24.10.1, mipsel_24kc / ramips/mt76x8)
- Wi-Spy DBx connected via USB
- SSH/SCP access to the Pager (`root@pineapple` or `root@172.16.42.1`)
- Python 3 on the Pager — install if missing:
  ```bash
  ssh root@pineapple "opkg update && opkg install python3"
  ```

---

## Step 1 — Upload the Payloads

Unzip the package on your computer, then SCP each payload into the `reconnaissance` category directory:

```bash
unzip pine-spectools.zip
scp -r pine-spectools/spectools_install         root@pineapple:/root/payloads/user/reconnaissance/
scp -r pine-spectools/spectools_waterfall        root@pineapple:/root/payloads/user/reconnaissance/
scp -r pine-spectools/spectools_waterfall_graphical root@pineapple:/root/payloads/user/reconnaissance/
```

After uploading, fix permissions:

```bash
ssh root@pineapple "chmod 755 \
    /root/payloads/user/reconnaissance/spectools_install/payload.sh \
    /root/payloads/user/reconnaissance/spectools_waterfall/payload.sh \
    /root/payloads/user/reconnaissance/spectools_waterfall/bin/*.py \
    /root/payloads/user/reconnaissance/spectools_waterfall_graphical/payload.sh \
    /root/payloads/user/reconnaissance/spectools_waterfall_graphical/bin/*.py"
```

---

## Step 2 — Run the Installer

Plug in your Wi-Spy DBx via USB, then on the Pager:

1. Navigate to **Payloads → user → pine-spectools → spectools_install**
2. Select **payload.sh** and run it
3. The payload log will show:
   ```
   SpecTools Installer v1.0
   Target: /opt/spectools
   Checking payload contents...
   ...
   Installation complete!
   ```
4. LED turns **green** on success, **yellow** if the Wi-Spy wasn't detected (that's OK — the files are still installed)

This installs:
- `/opt/spectools/bin/spectool_raw`
- `/opt/spectools/bin/spectool_net`
- `/opt/spectools/lib/libusb-*.so*`
- `/etc/spectools/spectools.conf`

You only need to run this once per Pager.

---

## Step 3 — Run the Waterfall

1. Make sure the Wi-Spy DBx is plugged into the Pager via USB
2. On the Pager: navigate to **Payloads → user → pine-spectools → spectools_waterfall**
3. Select **payload.sh** and run it

### What the display looks like

The payload log shows a scrolling ASCII waterfall. Each new line is one spectrum sweep:

```
SpecTools Waterfall - Wi-Spy DBx
[ ]=<-90 .=-80 -=-70 ==-65 +=-55 #>-55]
[2400MHz---------------------2483MHz    ]
|.. .. .---....  ....   ..  .  .  ..    | -72
|.. .. .---....  ....   ..  .  .  ..    | -74
|.....-===++==.------..--------.---.....| -55
|.....-===++==.------..--------.---.....| -57
```

- Each `|...|` row = one frequency sweep across 2400–2483 MHz
- Characters show signal strength: space (noise) → `.` → `-` → `=` → `+` → `#` (strong)
- The number at the right is the peak dBm for that sweep
- A frequency header reprints every 15 sweeps
- Press **Back** to stop

### Reading the waterfall

Active 2.4 GHz Wi-Fi channels show up as columns of `=` or `+` characters:
- **Channel 1** ≈ columns 1–11 (2401–2423 MHz)
- **Channel 6** ≈ columns 21–31 (2426–2448 MHz)
- **Channel 11** ≈ columns 37–47 (2451–2473 MHz)

Strong nearby APs produce `#` characters.

---

## Session Loot

Each run saves data to `/root/loot/spectools_waterfall/session_YYYYMMDD_HHMMSS/`:

| File | Contents |
|------|----------|
| `session_*.meta.json` | Device info, sweep count, timestamps |
| `session_*.summary.csv` | Per-sweep min/max/avg dBm statistics |

Retrieve with:
```bash
scp -r root@pineapple:/root/loot/spectools_waterfall/ ./loot/
```

---

## Troubleshooting

**"spectool_raw not found" / "Run spectools_install first"**
→ Run the installer payload first (Step 2).

**"python3 not found"**
→ `ssh root@pineapple "opkg update && opkg install python3"`

**"Bridge exited unexpectedly" / "Check USB"**
→ The Wi-Spy DBx isn't detected. Try:
```bash
ssh root@pineapple "lsusb"  # Should show "MetaGeek" or "0x1781"
ssh root@pineapple "LD_LIBRARY_PATH=/opt/spectools/lib /opt/spectools/bin/spectool_raw --list"
```

**Library errors (`error while loading shared libraries`)**
```bash
ssh root@pineapple "LD_LIBRARY_PATH=/opt/spectools/lib ldd /opt/spectools/bin/spectool_raw"
```

**Waterfall shows all spaces (no signal)**
→ The device is working but seeing only noise. This is normal in a quiet RF environment. Bring an active Wi-Fi device close to the Wi-Spy.

---

## Rebuilding the Package

From the repo root:
```bash
bash scripts/package.sh
```

Produces `pine-spectools.zip` in the repo root.
