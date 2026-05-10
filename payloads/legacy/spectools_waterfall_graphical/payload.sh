#!/bin/bash
# Title: SpecTools Waterfall (Graphical)
# Description: Full-colour RF spectrum waterfall on the Pager display (480x222)
# Author: Error404-net
# Category: reconnaissance
# Version: 1.0
#
# Requires: spectools_install to have been run first.
# Writes directly to /dev/fb0 — takes over the Pager display while running.
# Press Back (SIGTERM) to exit and restore the display.

PAYLOAD_ROOT="$(cd "$(dirname "$0")" && pwd)"
SPECTOOL_BIN="/opt/spectools/bin/spectool_raw"
SPECTOOL_LIB="/opt/spectools/lib"
BRIDGE_BIN="${PAYLOAD_ROOT}/bin/spectools_bridge.py"
RENDERER_BIN="${PAYLOAD_ROOT}/bin/spectools_waterfall_fb.py"

EVENTS_FILE="/tmp/spectools_events_fb.jsonl"
LOOT_ROOT="/root/loot/spectools_waterfall"
SESSION_TS="$(date +%Y%m%d_%H%M%S)"
SESSION_DIR="${LOOT_ROOT}/session_fb_${SESSION_TS}"
LOG_FILE="/tmp/spectools_waterfall_fb.log"
LOCK_FILE="/tmp/spectools_waterfall_fb.lock"
PID_FILE="/tmp/spectools_waterfall_fb.pid"
VTCON="/sys/class/vtconsole/vtcon1/bind"

BRIDGE_PID=""
RENDERER_PID=""

cleanup() {
    # Kill renderer first so it can re-enable vtcon via its own cleanup
    [ -n "$RENDERER_PID" ] && kill "$RENDERER_PID" 2>/dev/null || true
    pkill -f "spectools_waterfall_fb.py" 2>/dev/null || true
    # Give renderer a moment to re-enable vtcon itself
    sleep 0.3
    # Restore vtcon in case renderer didn't (path may not exist on all devices)
    [ -e "$VTCON" ] && echo 1 > "$VTCON" 2>/dev/null || true
    [ -n "$BRIDGE_PID" ] && kill "$BRIDGE_PID" 2>/dev/null || true
    pkill -f "spectools_bridge.py" 2>/dev/null || true
    rm -f "$LOCK_FILE" "$PID_FILE" "$EVENTS_FILE"
    LED R 0 G 0 B 0 2>/dev/null || LED OFF 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ── Singleton guard ──────────────────────────────────────────────────────────
if [ -f "$LOCK_FILE" ]; then
    OLD_PID="$(cat "$PID_FILE" 2>/dev/null)"
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        LOG red "Already running (pid $OLD_PID)"
        exit 1
    fi
    rm -f "$LOCK_FILE" "$PID_FILE"
fi
touch "$LOCK_FILE"
echo $$ > "$PID_FILE"

# ── Preflight ────────────────────────────────────────────────────────────────
LOG blue "SpecTools Waterfall (Graphical)"
LOG "Full-colour framebuffer display"
LOG "____________________________"

if [ ! -e "/dev/fb0" ]; then
    LOG red "/dev/fb0 not available"
    LOG red "Graphical mode requires framebuffer"
    ALERT "Framebuffer (/dev/fb0) not available on this device."
    exit 1
fi

if [ ! -x "$SPECTOOL_BIN" ]; then
    LOG red "spectool_raw not found"
    LOG red "Run spectools_install first"
    ALERT "Run the spectools_install payload to install binaries before using the waterfall."
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    LOG red "python3 not found"
    LOG red "Install: opkg install python3"
    exit 1
fi

if [ ! -f "$BRIDGE_BIN" ]; then
    LOG red "Missing: bin/spectools_bridge.py"
    exit 1
fi

if [ ! -f "$RENDERER_BIN" ]; then
    LOG red "Missing: bin/spectools_waterfall_fb.py"
    exit 1
fi

mkdir -p "$SESSION_DIR"
: > "$LOG_FILE"

LOG green "Dependencies OK"
LOG "Connecting to Wi-Spy DBx..."

# ── Start bridge ─────────────────────────────────────────────────────────────
rm -f "$EVENTS_FILE"

export LD_LIBRARY_PATH="${SPECTOOL_LIB}:${LD_LIBRARY_PATH:-}"
python3 "$BRIDGE_BIN" \
    --input-command "$SPECTOOL_BIN" \
    --events-file "$EVENTS_FILE" \
    --export-dir "$SESSION_DIR" \
    --stall-timeout 8 \
    --max-restarts 5 \
    >> "$LOG_FILE" 2>&1 &
BRIDGE_PID=$!

# Wait up to 6 s for bridge to produce data
waited=0
while [ ! -s "$EVENTS_FILE" ] && [ "$waited" -lt 6 ]; do
    sleep 1
    waited=$((waited + 1))
    if ! kill -0 "$BRIDGE_PID" 2>/dev/null; then
        LOG red "Bridge exited - check USB connection"
        LED R 255 G 0 B 0
        ALERT "Bridge failed to start. Is the Wi-Spy DBx plugged in?"
        exit 1
    fi
done

LED R 0 G 255 B 0
LOG green "Scanning - display is now live"
LOG "The Pager screen shows the waterfall."
LOG "Press Back to stop and restore display."
LOG "____________________________"

# ── Launch graphical renderer (takes over the display) ───────────────────────
python3 "$RENDERER_BIN" \
    --events-file "$EVENTS_FILE" \
    --follow \
    --poll-interval 0.05 \
    --fps 6 \
    >> "$LOG_FILE" 2>&1 &
RENDERER_PID=$!

# Wait for renderer to finish (user presses Back → SIGTERM → cleanup → exit)
wait "$RENDERER_PID"
RENDERER_PID=""

# ── Done ─────────────────────────────────────────────────────────────────────
LED R 0 G 0 B 128
LOG "____________________________"
LOG blue "Waterfall stopped"
LOG blue "Session: $SESSION_DIR"
