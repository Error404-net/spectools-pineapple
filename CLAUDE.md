# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

RF spectrum analysis tool that runs on the **Hak5 WiFi Pineapple Pager** (v24.10.1, mipsel_24kc / ramips/mt76x8). It bridges a **Wi-Spy DBx USB spectrum analyzer** to the Pager's display via three payloads: an installer, an ASCII text waterfall, and a full-colour framebuffer waterfall.

## Key Commands

**Package the distributable ZIP** (staged from `dist/pine-spectools/`, outputs `pine-spectools.zip`):
```bash
bash scripts/package.sh
```

**Cross-compile binaries for the Pager** (requires OpenWrt SDK 24.10.1 for mipsel_24kc):
```bash
cd "spectool sourcecode"
./configure --host=mipsel-openwrt-linux-musl --prefix=/usr --disable-gtk --disable-curses
make -j$(nproc)
strip spectool_raw spectool_net
```

**Smoke-test a binary** (run on-device or with correct LD_LIBRARY_PATH):
```bash
LD_LIBRARY_PATH=/opt/spectools/lib /opt/spectools/bin/spectool_raw --list
```

**Deploy to the Pager** (after packaging):
```bash
unzip pine-spectools.zip
scp -r pine-spectools root@pineapple:/root/payloads/user/
```

No automated test suite — validation is manual on hardware.

## Architecture

### Data Flow

```
Wi-Spy DBx (USB)
    → spectool_raw  (MIPS binary, emits text sweeps)
    → spectools_bridge.py  (parses text → JSONL events at /tmp/spectools_events*.jsonl)
    → spectools_waterfall_pager.py  (ASCII → Pager LOG)
      OR
      spectools_waterfall_fb.py  (RGB565 → /dev/fb0 framebuffer)
```

### Three Payload System

Each payload is a standalone directory with `payload.sh` as the entry point. The Pager firmware provides `LOG`, `LED`, and `ALERT` shell commands that payload scripts call for UI feedback.

| Payload | Location | Purpose |
|---------|----------|---------|
| `spectools_install` | `payloads/spectools_install/` | One-time: copies `spectool_raw`, `spectool_net`, and libusb libs to `/opt/spectools/` |
| `spectools_waterfall` | `payloads/spectools_waterfall/` | ASCII waterfall via Pager LOG display |
| `spectools_waterfall_graphical` | `payloads/spectools_waterfall_graphical/` | Full-colour 480×222 framebuffer waterfall |

### Bridge (`bridge/spectools_bridge.py`)

Central adapter between `spectool_raw` output and the renderers. It:
- Spawns `spectool_raw` as a subprocess and parses its text output
- Emits `device_config` JSONL events (frequency range, bin count) and `sweep` events (per-scan RSSI bins with min/max/avg stats)
- Handles USB stalls and auto-restarts with backoff (up to 5 restarts)
- Optionally exports session metadata (JSON) and per-sweep statistics (CSV) to a loot directory

Two copies of `spectools_bridge.py` exist in the dist: `spectools_waterfall/bin/` and `spectools_waterfall_graphical/bin/`. **The source of truth is `payloads/<payload>/bin/`** — `package.sh` copies from there.

### Renderers

**`spectools_waterfall_pager.py`** — Reads JSONL, resamples bins to 44 columns, maps RSSI to density glyphs (space/`.`/`-`/`=`/`+`/`#`), outputs one line per sweep via stdout (piped through `LOG green` in payload.sh). 50-char max line width for the Pager display.

**`spectools_waterfall_fb.py`** — Reads JSONL, writes RGB565 directly to `/dev/fb0` (physical 222×480, rotated to logical 480×222 landscape). Disables `vtcon1` (terminal console) while running; restores on exit. Runs at 6 FPS. The VTCON path (`/sys/class/vtconsole/vtcon1/bind`) may not exist on all devices — the payload guards this write with `[ -e "$VTCON" ]`.

### `dist/` Directory

Staging area rebuilt entirely by `scripts/package.sh`. Do not edit files here directly — edit the source under `payloads/` or `bridge/` and re-run the packaging script. The prebuilt MIPS binaries under `dist/pine-spectools/spectools_install/bin/` are gitignored but physically present; they come from `spectools-pineapple-build/`.

### `spectools-pineapple-build/`

Read-only directory containing pre-cross-compiled MIPS binaries and libraries. Treat as a build artifact — only regenerate when updating the upstream `spectool sourcecode/` and cross-compiling with the OpenWrt SDK.

## C Code Conventions

- K&R C, hard tabs
- Exported symbols: `Spectool_*` or `wispy_*`; internal helpers are `static` or lower-case snake_case
- Macros: uppercase with underscores
- Include local headers with quotes; reuse existing abstraction layers instead of direct OS calls
- Autotools control files (`configure.in`, `Makefile.in`, `config.h.in`) must be updated together when adding modules
