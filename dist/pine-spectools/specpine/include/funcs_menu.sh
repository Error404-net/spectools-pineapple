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

# ── Main menu dispatcher ───────────────────────────────────────────────────
# Tries the framebuffer HUD first (specpine_hud.py) so the most commonly
# seen screen is visibly, unmistakably SpecPine instead of the firmware's
# stock LIST_PICKER chrome. Falls back to the legacy LIST_PICKER menu on
# any HUD failure (missing /dev/fb0, missing evtest, bad output, etc.) so
# the user is never stranded with a blank or frozen screen.
main_menu() {
    EXIT_PRECONFIRMED=0
    if [ -x "$HUD_BIN" ] || [ -f "$HUD_BIN" ]; then
        main_menu_hud
        [ "$selnum" != "__HUD_FAIL__" ] && return 0
        LOG yellow "HUD unavailable — falling back to standard menu"
        if [ -s /tmp/specpine_hud_debug.log ]; then
            echo "[hud debug log follows]" >> "$LOG_FILE"
            tail -30 /tmp/specpine_hud_debug.log >> "$LOG_FILE" 2>/dev/null || true
        fi
        pineapple_ensure_running
    fi
    main_menu_legacy
}

# ── Framebuffer HUD main menu ──────────────────────────────────────────────
main_menu_hud() {
    [ "$mute" = "false" ] && led_safe MAGENTA
    local out ec
    out=$(python3 "$HUD_BIN" --app-version "$APP_VERSION" 2>>"$LOG_FILE")
    ec=$?
    case "$ec" in
        0)
            case "$out" in
                ''|*[!0-9]*)
                    selnum="__HUD_FAIL__"
                    ;;
                *)
                    selnum="$out"
                    [ "$selnum" -eq 0 ] && EXIT_PRECONFIRMED=1
                    ;;
            esac
            ;;
        *)
            selnum="__HUD_FAIL__"
            ;;
    esac
}

# ── Legacy LIST_PICKER main menu (BluePine pattern: funcs_menu.sh:683-763) ─
# Cancel/Back at LIST_PICKER returns selnum=-1 (no-op in payload.sh dispatch).
# Only an explicit "Exit" pick triggers selnum=0.
main_menu_legacy() {
    [ "$mute" = "false" ] && led_safe MAGENTA

    local items=( "2.4GHz Waterfall" "5GHz Waterfall" "NFO" )
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
        "2.4GHz Waterfall")  selnum=2 ;;
        "5GHz Waterfall")    selnum=3 ;;
        "NFO")               selnum=7 ;;
        *)                   selnum=-1 ;;   # Back/cancel → payload.sh prompts to exit
    esac
}

# ── NFO screen ────────────────────────────────────────────────────────────
sub_menu_nfo() {
    local wispy_line freq_line mute_val noloot_val

    if [ "$WISPY_PRESENT" = "true" ]; then
        wispy_line="${WISPY_DEVICE_NAME:-Wi-Spy DBx}"
        if [ -n "$FREQ_START_KHZ" ] && [ -n "$FREQ_END_KHZ" ]; then
            freq_line="$(( FREQ_START_KHZ / 1000 ))-$(( FREQ_END_KHZ / 1000 )) MHz"
        else
            freq_line="?"
        fi
    else
        wispy_line="--"
        freq_line="--"
    fi
    [ "$mute"   = "true" ] && mute_val="on"  || mute_val="off"
    [ "$noloot" = "true" ] && noloot_val="on" || noloot_val="off"

    LOG cyan   " ░░░░░░░░░░░░░░░░░░░░░░░░░░"
    LOG yellow "      S P E C P I N E"
    LOG cyan   "   RF SPECTRUM ANALYZER"
    LOG        "   Hak5 Pineapple Pager"
    LOG yellow "      v${APP_VERSION} // error404"
    LOG cyan   " ░░░░░░░░░░░░░░░░░░░░░░░░░░"
    LOG cyan   " ──────────────────────────"
    LOG blue   "  [ HARDWARE ]"
    if [ "$WISPY_PRESENT" = "true" ]; then
        LOG green  "  Wi-Spy .. ONLINE"
    else
        LOG red    "  Wi-Spy .. NOT FOUND"
    fi
    LOG        "  Device .. ${wispy_line}"
    LOG        "  Range ... ${freq_line}"
    LOG cyan   " ──────────────────────────"
    LOG blue   "  [ CONFIG ]"
    LOG        "  Stall ....... ${stall_timeout}s"
    LOG        "  Restarts .... ${max_restarts}"
    LOG        "  Mute ........ ${mute_val}"
    LOG        "  No-loot ..... ${noloot_val}"
    LOG cyan   " ──────────────────────────"
    LOG yellow "  [ GREETZ ]"
    LOG        "  :: hak5 community"
    LOG        "  :: spectools / caljorden"
    LOG        "  :: spectools / dragorn"
    LOG        "  :: ArmoredPixie"
    LOG cyan   " ░░░░░░░░░░░░░░░░░░░░░░░░░░"
    show_menu_end_OK=2
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
    current_session_name=""
    if [ "$noloot" = "true" ]; then
        current_save_loot="false"
    else
        current_save_loot="true"
    fi
    return 0
}
