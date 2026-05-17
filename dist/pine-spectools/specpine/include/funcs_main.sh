# funcs_main.sh — SpecPine domain helpers
# (sourced by payload.sh; uses globals defined there)

# ── Theme tokens + LOG colour wrappers (LOG_TITLE / LOG_GOOD / etc.) ──────
if [ -f "${PAYLOAD_ROOT}/data/theme/theme.sh" ]; then
    source "${PAYLOAD_ROOT}/data/theme/theme.sh"
fi

# ── ASCII logo ────────────────────────────────────────────────────────────
specpine_logo() {
    if [ -f "$LOGO_FILE" ]; then
        while IFS= read -r line; do
            LOG green "$line"
        done < "$LOGO_FILE"
    else
        LOG green " ____                  ____  _            "
        LOG green "/ ___| _ __   ___  ___|  _ \\(_)_ __   ___ "
        LOG green "\\___ \\| '_ \\ / _ \\/ __| |_) | | '_ \\ / _ \\"
        LOG green " ___) | |_) |  __/ (__|  __/| | | | |  __/"
        LOG green "|____/| .__/ \\___|\\___|_|   |_|_| |_|\\___|"
        LOG green "      |_|       wi-spy dbx . wargames OK?"
    fi
}

# ── Show one of the ASCII art frames. Searches data/ansi/<name>.txt first
# (per-mode frames) then data/theme/glyphs/<name>.txt (theme tokens). ──
show_ansi() {
    local name="$1"
    local f
    for f in "${PAYLOAD_ROOT}/data/ansi/${name}.txt" \
             "${PAYLOAD_ROOT}/data/theme/glyphs/${name}.txt"; do
        if [ -f "$f" ]; then
            while IFS= read -r line; do LOG green "$line"; done < "$f"
            return 0
        fi
    done
}

# ── Ringtone wrapper (respects mute) ──────────────────────────────────────
ringtone_play() {
    local name="$1"
    [ "$mute" = "false" ] && RINGTONE "$name"
}

# ── LED wrapper (single point for future stealth-mode support) ────────────
led_safe() {
    LED "$@" 2>/dev/null || true
}

# ── GPS wrapper ───────────────────────────────────────────────────────────
gps_get_wrapper() {
    if [ "$gps_enabled" = "true" ]; then
        local pos
        pos=$(GPS_GET 2>/dev/null)
        if [ -n "$pos" ]; then
            gpspos_last="$pos"
            echo "$pos"
        else
            gpspos_last="NoGPS"
            echo "NoGPS"
        fi
    else
        gpspos_last="GPSDisabled"
        echo "GPSDisabled"
    fi
}

# ── Probe Wi-Spy DBx via spectool_raw --list ──────────────────────────────
device_probe() {
    WISPY_PRESENT="false"
    WISPY_DEVICE_NAME=""
    WISPY_DEVICE_ID=""
    if [ ! -x "$SPECTOOL_BIN" ]; then
        return 0
    fi
    local out
    out=$(LD_LIBRARY_PATH="$SPECTOOL_LIB" "$SPECTOOL_BIN" --list 2>/dev/null)
    if echo "$out" | grep -qi "wi-spy\|device "; then
        WISPY_PRESENT="true"
        WISPY_DEVICE_NAME=$(echo "$out" | grep -i "wi-spy\|device " | head -1 | sed -E 's/^[[:space:]]*Device[[:space:]]+[0-9]+:[[:space:]]*//I' | head -c 48)
        WISPY_DEVICE_ID=$(echo "$out" | grep -iE "Device[[:space:]]+[0-9]+" | head -1 | sed -E 's/.*Device[[:space:]]+([0-9]+).*/\1/I')
        [ -z "$WISPY_DEVICE_ID" ] && WISPY_DEVICE_ID="0"
    fi
}

