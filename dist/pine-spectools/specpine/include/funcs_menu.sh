# funcs_menu.sh — SpecPine menus, dialogs, dependency + ringtone install
# (sourced by payload.sh; uses globals defined there)

# ── Dependency check (BluePine pattern: funcs_menu.sh:38-153) ─────────────
check_dependencies() {
    local need_evtest=0 need_python=0 need_grep=0 dep_text=""

    command -v evtest  >/dev/null 2>&1 || need_evtest=1
    command -v python3 >/dev/null 2>&1 || need_python=1
    if grep -V 2>/dev/null | grep -qi "GNU"; then :; else need_grep=1; fi

    [ "$need_evtest" -eq 1 ] && dep_text="evtest"
    [ "$need_python" -eq 1 ] && dep_text="${dep_text:+${dep_text} & }python3"
    [ "$need_grep"   -eq 1 ] && dep_text="${dep_text:+${dep_text} & }grep"

    [ -z "$dep_text" ] && return 0

    local resp
    resp=$(CONFIRMATION_DIALOG "Dependency not met!

Required: ${dep_text}

Install via opkg now?")
    if [ "$resp" != "$DUCKYSCRIPT_USER_CONFIRMED" ]; then
        ERROR_DIALOG "Cannot continue without ${dep_text}"
        exit 1
    fi

    local count=0
    while [ -f "/var/lock/opkg.lock" ] && [ "$count" -lt 3 ]; do
        LOG red "opkg locked, waiting..."; sleep 5; count=$((count+1))
    done

    if ! ping -c 1 -w 3 8.8.8.8 >/dev/null 2>&1; then
        ERROR_DIALOG "No network — connect Pager to the internet and retry."
        exit 1
    fi

    LOG "Running opkg update..."
    if ! opkg update >> "$LOG_FILE" 2>&1; then
        ERROR_DIALOG "opkg update failed — see $LOG_FILE"
        exit 1
    fi
    [ "$need_grep"   -eq 1 ] && opkg install grep   >> "$LOG_FILE" 2>&1
    [ "$need_evtest" -eq 1 ] && opkg install evtest >> "$LOG_FILE" 2>&1
    [ "$need_python" -eq 1 ] && opkg install python3 >> "$LOG_FILE" 2>&1
    LOG green "Dependencies installed"
}

# ── Ringtone install (BluePine pattern: funcs_menu.sh:156-211) ────────────
check_ringtones() {
    local DEST_DIR="/lib/pager/ringtones"
    [ -d "$DEST_DIR" ] || return 0

    local ringtones="Flutter GlitchHack ScaleTrill SideBeam Warning Achievement"
    local count=0
    for rt in $ringtones; do
        [ -f "${DEST_DIR}/${rt}" ] || count=$((count+1))
    done
    [ "$count" -eq 0 ] && return 0

    local resp
    resp=$(CONFIRMATION_DIALOG "${count} SpecPine sound effects are missing.

Install them to ${DEST_DIR}?")
    if [ "$resp" != "$DUCKYSCRIPT_USER_CONFIRMED" ]; then
        skip_ask_ringtones=1
        PAYLOAD_SET_CONFIG "$CONFIG_NS" skip_ask_ringtones 1 >/dev/null 2>&1
        return 0
    fi

    local rt content
    for rt in $ringtones; do
        [ -f "${DEST_DIR}/${rt}" ] && continue
        case "$rt" in
            Achievement) content="Achievement:d=16,o=5,b=125:c6,e6,g6,c7,e7,g7" ;;
            Flutter)     content="Flutter:d=4,o=5,b=565:8d5,8e5,8f5,8g5,8f5,8e5,8d5" ;;
            GlitchHack)  content="GlitchHack:d=16,o=5,b=285:c,g,c6,p,b,p,a,p,g,p,4c" ;;
            ScaleTrill)  content="ScaleTrill:o=5,d=32,b=160,b=160:c,d,e,f,g,a,b,c6,b,a,g,f,e,d,c" ;;
            SideBeam)    content="SideBeam:d=16,o=5,b=565:b,f6,f6,b,f6,f6,b,f6,f6" ;;
            Warning)     content="Warning:d=4,o=5,b=180:a,8p,a,8p,a,8p,a" ;;
        esac
        printf "%s\n" "$content" > "${DEST_DIR}/${rt}"
    done
    skip_ask_ringtones=1
    PAYLOAD_SET_CONFIG "$CONFIG_NS" skip_ask_ringtones 1 >/dev/null 2>&1
    LOG green "Ringtones installed"
}

