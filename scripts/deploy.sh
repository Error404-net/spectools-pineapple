#!/usr/bin/env bash
# Deploy pine-spectools.zip to the Pager.
# Run from the repo root: bash scripts/deploy.sh
set -euo pipefail
PAGER=172.16.52.1
PASS=qwerty
REPO="$(cd "$(dirname "$0")/.." && pwd)"

echo "Serving ${REPO}/pine-spectools.zip on :9876 …"
(cd "$REPO" && python3 -m http.server 9876 --bind 0.0.0.0 &>/tmp/specpine-http.log) &
HTTP_PID=$!
sleep 1

MAC_IP=$(ipconfig getifaddr en0 2>/dev/null || \
         ipconfig getifaddr en1 2>/dev/null || \
         route get "$PAGER" 2>/dev/null | awk '/interface:/{print $2}' | head -1)
echo "Mac IP on Pager network: $MAC_IP"

sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no root@"$PAGER" "
  echo '--- Downloading ---'
  wget -q -O /root/pine-spectools.zip http://${MAC_IP}:9876/pine-spectools.zip && echo 'download: OK'
  echo '--- Installing ---'
  cd /tmp && unzip -o /root/pine-spectools.zip
  rm -rf /root/payloads/user/reconnaissance/specpine
  cp -r pine-spectools-stage/specpine /root/payloads/user/reconnaissance/specpine
  chmod 755 /root/payloads/user/reconnaissance/specpine/payload.sh \
             /root/payloads/user/reconnaissance/specpine/bin/*.py \
             /root/payloads/user/reconnaissance/specpine/bin/spectool_raw \
             /root/payloads/user/reconnaissance/specpine/bin/spectool_net
  echo '--- Theme installer ---'
  ls /root/payloads/user/reconnaissance/specpine/bin/specpine_theme_install.py
  python3 -m py_compile /root/payloads/user/reconnaissance/specpine/bin/specpine_theme_install.py && echo 'compile: OK'
  python3 /root/payloads/user/reconnaissance/specpine/bin/specpine_theme_install.py --status
  echo 'INSTALL_DONE'
"

kill $HTTP_PID 2>/dev/null || true
echo "Deploy complete."