# ── Capture first device_config event from a brief bridge run ─────────────
device_config_dump() {
    FREQ_START_KHZ=""
    FREQ_END_KHZ=""
    BIN_COUNT=""
    RES_HZ=""
    [ "$WISPY_PRESENT" = "true" ] || return 0
    local tmp_events="/tmp/specpine_probe.jsonl"
    rm -f "$tmp_events"
    LD_LIBRARY_PATH="$SPECTOOL_LIB" python3 "$BRIDGE_BIN" \
        --input-command "$SPECTOOL_BIN" \
        --events-file "$tmp_events" \
        --stall-timeout 4 \
        --max-restarts 1 \
        >> "$LOG_FILE" 2>&1 &
    local pp=$!
    local waited=0
    while [ ! -s "$tmp_events" ] && [ "$waited" -lt 4 ]; do
        sleep 1; waited=$((waited+1))
        kill -0 "$pp" 2>/dev/null || break
    done
    kill "$pp" 2>/dev/null || true
    pkill -f "spectools_bridge.py" 2>/dev/null || true
    local cfg
    cfg=$(grep -m1 '"type":"device_config"' "$tmp_events" 2>/dev/null)
    if [ -n "$cfg" ]; then
        FREQ_START_KHZ=$(echo "$cfg" | sed -nE 's/.*"freq_start_khz":([0-9]+).*/\1/p')
        FREQ_END_KHZ=$(  echo "$cfg" | sed -nE 's/.*"freq_end_khz":([0-9]+).*/\1/p')
        BIN_COUNT=$(     echo "$cfg" | sed -nE 's/.*"bin_count":([0-9]+).*/\1/p')
        RES_HZ=$(        echo "$cfg" | sed -nE 's/.*"res_hz":([0-9]+).*/\1/p')
    fi
    rm -f "$tmp_events"
}

# ── Install / Repair / Uninstall (lifted from legacy spectools_install) ───
install_spectools() {
    LOG blue "Installing SpecTools binaries"
    LOG "Source : ${PAYLOAD_ROOT}/bin"
    LOG "Target : /opt/spectools"

    local missing=0
    for bin in spectool_raw spectool_net; do
        if [ ! -f "${PAYLOAD_ROOT}/bin/${bin}" ]; then
            LOG red "Missing: bin/${bin}"
            missing=$((missing+1))
        fi
    done
    for lib in libusb-0.1.so.4.4.4 libusb-1.0.so.0.4.0; do
        if [ ! -f "${PAYLOAD_ROOT}/lib/${lib}" ]; then
            LOG red "Missing: lib/${lib}"
            missing=$((missing+1))
        fi
    done
    if [ "$missing" -gt 0 ]; then
        led_safe R 255 G 0 B 0
        ringtone_play "SideBeam"
        ALERT "Install failed: $missing files missing from payload."
        return 1
    fi

    local avail
    avail="$(df /opt 2>/dev/null | awk 'NR==2 {print $4}')"
    if [ -n "$avail" ] && [ "$avail" -lt 2048 ]; then
        led_safe R 255 G 0 B 0
        ringtone_play "SideBeam"
        ALERT "Insufficient space in /opt (need ~2 MB)."
        return 1
    fi

    led_safe R 255 G 165 B 0
    mkdir -p "$INSTALL_BIN" "$INSTALL_LIB" "$INSTALL_CONF" 2>/dev/null || {
        led_safe R 255 G 0 B 0
        ALERT "Cannot create /opt/spectools — check permissions."
        return 1
    }

    for bin in spectool_raw spectool_net; do
        cp "${PAYLOAD_ROOT}/bin/${bin}" "${INSTALL_BIN}/${bin}" || {
            led_safe R 255 G 0 B 0
            LOG red "Copy failed: ${bin}"
            return 1
        }
        chmod 755 "${INSTALL_BIN}/${bin}"
    done
    LOG green "Binaries installed"

    for lib in "${PAYLOAD_ROOT}/lib"/*.so*; do
        [ -f "$lib" ] || continue
        cp "$lib" "${INSTALL_LIB}/$(basename "$lib")"
        chmod 644 "${INSTALL_LIB}/$(basename "$lib")"
    done
    local _lf _lb _sn _lk
    for _lf in "${INSTALL_LIB}"/libusb-*.so.*; do
        [ -f "$_lf" ] || continue
        _lb=$(basename "$_lf")
        _sn=$(printf '%s' "$_lb" | sed -E 's/^(.*\.so\.[0-9]+).*/\1/')
        _lk=$(printf '%s' "$_lb" | sed -E 's/^(.*\.so).*/\1/')
        [ "$_sn" != "$_lb" ] && [ ! -e "${INSTALL_LIB}/${_sn}" ] && \
            ln -sf "$_lb" "${INSTALL_LIB}/${_sn}" 2>/dev/null || true
        [ "$_lk" != "$_lb" ] && [ "$_lk" != "$_sn" ] && [ ! -e "${INSTALL_LIB}/${_lk}" ] && \
            ln -sf "$_sn" "${INSTALL_LIB}/${_lk}" 2>/dev/null || true
    done
    LOG green "Libraries installed"

    cat > "${INSTALL_CONF}/spectools.conf" <<'EOF'
# SpecTools configuration — written by SpecPine installer
SPECTOOL_BIN=/opt/spectools/bin/spectool_raw
SPECTOOL_LIB=/opt/spectools/lib
LD_LIBRARY_PATH=/opt/spectools/lib
EOF

    if [ -f "$UDEV_RULES_SRC" ]; then
        cp "$UDEV_RULES_SRC" "$UDEV_RULES_DST" 2>/dev/null || \
            LOG yellow "udev rules copy failed (non-fatal)"
        command -v udevadm >/dev/null 2>&1 && udevadm control --reload-rules 2>/dev/null || true
        LOG green "udev rules installed"
    fi

    export LD_LIBRARY_PATH="${INSTALL_LIB}:${LD_LIBRARY_PATH:-}"
    if "${INSTALL_BIN}/spectool_raw" --help >/dev/null 2>&1 || \
       "${INSTALL_BIN}/spectool_raw" --list >/dev/null 2>&1; then
        led_safe R 0 G 255 B 0
        ringtone_play "ScaleTrill"
        LOG green "Installation complete!"
    else
        led_safe R 255 G 255 B 0
        LOG yellow "Binary verify inconclusive (OK if no Wi-Spy plugged in)"
    fi
    show_menu_end_OK=2
    return 0
}