# ── Main menu (BluePine pattern: funcs_menu.sh:683-763) ───────────────────
# Cancel/Back at LIST_PICKER returns selnum=-1 (no-op in payload.sh dispatch).
# Only an explicit "Exit" pick triggers selnum=0.
main_menu() {
    [ "$mute" = "false" ] && led_safe MAGENTA

    local items=( "Status" "Quick Scan" "Text Waterfall" "Graphical Waterfall" \
                  "Channel Analysis" "Anomaly Detection" "Saved Sessions" \
                  "Install" "Settings" "About" "Exit" )
    local pick_str="\"SpecPine - Main Menu\""
    local i
    LOG blue "── SpecPine v${APP_VERSION} ──"
    for i in "${!items[@]}"; do
        pick_str="${pick_str} \"${items[$i]}\""
    done
    sleep 0.3
    local resp
    resp=$(eval "LIST_PICKER ${pick_str}")
    case "$resp" in
        "Status")              selnum=1  ;;
        "Quick Scan")          selnum=2  ;;
        "Text Waterfall")      selnum=3  ;;
        "Graphical Waterfall") selnum=4  ;;
        "Channel Analysis")    selnum=5  ;;
        "Anomaly Detection")   selnum=6  ;;
        "Saved Sessions")      selnum=7  ;;
        "Install")             selnum=8  ;;
        "Settings")            selnum=9  ;;
        "About")               selnum=10 ;;
        "Exit")                selnum=0  ;;
        *)                     selnum=-1 ;;   # cancelled/back → loop without exit
    esac
}

# ── Install / Repair / Uninstall sub-menu (OPTIONAL — system-wide install) ─
sub_menu_install() {
    while true; do
        show_ansi install
        LOG blue "── Install / Repair / Uninstall ──"
        LOG       "SpecPine bundles its own spectool_raw."
        LOG       "Install only if you also want it on PATH"
        LOG       "for other tools at /opt/spectools."
        if [ -x "${INSTALL_BIN}/spectool_raw" ]; then
            LOG green "System install : present at /opt/spectools"
        else
            LOG       "System install : not present"
        fi
        local resp
        resp=$(LIST_PICKER "Install Menu" "Install to /opt" "Repair" "Uninstall" "Back")
        case "$resp" in
            "Install to /opt") install_spectools;   return ;;
            "Repair")          repair_spectools;    return ;;
            "Uninstall")       uninstall_spectools; return ;;
            *)                 return ;;
        esac
    done
}

# ── Settings sub-menu ─────────────────────────────────────────────────────
sub_menu_settings() {
    while true; do
        settings_check
        show_ansi settings
        LOG blue "── Settings ──"
        LOG "Band: ${default_band}    Mode: ${default_mode}"
        LOG "Stall: ${stall_timeout}s   Restart: ${max_restarts}"
        LOG "Anom: ${anomaly_threshold_db}dB / ${anomaly_window} sweeps"
        LOG "Audio: ${mute_disp}   Loot: ${noloot_disp}   GPS: ${gps_disp}"
        WAIT_FOR_BUTTON_PRESS A
        local resp
        resp=$(LIST_PICKER "Settings" \
            "Default Band" "Default Mode" \
            "Stall Timeout" "Max Restarts" \
            "Anomaly Threshold" "Anomaly Window" \
            "Mute" "No-loot Mode" "GPS" \
            "Skip Ringtone Check" \
            "Diagnostics" \
            "Reset to Defaults" "Back")
        case "$resp" in
            "Default Band")        setting_default_band ;;
            "Default Mode")        setting_default_mode ;;
            "Stall Timeout")       setting_stall_timeout ;;
            "Max Restarts")        setting_max_restarts ;;
            "Anomaly Threshold")   setting_anomaly_threshold ;;
            "Anomaly Window")      setting_anomaly_window ;;
            "Mute")                setting_mute ;;
            "No-loot Mode")        setting_noloot ;;
            "GPS")                 setting_gps ;;
            "Skip Ringtone Check") setting_skip_ringtones ;;
            "Diagnostics")         sub_menu_diagnostics ;;
            "Reset to Defaults")   setting_reset_defaults ;;
            *)                     return ;;
        esac
        config_backup
    done
}

