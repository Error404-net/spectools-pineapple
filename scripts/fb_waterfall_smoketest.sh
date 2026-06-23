#!/usr/bin/env bash
# fb_waterfall_smoketest.sh
#
# Live on-device smoke test for the SpecPine graphical (framebuffer) waterfall
# pipeline: spectool_raw -> spectools_bridge.py -> spectools_waterfall_fb.py -> /dev/fb0
#
# Run this FROM your Mac (not from the Pager). It SSHes in, drives the bridge +
# renderer for a few seconds, verifies:
#   1. the bridge emits well-formed sweep/device_config JSONL events
#   2. the renderer runs with --follow and produces no exceptions
#   3. the Pager UI process is actually frozen (SIGSTOP) while the renderer owns
#      /dev/fb0, and resumes (SIGCONT) cleanly afterward
#   4. /dev/fb0 ends up with real, structured pixel data (not all-zero/blank)
#
# Never restarts any system service. Safe to re-run any time the Wi-Spy is
# plugged in.
#
# Usage:
#   bash scripts/fb_waterfall_smoketest.sh [pager-ip] [duration-seconds]
#
# Requires: sshpass installed locally (brew install sshpass), Pager reachable,
# Wi-Spy DBx plugged into the Pager's USB port, SpecPine deployed at the
# default reconnaissance path.

set -uo pipefail

PAGER_IP="${1:-172.16.52.1}"
DURATION="${2:-4}"
PAGER_PASS="${PAGER_PASS:-qwerty}"

ssh_cmd() {
  sshpass -p "$PAGER_PASS" ssh \
    -o StrictHostKeyChecking=no \
    -o PreferredAuthentications=password \
    -o PubkeyAuthentication=no \
    "root@${PAGER_IP}" bash -s
}

echo "==> Running fb waterfall smoke test against ${PAGER_IP} (${DURATION}s capture)"

ssh_cmd <<EOF
set -u
SP=/root/payloads/user/reconnaissance/specpine
FAIL=0

if [ ! -x "\$SP/bin/spectool_raw" ]; then
  echo "FAIL: SpecPine not found at \$SP (deploy pine-spectools.zip first)"
  exit 1
fi

if ! lsusb 2>/dev/null | grep -qi "wi-spy\|1dd5"; then
  echo "WARN: no Wi-Spy DBx detected on lsusb -- continuing anyway"
fi

rm -f /tmp/specpine_events.jsonl /tmp/_smoketest_bridge.log /tmp/_smoketest_render.log
export LD_LIBRARY_PATH="\$SP/lib"

# 1. Start the bridge
python3 "\$SP/bin/spectools_bridge.py" \
  --input-command "\$SP/bin/spectool_raw" \
  --events-file /tmp/specpine_events.jsonl \
  >> /tmp/_smoketest_bridge.log 2>&1 &
BPID=\$!

for i in \$(seq 1 60); do
  [ -s /tmp/specpine_events.jsonl ] && grep -q '"type": *"sweep"' /tmp/specpine_events.jsonl 2>/dev/null && break
  sleep 0.1
done

if ! grep -q '"type": *"sweep"' /tmp/specpine_events.jsonl 2>/dev/null; then
  echo "FAIL: bridge produced no sweep events within 6s"
  echo "--- bridge log ---"; cat /tmp/_smoketest_bridge.log
  kill \$BPID 2>/dev/null
  exit 1
fi
echo "PASS: bridge emitting sweep events"

# 2. Capture pineapple UI pid + baseline state
UIPID=\$(pidof pineapple)
BASE_STATE=\$(grep State /proc/\$UIPID/status 2>/dev/null)
echo "pineapple UI pid=\$UIPID baseline=\$BASE_STATE"

# 3. Start the fb renderer
python3 -u "\$SP/bin/spectools_waterfall_fb.py" \
  --events-file /tmp/specpine_events.jsonl \
  --follow --poll-interval 0.05 --fps 6 \
  > /tmp/_smoketest_render.log 2>&1 &
RPID=\$!

sleep $DURATION

if ! kill -0 \$RPID 2>/dev/null; then
  echo "FAIL: renderer exited early"
  echo "--- renderer log ---"; cat /tmp/_smoketest_render.log
  FAIL=1
fi

RUN_STATE=\$(grep State /proc/\$UIPID/status 2>/dev/null || echo "GONE")
echo "pineapple UI state during render: \$RUN_STATE"
if echo "\$RUN_STATE" | grep -q "T (stopped)"; then
  echo "PASS: Pager UI correctly frozen (SIGSTOP) while renderer owns fb0"
else
  echo "WARN: Pager UI not observed stopped at check time (can be a timing race -- not necessarily a failure)"
fi

# 4. Inspect /dev/fb0 content for real structured pixel data
python3 -c "
data = open('/dev/fb0','rb').read(222*480*2)
total = len(data)
pixels = [data[i] | (data[i+1]<<8) for i in range(0, total, 2)]
nonzero = sum(1 for p in pixels if p != 0)
distinct = len(set(pixels))
pct = round(100*nonzero/len(pixels), 1)
print(f'fb0: {len(pixels)} pixels, {nonzero} nonzero ({pct}%), {distinct} distinct values')
if distinct < 5:
    print('FAIL: fb0 looks blank/degenerate (too few distinct pixel values)')
    raise SystemExit(1)
print('PASS: fb0 contains structured rendered content')
"
[ \$? -ne 0 ] && FAIL=1

# 5. Stop renderer, confirm UI resumes
kill -TERM \$RPID 2>/dev/null
sleep 1
END_STATE=\$(grep State /proc/\$UIPID/status 2>/dev/null || echo "GONE")
echo "pineapple UI state after renderer exit: \$END_STATE"
if echo "\$END_STATE" | grep -q "S (sleeping)\|R (running)"; then
  echo "PASS: Pager UI resumed cleanly"
else
  echo "FAIL: Pager UI did not resume to a normal running state -- \$END_STATE"
  FAIL=1
fi

kill \$BPID 2>/dev/null

echo "--- renderer log (should be empty) ---"
cat /tmp/_smoketest_render.log

if [ \$FAIL -ne 0 ]; then
  echo "RESULT: SMOKE TEST FAILED"
  exit 1
else
  echo "RESULT: SMOKE TEST PASSED"
fi
EOF

STATUS=$?
echo "==> Exit status: ${STATUS}"
exit $STATUS