repair_spectools() {
    LOG yellow "Repairing /opt/spectools (re-copy)"
    rm -rf /opt/spectools 2>/dev/null
    install_spectools
}

uninstall_spectools() {
    local resp
    resp=$(CONFIRMATION_DIALOG "Remove /opt/spectools and udev rules?")
    if [ "$resp" != "$DUCKYSCRIPT_USER_CONFIRMED" ]; then
        LOG "Uninstall cancelled"
        show_menu_end_OK=2
        return 0
    fi
    rm -rf /opt/spectools /etc/spectools 2>/dev/null
    rm -f "$UDEV_RULES_DST" 2>/dev/null
    command -v udevadm >/dev/null 2>&1 && udevadm control --reload-rules 2>/dev/null || true
    led_safe R 0 G 0 B 128
    LOG green "Uninstalled"
    show_menu_end_OK=2
}

# ── Settings hygiene ──────────────────────────────────────────────────────
config_check() {
    case "$default_band" in
        2.4|5|auto) ;;
        *) default_band="auto"; PAYLOAD_SET_CONFIG "$CONFIG_NS" default_band auto >/dev/null 2>&1 ;;
    esac
    case "$default_mode" in
        text|graphical) ;;
        *) default_mode="text"; PAYLOAD_SET_CONFIG "$CONFIG_NS" default_mode text >/dev/null 2>&1 ;;
    esac
    case "$mute"        in true|false) ;; *) mute=false        ;; esac
    case "$noloot"      in true|false) ;; *) noloot=false      ;; esac
    case "$gps_enabled" in true|false) ;; *) gps_enabled=false ;; esac
    case "$stall_timeout" in ''|*[!0-9]*) stall_timeout=8  ;; esac
    case "$max_restarts"  in ''|*[!0-9]*) max_restarts=5   ;; esac
    case "$anomaly_window" in ''|*[!0-9]*) anomaly_window=10 ;; esac
    case "$anomaly_threshold_db" in ''|*[!0-9.-]*) anomaly_threshold_db=15 ;; esac
}

settings_check() {
    [ "$mute"        = "true" ] && mute_disp="Muted"      || mute_disp="Audible"
    [ "$noloot"      = "true" ] && noloot_disp="Memory"   || noloot_disp="Disk"
    [ "$gps_enabled" = "true" ] && gps_disp="On"          || gps_disp="Off"
}

