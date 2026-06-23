# WiFi Pineapple Pager — Reference Doc

A working reference for everything we've learned about the Pager while building
SpecPine, plus links out to the official docs/repos and the in-house tooling
(`mcp-servers/`) we built to control the hardware directly. Firmware itself is
closed-source (Hak5 ships binaries only), so most of the "how the display/UI
actually behaves" material below is reverse-engineered from observed behavior,
not from reading their source — flagged inline wherever that's the case.

## Hardware / firmware basics

- SoC: MIPS, little-endian (`mipsel`), identified by OpenWrt as `mipsel_24kc` / `ramips/mt76x8`.
- Display: physical framebuffer `/dev/fb0`, 222×480 (portrait, row-major); apps
  generally want it logically as 480×222 landscape, which means a rotation
  when writing pixels directly (see SpecPine's `spectools_waterfall_fb.py`).
- Firmware version we're targeting: 24.10.1.
- Active dev unit on the LAN at `172.16.52.1`, SSH `root`/`qwerty` (per this repo's `CLAUDE.md`).
- Downloads/changelogs: https://downloads.hak5.org/pineapple/pager

## Official documentation

Root: https://documentation.hak5.org/wifi-pineapple-pager
Machine-readable index: https://documentation.hak5.org/wifi-pineapple-pager/llms.txt
(GitBook-hosted; every page is also available as plain Markdown by appending `.md`.)

Setup & device basics:
- [Welcome to the WiFi Pineapple Pager](https://documentation.hak5.org/wifi-pineapple-pager/setup/welcome-to-the-wifi-pineapple-pager.md)
- [Unboxing Setup](https://documentation.hak5.org/wifi-pineapple-pager/setup/unboxing-setup.md)
- [On-Device Setup](https://documentation.hak5.org/wifi-pineapple-pager/setup/on-device-setup.md)
- [On-Device Tutorial](https://documentation.hak5.org/wifi-pineapple-pager/setup/on-device-tutorial.md)
- [Dashboard](https://documentation.hak5.org/wifi-pineapple-pager/dashboard.md)
- [Connecting the WiFi Pineapple Pager](https://documentation.hak5.org/wifi-pineapple-pager/connecting-to-the-wifi-pineapple-pager/connecting-the-wifi-pineapple-pager.md)
- [SSH and the WiFi Pineapple Pager](https://documentation.hak5.org/wifi-pineapple-pager/connecting-to-the-wifi-pineapple-pager/ssh-and-the-wifi-pineapple-pager.md)
- [Virtual Pager](https://documentation.hak5.org/wifi-pineapple-pager/connecting-to-the-wifi-pineapple-pager/virtual-pager.md) — on-screen/remote view of the device; this is the "view virtual pager screen" capability referenced in our own task list (#8).
- [Firewall](https://documentation.hak5.org/wifi-pineapple-pager/connecting-to-the-wifi-pineapple-pager/firewall.md)
- [Factory Reset](https://documentation.hak5.org/wifi-pineapple-pager/factory-reset.md)
- [Firmware Recovery](https://documentation.hak5.org/wifi-pineapple-pager/firmware-recovery.md)
- [Software Updates](https://documentation.hak5.org/wifi-pineapple-pager/software-updates/software-updates.md)
- [Glossary](https://documentation.hak5.org/wifi-pineapple-pager/glossary.md)

Recon / PineAP (the device's native attack suite — not part of SpecPine, but
useful context since SpecPine ships as a payload alongside these):
- [Recon](https://documentation.hak5.org/wifi-pineapple-pager/recon.md), [Recon (2)](https://documentation.hak5.org/wifi-pineapple-pager/recon-1.md)
- [PineAP](https://documentation.hak5.org/wifi-pineapple-pager/pineap.md)
- [Pineapple Open AP](https://documentation.hak5.org/wifi-pineapple-pager/pineapple-open-ap.md)
- [Pineapple Evil WPA](https://documentation.hak5.org/wifi-pineapple-pager/pineapple-evil-wpa.md)
- [SSID Pool](https://documentation.hak5.org/wifi-pineapple-pager/ssid-pool.md)
- [Handshake Collection](https://documentation.hak5.org/wifi-pineapple-pager/handshake-collection.md)
- [Alert Payloads](https://documentation.hak5.org/wifi-pineapple-pager/alert-payloads.md)
- [Ringtones](https://documentation.hak5.org/wifi-pineapple-pager/ringtones.md)
- [GPS](https://documentation.hak5.org/wifi-pineapple-pager/gps.md)
- [External Packages](https://documentation.hak5.org/wifi-pineapple-pager/external-packages.md)

Payload development (the section most relevant to SpecPine):
- [Introduction to Payloads](https://documentation.hak5.org/wifi-pineapple-pager/payloads-1/introduction-to-payloads.md)
- [Installing Payloads](https://documentation.hak5.org/wifi-pineapple-pager/payloads-1/installing-payloads.md)
- [Introduction to Scripting](https://documentation.hak5.org/wifi-pineapple-pager/payloads-1/introduction-to-scripting.md)
- [Speedrunning Payload Dev](https://documentation.hak5.org/wifi-pineapple-pager/payloads-1/speedrunning-payload-dev.md)
- [Recon Payloads](https://documentation.hak5.org/wifi-pineapple-pager/payloads-1/recon-payloads.md)
- [Alert Payloads](https://documentation.hak5.org/wifi-pineapple-pager/payloads-1/alert-payloads.md)
- [DuckyScript for the WiFi Pineapple Pager](https://documentation.hak5.org/wifi-pineapple-pager/payloads-1/duckyscript-for-the-wifi-pineapple-pager.md)
- [Advanced Payloads](https://documentation.hak5.org/wifi-pineapple-pager/payloads-1/advanced-payloads.md) — binary payloads, opkg, `mmc`-installed packages surviving firmware upgrades. **As of this writing, the docs explicitly note binary payloads aren't yet accepted into the official Payload Repository** — relevant since SpecPine ships its own MIPS `spectool_raw`/`spectool_net` binaries.

Command reference (one page per firmware-exposed shell command):

| Command | Doc |
|---|---|
| `ALERT` | https://documentation.hak5.org/wifi-pineapple-pager/alert.md |
| `BUTTON_PRESS` | https://documentation.hak5.org/wifi-pineapple-pager/button_press.md |
| `CONFIG` | https://documentation.hak5.org/wifi-pineapple-pager/config.md |
| `CONFIRMATION_DIALOG` | https://documentation.hak5.org/wifi-pineapple-pager/confirmation_dialog.md |
| `ERROR_DIALOG` | https://documentation.hak5.org/wifi-pineapple-pager/error_dialog.md |
| `IP_PICKER` | https://documentation.hak5.org/wifi-pineapple-pager/ip_picker.md |
| `LIST_PICKER` | https://documentation.hak5.org/wifi-pineapple-pager/list_picker.md |
| `LOG` | https://documentation.hak5.org/wifi-pineapple-pager/log.md |
| `MAC_PICKER` | https://documentation.hak5.org/wifi-pineapple-pager/mac_picker.md |
| `NUMBER_PICKER` | https://documentation.hak5.org/wifi-pineapple-pager/number_picker.md |
| `PROMPT` | https://documentation.hak5.org/wifi-pineapple-pager/prompt.md |
| `RINGTONE` | https://documentation.hak5.org/wifi-pineapple-pager/ringtone.md |
| `SPINNER` | https://documentation.hak5.org/wifi-pineapple-pager/spinner.md |
| `TEXT_PICKER` | https://documentation.hak5.org/wifi-pineapple-pager/text_picker.md |
| `VIBRATE` | https://documentation.hak5.org/wifi-pineapple-pager/vibrate.md |

Pineapple-specific WiFi commands (PineAP / recon, not used by SpecPine but
documented alongside the above):
`FIND_CLIENT_IP`, `DEAUTH_CLIENT`, `DEVICE_FILTER`, `EXAMINE`, `RECON_NEW`,
`SET_BANDS`, `MIMIC`, `NETWORK_FILTER`, `SSID_POOL`, `WIFI_PCAP`, `WIGLE` — all
under `https://documentation.hak5.org/wifi-pineapple-pager/wifi-pineapple-commands/<name>.md`.

**Notably absent from the official docs:** any page on framebuffer/display
ownership, or an API for a payload to draw to the screen directly. The docs
flag "documentation about PineAP features and writing payloads will be coming
soon" — so the `/dev/fb0` SIGSTOP/SIGCONT approach SpecPine uses (see below) is
not an officially sanctioned mechanism, just the only one that's been observed
to work.

GitBook's pages also support an `?ask=<question>` query param for natural-language
lookups against the docs (e.g. `…/wifi-pineapple-pager-by-hak5.md?ask=...`) —
useful for quick lookups without crawling the whole index.

## Official Hak5 repositories

Umbrella repo (submodule pointers only, "under construction" per its own README):
- https://github.com/hak5/wifipineapplepager

Actual content lives in the linked subrepos:
- **Payloads** — https://github.com/hak5/wifipineapplepager-payloads
- **Themes** — https://github.com/hak5/wifipineapplepager-themes
- **Ringtones** — https://github.com/hak5/wifipineapplepager-ringtones

Contribution policy: PRs go to the relevant subrepo directly, not the umbrella
repo. Binary payloads (SpecPine included) are currently *not* accepted into
the official Payload Repository per the Advanced Payloads doc above — worth
re-checking periodically since Hak5 says a binary-payload build/submission
process is in progress.

Community: https://hak5.org/discord, forum threads at
https://forums.hak5.org/forum/113-wifi-pineapple-pager/, featured-payload
leaderboard at https://hak5.org/blogs/payloads/tagged/wifi-pineapple-pager.

Licensing/legal note (from the umbrella repo's README): Pager content,
DuckyScript, and the WiFi Pineapple trademark are all under Hak5's own license
terms — see https://hak5.org/license and https://shop.hak5.org/pages/software-license-agreement.
Relevant if SpecPine is ever submitted upstream or redistributed standalone.

## Third-party reference used in this project

- **BluePine** (cncartist) — the UI conventions, ringtone-name set, and
  button-watcher (tap=pause/long-press=stop via background `evtest`) pattern
  that SpecPine's `payload.sh` explicitly credits and adapts. Snapshot lives
  in this repo at `BluePine-WiFi-Pineapple-Pager-main/`.

## This project: SpecPine

Full architecture, file layout, build/deploy commands, and conventions are
documented in this repo's own `CLAUDE.md` — that's the source of truth for
day-to-day dev work and isn't duplicated here. Summary of what it covers:
payload layout (`payloads/specpine/`), the `spectool_raw → bridge.py → renderer`
data flow, persistent settings, loot layout, and the C conventions for the
upstream `spectool sourcecode/`.

### Reverse-engineered display behavior (not in any official doc)

- `/dev/fb0` is normally owned and repainted by the device's native
  `/pineapple/pineapple` process roughly every ~750ms.
- For a payload to draw its own frames and have them stick, it must
  `SIGSTOP` that process first and `SIGCONT` it on exit/signal — there is no
  officially documented "take over the screen" call. SpecPine's
  `spectools_waterfall_fb.py` does this via `pineapple_stop()`/`pineapple_cont()`,
  locating the PID with `pidof pineapple` → `pgrep -x pineapple` →
  `pgrep -f /pineapple/pineapple` (first one that succeeds wins).
- **Known fragility**: if none of those three lookups find the process (e.g.
  different PATH/process name under a menu-launched process tree vs. an
  SSH-driven one), `pineapple_stop()` silently no-ops — no error is logged
  anywhere. The renderer then writes a frame, and the native UI's own repaint
  loop overwrites it roughly a second later, with no visible symptom besides
  "the payload seems to run in the background and never displays anything."
  This is the live, not-yet-confirmed hypothesis for the current graphical
  waterfall display bug (tracked as task #1 in this project's task list,
  reopened) — verification requires checking `ps` for `pineapple`'s state
  during a *menu-launched* (not SSH-launched) run.
- Button input still works correctly while `pineapple` is SIGSTOPped, because
  `evtest`/the kernel input device (`/dev/input/event0`) is independent of the
  UI process.

## `spectool sourcecode/` — rebuilding from source

This repo vendors the upstream `spectool` C project under `spectool sourcecode/`
(flat directory, no subdirs). It's the canonical low-level reference for how
the Wi-Spy DBx is actually driven, and the source SpecPine's bundled MIPS
`spectool_raw`/`spectool_net` binaries are cross-compiled from (see `CLAUDE.md`
for the OpenWrt SDK build command).

### Device range/profile table (Wi-Spy DBx)

`wispy_hw_dbx.c`'s `wispydbx_add_supportedranges()` hardcodes 6 fixed sweep
profiles for `WISPYDBx_MODEL_DBxV1/V2/V3` (the model in the Pager). `spectool_raw`
selects one via `-r/--range [device:]<index>`, which maps to
`spectool_phy_setposition()`. If no `-r` is passed, the device defaults to
profile 0.

| Index | Name | Range | Resolution | Dwell |
|---|---|---|---|---|
| 0 | Full 2.4GHz Band | 2400.0–2495.0 MHz | 333.3 kHz | 200 |
| 1 | Full 2.4GHz Band (Turbo) | 2400.0–2495.0 MHz | 1000.0 kHz | 500 |
| 2 | Full 5GHz Band | 5150.0–5836.0 MHz | 1497.070 kHz | 428 |
| 3 | UNII Low (ch. 36-64) | 5150.0–5350.0 MHz | — | — |
| 4 | UNII Mid (ch. 100-140) | 5470.0–5725.0 MHz | — | — |
| 5 | UNII High (ch. 149-165) | 5725.0–5836.0 MHz | — | — |

(`24i`/`24xV2` Wi-Spy models only expose ranges 0–1; `900x`/`950x` models expose
an entirely different sub-1GHz set — not relevant to the Pager's DBx unit, but
useful context if another Wi-Spy variant is ever wired in.)

SpecPine's `band_to_range_index()` (in `include/funcs_main.sh`) maps the
user-facing band setting (`auto`/`2.4`/`5`) to this table:

```bash
band_to_range_index() {
    case "$1" in
        5)   echo 2 ;;   # Full 5GHz Band
        2.4|auto|*) echo 0 ;;   # Full 2.4GHz Band
    esac
}
```

`start_bridge()` and `device_config_dump()` both resolve this index and pass
`--range <idx>` into `spectool_raw` via the bridge's `--input-command` string
(`spectools_bridge.py`'s `_iter_command()` already `shlex.split()`s that string
before exec, so no bridge.py changes were needed).

**Bug fixed (this session):** prior to this fix, `current_band`/`default_band`
were threaded through the menu UI (`pre_scan_dialog`, `setting_default_band`)
and displayed/logged everywhere, but **never actually passed to `spectool_raw`**
— `start_bridge()` invoked the binary with no `-r` flag at all, so the device
always swept profile 0 (2.4GHz) regardless of what band the user picked. This
was the real root cause of "5GHz mode" appearing to do nothing. Fixed by adding
`band_to_range_index()` and wiring `--range ${range_idx}` into both call sites.

### Renderer band-awareness

Once the device actually sweeps a non-2.4GHz range, the renderer also has to
know what it's looking at:

- `bin/spectools_waterfall_pager.py` (ASCII/text renderer) was already
  correctly band-aware: `freq_header()` picks `_CH_2G` or `_CH_5G` channel-tick
  dicts based on `freq_start_khz < 3_000_000`, with tick x-positions computed
  from the actual `freq_start_khz`/`freq_end_khz` span. No change needed.
- `bin/spectools_waterfall_fb.py` (graphical/framebuffer renderer) **was not**
  band-aware — `_freq_to_x()` had hardcoded 2.4GHz default args and was called
  without passing the live freq range, and `_WIFI_CHANNELS` was a single
  2.4GHz-only dict. Fixed this session: split into `_WIFI_CHANNELS_24` /
  `_WIFI_CHANNELS_5` (the latter using the UNII-1/UNII-3 channel centres —
  36/40/44/48, 149/153/157/161 — matching the ASCII renderer's `_CH_5G` set),
  and `build_static()` now derives `start_mhz`/`end_mhz` from the actual
  `freq_start_khz`/`freq_end_khz` event data, selects the channel dict by band,
  and skips ticks that fall outside the currently-visible sweep range (e.g. a
  UNII-Low-only sweep won't try to draw UNII-High ticks).

### Legacy GTK/curses sources — reference only, not used by SpecPine

`spectool sourcecode/` also contains the upstream project's original
desktop visualization UIs:

`spectool_gtk.c/.h`, `spectool_gtk_channel.c/.h`, `spectool_gtk_hw_registry.c/.h`,
`spectool_gtk_planar.c/.h`, `spectool_gtk_spectral.c/.h`, `spectool_gtk_topo.c/.h`,
`spectool_gtk_widget.c/.h`, `spectool_curses.c`

These are GTK and curses-based waterfall/spectral/planar/topo views meant for
a desktop Linux box with a display server — they predate and are unrelated to
the Pager's framebuffer. SpecPine does not call, link against, or build any of
these; they're kept in the repo purely as historical/architectural reference
for how the original spectool project rendered sweep data, in case that's
useful when designing future renderers. Don't resurrect them as a dependency —
`spectools_waterfall_pager.py` and `spectools_waterfall_fb.py` are the
maintained, Pager-native equivalents.

## In-house tooling: `mcp-servers/`

Built to stop doing risky ad hoc SSH sessions against the device by hand (one
of which previously hung the Pager and required a reboot). Full setup/registration
steps live in `mcp-servers/README.md`; summary:

- **`pager_mcp/`** — SSH-based device control: run arbitrary shell commands
  (always wrapped in `timeout -s KILL <n>` so a stuck remote process can't
  hang the device or the SSH session again), capture the LCD as a PNG,
  list/launch/stop/check SpecPine or other payloads, and an experimental
  button-press injection tool (`pager_press_button`) pending live verification
  of the actual keycode/mechanism.
- **`wispy_mcp/`** — Wi-Spy DBx control, switchable between the dongle being
  in the Pager (`mode="remote"`, driven over SSH) or plugged into this Mac
  directly (`mode="local"`).

Both are written, syntax-checked, and documented, but as of this writing are
**not yet registered** in this session's MCP config — live verification of the
display-bug hypothesis above needs them (or manual SSH) registered/run from
Jesse's machine directly.

## Open items

- Confirm the `pineapple` process state (`T`/stopped vs. running) during a
  *real menu-launched* Graphical Waterfall run, not just an SSH-driven one.
- If confirmed, harden `_pineapple_pid()` in `spectools_waterfall_fb.py` with
  a `ps`-based fallback and a non-silent log line when no PID is found.
- Verify the real button-press injection mechanism (`pager_press_button`) once
  `pager_mcp` is registered and reachable.
- Periodically re-check the Advanced Payloads doc for the binary-payload
  submission process Hak5 says is in progress, in case SpecPine becomes
  submittable to the official Payload Repository.
