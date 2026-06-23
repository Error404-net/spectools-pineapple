#!/usr/bin/env python3
"""
SpecPine Theme Installer — runs ON the Pager.

Clones /lib/pager/themes/wargames → specpine, patches colours
(shifts phosphor-green palette to teal/cyan), then symlink-swaps
wargames → specpine and hot-restarts the pager service.

Usage (from the Pager shell):
    python3 /root/payloads/user/reconnaissance/specpine/bin/specpine_theme_install.py
    python3 /root/payloads/user/reconnaissance/specpine/bin/specpine_theme_install.py --restore

Called automatically by the SpecPine "Settings → Theme" menu.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

THEME_DIR  = Path("/lib/pager/themes")
WARGAMES   = THEME_DIR / "wargames"
WARGAMES_BAK = THEME_DIR / "wargames.bak"
SPECPINE   = THEME_DIR / "specpine"

# ── Colour palette: wargames phosphor-green → SpecPine teal/cyan ─────────────
# The wargames theme encodes colours as {"r": N, "g": N, "b": N} objects
# and as plain RGB arrays [R, G, B] inside component JSONs.
# We shift:
#   primary green  (0, 220, 100) → teal        (0, 200, 180)
#   dim green      (0, 140,  60) → dim teal     (0, 130, 150)
#   dark green     (0,  70,  30) → dark navy    (0,  50, 100)
#   bright green   (0, 255, 120) → bright cyan  (0, 220, 220)
#   soft_white     (230,230,220) → cool-white   (220,240,240)  ← status bar text
#   amber          (255,180, 40) → amber kept (it's the Pager warning colour)
#
# We match the wargames-green hue: g > r*1.5 and b < g*0.6 and g > 100
# and remap it to a teal/cyan equivalent.

def _is_wargames_green(r: int, g: int, b: int) -> bool:
    """True if this colour reads as the wargames phosphor-green family."""
    return g > 100 and g > r * 1.5 and b < g * 0.6

def _remap(r: int, g: int, b: int) -> tuple[int, int, int]:
    """Shift a wargames-green colour into SpecPine teal."""
    if not _is_wargames_green(r, g, b):
        return r, g, b
    # Keep luminance (roughly), tilt hue from green toward cyan:
    #   new_b ≈ b + (g - b) * 0.8   (borrow from the green channel)
    new_b = min(255, int(b + (g - b) * 0.80))
    new_g = min(255, int(g * 0.88))   # soften green slightly
    new_r = r                          # red stays (usually 0)
    return new_r, new_g, new_b


# ── JSON patching ─────────────────────────────────────────────────────────────

def _patch_value(val: object) -> object:
    """Recursively recolour a JSON value."""
    if isinstance(val, dict):
        # {"r": N, "g": N, "b": N} inline colour objects
        if set(val.keys()) >= {"r", "g", "b"}:
            nr, ng, nb = _remap(int(val["r"]), int(val["g"]), int(val["b"]))
            return {**val, "r": nr, "g": ng, "b": nb}
        return {k: _patch_value(v) for k, v in val.items()}
    if isinstance(val, list):
        # [R, G, B] colour arrays
        if len(val) == 3 and all(isinstance(x, int) for x in val):
            return list(_remap(val[0], val[1], val[2]))
        return [_patch_value(v) for v in val]
    if isinstance(val, str):
        # hex strings "#RRGGBB" or "RRGGBB"
        m = re.fullmatch(r'#?([0-9a-fA-F]{6})', val.strip())
        if m:
            h = m.group(1)
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            nr, ng, nb = _remap(r, g, b)
            prefix = "#" if val.startswith("#") else ""
            return f"{prefix}{nr:02x}{ng:02x}{nb:02x}"
    return val


def patch_json_file(path: Path) -> bool:
    """Patch a single JSON file in-place. Returns True if changed."""
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except Exception:
        return False  # skip non-JSON or malformed files
    patched = _patch_value(data)
    new_text = json.dumps(patched, separators=(",", ":"))
    if new_text != json.dumps(data, separators=(",", ":")):
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def patch_theme_root(theme_path: Path) -> int:
    """Patch all JSON files under theme_path. Returns count changed."""
    changed = 0
    for json_file in theme_path.rglob("*.json"):
        if patch_json_file(json_file):
            changed += 1
    # Also update the theme display name inside theme.json if it has one
    root_json = theme_path / "theme.json"
    if root_json.exists():
        try:
            data = json.loads(root_json.read_text())
            # Try common name fields
            for key in ("name", "theme_name", "display_name", "title"):
                if key in data and isinstance(data[key], str):
                    data[key] = "SpecPine"
            root_json.write_text(json.dumps(data, separators=(",", ":")))
        except Exception:
            pass
    return changed


# ── Symlink swap ──────────────────────────────────────────────────────────────

def install() -> int:
    print("=== SpecPine Theme Installer ===")

    if not WARGAMES.exists() and not WARGAMES.is_symlink():
        print(f"ERROR: {WARGAMES} not found — cannot clone base theme.")
        return 1

    # Step 1 — preserve original wargames (once)
    if not WARGAMES_BAK.exists():
        print(f"Backing up wargames → {WARGAMES_BAK} …")
        # If wargames is already our symlink, back up specpine instead
        real_src = WARGAMES.resolve() if WARGAMES.is_symlink() else WARGAMES
        shutil.copytree(str(real_src), str(WARGAMES_BAK))
        print("  Backup done.")
    else:
        print(f"  Backup already exists at {WARGAMES_BAK}")

    # Step 2 — create/refresh specpine directory from the backup
    if SPECPINE.exists():
        print(f"  Removing stale {SPECPINE} …")
        shutil.rmtree(str(SPECPINE))
    print(f"Cloning wargames.bak → {SPECPINE} …")
    shutil.copytree(str(WARGAMES_BAK), str(SPECPINE))
    print("  Clone done.")

    # Step 3 — patch colours
    print("Patching SpecPine colours (green → teal) …")
    n = patch_theme_root(SPECPINE)
    print(f"  {n} JSON file(s) patched.")

    # Step 4 — activate: replace wargames with symlink → specpine
    print("Activating SpecPine theme (symlink swap) …")
    if WARGAMES.exists() or WARGAMES.is_symlink():
        if WARGAMES.is_symlink():
            WARGAMES.unlink()
        else:
            shutil.rmtree(str(WARGAMES))
    WARGAMES.symlink_to(SPECPINE)
    print(f"  {WARGAMES} → {SPECPINE}")

    # Step 5 — restart pager service
    print("Restarting pineapplepager …")
    ret = subprocess.call(["service", "pineapplepager", "restart"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if ret == 0:
        print("  Service restarted OK.")
    else:
        print(f"  Warning: service restart returned {ret} — try manually:")
        print("    service pineapplepager restart")

    print("=== SpecPine theme active ===")
    return 0


def restore() -> int:
    print("=== Restoring wargames theme ===")

    if not WARGAMES_BAK.exists():
        print(f"ERROR: no backup at {WARGAMES_BAK} — nothing to restore.")
        return 1

    print("Removing current wargames (or symlink) …")
    if WARGAMES.exists() or WARGAMES.is_symlink():
        if WARGAMES.is_symlink():
            WARGAMES.unlink()
        else:
            shutil.rmtree(str(WARGAMES))

    print(f"Restoring from {WARGAMES_BAK} …")
    shutil.copytree(str(WARGAMES_BAK), str(WARGAMES))

    print("Restarting pineapplepager …")
    subprocess.call(["service", "pineapplepager", "restart"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("=== wargames theme restored ===")
    return 0


def status() -> None:
    wg_is_link = WARGAMES.is_symlink()
    wg_target  = os.readlink(str(WARGAMES)) if wg_is_link else "(real dir)"
    bak_exists = WARGAMES_BAK.exists()
    sp_exists  = SPECPINE.exists()

    print(f"wargames   : {'→ ' + wg_target if wg_is_link else 'real directory'}")
    print(f"specpine   : {'present' if sp_exists else 'not installed'}")
    print(f"backup     : {'present' if bak_exists else 'none'}")
    if wg_is_link and str(WARGAMES.resolve()) == str(SPECPINE):
        print("active     : SpecPine")
    else:
        print("active     : wargames (default)")


if __name__ == "__main__":
    if "--restore" in sys.argv:
        sys.exit(restore())
    elif "--status" in sys.argv:
        status()
        sys.exit(0)
    else:
        sys.exit(install())
