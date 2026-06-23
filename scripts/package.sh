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
# Some sandboxed/synced filesystems (e.g. Cowork's connected-folder mount)
# disallow unlinking existing files even though overwriting them via cp is
# fine. Tolerate a failed rm -rf here -- every file below is recreated by an
# explicit cp/cp+chmod with a fixed, known filename, so stale leftovers are
# always overwritten in place rather than silently lingering.
rm -rf "$STAGE_DIR" 2>/dev/null || true
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

# Python helpers (bridge + renderers + splash + theme installer)
for py in spectools_bridge.py spectools_waterfall_pager.py spectools_waterfall_fb.py spectools_waterfall_http.py specpine_splash.py specpine_theme_install.py specpine_hud.py fb_screenshot.py; do
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

# Theme tree (theme.sh + glyphs/*.txt + palette.md + .fb framebuffer assets)
if [ -d "${SRC_PAY}/data/theme" ]; then
    mkdir -p "${STAGE_DIR}/specpine/data/theme/glyphs" \
             "${STAGE_DIR}/specpine/data/theme/boot_animation"
    [ -f "${SRC_PAY}/data/theme/theme.sh" ] && \
        cp "${SRC_PAY}/data/theme/theme.sh"   "${STAGE_DIR}/specpine/data/theme/theme.sh"
    [ -f "${SRC_PAY}/data/theme/palette.md" ] && \
        cp "${SRC_PAY}/data/theme/palette.md" "${STAGE_DIR}/specpine/data/theme/palette.md"
    [ -f "${SRC_PAY}/data/theme/splash.fb" ] && \
        cp "${SRC_PAY}/data/theme/splash.fb"  "${STAGE_DIR}/specpine/data/theme/splash.fb"
    for f in "${SRC_PAY}/data/theme/glyphs/"*.txt; do
        [ -f "$f" ] || continue
        cp "$f" "${STAGE_DIR}/specpine/data/theme/glyphs/$(basename "$f")"
    done
    for f in "${SRC_PAY}/data/theme/boot_animation/"*.fb; do
        [ -f "$f" ] || continue
        cp "$f" "${STAGE_DIR}/specpine/data/theme/boot_animation/$(basename "$f")"
    done
fi

# ── Instructions ──────────────────────────────────────────────────────────────
cp "${REPO_ROOT}/INSTALL.md" "${STAGE_DIR}/INSTALL.md"

# ── Build zip ─────────────────────────────────────────────────────────────────
# `zip` finalizes its output by writing a temp file and renaming it over the
# target -- that rename fails on some sandboxed/synced filesystems (e.g.
# Cowork's connected-folder mount) even when the target doesn't yet exist.
# Building in /tmp (a plain local filesystem) sidesteps that, then a final
# cp (overwrite-in-place, not rename) lands it at $ZIP_OUT.
echo "Creating zip..."
ZIP_TMP="$(mktemp -d)/pine-spectools.zip"
(
    cd "${REPO_ROOT}/dist"
    zip -r -y "$ZIP_TMP" "pine-spectools/" >/dev/null
)
cp -f "$ZIP_TMP" "$ZIP_OUT"
rm -f "$ZIP_TMP" 2>/dev/null || true

echo ""
echo "Done: $ZIP_OUT"
echo ""
echo "Contents:"
(cd "${REPO_ROOT}/dist" && find pine-spectools -type f -o -type l | sort)
