#!/usr/bin/env bash
# Double-click me to deploy pine-spectools.zip to the Pager.
cd "$(dirname "$0")"
bash scripts/deploy.sh
echo ""
echo "Press any key to close..."
read -n1
