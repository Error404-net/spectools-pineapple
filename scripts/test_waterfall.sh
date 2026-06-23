#!/bin/bash
# test_waterfall.sh — Deploy SpecPine, start waterfall on device, print test URL.
#
# Usage:
#   bash scripts/test_waterfall.sh [--mock] [--no-deploy] [--band 2.4|5]
#
# Options:
#   --mock       Use mock sweep data (no Wi-Spy required); runs mock generator
#                on the device via SSH
#   --no-deploy  Skip package+deploy step (assume already deployed)
#   --band 2.4|5 Frequency band for mock mode (default: 2.4)
#
# Requirements:
#   sshpass      brew install sshpass  (on macOS)
#
# Device: 172.16.52.1  password: qwerty

set -euo pipefail

DEVICE="172.16.52.1"
PASS="qwerty"
PORT=8080
MOCK=0
DEPLOY=1
BAND="2.4"

for arg in "$@"; do
    case "$arg" in
        --mock)       MOCK=1 ;;
        --no-deploy)  DEPLOY=0 ;;
        --band)       shift; BAND="${1:-2.4}" ;;
        --band=*)     BAND="${arg#--band=}" ;;
    esac
done

SSH() { sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=6 \
        root@"$DEVICE" "$@"; }
SCP() { sshpass -p "$PASS" scp -o StrictHostKeyChecking=no "$@"; }

log()  { echo "[test] $*"; }
ok()   { echo "[test] ✓ $*"; }
fail() { echo "[test] ✗ $*" >&2; exit 1; }

# ── connectivity check ────────────────────────────────────────────────────────
log "Checking connectivity to $DEVICE ..."
if ! ping -c 1 -W 3 "$DEVICE" >/dev/null 2>&1; then
    fail "Cannot reach $DEVICE — check Pager USB/network connection"
fi
ok "Device reachable"

if ! command -v sshpass >/dev/null 2>&1; then
    fail "sshpass not installed.  Run: brew install sshpass"
fi

# ── optional package + deploy ─────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ "$DEPLOY" -eq 1 ]; then
    log "Packaging SpecPine ..."
    bash "$REPO_ROOT/scripts/package.sh"
    ok "Package built: pine-spectools.zip"

    log "Deploying to $DEVICE ..."
    SCP "$REPO_ROOT/pine-spectools.zip" root@"$DEVICE":/root/
    SSH 'cd /tmp && unzip -o /root/pine-spectools.zip && \
         rm -rf /root/payloads/user/reconnaissance/specpine && \
         cp -r pine-spectools/specpine /root/payloads/user/reconnaissance/specpine && \
         chmod 755 /root/payloads/user/reconnaissance/specpine/payload.sh \
                   /root/payloads/user/reconnaissance/specpine/bin/spectool_raw \
                   /root/payloads/user/reconnaissance/specpine/bin/spectool_net \
                   /root/payloads/user/reconnaissance/specpine/bin/*.py'
    ok "Deployed to /root/payloads/user/reconnaissance/specpine"
fi

PAYLOAD_DIR="/root/payloads/user/reconnaissance/specpine"
EVENTS_FILE="/tmp/specpine_events.jsonl"

# ── kill any leftover processes ───────────────────────────────────────────────
log "Cleaning up old processes ..."
SSH 'pkill -f spectools_bridge.py 2>/dev/null || true
     pkill -f spectools_waterfall_http.py 2>/dev/null || true
     pkill -f mock_sweep.py 2>/dev/null || true
     pkill -f spectool_raw 2>/dev/null || true
     rm -f '"$EVENTS_FILE"
sleep 1
ok "Cleanup done"

# ── start HTTP server on device ───────────────────────────────────────────────
log "Starting HTTP waterfall server on device (port $PORT) ..."
SSH "nohup python3 $PAYLOAD_DIR/bin/spectools_waterfall_http.py \
     --events-file $EVENTS_FILE \
     --port $PORT \
     >> /tmp/specpine_http.log 2>&1 &"
sleep 1
ok "HTTP server started"

# ── start data source ─────────────────────────────────────────────────────────
if [ "$MOCK" -eq 1 ]; then
    log "Starting MOCK sweep generator (band $BAND) ..."
    # Copy mock_sweep.py to device
    SCP "$REPO_ROOT/scripts/mock_sweep.py" root@"$DEVICE":/tmp/mock_sweep.py
    SSH "nohup python3 /tmp/mock_sweep.py \
         --output $EVENTS_FILE \
         --band $BAND \
         --rate 4 \
         >> /tmp/specpine_mock.log 2>&1 &"
    sleep 1
    ok "Mock sweep generator started (band ${BAND} GHz)"
else
    log "Starting live bridge (Wi-Spy must be plugged in) ..."
    SSH "LD_LIBRARY_PATH=$PAYLOAD_DIR/lib \
         nohup python3 $PAYLOAD_DIR/bin/spectools_bridge.py \
         --input-command $PAYLOAD_DIR/bin/spectool_raw \
         --events-file $EVENTS_FILE \
         --stall-timeout 10 \
         --max-restarts 3 \
         >> /tmp/specpine_bridge.log 2>&1 &"
    sleep 2
    # Check if events are flowing
    if SSH "[ -s $EVENTS_FILE ]"; then
        ok "Bridge running — sweep data flowing"
    else
        echo "[test] ⚠ No sweep data yet. If Wi-Spy is not connected, re-run with --mock"
    fi
fi

# ── verify HTTP server is responding ─────────────────────────────────────────
log "Verifying HTTP server responds ..."
sleep 1
if curl -sf --max-time 5 "http://$DEVICE:$PORT/" -o /dev/null; then
    ok "HTTP waterfall is up at http://$DEVICE:$PORT/"
else
    fail "HTTP server did not respond at http://$DEVICE:$PORT/"
fi

# ── show event counts ─────────────────────────────────────────────────────────
sleep 2
SWEEP_COUNT=$(SSH "grep -c '\"type\":\"sweep\"' $EVENTS_FILE 2>/dev/null || echo 0")
CFG_COUNT=$(  SSH "grep -c '\"type\":\"device_config\"' $EVENTS_FILE 2>/dev/null || echo 0")
log "Events so far: ${CFG_COUNT} device_config, ${SWEEP_COUNT} sweeps"

# ── summary ───────────────────────────────────────────────────────────────────
echo ""
echo "────────────────────────────────────────────────────────"
echo "  SpecPine waterfall is LIVE"
echo "  Open in browser: http://$DEVICE:$PORT/"
echo ""
if [ "$MOCK" -eq 1 ]; then
echo "  Data source : MOCK (${BAND} GHz simulated APs)"
else
echo "  Data source : Wi-Spy DBx (live RF)"
fi
echo ""
echo "  Logs:"
echo "    HTTP server : /tmp/specpine_http.log"
if [ "$MOCK" -eq 1 ]; then
echo "    Mock sweep  : /tmp/specpine_mock.log"
else
echo "    Bridge      : /tmp/specpine_bridge.log"
fi
echo "    Events      : $EVENTS_FILE"
echo ""
echo "  To stop:"
echo "    ssh root@$DEVICE 'pkill -f spectools_waterfall_http.py'"
echo "────────────────────────────────────────────────────────"
