# funcs_main.sh — SpecPine domain helpers
# (sourced by payload.sh; uses globals defined there)

# ── Theme tokens + LOG colour wrappers (LOG_TITLE / LOG_GOOD / etc.) ──────
if [ -f "${PAYLOAD_ROOT}/data/theme/theme.sh" ]; then
    source "${PAYLOAD_ROOT}/data/theme/theme.sh"
fi

# ── Stray-worker reaper ────────────────────────────────────────────────────
# Kill any spectools_bridge.py / spectools_waterfall_*.py processes by name,
# regardless of whether this script currently tracks their PID. Needed in two
# places: (1) once at startup, in case a previous run crashed, got kill -9'd,
# or otherwise left a renderer orphaned and still holding /dev/fb0 with
# pineapple SIGSTOPped -- a fresh launch should never inherit that; (2) in the
# cleanup() trap, as a fallback alongside the tracked-PID kills.
#
# MUST use `ps w`, not plain `ps`: BusyBox `ps` truncates the COMMAND column
# on a narrow/non-pty session, and these scripts' full installed path
# (/root/payloads/user/reconnaissance/specpine/bin/spectools_waterfall_fb.py)
# is long enough to get cut off before the matched substring -- which made
# this fallback silently never catch anything. Confirmed live: a stray
# graphical waterfall renderer kept running (still drawing, pineapple still
# stopped) even after the whole payload had exited and the menu was gone.
# NOTE: also matches spectool_raw|spectool_net -- the actual MIPS binaries
# the bridge launches as a *subprocess* (via Python's subprocess.Popen).
# bridge.py's SIGTERM handler only flips a `stop` flag and unwinds its own
# read loop; it never explicitly kills its spectool_raw child, and Python
# does not auto-kill children when the parent dies. So a killed/crashed
# bridge can leave spectool_raw running and still holding an exclusive
# libusb claim on the Wi-Spy -- confirmed live: `ps` showed two orphaned
# spectool_raw processes from earlier sessions, and every scan after that
# failed with "no device_config/sweep data" (looked like a USB/hardware
# fault, but spectool_raw run by hand against the same idle device worked
# instantly). Reaping by name here, not just by tracked PID, is what catches
# that case.
kill_stray_specpine_workers() {
    local _pid
    for _pid in $(ps w 2>/dev/null | awk '/spectools_bridge|spectools_waterfall|spectool_raw|spectool_net/{print $1}'); do
        kill "$_pid" 2>/dev/null || true
    done
    sleep 0.3
    for _pid in $(ps w 2>/dev/null | awk '/spectools_bridge|spectools_waterfall|spectool_raw|spectool_net/{print $1}'); do
        kill -9 "$_pid" 2>/dev/null || true
    done
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
    local band="${1:-${default_band:-auto}}"
    local range_idx
    range_idx=$(band_to_range_index "$band")
    FREQ_START_KHZ=""
    FREQ_END_KHZ=""
    BIN_COUNT=""
    RES_HZ=""
    [ "$WISPY_PRESENT" = "true" ] || return 0
    local tmp_events="/tmp/specpine_probe.jsonl"
    rm -f "$tmp_events"
    LD_LIBRARY_PATH="$SPECTOOL_LIB" python3 "$BRIDGE_BIN" \
        --input-command "${SPECTOOL_BIN} --range ${range_idx}" \
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
    : > "$DPAD_EVT_FILE"
    : > "$DPAD_PENDING_FILE"
    : > "$SCREENSHOT_EVT_FILE"
    if [ ! -e /dev/input/event0 ]; then
        # Best-effort fallback
        local cand
        cand=$(ls /dev/input/event* 2>/dev/null | head -1)
        [ -z "$cand" ] && return 1
        ((evtest "$cand" | grep "^Event:" &> "$KEYCKTMP_FILE") &) > /dev/null 2>&1
    else
        ((evtest /dev/input/event0 | grep "^Event:" &> "$KEYCKTMP_FILE") &) > /dev/null 2>&1
    fi
    # pgrep not on BusyBox; pidof works and returns newest PID last
    EVTEST_PID="$(pidof evtest 2>/dev/null | awk '{print $NF}')"
}

