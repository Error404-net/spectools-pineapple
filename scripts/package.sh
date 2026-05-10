#!/usr/bin/env bash
# Builds pine-spectools.zip from repo contents.
# Run from the repository root: bash scripts/package.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE_DIR="${REPO_ROOT}/dist/pine-spectools"
ZIP_OUT="${REPO_ROOT}/pine-spectools.zip"
SRC_PAY="${REPO_ROOT}/payloads/specpine"
SRC_BUILD="${REPO_ROOT}/spectools-pineapple-build"

echo "Building SpecPine payload package..."
echo "Repo:    $REPO_ROOT"
echo "Output:  $ZIP_OUT"
echo ""

# ── Clean staging area ────────────────────────────────────────────────────────
rm -rf "$STAGE_DIR"
mkdir -p \
    "${STAGE_DIR}/specpine/bin" \
    "${STAGE_DIR}/specpine/lib" \
    "${STAGE_DIR}/specpine/include" \
    "${STAGE_DIR}/specpine/data"

# ── SpecPine bundled payload ──────────────────────────────────────────────────
echo "Staging SpecPine payload..."
cp "${SRC_PAY}/payload.sh" "${STAGE_DIR}/specpine/payload.sh"
chmod 755 "${STAGE_DIR}/specpine/payload.sh"

for f in funcs_main.sh funcs_menu.sh funcs_scan.sh; do
    cp "${SRC_PAY}/include/${f}" "${STAGE_DIR}/specpine/include/${f}"
    chmod 644 "${STAGE_DIR}/specpine/include/${f}"
done

if [ -f "${SRC_PAY}/README.md" ]; then
    cp "${SRC_PAY}/README.md" "${STAGE_DIR}/specpine/README.md"
fi

# Python helpers (bridge + renderers + splash)
for py in spectools_bridge.py spectools_waterfall_pager.py spectools_waterfall_fb.py specpine_splash.py; do
    SRC="${SRC_PAY}/bin/${py}"
    if [ ! -f "$SRC" ]; then
        echo "ERROR: Missing python helper: $SRC"
        exit 1
    fi
    cp "$SRC" "${STAGE_DIR}/specpine/bin/${py}"
    chmod 755 "${STAGE_DIR}/specpine/bin/${py}"
done

# MIPS binaries (compiled for ramips/mt76x8 / mipsel_24kc)
for bin in spectool_raw spectool_net; do
    SRC="${SRC_BUILD}/bin/${bin}"
    if [ ! -f "$SRC" ]; then
        echo "ERROR: Missing binary: $SRC"
        echo "       Cross-compile with the OpenWrt SDK first."
        exit 1
    fi
    cp "$SRC" "${STAGE_DIR}/specpine/bin/${bin}"
    chmod 755 "${STAGE_DIR}/specpine/bin/${bin}"
done

# Libraries (real files + symlinks)
for lib in libusb-0.1.so.4.4.4 libusb-1.0.so.0.4.0; do
    SRC="${SRC_BUILD}/lib/${lib}"
    if [ ! -f "$SRC" ]; then
        echo "ERROR: Missing library: $SRC"
        exit 1
    fi
    cp "$SRC" "${STAGE_DIR}/specpine/lib/${lib}"
    chmod 644 "${STAGE_DIR}/specpine/lib/${lib}"
done
(
    cd "${STAGE_DIR}/specpine/lib"
    ln -sf libusb-0.1.so.4.4.4 libusb-0.1.so.4
    ln -sf libusb-1.0.so.0.4.0 libusb-1.0.so.0
)

# Data files (udev rules, ASCII logo)
if [ -f "${SRC_PAY}/data/99-wispy.rules" ]; then
    cp "${SRC_PAY}/data/99-wispy.rules" "${STAGE_DIR}/specpine/data/99-wispy.rules"
elif [ -f "${REPO_ROOT}/99-wispy.rules" ]; then
    cp "${REPO_ROOT}/99-wispy.rules" "${STAGE_DIR}/specpine/data/99-wispy.rules"
fi
if [ -f "${SRC_PAY}/data/specpine_logo.txt" ]; then
    cp "${SRC_PAY}/data/specpine_logo.txt" "${STAGE_DIR}/specpine/data/specpine_logo.txt"
fi

# ANSI/ASCII LOG art for each scan mode
if [ -d "${SRC_PAY}/data/ansi" ]; then
    mkdir -p "${STAGE_DIR}/specpine/data/ansi"
    for f in "${SRC_PAY}/data/ansi/"*.txt; do
        [ -f "$f" ] || continue
        cp "$f" "${STAGE_DIR}/specpine/data/ansi/$(basename "$f")"
    done
fi

# ── Instructions ──────────────────────────────────────────────────────────────
cp "${REPO_ROOT}/INSTALL.md" "${STAGE_DIR}/INSTALL.md"

# ── Build zip ─────────────────────────────────────────────────────────────────
echo "Creating zip..."
rm -f "$ZIP_OUT"
(
    cd "${REPO_ROOT}/dist"
    zip -r -y "$ZIP_OUT" "pine-spectools/" >/dev/null
)

echo ""
echo "Done: $ZIP_OUT"
echo ""
echo "Contents:"
(cd "${REPO_ROOT}/dist" && find pine-spectools -type f -o -type l | sort)
