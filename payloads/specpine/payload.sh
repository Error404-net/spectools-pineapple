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

PAYLOAD_SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "${PAYLOAD_SELF_DIR}/include/funcs_main.sh" ]; then
    PAYLOAD_ROOT="$PAYLOAD_SELF_DIR"
else
    # The Pager firmware stages a standalone copy of this script into /tmp
    # (e.g. /tmp/payload-<rand>.sh) and executes THAT, without copying the
    # sibling include/bin/data directories alongside it. When that happens,
    # $0 points at the /tmp staging copy, so dirname-based resolution would
    # silently point PAYLOAD_ROOT at /tmp and break every `source` below
    # (confirmed live via `ps`: the running process is /bin/bash
    # /tmp/payload-<rand>.sh, and /tmp/include/funcs_main.sh does not
    # exist). Fall back to the known install location used by every
    # deploy in this repo (see CLAUDE.md's deploy command).
    PAYLOAD_ROOT="/root/payloads/user/reconnaissance/specpine"
fi

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
FB_SCREENSHOT_BIN="${PAYLOAD_ROOT}/bin/fb_screenshot.py"
HUD_BIN="${PAYLOAD_ROOT}/bin/specpine_hud.py"
UDEV_RULES_SRC="${PAYLOAD_ROOT}/data/99-wispy.rules"
UDEV_RULES_DST="/etc/udev/rules.d/99-wispy.rules"

LOOT_ROOT="/root/loot/specpine"
TMP_LOOT_ROOT="/tmp/specpine"
EVENTS_FILE="/tmp/specpine_events.jsonl"
BTN_EVT_FILE="/tmp/specpine_btn_evt"
DPAD_EVT_FILE="/tmp/specpine_dpad_evt"
DPAD_PENDING_FILE="/tmp/specpine_dpad_pending"
SCREENSHOT_EVT_FILE="/tmp/specpine_screenshot_evt"
KEYCKTMP_FILE="/tmp/specpine_keyck.tmp"
LOG_FILE="/tmp/specpine.log"
LOCK_FILE="/tmp/specpine.lock"
PID_FILE="/tmp/specpine.pid"

APP_VERSION="1.2"
CONFIG_NS="specpine"

# ── Defaults (overridden by PAYLOAD_GET_CONFIG below) ─────────────────────
default_band="2.4"
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
EXIT_PRECONFIRMED=0
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
    # Fallback: kill any orphaned SpecPine python3 workers by matching args
    # (ps w, not plain ps -- see kill_stray_specpine_workers() in funcs_main.sh)
    kill_stray_specpine_workers
    killall evtest 2>/dev/null || true
    pineapple_ensure_running   # safety net: force-resume firmware UI if a renderer left it SIGSTOPped
    LED R 0 G 0 B 0 2>/dev/null || true
    rm -f "$LOCK_FILE" "$PID_FILE" "$EVENTS_FILE" "$BTN_EVT_FILE" "$KEYCKTMP_FILE" \
          "$DPAD_EVT_FILE" "$DPAD_PENDING_FILE" "$SCREENSHOT_EVT_FILE"
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

# A previous run that crashed, got SIGKILL'd, or was killed mid-test can leave
# a renderer/bridge orphaned and still holding /dev/fb0 with pineapple
# SIGSTOPped -- a fresh launch should never inherit that state. Reap any
# stray workers and force-resume the firmware UI before doing anything else.
kill_stray_specpine_workers
pineapple_ensure_running
rm -f /tmp/specpine_hud.lock

mkdir -p "$LOOT_ROOT" "$TMP_LOOT_ROOT" 2>/dev/null || true

# ── Dependencies + ringtone install ───────────────────────────────────────
check_dependencies
[ "$skip_ask_ringtones" -eq 0 ] && check_ringtones
config_check
settings_check

# ── Boot splash, then straight to the menu (BluePine pattern: payload.sh:400-414)
# Removed: the tap-vs-hold landing gate and its auto-launched default
# waterfall. On hardware it consistently landed on the waterfall regardless
# of a tap, and OK couldn't be used to reach the menu at all -- not worth
# debugging further when the actual goal is simpler: always land on the menu,
# no auto-launched scan, no button gate to get wrong.
#
# Also removed: the ASCII-art logo (specpine_logo, LOG'd line-by-line from
# data/specpine_logo.txt) that used to print here. Didn't render cleanly on
# the Pager's small screen and the user asked for it gone outright -- not
# resized, just removed.
[ "$mute" = "false" ] && RINGTONE "Flutter"

# Optional framebuffer splash plays first (skips silently if /dev/fb0 missing).
#
# Was previously `python3 specpine_splash.py 2>/dev/null || true` -- any
# error (or a hang) swallowed completely, which matches the "intermittent"
# symptom reported on hardware (sometimes shows, sometimes doesn't, no trace
# left behind to diagnose with). Two changes: (1) stderr now goes to
# $LOG_FILE instead of /dev/null, so a real failure leaves evidence; (2) a
# 5s watchdog kills it if it hangs, instead of blocking the rest of
# payload.sh (and the menu) forever behind a stuck splash.
if [ -e /dev/fb0 ] && [ -x "${PAYLOAD_ROOT}/bin/specpine_splash.py" ]; then
    python3 "${PAYLOAD_ROOT}/bin/specpine_splash.py" >>"$LOG_FILE" 2>&1 &
    SPLASH_PID=$!
    SPLASH_DEADLINE=$(( $(date +%s) + 5 ))
    while kill -0 "$SPLASH_PID" 2>/dev/null && [ "$(date +%s)" -lt "$SPLASH_DEADLINE" ]; do
        sleep 0.1
    done
    if kill -0 "$SPLASH_PID" 2>/dev/null; then
        echo "[payload] specpine_splash.py exceeded 5s watchdog, killing (pid $SPLASH_PID)" >> "$LOG_FILE"
        kill -9 "$SPLASH_PID" 2>/dev/null || true
        pineapple_ensure_running   # in case it died mid-SIGSTOP, holding the screen
    fi
    wait "$SPLASH_PID" 2>/dev/null || true
fi

device_probe   # populates WISPY_PRESENT, WISPY_DEVICE_NAME, WISPY_DEVICE_ID

# ── Main menu loop (BluePine pattern: payload.sh:420-965) ─────────────────
while true; do
    show_menu_end_OK=1
    main_menu
    main_option="$selnum"

    case "$main_option" in
        2)  if pre_scan_dialog; then current_band="2.4"; graphical_waterfall; fi ;;
        3)  if pre_scan_dialog; then current_band="5";   graphical_waterfall; fi ;;
        7)  sub_menu_nfo ;;
        0)
            # selnum=0 set by HUD on Back-hold (EXIT_PRECONFIRMED=1) or by
            # legacy Back-press path below — always pre-confirmed by the time
            # we get here, so no second dialog needed.
            LOG cyan "── shall we play a game? ──"
            [ "$mute" = "false" ] && RINGTONE "Flutter"
            exit 0   # trap → cleanup
            ;;
        -1)
            # Back at legacy LIST_PICKER main menu → prompt to exit
            local _exit_resp
            _exit_resp=$(CONFIRMATION_DIALOG "Exit SpecPine?")
            if [ "$_exit_resp" = "$DUCKYSCRIPT_USER_CONFIRMED" ]; then
                LOG cyan "── shall we play a game? ──"
                [ "$mute" = "false" ] && RINGTONE "Flutter"
                exit 0
            fi
            ;;
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
