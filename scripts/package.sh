#!/usr/bin/env bash
# Builds spectools-pineapple-payload.zip from repo contents.
# Run from the repository root: bash scripts/package.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE_DIR="${REPO_ROOT}/dist/spectools-pineapple-payload"
ZIP_OUT="${REPO_ROOT}/spectools-pineapple-payload.zip"

echo "Building payload package..."
echo "Repo:    $REPO_ROOT"
echo "Output:  $ZIP_OUT"
echo ""

# ── Clean staging area ────────────────────────────────────────────────────────
rm -rf "$STAGE_DIR"
mkdir -p \
    "${STAGE_DIR}/payloads/spectools_install/bin" \
    "${STAGE_DIR}/payloads/spectools_install/lib" \
    "${STAGE_DIR}/payloads/spectools_waterfall/bin"

# ── Installer payload ─────────────────────────────────────────────────────────
echo "Staging installer payload..."
cp "${REPO_ROOT}/payloads/spectools_install/payload.sh" \
   "${STAGE_DIR}/payloads/spectools_install/payload.sh"
chmod 755 "${STAGE_DIR}/payloads/spectools_install/payload.sh"

# Binaries (compiled for Pineapple Pager mipsel_24kc)
for bin in spectool_raw spectool_net; do
    SRC="${REPO_ROOT}/spectools-pineapple-build/bin/${bin}"
    if [ ! -f "$SRC" ]; then
        echo "ERROR: Missing binary: $SRC"
        exit 1
    fi
    cp "$SRC" "${STAGE_DIR}/payloads/spectools_install/bin/${bin}"
    chmod 755 "${STAGE_DIR}/payloads/spectools_install/bin/${bin}"
done

# Libraries (dereference symlinks so zip contains real files)
for lib in libusb-0.1.so.4.4.4 libusb-1.0.so.0.4.0; do
    SRC="${REPO_ROOT}/spectools-pineapple-build/lib/${lib}"
    if [ ! -f "$SRC" ]; then
        echo "ERROR: Missing library: $SRC"
        exit 1
    fi
    cp "$SRC" "${STAGE_DIR}/payloads/spectools_install/lib/${lib}"
    chmod 644 "${STAGE_DIR}/payloads/spectools_install/lib/${lib}"
done
# Re-create symlinks in staging (zip -y preserves them)
(
    cd "${STAGE_DIR}/payloads/spectools_install/lib"
    ln -sf libusb-0.1.so.4.4.4 libusb-0.1.so.4
    ln -sf libusb-1.0.so.0.4.0 libusb-1.0.so.0
)

# udev rules (optional — include if present)
UDEV="${REPO_ROOT}/99-wispy.rules"
[ -f "$UDEV" ] && cp "$UDEV" "${STAGE_DIR}/payloads/spectools_install/99-wispy.rules"

# ── Text waterfall payload ────────────────────────────────────────────────────
echo "Staging text waterfall payload..."
cp "${REPO_ROOT}/payloads/spectools_waterfall/payload.sh" \
   "${STAGE_DIR}/payloads/spectools_waterfall/payload.sh"
chmod 755 "${STAGE_DIR}/payloads/spectools_waterfall/payload.sh"

cp "${REPO_ROOT}/payloads/spectools_waterfall/bin/spectools_bridge.py" \
   "${STAGE_DIR}/payloads/spectools_waterfall/bin/spectools_bridge.py"
cp "${REPO_ROOT}/payloads/spectools_waterfall/bin/spectools_waterfall_pager.py" \
   "${STAGE_DIR}/payloads/spectools_waterfall/bin/spectools_waterfall_pager.py"
chmod 755 \
    "${STAGE_DIR}/payloads/spectools_waterfall/bin/spectools_bridge.py" \
    "${STAGE_DIR}/payloads/spectools_waterfall/bin/spectools_waterfall_pager.py"

# ── Graphical waterfall payload ───────────────────────────────────────────────
echo "Staging graphical waterfall payload..."
mkdir -p "${STAGE_DIR}/payloads/spectools_waterfall_graphical/bin"
cp "${REPO_ROOT}/payloads/spectools_waterfall_graphical/payload.sh" \
   "${STAGE_DIR}/payloads/spectools_waterfall_graphical/payload.sh"
chmod 755 "${STAGE_DIR}/payloads/spectools_waterfall_graphical/payload.sh"

cp "${REPO_ROOT}/payloads/spectools_waterfall_graphical/bin/spectools_bridge.py" \
   "${STAGE_DIR}/payloads/spectools_waterfall_graphical/bin/spectools_bridge.py"
cp "${REPO_ROOT}/payloads/spectools_waterfall_graphical/bin/spectools_waterfall_fb.py" \
   "${STAGE_DIR}/payloads/spectools_waterfall_graphical/bin/spectools_waterfall_fb.py"
chmod 755 \
    "${STAGE_DIR}/payloads/spectools_waterfall_graphical/bin/spectools_bridge.py" \
    "${STAGE_DIR}/payloads/spectools_waterfall_graphical/bin/spectools_waterfall_fb.py"

# ── Instructions ──────────────────────────────────────────────────────────────
cp "${REPO_ROOT}/INSTALL.md" "${STAGE_DIR}/INSTALL.md"

# ── Build zip ─────────────────────────────────────────────────────────────────
echo "Creating zip..."
rm -f "$ZIP_OUT"
(
    cd "${REPO_ROOT}/dist"
    zip -r -y "$ZIP_OUT" "spectools-pineapple-payload/"
)

echo ""
echo "Done: $ZIP_OUT"
echo ""
echo "Contents:"
(cd "${REPO_ROOT}/dist" && find spectools-pineapple-payload -type f | sort)
