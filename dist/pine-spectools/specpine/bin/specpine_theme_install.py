#!/usr/bin/env python3
"""
SpecPine Theme Installer — runs ON the Pager.

Creates /lib/pager/themes/specpine alongside (not replacing) the existing
wargames theme, patches colours (shifts phosphor-green → teal/cyan), and
restarts pineapplepager so the firmware's Theme selector lists both options.

The firmware scans /lib/pager/themes/ for directories, so having two real
directories means the user can switch between them via Settings → Display →
Theme without SpecPine replacing wargames.

Usage (from the Pager shell):
    python3 /root/payloads/user/reconnaissance/specpine/bin/specpine_theme_install.py
    python3 /root/payloads/user/reconnaissance/specpine/bin/specpine_theme_install.py --restore
    python3 /root/payloads/user/reconnaissance/specpine/bin/specpine_theme_install.py --status

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
# (in theme.json color_palette and inline in component JSONs) and as [R,G,B]
# arrays. We detect wargames-green by hue (high G, low B relative to G) and
# shift it to teal/cyan by blending blue up from the green channel.
#
#   primary green  (0, 220, 80)  → teal       (0, 194, 185)
#   dim green      (0, 140, 50)  → dim teal   (0, 123, 122)
#   bright green   (0, 255, 120) → cyan       (0, 224, 221)
#
# Colours that aren't green-family (reds, whites, ambers, navies) pass through.

def _is_wargames_green(r: int, g: int, b: int) -> bool:
    """True if this colour belongs to the wargames phosphor-green family.

    Criteria: green-dominant, not neutral, and blue is clearly less than green.
    We use strict thresholds to avoid accidentally recolouring reds or whites.
    """
    return g >= 80 and g > r * 1.4 and b < g * 0.65 and g > b + 30

def _remap(r: int, g: int, b: int) -> tuple[int, int, int]:
    """Shift a wargames-green colour into SpecPine teal/cyan."""
    if not _is_wargames_green(r, g, b):
        return r, g, b
    # Tilt hue from green toward cyan by boosting blue toward the green level.
    # Slight green reduction keeps the overall luminance stable.
    new_b = min(255, int(b + (g - b) * 0.86))
    new_g = min(255, int(g * 0.88))
    new_r = r  # red stays (usually 0 in wargames)
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


# ── Theme management ─────────────────────────────────────────────────────────
# Strategy: side-by-side real directories.
# The firmware scans /lib/pager/themes/ for subdirectories and lists all of
# them in Settings → Display → Theme. We create specpine/ as a separate real
# directory alongside wargames/ — no symlink swap needed. The user switches
# themes using the firmware's own selector.

def _ensure_wargames_is_real_dir() -> bool:
    """Make sure wargames exists as a real directory (not a symlink).

    If wargames is currently a symlink (from a previous installer run) or is
    missing, restore it from wargames.bak. Returns True on success.
    """
    if WARGAMES.is_symlink():
        print("  wargames is a symlink — unlinking …")
        WARGAMES.unlink()

    if not WARGAMES.exists():
        if not WARGAMES_BAK.exists():
            print(f"ERROR: {WARGAMES} missing and no backup to restore from.")
            return False
        print(f"  Restoring wargames from {WARGAMES_BAK} …")
        shutil.copytree(str(WARGAMES_BAK), str(WARGAMES))

    return True


def _restart_pager() -> None:
    """Hot-restart pineapplepager so it rescans the themes directory."""
    print("Restarting pineapplepager …")
    ret = subprocess.call(["service", "pineapplepager", "restart"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if ret == 0:
        print("  Service restarted OK.")
    else:
        print(f"  Warning: service restart returned {ret} — try manually:")
        print("    service pineapplepager restart")


def install() -> int:
    print("=== SpecPine Theme Installer ===")

    # Step 1 — ensure we have a clean wargames backup to clone from
    if WARGAMES_BAK.exists():
        print(f"  Backup already present at {WARGAMES_BAK}")
    else:
        src = WARGAMES.resolve() if WARGAMES.is_symlink() else WARGAMES
        if not src.exists():
            print(f"ERROR: {WARGAMES} not found — cannot clone base theme.")
            return 1
        print(f"Backing up wargames → {WARGAMES_BAK} …")
        shutil.copytree(str(src), str(WARGAMES_BAK))
        print("  Backup done.")

    # Step 2 — ensure wargames is a real directory (un-symlink if needed)
    if not _ensure_wargames_is_real_dir():
        return 1

    # Step 3 — create/refresh specpine from the backup
    if SPECPINE.exists():
        print(f"  Removing stale {SPECPINE} …")
        shutil.rmtree(str(SPECPINE))
    print(f"Cloning wargames.bak → {SPECPINE} …")
    shutil.copytree(str(WARGAMES_BAK), str(SPECPINE))
    print("  Clone done.")

    # Step 4 — patch colours in specpine only (wargames stays vanilla)
    print("Patching SpecPine colours (green → teal/cyan) …")
    n = patch_theme_root(SPECPINE)
    print(f"  {n} JSON file(s) patched.")

    # Step 5 — restart so the firmware rescans /lib/pager/themes/
    # After restart, Settings → Display → Theme will list both wargames and specpine.
    _restart_pager()

    print("=== SpecPine theme installed ===")
    print("  Switch to it via: Settings → Display → Theme → specpine")
    return 0


def remove() -> int:
    """Remove the specpine theme directory. wargames is left untouched."""
    print("=== Removing SpecPine theme ===")

    if not SPECPINE.exists():
        print("  specpine not installed — nothing to do.")
        return 0

    print(f"Removing {SPECPINE} …")
    shutil.rmtree(str(SPECPINE))

    # Also clean up any leftover symlink in case wargames is still pointing at it
    if WARGAMES.is_symlink():
        print("  Detected stale wargames symlink — restoring real directory …")
        _ensure_wargames_is_real_dir()

    _restart_pager()
    print("=== SpecPine theme removed ===")
    return 0


def restore() -> int:
    """Alias for remove() — kept for backward compatibility."""
    return remove()


def status() -> None:
    themes = sorted(
        p.name for p in THEME_DIR.iterdir()
        if (p.is_dir() or p.is_symlink()) and not p.name.startswith(".")
    ) if THEME_DIR.exists() else []

    print(f"themes dir : {THEME_DIR}")
    for t in themes:
        p = THEME_DIR / t
        if p.is_symlink():
            print(f"  {t:20s} → {os.readlink(str(p))}  (symlink)")
        else:
            print(f"  {t:20s}   (real dir)")

    sp_installed = SPECPINE.exists() and not SPECPINE.is_symlink()
    wg_ok        = WARGAMES.exists() and not WARGAMES.is_symlink()
    print(f"specpine   : {'installed' if sp_installed else 'not installed'}")
    print(f"wargames   : {'real dir (OK)' if wg_ok else 'symlink or missing (run install to fix)'}")
    print(f"backup     : {'present' if WARGAMES_BAK.exists() else 'none'}")


if __name__ == "__main__":
    if "--restore" in sys.argv or "--remove" in sys.argv:
        sys.exit(restore())
    elif "--status" in sys.argv:
        status()
        sys.exit(0)
    else:
        sys.exit(install())