_set_one() {
    # $1=key, $2=value. Logs failures to $LOG_FILE; retries once on empty value.
    local key="$1" val="$2"
    [ -z "$val" ] && val="0"   # PAYLOAD_SET_CONFIG drops empty values silently
    if ! PAYLOAD_SET_CONFIG "$CONFIG_NS" "$key" "$val" >>"$LOG_FILE" 2>&1; then
        sleep 0.1
        PAYLOAD_SET_CONFIG "$CONFIG_NS" "$key" "$val" >>"$LOG_FILE" 2>&1
    fi
}

config_backup() {
    _set_one default_band         "$default_band"
    _set_one default_mode         "$default_mode"
    _set_one stall_timeout        "$stall_timeout"
    _set_one max_restarts         "$max_restarts"
    _set_one anomaly_threshold_db "$anomaly_threshold_db"
    _set_one anomaly_window       "$anomaly_window"
    _set_one mute                 "$mute"
    _set_one noloot               "$noloot"
    _set_one gps_enabled          "$gps_enabled"
    _set_one skip_ask_ringtones   "$skip_ask_ringtones"
    _set_one selnum_main          "$selnum_main"
    _set_one total_scans          "$total_scans"
    _set_one total_anomalies      "$total_anomalies"
    _set_one app_version          "$APP_VERSION"
    [ "$silent_backup" -eq 0 ] && LOG green "Settings saved"
    silent_backup=0
}

# ── Loot helpers ──────────────────────────────────────────────────────────
noloot_dirs() {
    if [ "$noloot" = "true" ]; then echo "$TMP_LOOT_ROOT"; else echo "$LOOT_ROOT"; fi
}

noloot_wipe() {
    rm -rf "${TMP_LOOT_ROOT:?}/"session_* 2>/dev/null || true
}

make_session_dir() {
    local name="$1"
    [ -z "$name" ] && name="session"
    local safe
    safe=$(printf '%s' "$name" | sed 's/[^A-Za-z0-9_.-]/_/g' | head -c 32)
    local ts
    ts=$(date +%Y%m%d_%H%M%S)
    local root
    root="$(noloot_dirs)"
    SESSION_DIR="${root}/session_${ts}_${safe}"
    mkdir -p "$SESSION_DIR" 2>/dev/null
    if [ "$gps_enabled" = "true" ]; then
        gps_get_wrapper > "${SESSION_DIR}/gps.txt"
    fi
}

write_meta_json() {
    local dir="$1"
    local mode="$2"
    local status="${3:-success}"
    local reason="${4:-}"
    [ -z "$dir" ] && return 0
    local ended
    ended=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local reason_json=""
    [ -n "$reason" ] && reason_json=",
  \"reason\": \"$(printf '%s' "$reason" | sed 's/"/\\"/g; s/\\/\\\\/g' | head -c 200)\""
    cat > "${dir}/meta.json" <<EOF
{
  "session_name": "$(basename "$dir")",
  "ended_at": "${ended}",
  "mode": "${mode}",
  "status": "${status}",
  "band": "${current_band:-${default_band}}",
  "device": {"name": "${WISPY_DEVICE_NAME}", "id": "${WISPY_DEVICE_ID}", "present": ${WISPY_PRESENT}},
  "freq_range_khz": {"start": "${FREQ_START_KHZ}", "end": "${FREQ_END_KHZ}", "bin_count": "${BIN_COUNT}", "res_hz": "${RES_HZ}"},
  "settings": {"stall_timeout": ${stall_timeout}, "max_restarts": ${max_restarts}, "mute": ${mute}, "noloot": ${noloot}, "anomaly_threshold_db": ${anomaly_threshold_db}, "anomaly_window": ${anomaly_window}},
  "gps": "${gpspos_last}",
  "app_version": "${APP_VERSION}"${reason_json}
}
EOF
}

# ── Button-event watcher (BluePine pattern: funcs_main.sh:2031-2082) ──────
start_evtest() {
    : > "$KEYCKTMP_FILE"
    : > "$BTN_EVT_FILE"
    if [ ! -e /dev/input/event0 ]; then
        # Best-effort fallback
        local cand
        cand=$(ls /dev/input/event* 2>/dev/null | head -1)
        [ -z "$cand" ] && return 1
        ((evtest "$cand" | grep "^Event:" &> "$KEYCKTMP_FILE") &) > /dev/null 2>&1
    else
        ((evtest /dev/input/event0 | grep "^Event:" &> "$KEYCKTMP_FILE") &) > /dev/null 2>&1
    fi
    EVTEST_PID="$(pgrep -n evtest 2>/dev/null)"
}