check_cancel() {
    local press_ts release_line release_ts elapsed_ms i
    [ -s "$KEYCKTMP_FILE" ] || return 0

    # Single awk pass does what used to be a filter-grep + cat + rm, plus a
    # separate grep -q (BTN_SOUTH) and a separate grep|tail (BTN_EAST press)
    # -- 5-6 forked processes every single tick. On this device's slow,
    # single-core MIPS CPU, that fork overhead competes directly against
    # whatever scan renderer is running; during graphical_waterfall
    # (spectools_waterfall_fb.py, which does real per-pixel framebuffer
    # writes every frame) that contention was severe enough that OK/Back
    # presses and LEFT/RIGHT band-switches were getting missed entirely --
    # the text/ASCII renderer is far lighter on CPU and was not reported
    # broken, which is the tell. One awk invocation does the filtering AND
    # the BTN_SOUTH/BTN_EAST detection in a single process.
    #
    # Also still does the original job of dropping the SYN_REPORT/housekeeping
    # lines evtest prints after every event -- check_dpad strips KEY_*, this
    # strips everything that isn't a BTN_SOUTH/BTN_EAST line, so an
    # OK/Back-free stretch of pure d-pad use doesn't let $KEYCKTMP_FILE grow
    # unbounded over a long session ("glitch"/bog-down symptom).
    #
    # Truncate in place (not mv -- see check_dpad's comment on why) so the
    # live evtest writer's fd stays valid.
    local cancel_out south_hit
    cancel_out=$(awk -v tmpf="${KEYCKTMP_FILE}.tmp" '
        function getts(l,    a,b) {
            split(l, a, "time "); split(a[2], b, ",")
            return b[1]
        }
        /\(BTN_SOUTH\), value 1/ { south = 1 }
        /\(BTN_EAST\), value 1/  { press_line = $0 }
        /\(BTN_SOUTH\)|\(BTN_EAST\)/ { print > tmpf }
        END {
            if (south)      print "SOUTH"
            if (press_line) print "PRESS " getts(press_line)
        }
    ' "$KEYCKTMP_FILE")
    cat "${KEYCKTMP_FILE}.tmp" > "$KEYCKTMP_FILE" 2>/dev/null
    rm -f "${KEYCKTMP_FILE}.tmp"

    south_hit=""
    press_ts=""
    while IFS=' ' read -r _kind _val; do
        case "$_kind" in
            SOUTH) south_hit=1 ;;
            PRESS) press_ts="$_val" ;;
        esac
    done <<EOF
$cancel_out
EOF

    # Back / red button. Hardware-verified via evtest: code 304 (BTN_SOUTH)
    # -- distinct from BTN_EAST (305, OK). The Pager firmware itself reacts to
    # Back at native LIST_PICKER/dialog prompts ("Press Back to bail out"),
    # but during a framebuffer takeover (graphical_waterfall etc.) the
    # firmware's own UI process is SIGSTOPped, so it can only queue the event
    # and flash its exit dialog once resumed -- it can't actually act on it.
    # Watch BTN_SOUTH here too so Back works as an immediate stop while our
    # own evtest loop owns input, same as a long OK-press. No tap/hold
    # disambiguation needed: Back is a dedicated button, any press stops.
    if [ -n "$south_hit" ]; then
        echo "stop" > "$BTN_EVT_FILE"
        : > "$KEYCKTMP_FILE"
        return 0
    fi

    [ -z "$press_ts" ] && return 0

    # Poll for BTN_EAST release (value 0) for up to 1.2s.
    # Match (BTN_EAST) specifically — not EV_SYN "value 0" lines.
    release_line=""
    i=0
    while [ "$i" -lt 12 ] && [ -z "$release_line" ]; do
        release_line=$(awk -v ts="$press_ts" \
            '/(BTN_EAST), value 0/ {
                split($0,a,"time "); split(a[2],b,",");
                if (b[1]+0 > ts+0) { print; exit }
            }' "$KEYCKTMP_FILE")
        [ -z "$release_line" ] && sleep 0.1
        i=$(( i + 1 ))
    done

    if [ -z "$release_line" ]; then
        # No BTN_EAST release within 1.2s → genuine long-press → stop
        echo "stop" > "$BTN_EVT_FILE"
    else
        release_ts=$(echo "$release_line" | sed -n 's/.*time \([0-9.]*\).*/\1/p')
        elapsed_ms=$(awk -v p="$press_ts" -v r="$release_ts" 'BEGIN{ printf "%.0f", (r-p)*1000 }')
        if [ "${elapsed_ms:-0}" -ge 800 ]; then
            echo "stop" > "$BTN_EVT_FILE"
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

