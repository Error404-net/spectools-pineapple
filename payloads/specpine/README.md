# SpecPine

RF spectrum analysis for the Hak5 WiFi Pineapple Pager via Wi-Spy DBx.

One bundled payload, BluePine-style. Drop this folder onto the Pager at `/root/payloads/user/reconnaissance/specpine/`, run `payload.sh`, and the in-app menu walks you through install + every scan mode.

## Menu

```
1: Status              2: Quick Scan
3: Text Waterfall      4: Graphical Waterfall
5: Channel Analysis    6: Anomaly Detection
7: Saved Sessions      8: Install / Repair
9: Settings           10: About
0: Exit
```

## Controls during scans

- Tap OK = pause/resume
- Hold OK ≥ 0.8 s = stop, return to menu
- Settings → Mute = silence ringtones; → No-loot Mode = memory-only sessions; → GPS = embed `GPS_GET` in session metadata

## Layout

```
specpine/
├── payload.sh           # orchestrator
├── include/
│   ├── funcs_main.sh    # install, probe, helpers, button watcher
│   ├── funcs_menu.sh    # menus, dialogs, dependency + ringtone install
│   └── funcs_scan.sh    # 5 scan modes
├── bin/
│   ├── spectool_raw     # MIPS binary (mipsel_24kc)
│   ├── spectool_net
│   ├── spectools_bridge.py
│   ├── spectools_waterfall_pager.py
│   └── spectools_waterfall_fb.py
├── lib/                 # libusb-{0.1,1.0}.so* + symlinks
└── data/
    ├── 99-wispy.rules
    └── specpine_logo.txt
```

See the repo-root `INSTALL.md` for the full upload walkthrough and troubleshooting.