check_cancel() {
    local press_line release_line press_ts release_ts elapsed_ms
    [ -s "$KEYCKTMP_FILE" ] || return 0
    press_line=$(grep "(BTN_EAST), value 1" "$KEYCKTMP_FILE" | tail -1)
    [ -z "$press_line" ] && return 0
    press_ts=$(echo "$press_line" | sed -n 's/.*time \([0-9.]*\).*/\1/p')
    [ -z "$press_ts" ] && return 0
    release_line=$(awk -v ts="$press_ts" '
        / value 0/ { split($0,a,"time "); split(a[2],b,","); if (b[1]+0 > ts+0) { print; exit } }
    ' "$KEYCKTMP_FILE")
    if [ -z "$release_line" ]; then
        sleep 0.3
        release_line=$(awk -v ts="$press_ts" '
            / value 0/ { split($0,a,"time "); split(a[2],b,","); if (b[1]+0 > ts+0) { print; exit } }
        ' "$KEYCKTMP_FILE")
    fi
    if [ -z "$release_line" ]; then
        echo "stop" > "$BTN_EVT_FILE"
    else
        release_ts=$(echo "$release_line" | sed -n 's/.*time \([0-9.]*\).*/\1/p')
        elapsed_ms=$(awk -v p="$press_ts" -v r="$release_ts" 'BEGIN{ printf "%.0f", (r-p)*1000 }')
        if [ "${elapsed_ms:-0}" -ge 800 ]; then
            echo "stop"  > "$BTN_EVT_FILE"
        else
            local cur
            cur=$(cat "$BTN_EVT_FILE" 2>/dev/null)
            if [ "$cur" = "pause" ]; then
                : > "$BTN_EVT_FILE"   # second tap → resume
            else
                echo "pause" > "$BTN_EVT_FILE"
            fi
        fi
    fi
    : > "$KEYCKTMP_FILE"
}

is_btn_paused()  { [ "$(cat "$BTN_EVT_FILE" 2>/dev/null)" = "pause" ]; }
is_btn_stopped() { [ "$(cat "$BTN_EVT_FILE" 2>/dev/null)" = "stop"  ]; }
clear_btn_evt()  { : > "$BTN_EVT_FILE"; }

# ── Bridge lifecycle ──────────────────────────────────────────────────────
start_bridge() {
    local session_dir="$1"
    rm -f "$EVENTS_FILE"
    BRIDGE_FAIL_REASON=""
    export LD_LIBRARY_PATH="${SPECTOOL_LIB}:${LD_LIBRARY_PATH:-}"
    python3 "$BRIDGE_BIN" \
        --input-command "$SPECTOOL_BIN" \
        --events-file "$EVENTS_FILE" \
        --export-dir "$session_dir" \
        --stall-timeout "$stall_timeout" \
        --max-restarts "$max_restarts" \
        >> "$LOG_FILE" 2>&1 &
    BRIDGE_PID=$!
    local waited=0
    while [ ! -s "$EVENTS_FILE" ] && [ "$waited" -lt 6 ]; do
        sleep 1; waited=$((waited+1))
        if ! kill -0 "$BRIDGE_PID" 2>/dev/null; then
            BRIDGE_FAIL_REASON=$(tail -1 "$LOG_FILE" 2>/dev/null | head -c 160)
            [ -z "$BRIDGE_FAIL_REASON" ] && BRIDGE_FAIL_REASON="bridge exited before emitting any data (Wi-Spy unplugged?)"
            LOG red "Bridge exited - check Wi-Spy USB"
            LOG yellow "${BRIDGE_FAIL_REASON}"
            led_safe R 255 G 0 B 0
            ringtone_play "SideBeam"
            BRIDGE_PID=""
            return 1
        fi
    done
    return 0
}

stop_bridge() {
    [ -n "$BRIDGE_PID" ] && kill "$BRIDGE_PID" 2>/dev/null || true
    pkill -f "spectools_bridge.py" 2>/dev/null || true
    BRIDGE_PID=""
}

# ── Session lifecycle helpers (always keep session dir on disk) ───────────
mark_session_started() {
    write_meta_json "$1" "$2" "started"
}

mark_session_failed() {
    local dir="$1" mode="$2" reason="${3:-${BRIDGE_FAIL_REASON:-unknown}}"
    write_meta_json "$dir" "$mode" "failed" "$reason"
}

mark_session_cancelled() {
    write_meta_json "$1" "$2" "cancelled" "${3:-user cancelled}"
}

mark_session_success() {
    write_meta_json "$1" "$2" "success"
}

# ── JSONL helpers (no jq dependency) ──────────────────────────────────────
parse_sweep_stats() {
    local line="$1"
    local mn mx av
    mn=$(echo "$line" | sed -nE 's/.*"min":(-?[0-9.]+).*/\1/p')
    mx=$(echo "$line" | sed -nE 's/.*"max":(-?[0-9.]+).*/\1/p')
    av=$(echo "$line" | sed -nE 's/.*"avg":(-?[0-9.]+).*/\1/p')
    echo "${mn:-?} ${mx:-?} ${av:-?}"
}

band_to_filter() {
    case "$1" in
        2.4) echo "2400000 2500000" ;;
        5)   echo "5170000 5835000" ;;
        *)   echo "0 99999999" ;;
    esac
}

