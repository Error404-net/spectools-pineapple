# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

RF spectrum analysis app for the **Hak5 WiFi Pineapple Pager** (firmware 24.10.1, mipsel_24kc / ramips/mt76x8). It bridges a **Wi-Spy DBx USB spectrum analyzer** to the Pager's display as **SpecPine** — a single bundled BluePine-style payload that ships its own MIPS binaries, libusb, Python helpers, ASCII art, and on-device framebuffer splash. The project also contains the upstream `spectools` C sources and a cross-compiled MIPS drop used to feed the payload.

## Key Commands

**Package the distributable ZIP** (clean-builds `dist/pine-spectools/specpine/`, outputs `pine-spectools.zip`):
```bash
bash scripts/package.sh
```

**Cross-compile MIPS binaries for the Pager** (requires OpenWrt SDK 24.10.1 for mipsel_24kc — only needed when updating `spectool sourcecode/`):
```bash
cd "spectool sourcecode"
./configure --host=mipsel-openwrt-linux-musl --prefix=/usr --disable-gtk --disable-curses
make -j$(nproc)
strip spectool_raw spectool_net
```
The output then goes into `spectools-pineapple-build/{bin,lib}/` (which `package.sh` reads from).

**Regenerate WarGames-style promo art** (Pillow required):
```bash
python3 scripts/generate_theme_images.py     # writes 11 PNGs to images/specpine/
```

**Lint the payload before deploying**:
```bash
bash -n payloads/specpine/payload.sh \
        payloads/specpine/include/funcs_main.sh \
        payloads/specpine/include/funcs_menu.sh \
        payloads/specpine/include/funcs_scan.sh
python3 -m py_compile payloads/specpine/bin/*.py scripts/generate_theme_images.py
```

**Deploy to the Pager** (active dev target is `172.16.52.1`, password `qwerty`):
```bash
sshpass -p qwerty scp pine-spectools.zip root@172.16.52.1:/root/
sshpass -p qwerty ssh root@172.16.52.1 'cd /tmp && unzip -o /root/pine-spectools.zip && \
  rm -rf /root/payloads/user/reconnaissance/specpine && \
  cp -r pine-spectools/specpine /root/payloads/user/reconnaissance/specpine && \
  chmod 755 /root/payloads/user/reconnaissance/specpine/{payload.sh,bin/*.py,bin/spectool_raw,bin/spectool_net}'
```

**Smoke-test `spectool_raw` against a plugged-in Wi-Spy** (uses payload-local libs — no `/opt` install required):
```bash
LD_LIBRARY_PATH=…/specpine/lib …/specpine/bin/spectool_raw --list
```

No automated test suite — validation is manual on hardware. SpecPine's **Settings → Diagnostics** submenu exercises button-watcher, framebuffer, LIST_PICKER, settings persistence, and bridge dry-run on-device.

## Architecture

### Data flow

```
Wi-Spy DBx (USB)
    → spectool_raw            (MIPS binary; emits "Configured device …", "<lo>MHz-<hi>MHz @ <res>KHz, <N> samples", and "Wi-Spy …: <bins>" sweep lines)
    → spectools_bridge.py     (parses the native text format → JSONL events at /tmp/specpine_events.jsonl)
    → spectools_waterfall_pager.py   (ASCII → Pager LOG)
      OR
      spectools_waterfall_fb.py      (RGB565 → /dev/fb0 framebuffer)
```

### SpecPine payload layout

`payloads/specpine/` is a single bundled BluePine-style app. Source of truth for everything that ships:

- `payload.sh` — orchestrator. Header metadata, PAYLOAD_GET_CONFIG restore, `cleanup` trap, singleton lock, boot splash + Flutter ringtone, `device_probe`, `while true; do main_menu; case "$selnum" in …`. Resolves `SPECTOOL_BIN` to the payload's own `bin/spectool_raw` (preferred) or `/opt/spectools/bin/spectool_raw` (fallback) — see `SPECTOOL_SOURCE` global.
- `include/funcs_main.sh` — domain helpers: `specpine_logo`, `show_ansi`, `device_probe`, `device_config_dump`, `gps_get_wrapper`, `install/repair/uninstall_spectools`, `config_check`, `_set_one`/`config_backup`, `noloot_dirs`, `make_session_dir`, `write_meta_json` (status field: `started`/`success`/`failed`/`cancelled`), `mark_session_*` lifecycle wrappers, `start_evtest` + `check_cancel` (BluePine button-watcher pattern), `start_bridge`/`stop_bridge` (with `BRIDGE_FAIL_REASON` capture), `parse_sweep_stats`, `band_to_filter`, `dbm_to_glyph`, `wifi_channel_for_freq`, `status_display`.
- `include/funcs_menu.sh` — `check_dependencies` (auto-installs evtest/python3/grep via opkg with confirm), `check_ringtones` (inline RTTTL strings — names: Flutter, GlitchHack, ScaleTrill, SideBeam, Warning, Achievement), `main_menu` (cancel returns `selnum=-1` → no-op loop, **NOT** exit), `sub_menu_install`/`settings`/`about`/`sessions`/`diagnostics`, `pre_scan_dialog`, all `setting_*` and `diag_test_*` helpers.
- `include/funcs_scan.sh` — five scan modes: `quick_scan`, `text_waterfall` (with tap-OK pause / long-press OK stop), `graphical_waterfall`, `channel_analysis` (inline `python3 -c` ranks Wi-Fi channels), `anomaly_detection` (process-substitution `python3 -c` watcher with sliding-window baseline, tagged with GPS).
- `bin/spectools_bridge.py` — JSONL emitter. **Important**: `spectool_raw` outputs number-first patterns (`2400MHz-2495MHz @ 333.00KHz, 285 samples`), so the bridge has dedicated `RANGE_RE`/`NSAMP_RE`/`NRES_RE`/`DEVCFG_RE` patterns AND a "debug -" line filter. The legacy keyword-first regexes (`FREQ_RE`, `BIN_RE`, `RES_RE`) are still in place as a fallback. `_last_device_name` threads the `Configured device …` line into the indented config-line that follows.
- `bin/spectools_waterfall_pager.py` — ASCII renderer. 50-char Pager-LOG width. Casts peak with `int(round(max(bins)))` (legacy renderer crashed on float bins).
- `bin/spectools_waterfall_fb.py` — RGB565 renderer. Physical fb 222×480, logical 480×222 landscape. Disables `vtcon1` while running; restores on exit. 6 FPS. Guards `[ -e /sys/class/vtconsole/vtcon1/bind ]` because not all Pager firmware has `vtcon1`.
- `bin/specpine_splash.py` — short WOPR-style boot animation drawn straight to `/dev/fb0`. Skips silently if `/dev/fb0` missing. Inlines a 5×7 bitmap font sized for "SPECPINE READY".
- `data/specpine_logo.txt` — 7-line ASCII logo shown via LOG on launch.
- `data/ansi/<mode>.txt` — per-screen CRT-style frames shown by `show_ansi <mode>`.
- `data/99-wispy.rules` — udev rules used by the optional `Install to /opt` step.
- `lib/` — populated at package time from `spectools-pineapple-build/lib/` (libusb-0.1 + libusb-1.0 + symlinks).

### Pager firmware integration

The Pager firmware exposes shell commands as binaries in `/usr/bin/`. SpecPine relies on:

- **Display/sound**: `LOG [color] "txt"`, `LED R G B` / `LED COLORNAME`, `RINGTONE "<name>"`, `ALERT`, `ERROR_DIALOG`
- **Input**: `WAIT_FOR_BUTTON_PRESS A`, `LIST_PICKER "title" "opt1" …`, `CONFIRMATION_DIALOG`, `TEXT_PICKER`, `NUMBER_PICKER`
- **State**: `PAYLOAD_GET_CONFIG`, `PAYLOAD_SET_CONFIG`, `PAYLOAD_DEL_CONFIG` — namespace `specpine`
- **GPS**: `GPS_GET`

