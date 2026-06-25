#!/usr/bin/env python3
"""
SpecPine custom main-menu HUD.

Draws the top-level SpecPine menu directly to /dev/fb0 instead of handing
it to the firmware's LIST_PICKER. Until now, EVERY screen except the
graphical waterfall (logo, main menu, "Exit SpecPine?", settings, etc.)
was rendered by the firmware's own UI process using its standard wargames
dialog chrome -- which is why the app could look indistinguishable from
"the default Pager screen" even while running correctly. This script
takes over the framebuffer the same way spectools_waterfall_fb.py does
(SIGSTOP /pineapple/pineapple, write RGB565 frames directly) so the most
commonly seen screen -- the main menu -- is visibly, unmistakably SpecPine.

Reuses the framebuffer primitives (RGB565 packing, font, raw fb writes,
pineapple SIGSTOP/CONT) from spectools_waterfall_fb.py rather than
duplicating them, and extends its font with the extra letters menu text
needs (that module only defined enough glyphs for its own waterfall UI).

Protocol: on a real selection, prints a single integer to stdout and
exits 0 -- the chosen menu index, matching the existing case statement in
payload.sh (1=Status, 2=Quick Scan, ... 0=Exit, already confirmed by the
user inside this script). Any other exit code, or non-numeric/empty
stdout, means the caller should fall back to the firmware LIST_PICKER
menu (see main_menu_hud() in funcs_menu.sh) -- this script is deliberately
defensive about that so a missing evtest/fb0 never leaves the user
stranded with a blank screen.

Usage:
    specpine_hud.py --app-version 1.2
"""
from __future__ import annotations

import argparse
import atexit
import os
import re
import select
import signal
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spectools_waterfall_fb as wf  # noqa: E402  (reuse fb primitives/font/pineapple stop-cont)

FB_PATH = wf.FB_PATH
IMG_W, IMG_H = wf.IMG_W, wf.IMG_H
FB_W, FB_H = wf.FB_W, wf.FB_H

