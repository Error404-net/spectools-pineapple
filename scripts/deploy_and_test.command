#!/bin/bash
# SpecPine deploy + test launcher
# Double-click this file in Finder OR run: bash scripts/deploy_and_test.command
# It packages, deploys, starts mock data + HTTP server, then opens the browser.

set -euo pipefail
DEVICE="172.16.52.1"
PASS="qwerty"
PORT=8080
REPO="$(cd "$(dirname "$0")/.." && pwd)"

log()  { echo "▶ $*"; }
ok()   { echo "✓ $*"; }
fail() { echo "✗ $*" >&2; read -p "Press enter to close..."; exit 1; }

log "SpecPine deploy + test starting..."
echo ""

# sshpass availability
SSH_CMD=""
if command -v sshpass >/dev/null 2>&1; then
    SSH_CMD="sshpass -p $PASS ssh -o StrictHostKeyChecking=no -o ConnectTimeout=8 root@$DEVICE"
    SCP_CMD="sshpass -p $PASS scp -o StrictHostKeyChecking=no"
else
    # Fallback: use SSH with BatchMode — will work if key auth is set up
    SSH_CMD="ssh -o StrictHostKeyChecking=no -o ConnectTimeout=8 -o BatchMode=yes root@$DEVICE"
    SCP_CMD="scp -o StrictHostKeyChecking=no -o BatchMode=yes"
    log "sshpass not found; trying key-based auth..."
fi

# Connectivity
log "Checking $DEVICE ..."
if ! ping -c 1 -W 3 "$DEVICE" >/dev/null 2>&1; then
    fail "Cannot reach $DEVICE — check Pager USB/network"
fi
ok "Device reachable"

# Package
log "Packaging SpecPine ..."
cd "$REPO"
bash scripts/package.sh
ok "Package built: pine-spectools.zip"

# Deploy
log "Deploying to $DEVICE ..."
$SCP_CMD "$REPO/pine-spectools.zip" root@"$DEVICE":/root/
$SSH_CMD 'cd /tmp && unzip -o /root/pine-spectools.zip \
  && rm -rf /root/payloads/user/reconnaissance/specpine \
  && cp -r pine-spectools/specpine /root/payloads/user/reconnaissance/specpine \
  && chmod 755 /root/payloads/user/reconnaissance/specpine/payload.sh \
               /root/payloads/user/reconnaissance/specpine/bin/spectool_raw \
               /root/payloads/user/reconnaissance/specpine/bin/spectool_net \
               /root/payloads/user/reconnaissance/specpine/bin/*.py'
ok "Deployed to device"

# Kill old processes
log "Cleaning up old processes..."
$SSH_CMD 'pkill -f spectools_waterfall_http.py 2>/dev/null || true
          pkill -f spectools_bridge.py 2>/dev/null || true
          pkill -f mock_sweep.py 2>/dev/null || true
          rm -f /tmp/specpine_events.jsonl' 2>/dev/null || true
sleep 1

PAYLOAD_DIR="/root/payloads/user/reconnaissance/specpine"
EVENTS_FILE="/tmp/specpine_events.jsonl"

# Copy mock sweep script to device
log "Installing mock sweep generator..."
$SCP_CMD "$REPO/scripts/mock_sweep.py" root@"$DEVICE":/tmp/mock_sweep.py

# Start HTTP server
log "Starting HTTP waterfall server on :$PORT ..."
$SSH_CMD "nohup python3 $PAYLOAD_DIR/bin/spectools_waterfall_http.py \
  --events-file $EVENTS_FILE --port $PORT >> /tmp/specpine_http.log 2>&1 &"
sleep 1

# Start mock sweep (simulates Wi-Spy DBx 2.4 GHz)
log "Starting mock sweep generator (2.4 GHz) ..."
$SSH_CMD "nohup python3 /tmp/mock_sweep.py \
  --output $EVENTS_FILE --band 2.4 --rate 4 >> /tmp/specpine_mock.log 2>&1 &"
sleep 2

# Verify HTTP
log "Verifying waterfall HTTP server..."
if curl -sf --max-time 5 "http://$DEVICE:$PORT/" -o /dev/null; then
    ok "Waterfall is live at http://$DEVICE:$PORT/"
else
    fail "HTTP server not responding at http://$DEVICE:$PORT/"
fi

# Sweep count check
NSWEEPS=$($SSH_CMD "wc -l < $EVENTS_FILE 2>/dev/null || echo 0")
ok "Events flowing: ~$NSWEEPS lines in events file"

# Open browser
log "Opening browser..."
open "http://$DEVICE:$PORT/"

echo ""
echo "═══════════════════════════════════════════════════"
echo "  SpecPine waterfall is LIVE"
echo "  URL: http://$DEVICE:$PORT/"
echo ""
echo "  To stop all processes on device:"
echo "  ssh root@$DEVICE 'pkill -f spectools_waterfall_http.py; pkill -f mock_sweep.py'"
echo "═══════════════════════════════════════════════════"
read -p "Press enter to close this window..."