dbm_to_glyph() {
    local v=$1
    if   [ "$v" -le -90 ]; then echo " "
    elif [ "$v" -le -80 ]; then echo "."
    elif [ "$v" -le -70 ]; then echo "-"
    elif [ "$v" -le -65 ]; then echo "="
    elif [ "$v" -le -55 ]; then echo "+"
    else                        echo "#"
    fi
}

wifi_channel_for_freq() {
    local khz=$1
    if [ "$khz" -ge 2412000 ] && [ "$khz" -le 2472000 ]; then
        echo $(( (khz - 2412000) / 5000 + 1 ))
    elif [ "$khz" -ge 5170000 ] && [ "$khz" -le 5835000 ]; then
        echo $(( (khz - 5000000) / 5000 ))
    else
        echo "?"
    fi
}

# ── Status / Device Info screen ───────────────────────────────────────────
status_display() {
    LOG blue   "── SpecPine Status ──"
    case "${SPECTOOL_SOURCE:-payload}" in
        payload) LOG green "spectool_raw : payload (self-contained)" ;;
        opt)     LOG green "spectool_raw : /opt/spectools (system)" ;;
    esac
    device_probe
    if [ "$WISPY_PRESENT" = "true" ]; then
        LOG green "Wi-Spy       : present  [${WISPY_DEVICE_NAME}]"
        device_config_dump
        if [ -n "$FREQ_START_KHZ" ]; then
            local span_mhz
            span_mhz=$(( (FREQ_END_KHZ - FREQ_START_KHZ) / 1000 ))
            LOG       "Range : ${FREQ_START_KHZ} - ${FREQ_END_KHZ} kHz (${span_mhz} MHz)"
            LOG       "Bins  : ${BIN_COUNT}   Res: ${RES_HZ} Hz"
        else
            LOG yellow "Could not query device_config (USB stall?)"
        fi
    else
        LOG yellow "Wi-Spy       : NOT detected"
        if [ ! -x "$SPECTOOL_BIN" ]; then
            LOG red    "spectool_raw missing at ${SPECTOOL_BIN}"
        else
            LOG       "Plug in Wi-Spy DBx and re-check."
        fi
    fi
    LOG cyan   "------------- settings ------------------------"
    LOG       "Band   : ${default_band}        Mode  : ${default_mode}"
    LOG       "Stall  : ${stall_timeout}s        Restart: ${max_restarts}"
    LOG       "Anomaly: ${anomaly_threshold_db}dB / ${anomaly_window} sweeps"
    LOG       "Audio  : ${mute_disp:-Audible}   Loot : ${noloot_disp:-Disk}"
    LOG       "GPS    : ${gps_disp:-Off}     Scans: ${total_scans}"
    LOG       "Anomal.: ${total_anomalies}"
    local restarts
    restarts=$(grep -c "Restarting bridge\|restart" "$LOG_FILE" 2>/dev/null || echo 0)
    [ "$restarts" -gt 0 ] && LOG yellow "Bridge restarts this session: ${restarts}"
    LOG blue   "================================================"
    show_menu_end_OK=2
}