# ── D-pad watcher (LEFT/RIGHT band switch, UP+DOWN combo screenshot) ──────
# Hardware-verified keycodes (decoded from /proc/bus/input/devices' KEY
# capability bitmap AND confirmed live via evtest on real button presses):
#   KEY_UP=103  KEY_LEFT=105  KEY_RIGHT=106  KEY_DOWN=108  (BTN_EAST=305 is OK)
# Reads the same $KEYCKTMP_FILE that check_cancel() reads. Only consumes the
# KEY_UP/DOWN/LEFT/RIGHT lines it matched (via grep -v) so a BTN_EAST press
# arriving in the same poll window is left intact for check_cancel() to see.
# Call check_dpad() *before* check_cancel() each loop tick.
check_dpad() {
    [ -s "$KEYCKTMP_FILE" ] || return 0

    # Single awk pass replaces what used to be 4 separate grep|tail pipelines
    # plus 2 sed timestamp extractions plus a final grep -v cleanup -- 7+
    # forked processes every single tick, run unconditionally regardless of
    # whether any d-pad key was even pressed. On this device's slow,
    # single-core MIPS CPU that overhead competes against whatever scan
    # renderer is running, and was almost certainly contributing to the
    # graphical waterfall's L/R band-switch and OK/Back-stop becoming
    # unresponsive (the text/ASCII renderer, much lighter on CPU, was not
    # reported broken). BTN_SOUTH/BTN_EAST lines are left untouched here --
    # check_cancel() does its own filtering of those.
    local dpad_out up_ts down_ts left_hit right_hit _kind _val
    dpad_out=$(awk -v tmpf="${KEYCKTMP_FILE}.tmp" '
        function getts(l,    a,b) {
            split(l, a, "time "); split(a[2], b, ",")
            return b[1]
        }
        /\(KEY_UP\), value 1/    { up_line = $0; next }
        /\(KEY_DOWN\), value 1/  { down_line = $0; next }
        /\(KEY_LEFT\), value 1/  { left_hit = 1; next }
        /\(KEY_RIGHT\), value 1/ { right_hit = 1; next }
        { print > tmpf }
        END {
            if (up_line)    print "UP " getts(up_line)
            if (down_line)  print "DOWN " getts(down_line)
            if (left_hit)   print "LEFT"
            if (right_hit)  print "RIGHT"
        }
    ' "$KEYCKTMP_FILE")
    cat "${KEYCKTMP_FILE}.tmp" > "$KEYCKTMP_FILE" 2>/dev/null
    rm -f "${KEYCKTMP_FILE}.tmp"

    up_ts=""; down_ts=""; left_hit=""; right_hit=""
    while IFS=' ' read -r _kind _val; do
        case "$_kind" in
            UP)    up_ts="$_val" ;;
            DOWN)  down_ts="$_val" ;;
            LEFT)  left_hit=1 ;;
            RIGHT) right_hit=1 ;;
        esac
    done <<EOF
