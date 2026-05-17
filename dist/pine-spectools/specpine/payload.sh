#!/bin/bash
# Title: SpecPine
# Author: Error404-net
# Description: SpecPine - RF spectrum analysis suite for Wi-Spy DBx. Status, Quick Scan, ASCII Waterfall, Graphical Waterfall, Channel Analysis, Anomaly Detection, Saved Sessions, Install, Settings.
# Category: reconnaissance
# Version: 1.2
#
# ──────────────────────────────────────────────────────────────────────────
# UI conventions, structure, ringtone names, and button-watcher pattern are
# adapted from BluePine (cncartist) — credit & thanks. Spectrum data flow:
#   Wi-Spy DBx → spectool_raw → spectools_bridge.py (JSONL) → renderers.
# Press OK (tap) to pause, OK (long-press ≥0.8s) to stop and return to menu.
# Press Back (Pager) to bail out at any prompt.
# ──────────────────────────────────────────────────────────────────────────

PAYLOAD_ROOT="$(cd "$(dirname "$0")" && pwd)"

# Source modular helpers (BluePine pattern: payload.sh:172-175)
source "${PAYLOAD_ROOT}/include/funcs_main.sh"
source "${PAYLOAD_ROOT}/include/funcs_menu.sh"
source "${PAYLOAD_ROOT}/include/funcs_scan.sh"

# ── Paths and constants ───────────────────────────────────────────────────
# SpecPine is a self-contained middleware: it ships its own spectool_raw and
# libusb in bin/ and lib/ next to payload.sh. The "Install" menu is OPTIONAL
# and only useful for making spectool_raw available system-wide for other
# tools. By default we resolve binaries inside the payload directory first
# and fall back to /opt/spectools if a system install exists.
PAYLOAD_BIN="${PAYLOAD_ROOT}/bin"
PAYLOAD_LIB="${PAYLOAD_ROOT}/lib"
INSTALL_BIN="/opt/spectools/bin"
INSTALL_LIB="/opt/spectools/lib"
INSTALL_CONF="/etc/spectools"

# Resolve SPECTOOL_BIN / SPECTOOL_LIB: prefer self-contained, fall back to /opt
if [ -x "${PAYLOAD_BIN}/spectool_raw" ]; then
    SPECTOOL_BIN="${PAYLOAD_BIN}/spectool_raw"
    SPECTOOL_LIB="${PAYLOAD_LIB}"
    SPECTOOL_SOURCE="payload"
else
    SPECTOOL_BIN="${INSTALL_BIN}/spectool_raw"
    SPECTOOL_LIB="${INSTALL_LIB}"
    SPECTOOL_SOURCE="opt"
fi

BRIDGE_BIN="${PAYLOAD_ROOT}/bin/spectools_bridge.py"
RENDERER_ASCII_BIN="${PAYLOAD_ROOT}/bin/spectools_waterfall_pager.py"
RENDERER_FB_BIN="${PAYLOAD_ROOT}/bin/spectools_waterfall_fb.py"
LOGO_FILE="${PAYLOAD_ROOT}/data/specpine_logo.txt"
UDEV_RULES_SRC="${PAYLOAD_ROOT}/data/99-wispy.rules"
UDEV_RULES_DST="/etc/udev/rules.d/99-wispy.rules"

LOOT_ROOT="/root/loot/specpine"
TMP_LOOT_ROOT="/tmp/specpine"
EVENTS_FILE="/tmp/specpine_events.jsonl"
BTN_EVT_FILE="/tmp/specpine_btn_evt"
KEYCKTMP_FILE="/tmp/specpine_keyck.tmp"
LOG_FILE="/tmp/specpine.log"
LOCK_FILE="/tmp/specpine.lock"
PID_FILE="/tmp/specpine.pid"
VTCON="/sys/class/vtconsole/vtcon1/bind"

APP_VERSION="1.2"
CONFIG_NS="specpine"

# ── Defaults (overridden by PAYLOAD_GET_CONFIG below) ─────────────────────
default_band="auto"
default_mode="text"
stall_timeout=8
max_restarts=5
anomaly_threshold_db=15
anomaly_window=10
mute="false"
noloot="false"
gps_enabled="false"
skip_ask_ringtones=0
selnum_main=1
total_scans=0
total_anomalies=0

