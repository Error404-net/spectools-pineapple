#!/usr/bin/env python3
"""
Render the SpecPine WarGames-style promo image set.

Produces PNGs to images/specpine/. Each card is a synthesised "screenshot":
green CRT phosphor on near-black, with optional cyan/magenta neon accents
(Hackers '95 palette). Mirrors BluePine's images/ promo-art convention but
generated programmatically so it stays reproducible.

Run:
    python3 scripts/generate_theme_images.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:
    print("Pillow is required:  python3 -m pip install --user --break-system-packages Pillow")
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR   = REPO_ROOT / "images" / "specpine"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Palette ──────────────────────────────────────────────────────────────
BG       = (8, 12, 8)
BG_DARK  = (3, 6,  3)
GREEN    = (0,   220, 100)
GREEN_D  = (0,   140, 60)
GREEN_DD = (0,   70,  30)
AMBER    = (255, 180, 40)
RED      = (220, 50,  60)
CYAN     = (60,  220, 220)
MAGENTA  = (220, 60,  180)
WHITE    = (220, 255, 220)

# ── Font discovery — prefer monospaced, fall back to PIL default ─────────
def _find_mono_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Monaco.dfont",
        "/Library/Fonts/Andale Mono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
        "/Library/Fonts/Courier New Bold.ttf",
        "/System/Library/Fonts/Courier.dfont",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


# ── Drawing primitives ───────────────────────────────────────────────────

def _scanlines(img: Image.Image, dim: tuple[int, int, int] = BG_DARK, every: int = 3) -> None:
    draw = ImageDraw.Draw(img)
    for y in range(0, img.height, every):
        draw.line([(0, y), (img.width, y)], fill=dim, width=1)


def _grid(img: Image.Image, color: tuple[int, int, int], step: int = 24) -> None:
    draw = ImageDraw.Draw(img)
    for x in range(0, img.width, step):
        draw.line([(x, 0), (x, img.height)], fill=color, width=1)
    for y in range(0, img.height, step):
        draw.line([(0, y), (img.width, y)], fill=color, width=1)


def _crt_frame(img: Image.Image, accent: tuple[int, int, int]) -> None:
    """Outer brackets + corner notches for the CRT-card aesthetic."""
    draw = ImageDraw.Draw(img)
    w, h = img.width, img.height
    pad = 14
    # Outer border
    draw.rectangle([pad, pad, w - pad - 1, h - pad - 1], outline=accent, width=2)
    # Corner notches
    notch = 18
    for cx, cy in [(pad, pad), (w - pad - 1, pad), (pad, h - pad - 1), (w - pad - 1, h - pad - 1)]:
        draw.line([(cx - notch, cy), (cx + notch, cy)], fill=accent, width=2)
        draw.line([(cx, cy - notch), (cx, cy + notch)], fill=accent, width=2)


def _phosphor_glow(img: Image.Image) -> Image.Image:
    """Soft glow over green text (cheap bloom)."""
    glow = img.filter(ImageFilter.GaussianBlur(radius=2))
    return Image.blend(img, glow, 0.35)


def render_card(
    out_path: Path,
    title: str,
    body_lines: list[str],
    accent: tuple[int, int, int] = GREEN,
    size: tuple[int, int] = (1200, 600),
    title_size: int = 56,
    body_size: int = 22,
    sub_title: str | None = None,
    sub_size: int | None = None,
    footer: str | None = None,
) -> None:
    img = Image.new("RGB", size, BG)
    _grid(img, GREEN_DD, step=20)
    _crt_frame(img, accent)

    draw = ImageDraw.Draw(img)
    title_font = _find_mono_font(title_size)
    sub_size_eff = sub_size if sub_size else min(int(title_size * 0.45), 28)
    sub_font   = _find_mono_font(sub_size_eff)
    body_font  = _find_mono_font(body_size)
    footer_font = _find_mono_font(18)

    # Title — top left after notch
    margin_x = 60
    title_y  = 50
    draw.text((margin_x, title_y), title, font=title_font, fill=accent)

    # Subtitle
    sub_y = title_y + title_size + 6
    if sub_title:
        draw.text((margin_x, sub_y), sub_title, font=sub_font, fill=GREEN_D)

    # Body — terminal-like prompt lines
    body_y = sub_y + (sub_size_eff + 18 if sub_title else 30) + 20
    for ln in body_lines:
        if ln.startswith("$ "):
            # leading prompt in white
            draw.text((margin_x, body_y), "$ ",   font=body_font, fill=WHITE)
            offset = draw.textlength("$ ", font=body_font)
            draw.text((margin_x + offset, body_y), ln[2:], font=body_font, fill=accent)
        elif ln.startswith("> "):
            draw.text((margin_x, body_y), "> ",   font=body_font, fill=AMBER)
            offset = draw.textlength("> ", font=body_font)
            draw.text((margin_x + offset, body_y), ln[2:], font=body_font, fill=GREEN)
        elif ln.startswith("! "):
            draw.text((margin_x, body_y), "! ",   font=body_font, fill=RED)
            offset = draw.textlength("! ", font=body_font)
            draw.text((margin_x + offset, body_y), ln[2:], font=body_font, fill=accent)
        else:
            draw.text((margin_x, body_y), ln, font=body_font, fill=accent)
        body_y += body_size + 8

    # Footer brand strip
    foot = footer if footer else "SpecPine . RF Intel . shall we play a game?"
    draw.text((margin_x, size[1] - 60), foot, font=footer_font, fill=GREEN_D)

    # CRT effects
    _scanlines(img, BG_DARK, every=3)
    img = _phosphor_glow(img)

    img.save(out_path, "PNG")
    print(f"  wrote {out_path.relative_to(REPO_ROOT)}")


# ── Image manifest ───────────────────────────────────────────────────────

def render_all() -> None:
    print(f"Rendering SpecPine theme images → {OUT_DIR.relative_to(REPO_ROOT)}")

    render_card(
        OUT_DIR / "specpine-poster.png",
        title="SpecPine",
        sub_title="RF SPECTRUM ANALYSIS . WI-SPY DBX . HAK5 PAGER",
        body_lines=[
            "$ specpine --start",
            "> bridge online",
            "> waterfall engaged",
            "> shall we play a game?",
        ],
        accent=GREEN,
        size=(1200, 600),
        title_size=110,
    )

    render_card(
        OUT_DIR / "specpine-poster-cyan.png",
        title="SpecPine",
        sub_title="WOPR . NORAD . 2.4 GHZ . HACKERS '95 EDITION",
        body_lines=[
            "$ specpine --neon",
            "> palette: cyan/magenta",
            "> mode: glitch",
            "> hack the planet.",
        ],
        accent=CYAN,
        size=(1200, 600),
        title_size=110,
    )

    render_card(
        OUT_DIR / "specpine-quickscan.png",
        title="QUICK SCAN",
        sub_title="single-shot RSSI snapshot",
        body_lines=[
            "$ pick band: 2.4 GHz",
            "> capture 3 s . 256 bins",
            "> min: -94 dBm",
            "> max: -42 dBm",
            "> avg: -78 dBm",
        ],
        accent=GREEN,
        title_size=56,
    )

    render_card(
        OUT_DIR / "specpine-text-waterfall.png",
        title="TEXT WATERFALL",
        sub_title="50-col density map on Pager LOG",
        body_lines=[
            "|. -=+++#.= +#-..  +###.| -42",
            "|. -==++===.= +##-.. +##| -41",
            "|.  -=+#==.+ -=#.. =##  | -45",
            "> tap OK pause / hold OK stop",
        ],
        accent=GREEN,
        title_size=56,
    )

    render_card(
        OUT_DIR / "specpine-graphical-waterfall.png",
        title="GRAPHICAL WATERFALL",
        sub_title="RGB565 . 480x222 . /dev/fb0",
        body_lines=[
            "$ vtcon released",
            "> 6 fps . 162-row history",
            "> ch markers . dBm legend",
            "> hold OK to restore display",
        ],
        accent=CYAN,
        title_size=52,
    )

    render_card(
        OUT_DIR / "specpine-channel-analysis.png",
        title="CHANNEL ANALYSIS",
        sub_title="Wi-Fi 2.4 / 5 GHz utilisation",
        body_lines=[
            "Ch    avg     max   util%",
            "  6  -64.2   -38.0   71.4",
            "  1  -71.8   -45.3   42.1",
            " 11  -76.4   -50.1   28.8",
            " 36  -82.0   -58.6    9.0",
        ],
        accent=GREEN,
        title_size=52,
    )

    render_card(
        OUT_DIR / "specpine-anomaly.png",
        title="ANOMALY DETECTION",
        sub_title="moving-baseline jammer watch",
        body_lines=[
            "> baseline: -82.4 dBm . window 10",
            "> threshold delta: 15 dB",
            "! ANOMALY 14:02:18  delta=23.1",
            "! ANOMALY 14:02:24  delta=18.7",
            "> red LED + Warning ringtone",
        ],
        accent=AMBER,
        title_size=52,
    )

    render_card(
        OUT_DIR / "specpine-sessions.png",
        title="SAVED SESSIONS",
        sub_title="/root/loot/specpine browser",
        body_lines=[
            "session_20260509_1402_quick    .meta.json",
            "session_20260509_1404_text     events.jsonl",
            "session_20260509_1410_anomaly  anomaly_log.txt",
            "> view summary . replay . delete",
        ],
        accent=GREEN,
        title_size=52,
    )

    render_card(
        OUT_DIR / "specpine-settings.png",
        title="SETTINGS",
        sub_title="persistent under PAYLOAD_GET_CONFIG specpine",
        body_lines=[
            "default_band         auto",
            "default_mode         text",
            "stall_timeout        8 s",
            "anomaly_threshold    15 dB",
            "mute / no-loot / GPS / diagnostics",
        ],
        accent=GREEN,
        title_size=52,
    )

    render_card(
        OUT_DIR / "specpine-install.png",
        title="INSTALL / REPAIR",
        sub_title="one-shot deploy to /opt/spectools",
        body_lines=[
            "$ install",
            "> spectool_raw . spectool_net",
            "> libusb-0.1 . libusb-1.0 + symlinks",
            "> /etc/spectools/spectools.conf",
            "> /etc/udev/rules.d/99-wispy.rules",
        ],
        accent=GREEN,
        title_size=52,
    )

    render_card(
        OUT_DIR / "specpine-boot.png",
        title="SpecPine v1.0",
        sub_title="Press OK to start",
        body_lines=[
            "> sourcing funcs_main . funcs_menu . funcs_scan",
            "> ringtone: Flutter",
            "> shall we play a game?",
            "> awaiting OK",
        ],
        accent=GREEN,
        title_size=68,
    )

    print("Done.")


if __name__ == "__main__":
    render_all()
