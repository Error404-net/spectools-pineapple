#!/bin/bash
# Title: SpecPine Installer
# Author: Error404-net
# Description: Installs SpecPine RF spectrum analyzer and required dependencies (python3, evtest) from pine-spectools.zip.
# Category: utils
# Version: 1.0

ZIP_PATH="/root/pine-spectools.zip"
DEST="/root/payloads/user/reconnaissance/specpine"
TMP="/tmp/specpine_install"

LOG blue "── SpecPine Installer ──"
LOG ""

# ── Verify ZIP is present ─────────────────────────────────────────────────
if [ ! -f "$ZIP_PATH" ]; then
    ERROR_DIALOG "pine-spectools.zip not found at /root/

Copy it to the Pager first:
  scp pine-spectools.zip root@<ip>:/root/"
    exit 1
fi
LOG green "Package: ${ZIP_PATH} found"
LOG ""

# ── opkg dependencies ─────────────────────────────────────────────────────
need=""
command -v python3 >/dev/null 2>&1 || need="python3"
command -v evtest  >/dev/null 2>&1 || need="${need:+${need} }evtest"

if [ -n "$need" ]; then
    LOG yellow "Missing: ${need}"
    resp=$(CONFIRMATION_DIALOG "Install missing packages via opkg?
Requires internet on the Pager.")
    if [ "$resp" != "$DUCKYSCRIPT_USER_CONFIRMED" ]; then
        LOG yellow "Cancelled"
        WAIT_FOR_BUTTON_PRESS A
        exit 0
    fi
    LOG "Running opkg update..."
    if ! opkg update; then
        ERROR_DIALOG "opkg update failed.
Check the Pager has internet access."
        exit 1
    fi
    command -v python3 >/dev/null 2>&1 || opkg install python3
    command -v evtest  >/dev/null 2>&1 || opkg install evtest
    LOG green "Dependencies installed"
else
    LOG green "Dependencies: already present"
fi
LOG ""

# ── Extract and install ───────────────────────────────────────────────────
LOG "Extracting package..."
rm -rf "$TMP"
mkdir -p "$TMP"
if ! unzip -o "$ZIP_PATH" -d "$TMP"; then
    ERROR_DIALOG "Extraction failed — is the ZIP valid?"
    rm -rf "$TMP"
    exit 1
fi

if [ ! -d "${TMP}/pine-spectools/specpine" ]; then
    ERROR_DIALOG "Unexpected ZIP layout — pine-spectools/specpine/ not found."
    rm -rf "$TMP"
    exit 1
fi

LOG "Installing to ${DEST} ..."
rm -rf "$DEST"
mkdir -p "$(dirname "$DEST")"
cp -r "${TMP}/pine-spectools/specpine" "$DEST"
rm -rf "$TMP"

chmod 755 "${DEST}/payload.sh"
find "${DEST}/bin" -name "*.py" -exec chmod 755 {} \;
chmod 755 "${DEST}/bin/spectool_raw"
chmod 755 "${DEST}/bin/spectool_net"

LOG ""
LOG green "SpecPine installed successfully."
LOG cyan  "Find it under:"
LOG cyan  "Payloads → reconnaissance → SpecPine"
LOG ""
WAIT_FOR_BUTTON_PRESS A
exit 0