# Runtime state
BRIDGE_PID=""
RENDERER_PID=""
EVTEST_PID=""
selnum=0
show_menu_end_OK=1
current_band=""
current_session_name=""
current_save_loot="false"
SESSION_DIR=""
WISPY_PRESENT="false"
WISPY_DEVICE_NAME=""
WISPY_DEVICE_ID=""
FREQ_START_KHZ=""
FREQ_END_KHZ=""
BIN_COUNT=""
RES_HZ=""
gpspos_last="NoGPS"
silent_backup=0

# ── Restore persistent settings (BluePine pattern: payload.sh:325-357) ────
v=$(PAYLOAD_GET_CONFIG "$CONFIG_NS" default_band);          [ -n "$v" ] && default_band="$v"
v=$(PAYLOAD_GET_CONFIG "$CONFIG_NS" default_mode);          [ -n "$v" ] && default_mode="$v"
v=$(PAYLOAD_GET_CONFIG "$CONFIG_NS" stall_timeout);         [ -n "$v" ] && stall_timeout="$v"
v=$(PAYLOAD_GET_CONFIG "$CONFIG_NS" max_restarts);          [ -n "$v" ] && max_restarts="$v"
v=$(PAYLOAD_GET_CONFIG "$CONFIG_NS" anomaly_threshold_db);  [ -n "$v" ] && anomaly_threshold_db="$v"
v=$(PAYLOAD_GET_CONFIG "$CONFIG_NS" anomaly_window);        [ -n "$v" ] && anomaly_window="$v"
v=$(PAYLOAD_GET_CONFIG "$CONFIG_NS" mute);                  [ -n "$v" ] && mute="$v"
v=$(PAYLOAD_GET_CONFIG "$CONFIG_NS" noloot);                [ -n "$v" ] && noloot="$v"
v=$(PAYLOAD_GET_CONFIG "$CONFIG_NS" gps_enabled);           [ -n "$v" ] && gps_enabled="$v"
v=$(PAYLOAD_GET_CONFIG "$CONFIG_NS" skip_ask_ringtones);    [ -n "$v" ] && skip_ask_ringtones="$v"
v=$(PAYLOAD_GET_CONFIG "$CONFIG_NS" selnum_main);           [ -n "$v" ] && selnum_main="$v"
v=$(PAYLOAD_GET_CONFIG "$CONFIG_NS" total_scans);           [ -n "$v" ] && total_scans="$v"
v=$(PAYLOAD_GET_CONFIG "$CONFIG_NS" total_anomalies);       [ -n "$v" ] && total_anomalies="$v"
unset v

# ── Cleanup trap (BluePine pattern: payload.sh:282-299) ───────────────────
cleanup() {
    [ -n "$RENDERER_PID" ] && kill "$RENDERER_PID" 2>/dev/null || true
    [ -n "$BRIDGE_PID" ]   && kill "$BRIDGE_PID"   2>/dev/null || true
    [ -n "$EVTEST_PID" ]   && kill "$EVTEST_PID"   2>/dev/null || true
    pkill -f "spectools_bridge.py"          2>/dev/null || true
    pkill -f "spectools_waterfall_pager.py" 2>/dev/null || true
    pkill -f "spectools_waterfall_fb.py"    2>/dev/null || true
    killall evtest 2>/dev/null || true
    sleep 0.3
    [ -e "$VTCON" ] && echo 1 > "$VTCON" 2>/dev/null || true
    LED R 0 G 0 B 0 2>/dev/null || true
    rm -f "$LOCK_FILE" "$PID_FILE" "$EVENTS_FILE" "$BTN_EVT_FILE" "$KEYCKTMP_FILE"
    if [ "$noloot" = "true" ]; then noloot_wipe; fi
    silent_backup=1
    config_backup
    exit 0
}
trap cleanup EXIT SIGINT SIGTERM SIGHUP

# ── Singleton guard (name-based; PID-based check false-triggered on PID reuse)
SPECPINE_PEERS=$(pgrep -f "specpine/payload.sh" 2>/dev/null | grep -vx "$$" | grep -vx "$PPID" | wc -l)
if [ "${SPECPINE_PEERS:-0}" -gt 0 ]; then
    LOG red "SpecPine already running (${SPECPINE_PEERS} peer(s))"
    ALERT "SpecPine is already running. Wait for it to exit."
    exit 1