# ── Diagnostics submenu — exercises the "needs UI testing" items ──────────
sub_menu_diagnostics() {
    while true; do
        LOG blue "── Diagnostics ──"
        local r
        r=$(LIST_PICKER "Diagnostics" \
            "Test Button Watcher" \
            "Test Framebuffer" \
            "Test LIST_PICKER" \
            "Test Settings Persist" \
            "Test Bridge Dry-run" \
            "Back")
        case "$r" in
            "Test Button Watcher") diag_test_button_watcher ;;
            "Test Framebuffer")    diag_test_framebuffer ;;
            "Test LIST_PICKER")    diag_test_list_picker ;;
            "Test Settings Persist") diag_test_settings_persist ;;
            "Test Bridge Dry-run") diag_test_bridge_dryrun ;;
            *)                     return ;;
        esac
    done
}

diag_test_button_watcher() {
    LOG blue "── Button Watcher Test ──"
    LOG "Tap OK once, then long-press OK ≥0.8s,"
    LOG "then press Back to finish."
    start_evtest
    local seen_pause=0 seen_stop=0 deadline
    deadline=$(( $(date +%s) + 20 ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        check_cancel
        if is_btn_paused && [ "$seen_pause" -eq 0 ]; then
            LOG green "  ✓ pause event detected"
            seen_pause=1
            clear_btn_evt
        fi
        if is_btn_stopped; then
            LOG green "  ✓ stop event detected"
            seen_stop=1
            break
        fi
        sleep 0.3
    done
    killall evtest 2>/dev/null || true
    EVTEST_PID=""
    clear_btn_evt
    [ "$seen_pause" -eq 0 ] && LOG yellow "  ✗ no pause event (try tapping OK faster)"
    [ "$seen_stop"  -eq 0 ] && LOG yellow "  ✗ no stop event (try holding OK ≥0.8s)"
    [ "$seen_pause" -eq 1 ] && [ "$seen_stop" -eq 1 ] && LOG green "Button watcher: OK"
    show_menu_end_OK=2
}

diag_test_framebuffer() {
    LOG blue "── Framebuffer Test ──"
    if [ ! -e /dev/fb0 ]; then
        LOG red "  /dev/fb0 not present — skipped"
        show_menu_end_OK=2
        return
    fi
    if [ ! -x "${PAYLOAD_ROOT}/bin/specpine_splash.py" ]; then
        LOG yellow "  splash binary missing — skipped"
        show_menu_end_OK=2
        return
    fi
    LOG "  Playing 2.5s splash on /dev/fb0..."
    python3 "${PAYLOAD_ROOT}/bin/specpine_splash.py" 2>>"$LOG_FILE"
    sleep 0.3
    [ -e "$VTCON" ] && echo 1 > "$VTCON" 2>/dev/null || true
    LOG green "  Splash complete; LOG view should be restored"
    show_menu_end_OK=2
}

diag_test_list_picker() {
    LOG blue "── LIST_PICKER Test ──"
    local r
    r=$(LIST_PICKER "Pick anything" "Alpha" "Bravo" "Charlie")
    if [ -n "$r" ]; then
        LOG green "  Got response: '$r'"
    else
        LOG yellow "  Empty response (cancelled?)"
    fi
    show_menu_end_OK=2
}

diag_test_settings_persist() {
    LOG blue "── Settings Persist Test ──"
    silent_backup=1
    config_backup
    local key val miss=0
    for key in default_band default_mode stall_timeout max_restarts \
               anomaly_threshold_db anomaly_window mute noloot \
               gps_enabled skip_ask_ringtones selnum_main \
               total_scans total_anomalies app_version; do
        val=$(PAYLOAD_GET_CONFIG "$CONFIG_NS" "$key" 2>/dev/null)
        if [ -z "$val" ]; then
            LOG red "  ✗ ${key}: empty"
            miss=$((miss+1))
        else
            LOG green "  ✓ ${key} = ${val}"
        fi
    done
    [ "$miss" -eq 0 ] && LOG green "All keys persist OK" || LOG red "${miss} keys missing"
    show_menu_end_OK=2
}

diag_test_bridge_dryrun() {
    LOG blue "── Bridge Dry-run ──"
    if [ ! -x "$SPECTOOL_BIN" ]; then
        LOG red "  spectool_raw not installed — Run Install first"
        show_menu_end_OK=2
        return
    fi
    local d="/tmp/specpine_diag_$(date +%s)"
    mkdir -p "$d"
    rm -f "$EVENTS_FILE"
    LOG "  Spawning bridge for 3 s (will likely fail without Wi-Spy)..."
    if start_bridge "$d"; then
        LOG green "  Bridge stayed up for 6 s — Wi-Spy probably present"
        sleep 3
    else
        LOG yellow "  Bridge exited as expected (no Wi-Spy or stall)"
        LOG "  Reason: ${BRIDGE_FAIL_REASON:-(none captured)}"
    fi
    stop_bridge
    LOG "  Events captured:"
    if [ -s "$EVENTS_FILE" ]; then
        local n
        n=$(wc -l < "$EVENTS_FILE")
        LOG green "    ${n} JSONL lines in ${EVENTS_FILE}"
        head -3 "$EVENTS_FILE" | while IFS= read -r l; do LOG "    ${l:0:80}"; done
    else
        LOG yellow "    (no events file)"
    fi
    rm -rf "$d"
    show_menu_end_OK=2
}

setting_default_band() {
    local r; r=$(LIST_PICKER "Default Band" "Auto" "2.4 GHz" "5 GHz")
    case "$r" in
        "Auto")    default_band="auto" ;;
        "2.4 GHz") default_band="2.4" ;;
        "5 GHz")   default_band="5" ;;
    esac
}
setting_default_mode() {
    local r; r=$(LIST_PICKER "Default Mode" "Text" "Graphical")
    case "$r" in
        "Text")      default_mode="text" ;;
        "Graphical") default_mode="graphical" ;;
    esac
}
setting_stall_timeout() {
    local r; r=$(NUMBER_PICKER "Stall Timeout (s)" "$stall_timeout")
    [ -n "$r" ] && stall_timeout="$r"
}
setting_max_restarts() {
    local r; r=$(NUMBER_PICKER "Max Restarts" "$max_restarts")
    [ -n "$r" ] && max_restarts="$r"
}
setting_anomaly_threshold() {
    local r; r=$(NUMBER_PICKER "Anomaly Threshold (dB)" "$anomaly_threshold_db")
    [ -n "$r" ] && anomaly_threshold_db="$r"
}
setting_anomaly_window() {
    local r; r=$(NUMBER_PICKER "Anomaly Window (sweeps)" "$anomaly_window")
    [ -n "$r" ] && anomaly_window="$r"
}
setting_mute() {
    if [ "$mute" = "true" ]; then mute="false"; else mute="true"; fi
    LOG green "Mute: ${mute}"
}
setting_noloot() {
    if [ "$noloot" = "true" ]; then noloot="false"; else noloot="true"; fi
    LOG green "No-loot: ${noloot}"
}
setting_gps() {
    if [ "$gps_enabled" = "true" ]; then gps_enabled="false"; else gps_enabled="true"; fi
    LOG green "GPS: ${gps_enabled}"
}
setting_skip_ringtones() {
    if [ "$skip_ask_ringtones" -eq 1 ]; then skip_ask_ringtones=0; else skip_ask_ringtones=1; fi
    LOG green "Skip ringtone check: ${skip_ask_ringtones}"
}
setting_reset_defaults() {
    local resp
    resp=$(CONFIRMATION_DIALOG "Reset all settings to defaults?")
    [ "$resp" != "$DUCKYSCRIPT_USER_CONFIRMED" ] && return 0
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
    LOG green "Defaults restored"
}

