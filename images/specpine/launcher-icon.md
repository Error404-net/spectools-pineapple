# Launcher Icon — Investigation Findings

**TL;DR:** The Pac-Man-style icon shown in the "Launch Payload?" dialog is **shared by every payload** and hardcoded into the firmware theme. There is **no per-payload override** mechanism.

## What I checked (Pager firmware 24.10.1, mips)

The Pager UI is rendered from a JSON-described theme at `/lib/pager/themes/wargames/`. Each dialog is a `.json` file under `components/dialogs/` with explicit `image_path` references baked in.

The launch dialog is `components/dialogs/launch_payload_dialog.json`. The icon-like animation seen at the right of "Launch Payload?" is two PNGs:

```
/lib/pager/themes/wargames/assets/launch_payload_dialog/animation/anim_frame_1.png
/lib/pager/themes/wargames/assets/launch_payload_dialog/animation/anim_frame_2.png
```

Both paths are **literal strings in the JSON** — they do not interpolate any payload variable.

## Things that are NOT a per-payload icon

- `payload_name_in_list.json` — only specifies font size/colour for the payload's name in the category list. No image field.
- `payload_title.json` — same, just text formatting.
- `templates/payload_*.json` — text templates only, no image hooks.
- The Pager API surface (`/api/payload/...` endpoints listed via `strings /usr/bin/CONFIRMATION_DIALOG`) exposes interactions like `alert`, `list_picker`, `prompt`, `spinner`, etc. None reference a per-payload icon endpoint.

## Confirming no payload uses a custom icon today

```
find /root/payloads -maxdepth 5 -type f -name "*.png" → (empty)
find /root/payloads -maxdepth 5 -type f -name "*.fb"  → (empty)
grep -r "^# *Icon:\|^# *Image:" /root/payloads        → (empty)
```

Every existing payload (BluePine, all the user/* ones, the recon/client family) shows the same Pac-Man animation in the Launch Payload dialog.

## The only theoretical override paths

1. **Swap the firmware-shared PNGs system-wide.** Overwrite `anim_frame_1.png` and `anim_frame_2.png` with SpecPine-themed art. This changes the icon for **every payload**, not just SpecPine — disruptive to other apps and not actually a per-payload feature. Skipping.
2. **Patch the theme JSON to add an icon field** that resolves to the payload's directory (e.g. `${PAYLOAD_PATH}/icon.png`). This would require modifying `launch_payload_dialog.json` AND extending the firmware's JSON renderer to understand the placeholder. Out of scope for a payload deliverable; would need a Hak5-side feature request.
3. **In-payload framebuffer takeover.** SpecPine already has this via `bin/specpine_splash.py` — once the user launches the payload, we draw whatever we want to `/dev/fb0`. This is the practical "branding" win and is already wired up.

## Recommendation

Treat the Launch Payload icon as a Pager-OS limitation. SpecPine's branding lives in:

- `bin/specpine_splash.py` — WarGames-style boot animation on `/dev/fb0` (immediately after the user taps OK)
- `data/specpine_logo.txt` — ASCII logo on the Pager LOG
- `data/ansi/*.txt` — per-mode CRT frames on the LOG
- `images/specpine/*.png` — repo-level promo art (this directory)
- `bin/spectools_waterfall_fb.py` — full RGB565 waterfall while a scan runs

If we want to push for a per-payload Launch icon, the avenue is a Hak5 firmware feature request (post an issue in their payload-template repo: `wifipineapplepager-payloads`). For now, no in-tree code change for the icon itself.