fi
rm -f "$LOCK_FILE" "$PID_FILE"
touch "$LOCK_FILE"
echo $$ > "$PID_FILE"
: > "$LOG_FILE"
: > "$BTN_EVT_FILE"

mkdir -p "$LOOT_ROOT" "$TMP_LOOT_ROOT" 2>/dev/null || true

# ── Dependencies + ringtone install ───────────────────────────────────────
check_dependencies
[ "$skip_ask_ringtones" -eq 0 ] && check_ringtones
config_check
settings_check

# ── Boot splash + landing screen (BluePine pattern: payload.sh:400-414) ───
specpine_logo
[ "$mute" = "false" ] && RINGTONE "Flutter"

# Optional framebuffer splash plays first (skips silently if /dev/fb0 missing).
if [ -e /dev/fb0 ] && [ -x "${PAYLOAD_ROOT}/bin/specpine_splash.py" ]; then
    python3 "${PAYLOAD_ROOT}/bin/specpine_splash.py" 2>/dev/null || true
fi

# Show the landing glyph (theme/glyphs/landing.txt) so the user sees the
# tap-vs-hold instructions visibly framed.
show_ansi landing 2>/dev/null || \
    LOG green "── Tap OK: Waterfall   Hold OK: Menu ──"
LOG cyan  "(idle 30s also goes to Menu)"

device_probe   # populates WISPY_PRESENT, WISPY_DEVICE_NAME, WISPY_DEVICE_ID

# Tap-vs-hold gate. Re-uses the existing button watcher (start_evtest /
# check_cancel) so a tap sets is_btn_paused="pause" and a hold ≥0.8s
# sets is_btn_stopped="stop".
start_evtest
sleep 0.3   # drain A-release event from firmware launch screen before watching
clear_btn_evt
LANDING_CHOICE=""
LANDING_DEADLINE=$(( $(date +%s) + 30 ))
while [ -z "$LANDING_CHOICE" ] && [ "$(date +%s)" -lt "$LANDING_DEADLINE" ]; do
    check_cancel
    if is_btn_stopped; then LANDING_CHOICE="menu";      fi
    if is_btn_paused;  then LANDING_CHOICE="waterfall"; fi
    sleep 0.15
done
killall evtest 2>/dev/null || true
EVTEST_PID=""
clear_btn_evt

if [ "$LANDING_CHOICE" != "menu" ]; then
    LOG green "── Starting waterfall (defaults) ──"
    current_band="$default_band"
    current_session_name="$(date +%Y%m%d_%H%M%S)"
    current_save_loot="true"
    [ "$noloot" = "true" ] && current_save_loot="false"
    text_waterfall
fi

# ── Main menu loop (BluePine pattern: payload.sh:420-965) ─────────────────
while true; do
    show_menu_end_OK=1
    main_menu
    main_option="$selnum"

    case "$main_option" in
        1)  status_display ;;
        2)  if pre_scan_dialog; then quick_scan;        fi ;;
        3)  if pre_scan_dialog; then text_waterfall;    fi ;;
        4)  if pre_scan_dialog; then channel_analysis;  fi ;;
        5)  if pre_scan_dialog; then anomaly_detection; fi ;;
        6)  sub_menu_sessions ;;
        7)  sub_menu_install ;;
        8)  sub_menu_settings ;;
        9)  sub_menu_about ;;
        0)
            resp=$(CONFIRMATION_DIALOG "Exit SpecPine?")
            if [ "$resp" = "$DUCKYSCRIPT_USER_CONFIRMED" ]; then
                LOG cyan "── shall we play a game? ──"
                [ "$mute" = "false" ] && RINGTONE "Flutter"
                exit 0   # trap → cleanup
            fi
            ;;
        -1) ;;   # cancelled / Back at LIST_PICKER → loop and re-show menu
        *)  ;;
    esac

    # Persist last-selected index (only on real selections, not option 0 / cancel)
    if [ "$main_option" -ge 1 ] 2>/dev/null; then
        selnum_main="$main_option"
        PAYLOAD_SET_CONFIG "$CONFIG_NS" selnum_main "$selnum_main" >/dev/null 2>&1 || true
    fi

    if [ "$show_menu_end_OK" -eq 2 ]; then
        LOG green "Press OK to Return to Main Menu..."
        WAIT_FOR_BUTTON_PRESS A
        LOG " "
    fi
    sleep 0.3
done