$dpad_out
EOF

    # This loop polls every ~150ms, but the combo window is 400ms -- two
    # *separate* physical button presses (UP and DOWN) very rarely land in
    # the exact same poll's worth of evtest output, even when the user is
    # genuinely trying to press them together. The old code required both to
    # show up in the same tick, so whichever one arrived first got matched
    # against nothing, fell through to neither branch below, and was then
    # unconditionally discarded by the grep -v cleanup at the bottom -- by
    # the time its partner arrived on the next tick, the first press was
    # already gone and the combo could never fire. This is the root cause of
    # "screenshot does not work with up/down."
    #
    # Fix: carry a single unpaired UP or DOWN press forward (with its real
    # evtest timestamp, so the eventual delta_ms check is still accurate)
    # across ticks via $DPAD_PENDING_FILE, instead of dropping it the instant
    # this tick doesn't also contain its partner.
    local pending pending_key pending_ts pending_age
    if [ -s "$DPAD_PENDING_FILE" ]; then
        pending=$(cat "$DPAD_PENDING_FILE")
        pending_key="${pending%% *}"
        pending="${pending#* }"
        pending_ts="${pending%% *}"
        if [ "$pending_key" = "up" ] && [ -z "$up_ts" ]; then
            up_ts="$pending_ts"
        elif [ "$pending_key" = "down" ] && [ -z "$down_ts" ]; then
            down_ts="$pending_ts"
        fi
    fi

    if [ -n "$up_ts" ] && [ -n "$down_ts" ]; then
        local delta_ms
        delta_ms=$(awk -v a="$up_ts" -v b="$down_ts" \
            'BEGIN{ d=a-b; if (d<0) d=-d; printf "%.0f", d*1000 }')
        # UP and DOWN within 400ms of each other = combo press
        if [ "${delta_ms:-9999}" -le 400 ]; then
            echo "1" > "$SCREENSHOT_EVT_FILE"
        fi
        : > "$DPAD_PENDING_FILE"
    elif [ -n "$up_ts" ]; then
        echo "up ${up_ts} $(date +%s)" > "$DPAD_PENDING_FILE"
    elif [ -n "$down_ts" ]; then
        echo "down ${down_ts} $(date +%s)" > "$DPAD_PENDING_FILE"
    elif [ -s "$DPAD_PENDING_FILE" ]; then
        # No new UP/DOWN this tick -- expire a pending half-combo after ~1s
        # of real wall-clock waiting (using our own clock here, not evtest's,
        # since this is just "how long have we been waiting", not a combo
        # timing comparison) so a single stray tap doesn't sit around
        # forever waiting for a partner that never arrives.
        pending=$(cat "$DPAD_PENDING_FILE")
        pending_age="${pending##* }"
        if [ -n "$pending_age" ] && [ "$(( $(date +%s) - pending_age ))" -ge 1 ]; then
            : > "$DPAD_PENDING_FILE"
        fi
    fi

    if [ -n "$left_hit" ]; then
        echo "left" > "$DPAD_EVT_FILE"
    elif [ -n "$right_hit" ]; then
        echo "right" > "$DPAD_EVT_FILE"
    fi

    # NOTE: the awk pass above already wrote everything that wasn't a
    # KEY_UP/DOWN/LEFT/RIGHT line out to $KEYCKTMP_FILE (via the cat/rm right
    # after it runs) -- notably any pending BTN_EAST press/release line is
    # left intact in there for check_cancel() to see. No separate cleanup
    # pass needed here anymore.
    #
    # IMPORTANT: that cat was a redirect `>` onto the *existing* $KEYCKTMP_FILE
    # path, never an `mv` of a temp file over it. start_evtest backgrounds
    # `evtest ... | grep "^Event:" &> "$KEYCKTMP_FILE"`, which opens that path
    # ONCE and holds the fd open on that inode for the life of the scan. `mv`
    # would replace the path with a *new* inode -- the live evtest writer
    # would keep appending to the old, now-pathless inode forever, while every
    # future read of $KEYCKTMP_FILE (by check_dpad OR check_cancel) would see a
    # file that never updates again. This was confirmed as the cause of
    # LEFT/RIGHT band switching going silently dead after the very first dpad
    # check, so it stays a `>` redirect onto the existing path/inode.
}

is_dpad_left()           { [ "$(cat "$DPAD_EVT_FILE" 2>/dev/null)" = "left"  ]; }
is_dpad_right()          { [ "$(cat "$DPAD_EVT_FILE" 2>/dev/null)" = "right" ]; }
clear_dpad_evt()         { : > "$DPAD_EVT_FILE"; : > "$DPAD_PENDING_FILE"; }
is_screenshot_requested() { [ "$(cat "$SCREENSHOT_EVT_FILE" 2>/dev/null)" = "1" ]; }
clear_screenshot_evt()    { : > "$SCREENSHOT_EVT_FILE"; }

# ── Firmware UI process safety net ────────────────────────────────────────
# spectools_waterfall_fb.py SIGSTOPs /pineapple/pineapple for the duration of
# a graphical waterfall so it can own /dev/fb0 without the firmware's own
# redraw loop racing it, then SIGCONTs on exit. That SIGCONT relies on the
# renderer shutting down cleanly (normal exit, or SIGINT/SIGTERM caught by
# its own handler). If the renderer is killed -9, OOM-killed, or hits an
# uncaught exception that bypasses its handler, /pineapple/pineapple is left
# permanently stopped and the whole UI (display + input + debug terminal)
# freezes — confirmed live during development. pineapple_ensure_running is
# an independent, idempotent check: find the PID, look at its /proc state,
# and CONT it if (and only if) it's actually stopped. Safe to call any time,
# from any code path, as a belt-and-suspenders recovery net.
pineapple_ensure_running() {
    local pid state
    pid="$(pidof pineapple 2>/dev/null | awk '{print $1}')"
    if [ -z "$pid" ]; then
        pid="$(pgrep -f /pineapple/pineapple 2>/dev/null | head -1)"
    fi
    [ -z "$pid" ] && return 0
    state="$(awk '{print $3}' "/proc/${pid}/stat" 2>/dev/null)"
    if [ "$state" = "T" ] || [ "$state" = "t" ]; then
        kill -CONT "$pid" 2>/dev/null || true
        echo "[safety] pineapple (pid ${pid}) was stopped -- sent CONT" >> "$LOG_FILE" 2>/dev/null
    fi
}