# ── About ─────────────────────────────────────────────────────────────────
sub_menu_about() {
    show_ansi about
    LOG blue   "── About SpecPine ──"
    LOG green  "SpecPine v${APP_VERSION}"
    LOG       "RF spectrum analyser for the Hak5 Pager"
    LOG       "Backend: spectool_raw + Wi-Spy DBx"
    LOG       "Frontend: ASCII LOG + RGB565 framebuffer"
    LOG cyan  "------------- credits -------------------------"
    LOG       "BluePine (cncartist) — UX patterns, ringtones"
    LOG       "Kismet/spectools authors — driver code"
    LOG       "Error404-net — Pager port + SpecPine bundle"
    LOG       "WarGames (1983) — title-card inspiration"
    LOG blue   "================================================"
    show_menu_end_OK=2
}

# ── Saved sessions browser ────────────────────────────────────────────────
sub_menu_sessions() {
    show_ansi sessions
    while true; do
        local entries=()
        local d
        for d in "$LOOT_ROOT"/session_* "$TMP_LOOT_ROOT"/session_*; do
            [ -d "$d" ] && entries+=( "$(basename "$d")" )
        done
        if [ "${#entries[@]}" -eq 0 ]; then
            LOG yellow "No saved sessions yet"
            show_menu_end_OK=2
            return 0
        fi
        local pick_str="\"Saved Sessions\""
        for e in "${entries[@]}"; do pick_str="${pick_str} \"${e}\""; done
        pick_str="${pick_str} \"Back\""
        WAIT_FOR_BUTTON_PRESS A
        local resp
        resp=$(eval "LIST_PICKER ${pick_str}")
        [ "$resp" = "Back" ] || [ -z "$resp" ] && return 0

        local picked=""
        for e in "${entries[@]}"; do
            [ "$e" = "$resp" ] && picked="$e" && break
        done
        [ -z "$picked" ] && return 0

        local target=""
        [ -d "${LOOT_ROOT}/${picked}" ]     && target="${LOOT_ROOT}/${picked}"
        [ -d "${TMP_LOOT_ROOT}/${picked}" ] && target="${TMP_LOOT_ROOT}/${picked}"

        local action
        action=$(LIST_PICKER "$picked" "View Summary" "Replay" "Delete" "Back")
        case "$action" in
            "View Summary") session_view_summary "$target" ;;
            "Replay")       session_replay "$target" ;;
            "Delete")       session_delete "$target" ;;
            *) ;;
        esac
    done
}