Tap OK / long-press OK during scans is implemented by a background `evtest /dev/input/event0` whose output is parsed by `check_cancel` and written as `pause` / `stop` flags into `/tmp/specpine_btn_evt`. Renderers / scan loops poll the flag.

### Pager UI theme

The Pager renders dialogs from `/lib/pager/themes/wargames/components/*.json`. The "Launch Payload?" icon (Pac-Man) is **firmware-baked** — not customisable per payload. SpecPine's branding is therefore on-device via `bin/specpine_splash.py`, `data/specpine_logo.txt`, `data/ansi/*.txt`, and the in-payload framebuffer rendering. See `images/specpine/launcher-icon.md` for the investigation log.

### `images/specpine/`

Repo/README promo art only — generated by `scripts/generate_theme_images.py`. Eleven PNGs in green-on-black CRT or Hackers '95 cyan/magenta. **Not** shipped in `pine-spectools.zip`.

### `dist/pine-spectools/`

Staging area rebuilt entirely by `scripts/package.sh`. Do not edit files here directly. The MIPS binaries under `dist/pine-spectools/specpine/bin/` are gitignored but materialise at package time; they come from `spectools-pineapple-build/`.

### `payloads/legacy/`

Preserved snapshot of the prior 3-payload split (`spectools_install`, `spectools_waterfall`, `spectools_waterfall_graphical`). **Not** shipped in the zip. Kept for reference only.

### `spectools-pineapple-build/`

Read-only directory with pre-cross-compiled MIPS `spectool_raw` / `spectool_net` and libusb. Treat as a build artifact; only regenerate when updating the upstream `spectool sourcecode/` and rebuilding with the OpenWrt SDK.

## Loot layout

```
/root/loot/specpine/session_<TS>_<NAME>/
├── meta.json           (status: started/success/failed/cancelled, band, device, freq range, GPS, settings snapshot, reason if failed)
├── events.jsonl        (full bridge stream — copied if loot enabled)
├── sweep_summary.csv   (bridge --export-dir output)
├── channel_report.txt  (channel_analysis)
├── anomaly_log.txt     (anomaly_detection hits + GPS)
└── gps.txt             (initial GPS_GET if enabled)
```

In **No-loot mode** (Settings) the same tree lives under `/tmp/specpine/session_*/` and is wiped by `cleanup` at exit. Failed/cancelled scans **always** keep their dir with `status` set so the user has a diagnostic trail.

## Persistent settings

PAYLOAD config namespace is `specpine`. Every key is set via `_set_one` (which redirects errors to `$LOG_FILE` and retries once). Empty values are coerced to `"0"` because the firmware silently drops empty `PAYLOAD_SET_CONFIG` values. Keys: `default_band`, `default_mode`, `stall_timeout`, `max_restarts`, `anomaly_threshold_db`, `anomaly_window`, `mute`, `noloot`, `gps_enabled`, `skip_ask_ringtones`, `selnum_main`, `total_scans`, `total_anomalies`, `app_version`.

## C code conventions (for `spectool sourcecode/`)

- K&R C, hard tabs
- Exported symbols: `Spectool_*` or `wispy_*`; internal helpers `static` or lowercase snake_case
- Macros uppercase with underscores
- Include local headers with quotes; reuse existing abstraction layers instead of direct OS calls
- Autotools control files (`configure.in`, `Makefile.in`, `config.h.in`) must be updated together when adding modules

## Things to check before declaring success

- `bash -n` on all four payload shell files (legacy `payloads/legacy/` ones are not shipped — don't edit them)
- `python3 -m py_compile` on every `.py` under `payloads/specpine/bin/` and `scripts/`
- `unzip -l pine-spectools.zip | grep -E 'pine-spectools/(spectools_install|spectools_waterfall)/'` returns nothing (legacy must not leak into the zip)
- The deployed binary architecture: `file …/specpine/bin/spectool_raw` should report `ELF 32-bit LSB executable, MIPS … interpreter /lib/ld-musl-mipsel-sf.so.1`
- After a fresh deploy, **Status** should show `spectool_raw : payload (self-contained)` — meaning the resolver picked the payload-local binary, not `/opt`. Running scans from a fresh install must not require running **Install** first.
