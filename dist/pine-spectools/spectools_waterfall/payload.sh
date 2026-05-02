#!/bin/bash
# Title: SpecTools Waterfall
# Description: Live RF spectrum waterfall from Wi-Spy DBx
# Author: Error404-net
# Category: reconnaissance
# Version: 1.0

PAYLOAD_ROOT="$(cd "$(dirname "$0")" && pwd)"
SPECTOOL_BIN="/opt/spectools/bin/spectool_raw"
SPECTOOL_LIB="/opt/spectools/lib"
BRIDGE_BIN="${PAYLOAD_ROOT}/bin/spectools_bridge.py"
RENDERER_BIN="${PAYLOAD_ROOT}/bin/spectools_waterfall_pager.py"

EVENTS_FILE="/tmp/spectools_events.jsonl"
LOOT_ROOT="/root/loot/spectools_waterfall"
SESSION_TS="$(date +%Y%m%d_%H%M%S)"
SESSION_DIR="${LOOT_ROOT}/session_${SESSION_TS}"
LOG_FILE="/tmp/spectools_waterfall.log"
LOCK_FILE="/tmp/spectools_waterfall.lock"
PID_FILE="/tmp/spectools_waterfall.pid"

BRIDGE_PID=""

cleanup() {
    LED R 0 G 0 B 0 2>/dev/null || LED OFF 2>/dev/null || true
    [ -n "$BRIDGE_PID" ] && kill "$BRIDGE_PID" 2>/dev/null || true
    pkill -f "spectools_bridge.py" 2>/dev/null || true
    pkill -f "spectools_waterfall_pager.py" 2>/dev/null || true
    rm -f "$LOCK_FILE" "$PID_FILE" "$EVENTS_FILE"
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
LOG blue "SpecTools Waterfall v1.0"
LOG "Checking dependencies..."

if [ ! -x "$SPECTOOL_BIN" ]; then
    LED R 255 G 0 B 0
    LOG red "spectool_raw not found"
    LOG red "Run spectools_install first"
    ALERT "Run the spectools_install payload to install binaries before using the waterfall."
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    LED R 255 G 0 B 0
    LOG red "python3 not found"
    LOG red "Install python3: opkg install python3"
    exit 1
fi

if [ ! -f "$BRIDGE_BIN" ]; then
    LOG red "Missing: bin/spectools_bridge.py"
    exit 1
fi

if [ ! -f "$RENDERER_BIN" ]; then
    LOG red "Missing: bin/spectools_waterfall_pager.py"
    exit 1
fi

mkdir -p "$SESSION_DIR"
: > "$LOG_FILE"

LOG green "Dependencies OK"
LOG "Connecting to Wi-Spy DBx..."
LOG "Plug USB now if not already."

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

# Wait up to 6 seconds for bridge to start producing data
waited=0
while [ ! -s "$EVENTS_FILE" ] && [ "$waited" -lt 6 ]; do
    sleep 1
    waited=$((waited + 1))
    if ! kill -0 "$BRIDGE_PID" 2>/dev/null; then
        LOG red "Bridge exited unexpectedly"
        LOG red "Check USB: spectool_raw needs Wi-Spy"
        LED R 255 G 0 B 0
        ALERT "Could not start bridge. Is the Wi-Spy DBx plugged in?"
        exit 1
    fi
done

if [ ! -s "$EVENTS_FILE" ]; then
    LOG yellow "No data yet - continuing anyway"
fi

LED R 0 G 255 B 0
LOG green "Scanning - Press Back to exit"
LOG "____________________________"

# ── Run renderer and stream to LOG ───────────────────────────────────────────
python3 "$RENDERER_BIN" \
    --events-file "$EVENTS_FILE" \
    --follow \
    --poll-interval 0.05 \
    2>/dev/null | \
while IFS= read -r waterfall_line; do
    LOG green "$waterfall_line"
done

# ── Done ─────────────────────────────────────────────────────────────────────
LOG "____________________________"
LOG blue "Session saved to:"
LOG "$SESSION_DIR"