# ── Extra glyphs spectools_waterfall_fb.py's font doesn't define ────────────
# That module only drew its own waterfall UI strings ("SpecTools Waterfall",
# "Wi-Spy DBx", dBm numbers, MHz labels) so its 5x7 font is missing most of
# the alphabet. Extend it in place (module-level dict, shared by reference)
# rather than keeping a second copy of the font to drift out of sync.
wf._GLYPHS.update({
    'A': [0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    'E': [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F],
    'F': [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10],
    'G': [0x0F, 0x10, 0x10, 0x17, 0x11, 0x11, 0x0E],
    'I': [0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E],
    'J': [0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C],
    'K': [0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11],
    'L': [0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F],
    'N': [0x11, 0x19, 0x15, 0x15, 0x13, 0x11, 0x11],
    'O': [0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    'Q': [0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D],
    'R': [0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11],
    'U': [0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    'V': [0x11, 0x11, 0x11, 0x11, 0x0A, 0x0A, 0x04],
    'Y': [0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04],
    'Z': [0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F],
    'a': [0x00, 0x00, 0x0E, 0x01, 0x0F, 0x11, 0x0F],
    'f': [0x06, 0x09, 0x08, 0x1C, 0x08, 0x08, 0x08],
    'g': [0x00, 0x00, 0x0F, 0x11, 0x0F, 0x01, 0x0E],
    'j': [0x02, 0x00, 0x06, 0x02, 0x02, 0x12, 0x0C],
    'q': [0x00, 0x00, 0x0F, 0x11, 0x0F, 0x01, 0x01],
    'u': [0x00, 0x00, 0x11, 0x11, 0x11, 0x13, 0x0D],
    'v': [0x00, 0x00, 0x11, 0x11, 0x0A, 0x0A, 0x04],
    ':': [0x00, 0x06, 0x06, 0x00, 0x06, 0x06, 0x00],
    '!': [0x04, 0x04, 0x04, 0x04, 0x04, 0x00, 0x04],
    '?': [0x0E, 0x11, 0x01, 0x02, 0x04, 0x00, 0x04],
    '/': [0x01, 0x02, 0x04, 0x08, 0x10, 0x00, 0x00],
    '_': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1F],
    '=': [0x00, 0x00, 0x1F, 0x00, 0x1F, 0x00, 0x00],
})


def _text2x(fb: bytearray, text: str, x: int, y: int, color: int) -> None:
    """Draw text at 2× scale. Each pixel becomes a 2×2 block; char stride = 12."""
    for i, ch in enumerate(text):
        glyph = wf._GLYPHS.get(ch.upper(), wf._GLYPHS.get(' ', [0] * 7))
        cx = x + i * 12
        for row, bits in enumerate(glyph):
            for col in range(5):
                if bits & (1 << (4 - col)):
                    px, py = cx + col * 2, y + row * 2
                    wf._put(fb, px,     py,     color)
                    wf._put(fb, px + 1, py,     color)
                    wf._put(fb, px,     py + 1, color)
                    wf._put(fb, px + 1, py + 1, color)


def _scanlines(fb: bytearray, y0: int, y1: int) -> None:
    """Overlay subtle dark scanlines between rows for CRT effect."""
    dark = wf.rgb565(*C_SCAN_DARK)
    for ly in range(y0, y1, 4):   # every 4th row slightly darker
        wf._fill(fb, 0, ly, wf.IMG_W, 1, dark)


# Layout — 4 menu items with generous row spacing
# Total vertical budget: IMG_H=222. 30 + 4 + 4*38 + 20 = 206 ≤ 222 ✓
HEADER_H  = 30    # header bar height
FOOTER_H  = 20    # footer bar height
ROW_H     = 38    # per menu row (14px text + padding for spacious look)
MENU_Y0   = HEADER_H + 4   # first item y (4px gap after header bar)

BACK_HOLD_SECS = 2.0

# Kept for compatibility; new draw_menu() uses inline WarGames palette instead.
C_HILITE    = (0, 70, 80)
C_SCAN_DARK = (7, 11, 19)
C_PROGRESS  = (0, 160, 120)

EVT_CANDIDATES_DIR = "/dev/input"
EVT_DEFAULT = "/dev/input/event0"

_UP_RE   = re.compile(r"\(KEY_UP\), value 1")
_DOWN_RE = re.compile(r"\(KEY_DOWN\), value 1")
_OK_RE   = re.compile(r"\(BTN_EAST\), value 1")
# Back button: any EV_KEY press/release that isn't the d-pad or OK.
# Using broad match after the specific elif checks ensures d-pad/OK are
# never double-counted; the DPAD/OK exclusion regex is just belt-and-suspenders.
_DPAD_OK_RE    = re.compile(r"KEY_UP|KEY_DOWN|KEY_LEFT|KEY_RIGHT|BTN_EAST")
_BACK_PRESS_RE = re.compile(r"type 1.*value 1")
_BACK_REL_RE   = re.compile(r"type 1.*value 0")

# Debug trail for diagnosing input issues without a live session: every raw
# evtest line and every parsed event gets appended here. Caller (payload.sh's
# main_menu_hud) already redirects this script's own stderr into
# /tmp/specpine.log, but evtest's *raw* output is otherwise discarded
# (stderr=DEVNULL on the evtest Popen) -- this file is the only place that
# raw stream is ever visible, which is exactly what's needed to tell "evtest
# never started" apart from "evtest ran but our regex didn't match" apart
# from "events matched but never reached the draw loop".
DEBUG_LOG = "/tmp/specpine_hud_debug.log"


def _dbg(msg: str) -> None:
    try:
        with open(DEBUG_LOG, "a") as fh:
            fh.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except OSError:
        pass


# Singleton lock. payload.sh already has its own lock so two *payload*
# launches can't collide, but that lock doesn't cover this script: a stray
# manual invocation (e.g. `python3 specpine_hud.py ...` run directly in a
# shell for debugging) is invisible to it. If that stray process is still
# alive -- holding the framebuffer, evtest, and a SIGSTOPped pineapple --
# real button presses on a later, legitimate payload launch can be picked up
# by the wrong process entirely, which looks exactly like "the menu is
# wired up wrong" from the user's seat even though it's actually two
# instances fighting over the same hardware. Refuse to start a second
# instance instead; the caller falls back to the firmware LIST_PICKER menu,
# which is a safe, correct screen even if a stray process is still around.
LOCK_PATH = "/tmp/specpine_hud.lock"


def _acquire_lock() -> bool:
    try:
        if os.path.exists(LOCK_PATH):
            with open(LOCK_PATH) as fh:
                old_pid_s = fh.read().strip()
            if old_pid_s.isdigit():
                old_pid = int(old_pid_s)
                try:
                    os.kill(old_pid, 0)
                except OSError:
                    pass  # stale lock -- that pid is gone, safe to take over
                else:
                    _dbg(f"_acquire_lock: refusing -- pid {old_pid} already holds {LOCK_PATH}")
                    return False
        with open(LOCK_PATH, "w") as fh:
            fh.write(str(os.getpid()))
        return True
    except OSError as exc:
        _dbg(f"_acquire_lock: OSError {exc!r} -- proceeding without lock")
        return True


def _release_lock() -> None:
    try:
        if os.path.exists(LOCK_PATH):
            with open(LOCK_PATH) as fh:
                if fh.read().strip() == str(os.getpid()):
                    os.remove(LOCK_PATH)
    except OSError:
        pass


def open_evtest() -> "subprocess.Popen | None":
    path = EVT_DEFAULT
    if not os.path.exists(path):
        try:
            cands = sorted(p for p in os.listdir(EVT_CANDIDATES_DIR) if p.startswith("event"))
        except OSError:
            cands = []
        if not cands:
            _dbg("open_evtest: no /dev/input/event* candidates found")
            return None
        path = os.path.join(EVT_CANDIDATES_DIR, cands[0])
    evtest_bin = shutil.which("evtest")
    if evtest_bin is None:
        for _candidate in ("/sbin/evtest", "/usr/sbin/evtest", "/usr/bin/evtest", "/bin/evtest"):
            if os.path.isfile(_candidate):
                evtest_bin = _candidate
                break
    if evtest_bin is None:
        _dbg(f"open_evtest: evtest not found; PATH={os.environ.get('PATH', '')}")
        print("[hud] evtest not found in PATH or known locations", file=sys.stderr)
        return None

    _dbg(f"open_evtest: using {path!r}, evtest_bin={evtest_bin!r}")
    try:
        proc = subprocess.Popen(
            [evtest_bin, path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        _dbg(f"open_evtest: evtest pid={proc.pid}")
        return proc
    except Exception as exc:
        print(f"[hud] could not start evtest: {exc}", file=sys.stderr)
        _dbg(f"open_evtest: Popen raised {exc!r}")
        return None


def poll(proc: "subprocess.Popen | None", deadline: float) -> list[str]:
    """Collect parsed event names ('up'/'down'/'ok') available before `deadline`
    (an absolute time.monotonic() value). Always waits out the full window
    (sleeping if there's nothing to read) so callers get a steady tick rate.
    """
    out: list[str] = []
    if proc is None or proc.stdout is None:
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
        return out
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        r, _, _ = select.select([proc.stdout], [], [], remaining)
        if not r:
            break
        line = proc.stdout.readline()
        if not line:
            # evtest's stdout closed (process died). Log its stderr once so
            # the cause (bad device path, permission denied, etc.) shows up
            # in the debug trail instead of just silently never matching.
            _dbg("poll: evtest stdout EOF -- process likely exited")
            if proc.stderr is not None:
                try:
                    err = proc.stderr.read()
                except Exception:
                    err = ""
                if err:
                    _dbg(f"poll: evtest stderr: {err.strip()!r}")
            break
        _dbg(f"raw: {line.rstrip()}")
        if _UP_RE.search(line):
            out.append("up")
        elif _DOWN_RE.search(line):
            out.append("down")
        elif _OK_RE.search(line):
            out.append("ok")
        elif _BACK_PRESS_RE.search(line) and not _DPAD_OK_RE.search(line):
            out.append("back_press")
        elif _BACK_REL_RE.search(line) and not _DPAD_OK_RE.search(line):
            out.append("back_release")
    if out:
        _dbg(f"poll: parsed events {out}")
    return out


def draw_menu(
    fb: bytearray,
    items: list[tuple[str, int]],
    cursor: int,
    app_version: str,
    back_hold_frac: float = 0.0,   # 0.0–1.0 progress while holding Back
) -> None:
    # WarGames CRT phosphor palette — matches the boot splash
    bg     = wf.rgb565(  0,   8,   4)   # near-black with green tint
    bar_bg = wf.rgb565(  0,  20,  10)   # slightly lighter bar
    green  = wf.rgb565(  0, 220, 100)   # bright phosphor green (selected / accents)
    dim    = wf.rgb565(  0,  80,  40)   # dim green (unselected items / hints)
    grid_c = wf.rgb565(  0,  35,  18)   # very faint grid lines
    amber  = wf.rgb565(255, 180,   0)   # amber (title / hold-bar)

    # ── background + horizontal grid ──────────────────────────────────────
    wf._fill(fb, 0, 0, IMG_W, IMG_H, bg)
    for gy in range(0, IMG_H, 24):
        wf._fill(fb, 0, gy, IMG_W, 1, grid_c)

    # ── 1-px border ───────────────────────────────────────────────────────
    wf._fill(fb, 0, 0, IMG_W, 1, dim)
    wf._fill(fb, 0, IMG_H - 1, IMG_W, 1, dim)
    wf._fill(fb, 0, 0, 1, IMG_H, dim)
    wf._fill(fb, IMG_W - 1, 0, 1, IMG_H, dim)

    # ── header bar ────────────────────────────────────────────────────────
    wf._fill(fb, 0, 0, IMG_W, HEADER_H, bar_bg)
    _text2x(fb, "SPECPINE", 8, 8, amber)
    ver_label = f"v{app_version}"
    _text2x(fb, ver_label, IMG_W - len(ver_label) * 12 - 8, 8, dim)
    wf._hline(fb, 0, IMG_W - 1, HEADER_H - 1, green)
    wf._hline(fb, 0, IMG_W - 1, HEADER_H - 2, green)

    # ── menu items ────────────────────────────────────────────────────────
    for i, (label, _idx) in enumerate(items):
        y = MENU_Y0 + i * ROW_H
        if y + ROW_H > IMG_H - FOOTER_H:
            break
        ty = y + (ROW_H - 14) // 2   # vertically center 14px (2x) text in row
        if i == cursor:
            _text2x(fb, f"> {label}", 8, ty, green)
        else:
            _text2x(fb, f"  {label}", 8, ty, dim)

    # ── footer bar ────────────────────────────────────────────────────────
    footer_y0 = IMG_H - FOOTER_H
    wf._fill(fb, 0, footer_y0, IMG_W, FOOTER_H, bar_bg)
    wf._hline(fb, 0, IMG_W - 1, footer_y0,     green)
    wf._hline(fb, 0, IMG_W - 1, footer_y0 + 1, green)

    if back_hold_frac > 0.0:
        bar_w = int(IMG_W * min(back_hold_frac, 1.0))
        wf._fill(fb, 0, footer_y0 + 3, bar_w, FOOTER_H - 5, amber)
        hint = "HOLD BACK:EXIT"
        _text2x(fb, hint, (IMG_W - len(hint) * 12) // 2, footer_y0 + 3, bar_bg)
    else:
        hint = "UP/DN:NAV  OK:SEL  HOLD.B:EXIT"
        _text2x(fb, hint, (IMG_W - len(hint) * 12) // 2, footer_y0 + 3, dim)


def draw_confirm(fb: bytearray, app_version: str) -> None:
    bg = wf.rgb565(*wf.C_BG)
    wf._fill(fb, 0, 0, IMG_W, IMG_H, bg)

    bar = wf.rgb565(*wf.C_BAR)
    wf._fill(fb, 0, 0, IMG_W, 14, bar)
    white = wf.rgb565(*wf.C_WHITE)
    teal = wf.rgb565(*wf.C_TEAL)
    red = wf.rgb565(*C_EXIT)
    gray = wf.rgb565(*wf.C_GRAY)
    wf._text(fb, f"SpecPine v{app_version}", 4, 4, white)
    wf._hline(fb, 0, IMG_W - 1, 14, teal)

    wf._text(fb, "Exit SpecPine?", 170, 90, red)
    wf._text(fb, "OK = confirm exit", 130, 120, white)
    wf._text(fb, "any other key = cancel", 100, 140, gray)


def confirm_exit(fb: bytearray, flush, proc, app_version: str) -> bool:
    """Returns True only on an explicit OK press. Any other key, or a 6s
    timeout with no input at all, cancels -- defaults to NOT exiting, since
    that's the safer failure mode for an accidental press.
    """
    draw_confirm(fb, app_version)
    flush(fb)
    deadline = time.monotonic() + 6.0
    while time.monotonic() < deadline:
        events = poll(proc, min(deadline, time.monotonic() + 0.1))
        for ev in events:
            return ev == "ok"
    return False


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="SpecPine framebuffer main-menu HUD")
    p.add_argument("--app-version", default="1.0")
    args = p.parse_args(argv)

    items: list[tuple[str, int]] = [
        ("WATERFALL/ASCII",  2),
        ("WATERFALL/GRAPH",  3),
        ("SYS/CONFIG",       7),
    ]

    # Belt-and-suspenders, same pattern as spectools_waterfall_fb.py: any
    # interpreter exit path (signal, exception, normal return) must resume
    # pineapple, or the whole Pager UI (display + input) freezes permanently.
    def _bail(*_):
        wf.pineapple_cont()
        sys.exit(1)
    signal.signal(signal.SIGINT, _bail)
    signal.signal(signal.SIGTERM, _bail)
    atexit.register(wf.pineapple_cont)

    _dbg("=== specpine_hud.py starting ===")

    if not _acquire_lock():
        print("[hud] another instance already owns the framebuffer/input -- "
              "aborting to fallback menu", file=sys.stderr)
        _dbg("main: lock held by another live process -- aborting to fallback")
        return 1
    atexit.register(_release_lock)

    proc = open_evtest()
    if proc is None:
        print("[hud] no input device available -- aborting to fallback menu", file=sys.stderr)
        _dbg("main: open_evtest() returned None -- aborting to fallback")
        return 1

    wf.pineapple_stop()
    _dbg("main: pineapple_stop() called (see stderr/specpine.log for SIGSTOP result)")

    fb = bytearray(FB_W * FB_H * 2)

    def flush(buf: bytearray) -> None:
        try:
            with open(FB_PATH, "r+b", buffering=0) as dev:
                dev.seek(0)
                dev.write(buf)
        except OSError as exc:
            print(f"[hud] fb write error: {exc}", file=sys.stderr)

    cursor = 0
    n = len(items)
    result: int | None = None
    back_pressed_at: float | None = None

    draw_menu(fb, items, cursor, args.app_version)
    flush(fb)

    try:
        while result is None:
            events = poll(proc, time.monotonic() + 0.1)
            redraw = False
            for ev in events:
                if ev == "up":
                    cursor = (cursor - 1) % n
                    redraw = True
                    back_pressed_at = None   # navigation cancels any hold
                elif ev == "down":
                    cursor = (cursor + 1) % n
                    redraw = True
                    back_pressed_at = None
                elif ev == "ok":
                    result = items[cursor][1]
                    break
                elif ev == "back_press":
                    if back_pressed_at is None:
                        back_pressed_at = time.monotonic()
                        redraw = True
                elif ev == "back_release":
                    back_pressed_at = None
                    redraw = True   # clear the progress bar

            if result is not None:
                break

            # Back-hold threshold: exit without second confirmation
            if back_pressed_at is not None:
                elapsed = time.monotonic() - back_pressed_at
                if elapsed >= BACK_HOLD_SECS:
                    result = 0
                    break
                redraw = True   # keep refreshing progress bar

            if redraw:
                frac = 0.0
                if back_pressed_at is not None:
                    frac = (time.monotonic() - back_pressed_at) / BACK_HOLD_SECS
                draw_menu(fb, items, cursor, args.app_version, back_hold_frac=frac)
                flush(fb)
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

    wf.pineapple_cont()
    _dbg(f"main: exiting with result={result!r}")
    print(result if result is not None else -1)
    return 0 if result is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
