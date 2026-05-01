#!/bin/bash
# Title: SpecTools Install
# Description: Install Wi-Spy/Spectools binaries from payload to /opt/spectools
# Author: Error404-net
# Category: reconnaissance
# Version: 1.0

PAYLOAD_ROOT="$(cd "$(dirname "$0")" && pwd)"
SRC_BIN="${PAYLOAD_ROOT}/bin"
SRC_LIB="${PAYLOAD_ROOT}/lib"

INSTALL_BIN="/opt/spectools/bin"
INSTALL_LIB="/opt/spectools/lib"
INSTALL_CONF="/etc/spectools"
UDEV_RULES_SRC="${PAYLOAD_ROOT}/99-wispy.rules"
UDEV_RULES_DST="/etc/udev/rules.d/99-wispy.rules"

LOG blue "SpecTools Installer v1.0"
LOG "Target: /opt/spectools"
LOG "____________________________"

# ── Verify source binaries exist ─────────────────────────────────────────────
LOG "Checking payload contents..."
missing=0
for bin in spectool_raw spectool_net; do
    if [ ! -f "${SRC_BIN}/${bin}" ]; then
        LOG red "Missing: bin/${bin}"
        missing=$((missing + 1))
    fi
done

for lib in libusb-0.1.so.4.4.4 libusb-1.0.so.0.4.0; do
    if [ ! -f "${SRC_LIB}/${lib}" ]; then
        LOG red "Missing: lib/${lib}"
        missing=$((missing + 1))
    fi
done

if [ "$missing" -gt 0 ]; then
    LED R 255 G 0 B 0
    LOG red "$missing required files missing"
    LOG red "Re-upload the full payload folder"
    ALERT "Installation failed: $missing required files are missing from the payload. Please re-upload."
    exit 1
fi

LOG green "Payload contents verified"

# ── Disk space check (need ~2 MB) ─────────────────────────────────────────────
LOG "Checking disk space..."
AVAIL_BLOCKS="$(df /opt 2>/dev/null | awk 'NR==2 {print $4}')"
if [ -n "$AVAIL_BLOCKS" ] && [ "$AVAIL_BLOCKS" -lt 2048 ]; then
    LED R 255 G 0 B 0
    LOG red "Insufficient space in /opt"
    LOG red "Need at least 2 MB free"
    ALERT "Not enough space in /opt. Free up space and try again."
    exit 1
fi

LED R 255 G 165 B 0

# ── Create directories ────────────────────────────────────────────────────────
LOG "Creating directories..."
mkdir -p "$INSTALL_BIN" "$INSTALL_LIB" "$INSTALL_CONF" || {
    LED R 255 G 0 B 0
    LOG red "Cannot create /opt/spectools"
    ALERT "Failed to create install directories. Check filesystem permissions."
    exit 1
}

# ── Copy binaries ─────────────────────────────────────────────────────────────
LOG "Installing binaries..."
for bin in spectool_raw spectool_net; do
    cp "${SRC_BIN}/${bin}" "${INSTALL_BIN}/${bin}" || {
        LED R 255 G 0 B 0
        LOG red "Failed to copy ${bin}"
        exit 1
    }
    chmod 755 "${INSTALL_BIN}/${bin}"
done
LOG green "Binaries installed"

# ── Copy libraries ────────────────────────────────────────────────────────────
LOG "Installing libraries..."
for lib in "${SRC_LIB}"/*.so*; do
    [ -f "$lib" ] || continue
    libname="$(basename "$lib")"
    cp "$lib" "${INSTALL_LIB}/${libname}" || {
        LED R 255 G 0 B 0
        LOG red "Failed to copy ${libname}"
        exit 1
    }
    chmod 644 "${INSTALL_LIB}/${libname}"
done

# Create versioned symlinks (needed by dynamic linker)
[ ! -e "${INSTALL_LIB}/libusb-0.1.so.4" ] && \
    ln -sf libusb-0.1.so.4.4.4 "${INSTALL_LIB}/libusb-0.1.so.4" 2>/dev/null || true
[ ! -e "${INSTALL_LIB}/libusb-1.0.so.0" ] && \
    ln -sf libusb-1.0.so.0.4.0 "${INSTALL_LIB}/libusb-1.0.so.0" 2>/dev/null || true

LOG green "Libraries installed"

# ── Write config ──────────────────────────────────────────────────────────────
LOG "Writing config..."
cat > "${INSTALL_CONF}/spectools.conf" << 'EOF'
# SpecTools configuration — sourced by waterfall payload
SPECTOOL_BIN=/opt/spectools/bin/spectool_raw
SPECTOOL_LIB=/opt/spectools/lib
LD_LIBRARY_PATH=/opt/spectools/lib
EOF

# ── Install udev rules if available ───────────────────────────────────────────
if [ -f "$UDEV_RULES_SRC" ]; then
    LOG "Installing udev rules..."
    cp "$UDEV_RULES_SRC" "$UDEV_RULES_DST" 2>/dev/null || \
        LOG yellow "udev rules copy failed (non-fatal)"
    if command -v udevadm >/dev/null 2>&1; then
        udevadm control --reload-rules 2>/dev/null || true
    fi
    LOG green "udev rules installed"
fi

# ── Verify installation ───────────────────────────────────────────────────────
LOG "Verifying installation..."
export LD_LIBRARY_PATH="${INSTALL_LIB}:${LD_LIBRARY_PATH:-}"

if "${INSTALL_BIN}/spectool_raw" --help >/dev/null 2>&1 || \
   "${INSTALL_BIN}/spectool_raw" --list >/dev/null 2>&1; then
    LED R 0 G 255 B 0
    LOG green "____________________________"
    LOG green "Installation complete!"
    LOG green "Binaries: $INSTALL_BIN"
    LOG green "Libraries: $INSTALL_LIB"
    LOG green "____________________________"
    LOG "Plug in Wi-Spy DBx and run"
    LOG "the spectools_waterfall payload"
else
    LED R 255 G 255 B 0
    LOG yellow "Binary test inconclusive"
    LOG yellow "(OK if no Wi-Spy is plugged in)"
    LOG "Files installed to $INSTALL_BIN"
    LOG "Connect Wi-Spy and run waterfall"
fi
