# SpecPine

RF spectrum analysis for the Hak5 WiFi Pineapple Pager via Wi-Spy DBx.

Single bundled payload, BluePine-style. Drop this folder onto the Pager at
`/root/payloads/user/reconnaissance/specpine/`, run `payload.sh`, and the
landing screen offers a one-tap waterfall path.

## One-click waterfall

After launch:

```
splash → Tap OK = Waterfall   Hold OK = Menu
                  (idle 30s   = Menu)
```

Tap OK → bridge starts with persisted defaults (band / no-loot / GPS) →
text waterfall streams to the Pager LOG with frequency-tagged sweep rows
and a colour-tiered peak indicator (green floor → yellow medium → red
strong). Hold OK ≥ 0.8 s during the scan = clean stop + finalised loot.

Hold OK on the landing screen → main menu (Status / Quick Scan / Text
Waterfall / Channel Analysis / Anomaly Detection / Saved Sessions /
Install / Settings / About / Exit).

## Loot

Each scan writes to `/root/loot/specpine/session_<TS>_<NAME>/`:

- `meta.json` — `status` (started → success / failed / cancelled),
  band, device, freq range, GPS, settings snapshot, reason if failed.
- `events.jsonl` — full bridge stream (device_config + sweep events).
- `sweep_summary.csv` — per-sweep min / max / avg dBm.

`scp -r root@pineapple:/root/loot/specpine ./loot/` to pull it home.

In **No-loot mode** (Settings) the same tree lives under `/tmp/specpine/`
and is wiped when SpecPine exits. Failed/cancelled scans keep their dir
with `status` set, so the loot directory always tells the truth.

## Layout

```
specpine/
├── payload.sh                 # orchestrator: singleton, splash, landing, menu loop
├── include/
│   ├── funcs_main.sh          # install, probe, helpers, button watcher,
│   │                          # session lifecycle, theme.sh source
│   ├── funcs_menu.sh          # menus, dialogs, diagnostics, settings
│   └── funcs_scan.sh          # 4 active scan modes (text waterfall, quick,
│                              # channel, anomaly) — graphical demoted
├── bin/
│   ├── spectool_raw           # MIPS binary (mipsel_24kc)
│   ├── spectool_net
│   ├── spectools_bridge.py    # JSONL emitter (parses native spectool_raw)
│   ├── spectools_waterfall_pager.py    # ASCII renderer (R:/Y:/G: tags)
│   ├── spectools_waterfall_fb.py       # framebuffer renderer (broken — see below)
│   └── specpine_splash.py     # boot animation (uses pre-rendered .fb if present)
├── lib/                       # libusb-{0.1,1.0}.so* + symlinks
└── data/
    ├── 99-wispy.rules
    ├── specpine_logo.txt
    ├── ansi/                  # per-mode CRT frames shown via show_ansi
    └── theme/
        ├── theme.sh           # palette tokens + LOG_TITLE/GOOD/WARN/... wrappers
        ├── palette.md         # human-readable style guide
        ├── splash.fb          # pre-rendered 480×222 RGB565 splash
        ├── glyphs/            # branded ASCII frames (landing, scan_*, loot_saved)
        └── boot_animation/    # 4-frame WOPR-style boot sequence (.fb)
```

## Theme

Cohesive WarGames CRT identity across every output channel. The single
source of truth is `data/theme/theme.sh` (palette tokens + `LOG_TITLE`,
`LOG_GOOD`, `LOG_WARN`, `LOG_ALERT`, `LOG_HINT`, `LOG_BRAND`,
`LOG_DIVIDER`). All future menus should use those wrappers — a future
palette swap then re-skins everything in one place. Existing
`LOG green/red/yellow/...` calls remain valid. See
`data/theme/palette.md` for the full spec.

Promo art for repo / README use lives in `images/specpine/` and is
regenerable with `python3 scripts/generate_theme_images.py`. The on-device
framebuffer assets (`splash.fb` + `boot_animation/*.fb`) are regenerable
with `python3 scripts/generate_theme_fb.py`.

## Limitations

**Graphical waterfall is broken on Pager firmware 24.10.1.**
`/sys/class/vtconsole/vtcon1` does not exist (only `vtcon0`), and the
Pager UI continuously redraws the title bar, payload-log strip, and
footer to `/dev/fb0` while a payload runs. No combination of
`DISABLE_DISPLAY`, vtcon unbind, or direct fb writes can hold a sustained
image. `spectools_waterfall_fb.py` is preserved under
**Settings → Diagnostics → Graphical Waterfall (broken)** for future
firmware that exposes a payload-takeover hook. Use **Text Waterfall**
instead — it's the supported display path.

**Launcher icon is firmware-baked.** The Pac-Man icon shown in the
"Launch Payload?" dialog is not customisable per payload on this
firmware. SpecPine's branding is delivered via the boot splash, ASCII
logo, ANSI glyphs, and waterfall colour scheme. See
`images/specpine/launcher-icon.md` for the investigation log.

See the repo-root `INSTALL.md` for the full upload walkthrough and
troubleshooting.