session_view_summary() {
    local d="$1"
    LOG blue "------- $(basename "$d") -------"
    if [ -f "${d}/meta.json" ]; then
        while IFS= read -r line; do LOG "$line"; done < "${d}/meta.json"
    else
        LOG yellow "(no meta.json)"
    fi
    if [ -f "${d}/sweep_summary.csv" ]; then
        local rows
        rows=$(wc -l < "${d}/sweep_summary.csv" 2>/dev/null)
        LOG cyan "${rows} rows in sweep_summary.csv"
    fi
    if [ -f "${d}/anomaly_log.txt" ]; then
        local hits
        hits=$(grep -c '^ANOMALY' "${d}/anomaly_log.txt" 2>/dev/null || echo 0)
        LOG cyan "${hits} anomaly entries"
    fi
    LOG blue "----------------------------------"
    show_menu_end_OK=2
}

session_replay() {
    local d="$1"
    if [ ! -f "${d}/events.jsonl" ]; then
        LOG yellow "No events.jsonl in this session"
        show_menu_end_OK=2
        return 0
    fi
    LOG green "Replaying ASCII waterfall (Back to stop)"
    python3 "$RENDERER_ASCII_BIN" --events-file "${d}/events.jsonl" 2>/dev/null | \
        while IFS= read -r line; do LOG green "$line"; done
    show_menu_end_OK=2
}

session_delete() {
    local d="$1"
    local resp
    resp=$(CONFIRMATION_DIALOG "Delete $(basename "$d")?")
    if [ "$resp" = "$DUCKYSCRIPT_USER_CONFIRMED" ]; then
        rm -rf "$d"
        LOG green "Deleted"
    fi
}

# ── Pre-scan options dialog ───────────────────────────────────────────────
pre_scan_dialog() {
    if [ ! -x "$SPECTOOL_BIN" ]; then
        ERROR_DIALOG "spectool_raw not found at:
${SPECTOOL_BIN}

The payload should bundle its own — re-deploy
the SpecPine package."
        return 1
    fi

    local r
    r=$(LIST_PICKER "Band" "Auto" "2.4 GHz" "5 GHz" "Cancel")
    case "$r" in
        "Auto")    current_band="auto" ;;
        "2.4 GHz") current_band="2.4" ;;
        "5 GHz")   current_band="5" ;;
        *)         LOG yellow "Cancelled — returning to menu"; show_menu_end_OK=2; return 1 ;;
    esac

    local default_name
    default_name=$(date +%Y%m%d_%H%M%S)
    r=$(TEXT_PICKER "Session Name" "$default_name")
    if [ -z "$r" ]; then
        LOG yellow "Cancelled — returning to menu"
        show_menu_end_OK=2
        return 1
    fi
    current_session_name="$r"

    if [ "$noloot" = "true" ]; then
        current_save_loot="false"
        LOG yellow "No-loot mode: session will live in /tmp and be wiped on exit"
    else
        local s
        s=$(CONFIRMATION_DIALOG "Save loot to ${LOOT_ROOT}?")
        if [ "$s" = "$DUCKYSCRIPT_USER_CONFIRMED" ]; then
            current_save_loot="true"
        else
            current_save_loot="false"
        fi
    fi
    return 0
}