# ── Band → device range mapping ────────────────────────────────────────────
# Wi-Spy DBx is a single-radio swept analyzer: it exposes 6 fixed profiles via
# spectool_raw's "-r/--range" flag (see spectool sourcecode/wispy_hw_dbx.c,
# wispydbx_add_supportedranges()):
#   0  Full 2.4GHz Band            2400-2495 MHz @ 333kHz
#   1  Full 2.4GHz Band (Turbo)    2400-2495 MHz @ 1MHz  (faster, coarser)
#   2  Full 5GHz Band              5150-5836 MHz @ ~1.5MHz
#   3  UNII Low  (ch. 36-64)       5150-5350 MHz
#   4  UNII Mid  (ch. 100-140)     5470-5725 MHz
#   5  UNII High (ch. 149-165)     5725-5836 MHz
# It cannot sweep both bands at once, so "auto" defaults to 2.4GHz (profile 0)
# — same as the device's own out-of-the-box default range.
band_to_range_index() {
    case "$1" in
        5)   echo 2 ;;   # Full 5GHz Band
        2.4|auto|*) echo 0 ;;   # Full 2.4GHz Band
    esac
}

# ── Bridge lifecycle ──────────────────────────────────────────────────────
start_bridge() {
    local session_dir="$1"
    local band="${2:-${current_band:-${default_band:-auto}}}"
    local range_idx
    range_idx=$(band_to_range_index "$band")
    rm -f "$EVENTS_FILE"
    BRIDGE_FAIL_REASON=""
    # Always reap any leftover bridge/spectool_raw from a prior session before
    # claiming the USB device again -- see kill_stray_specpine_workers()'s
    # comment for why this is required (orphaned spectool_raw silently holds
    # an exclusive libusb claim and makes every later attempt look like a
    # dead/disconnected Wi-Spy).
    kill_stray_specpine_workers
    export LD_LIBRARY_PATH="${SPECTOOL_LIB}:${LD_LIBRARY_PATH:-}"
    python3 "$BRIDGE_BIN" \
        --input-command "${SPECTOOL_BIN} --range ${range_idx}" \
        --events-file "$EVENTS_FILE" \
        --export-dir "$session_dir" \
        --stall-timeout "$stall_timeout" \
        --max-restarts "$max_restarts" \
        >> "$LOG_FILE" 2>&1 &
    BRIDGE_PID=$!
    local waited=0
    # IMPORTANT: do NOT treat "$EVENTS_FILE is non-empty" as success. The
    # bridge's own emit() writes every event -- including its very first
    # "status: Bridge initializing" line -- into EVENTS_FILE within
    # milliseconds of starting, regardless of whether spectool_raw has
    # actually finished retuning the Wi-Spy and produced real device data.
    # That made this check pass instantly even for a band that never came up
    # (e.g. 5GHz ranges, which take noticeably longer to lock than 2.4GHz, or
    # fail outright on some hardware): the scan would report "success" and
    # start rendering against a feed that only ever contains status/error
    # lines -- explains the reported "5GHz: bottom labels stay 2.4GHz-shaped,
    # no waterfall data at all" symptom, since the renderer's freq_start/end
    # (and therefore its channel-tick selection) only update on a real
    # device_config/sweep event that never arrives. Wait specifically for one
    # of those two event types, and use a longer window than the original 6s
    # since 5GHz retune is slower in practice.
    local need_secs=12
    while [ "$waited" -lt "$need_secs" ] && \
          ! grep -q '"type":"device_config"\|"type":"sweep"' "$EVENTS_FILE" 2>/dev/null; do
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
    if ! grep -q '"type":"device_config"\|"type":"sweep"' "$EVENTS_FILE" 2>/dev/null; then
        BRIDGE_FAIL_REASON="no device_config/sweep data after ${need_secs}s for band '${band}' (range ${range_idx}) -- Wi-Spy busy retuning, this range unsupported, or USB unresponsive"
        LOG red "Bridge alive but no real data - check Wi-Spy USB"
        LOG yellow "${BRIDGE_FAIL_REASON}"
        led_safe R 255 G 0 B 0
        ringtone_play "SideBeam"
        stop_bridge
        return 1
    fi
    return 0
}

stop_bridge() {
    [ -n "$BRIDGE_PID" ] && kill "$BRIDGE_PID" 2>/dev/null || true
    pkill -f "spectools_bridge.py" 2>/dev/null || true
    # Also reap the bridge's spectool_raw/spectool_net child directly --
    # bridge.py's SIGTERM handler doesn't kill its own subprocess, so without
    # this an orphaned spectool_raw keeps the Wi-Spy's libusb claim open and
    # every subsequent start_bridge() fails as if the device were gone.
    pkill -f "spectool_raw" 2>/dev/null || true
    pkill -f "spectool_net" 2>/dev/null || true
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
