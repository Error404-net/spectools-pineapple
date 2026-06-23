# funcs_scan.sh — SpecPine scan modes (5)
# (sourced by payload.sh; uses globals defined there)

# ── Quick Scan: ~3 s, parse last sweep stats ──────────────────────────────
quick_scan() {
    make_session_dir "${current_session_name:-quick}"
    mark_session_started "$SESSION_DIR" "quick"
    show_ansi quick_scan
    LOG blue "── Quick Scan ──"
    led_safe R 255 G 165 B 0
    ringtone_play "GlitchHack"
    if ! start_bridge "$SESSION_DIR"; then
        mark_session_failed "$SESSION_DIR" "quick"
        LOG yellow "Session log: $SESSION_DIR"
        show_menu_end_OK=2
        return 1
    fi
    sleep 3
    stop_bridge

    local last
    last=$(grep '"type":"sweep"' "$EVENTS_FILE" 2>/dev/null | tail -1)
    if [ -z "$last" ]; then
        led_safe R 255 G 255 B 0
        LOG yellow "No sweep data captured"
        mark_session_failed "$SESSION_DIR" "quick" "no sweep events received"
        show_menu_end_OK=2
        return 1
    fi
    local stats mn mx av
    stats=$(parse_sweep_stats "$last")
    set -- $stats; mn="$1"; mx="$2"; av="$3"

    led_safe R 0 G 255 B 0
    LOG green "Quick Scan complete"
    LOG       "  band: ${current_band}"
    LOG       "  min : ${mn} dBm"
    LOG       "  max : ${mx} dBm"
    LOG       "  avg : ${av} dBm"
    if [ "$current_save_loot" = "true" ]; then
        cp "$EVENTS_FILE" "${SESSION_DIR}/events.jsonl" 2>/dev/null || true
    fi
    mark_session_success "$SESSION_DIR" "quick"
    ringtone_play "ScaleTrill"
    total_scans=$((total_scans+1))
    show_menu_end_OK=2
}

# ── Text Waterfall (BluePine-flavored) ────────────────────────────────────
text_waterfall() {
    make_session_dir "${current_session_name:-text}"
    mark_session_started "$SESSION_DIR" "text"
    show_ansi text_waterfall
    LOG blue "── Text Waterfall ──"
    if ! start_bridge "$SESSION_DIR"; then
        mark_session_failed "$SESSION_DIR" "text"
        LOG yellow "Session log: $SESSION_DIR"
        show_menu_end_OK=2
        return 1
    fi
    start_evtest
    ringtone_play "GlitchHack"
    led_safe R 0 G 255 B 0
    LOG green "Scanning - tap OK to pause, hold OK ≥0.8s to stop"
    LOG       "______________________________________________"

    # Process substitution keeps the while-loop in the parent shell so
    # `break` propagates and total_scans / SESSION_DIR mutations stick.
    while IFS= read -r wfline; do
        check_cancel
        if is_btn_stopped; then break; fi
        if is_btn_paused; then
            LOG yellow "[paused] tap OK to resume"
            while is_btn_paused; do
                sleep 0.4
                check_cancel
                is_btn_stopped && break 2
            done
            LOG green "[resumed]"
        fi
        # Renderer prefixes sweep rows with R:/Y:/G: based on peak dBm.
        # Strip + route to the matching LOG colour. Headers stay un-tagged.
        case "$wfline" in
            R:*) LOG red    "${wfline#R:}" ;;
            Y:*) LOG yellow "${wfline#Y:}" ;;
            G:*) LOG green  "${wfline#G:}" ;;
            *)   LOG green  "$wfline"      ;;
        esac
    done < <(python3 "$RENDERER_ASCII_BIN" \
                --events-file "$EVENTS_FILE" \
                --banner "Hold OK ≥0.8s stop. Loot:${SESSION_DIR##*/}" \
                --follow \
                --poll-interval 0.05 \
                2>/dev/null)

    stop_bridge
    killall evtest 2>/dev/null || true
    EVTEST_PID=""
    clear_btn_evt

    if [ "$current_save_loot" = "true" ] && [ -f "$EVENTS_FILE" ]; then
        cp "$EVENTS_FILE" "${SESSION_DIR}/events.jsonl" 2>/dev/null || true
    fi
    mark_session_success "$SESSION_DIR" "text"
    led_safe R 0 G 0 B 128
    LOG       "──────────────────────────────────────────"
    LOG green "Waterfall stopped"
    total_scans=$((total_scans+1))
    show_menu_end_OK=2
}

# ── Graphical Waterfall (RGB565 framebuffer) ──────────────────────────────
graphical_waterfall() {
    if [ ! -e /dev/fb0 ]; then
        ERROR_DIALOG "/dev/fb0 not available on this device."
        show_menu_end_OK=2
        return 1
    fi
    # Normalize the "auto" sentinel to a real band ("2.4") right away.
    # band_to_range_index() already treats auto==2.4 for the actual device
    # sweep, but the LEFT/RIGHT toggle below only ever compares against the
    # literal string "5" ("if current_band = 5 then 2.4 else 5") -- left as
    # "auto", that comparison still resolves correctly on the very first
    # press, but every status line and the renderer's on-screen state used
    # "auto" instead of the band actually being swept, which is what made
    # "Auto" look like it wasn't really tracking/switching bands. Pin it to
    # a concrete value up front so display and toggle logic agree.
    [ "$current_band" = "auto" ] && current_band="2.4"
    make_session_dir "${current_session_name:-fb}"
    mark_session_started "$SESSION_DIR" "graphical"
    show_ansi graphical_waterfall
    LOG blue "── Graphical Waterfall ──"
    LOG       "Display takes over. Hold OK ≥0.8s to stop."
    if ! start_bridge "$SESSION_DIR" "$current_band"; then
        mark_session_failed "$SESSION_DIR" "graphical"
        LOG yellow "Session log: $SESSION_DIR"
        show_menu_end_OK=2
        return 1
    fi
    start_evtest
    ringtone_play "GlitchHack"
    led_safe R 0 G 255 B 0
    LOG cyan  "LEFT/RIGHT: switch 2.4/5GHz   UP+DOWN: screenshot"

    python3 "$RENDERER_FB_BIN" \
        --events-file "$EVENTS_FILE" \
        --follow \
        --poll-interval 0.05 \
        --fps 6 \
        >> "$LOG_FILE" 2>&1 &
    RENDERER_PID=$!

    clear_dpad_evt
    clear_screenshot_evt
    local shot_n=0

    # Stall watchdog: if EVENTS_FILE stops growing (bridge died, USB hiccup,
    # device went unresponsive mid-sweep) the renderer just sits there idle
    # forever with pineapple still SIGSTOPped -- a silent, total UI freeze
    # indistinguishable from a crash. Detect via file size, not wall clock,
    # so a slow-but-alive feed never false-trips this.
    local last_evt_size=-1 last_evt_growth stall_limit
    last_evt_growth=$(date +%s)
    stall_limit=$(( stall_timeout * 3 ))
    [ "$stall_limit" -lt 15 ] && stall_limit=15

    while kill -0 "$RENDERER_PID" 2>/dev/null; do
        check_dpad
        check_cancel
        if is_btn_stopped; then
            kill "$RENDERER_PID" 2>/dev/null || true
            break
        fi

        local cur_evt_size
        cur_evt_size=$(wc -c < "$EVENTS_FILE" 2>/dev/null || echo -1)
        if [ "$cur_evt_size" != "$last_evt_size" ]; then
            last_evt_size="$cur_evt_size"
            last_evt_growth=$(date +%s)
        elif [ $(( $(date +%s) - last_evt_growth )) -ge "$stall_limit" ]; then
            LOG red "Feed stalled (${stall_limit}s no data) -- recovering"
            stop_bridge
            if start_bridge "$SESSION_DIR" "$current_band"; then
                kill -USR1 "$RENDERER_PID" 2>/dev/null || true
                LOG yellow "Feed restarted: ${current_band} GHz"
                last_evt_size=-1
                last_evt_growth=$(date +%s)
            else
                LOG red "Feed recovery failed -- stopping scan: ${BRIDGE_FAIL_REASON:-unknown}"
                kill "$RENDERER_PID" 2>/dev/null || true
                break
            fi
        fi

        if is_dpad_left || is_dpad_right; then
            local new_band old_band
            old_band="$current_band"
            if [ "$current_band" = "5" ]; then
                new_band="2.4"
            else
                new_band="5"
            fi
            clear_dpad_evt
            LOG yellow "Switching band: ${current_band} → ${new_band}"
            stop_bridge
            current_band="$new_band"
            if start_bridge "$SESSION_DIR" "$current_band"; then
                kill -USR1 "$RENDERER_PID" 2>/dev/null || true
                LOG green "Now scanning: ${current_band} GHz"
            else
                # Band switch failed (e.g. Wi-Spy busy re-tuning). start_bridge
                # already rm -f'd EVENTS_FILE before trying, so the renderer's
                # open file handle now points at a deleted inode -- readline()
                # would return EOF forever, the display would never update
                # again, and pineapple stays SIGSTOPped indefinitely (looks
                # exactly like a full freeze). Fall back to restarting the
                # OLD band so the feed recovers instead of dying silently.
                LOG red "Band switch failed: ${BRIDGE_FAIL_REASON:-unknown}"
                current_band="$old_band"
                if start_bridge "$SESSION_DIR" "$current_band"; then
                    kill -USR1 "$RENDERER_PID" 2>/dev/null || true
                    LOG yellow "Reverted to: ${current_band} GHz"
                else
                    LOG red "Recovery failed too -- stopping scan: ${BRIDGE_FAIL_REASON:-unknown}"
                    kill "$RENDERER_PID" 2>/dev/null || true
                    break
                fi
            fi
        fi

        if is_screenshot_requested; then
            clear_screenshot_evt
            shot_n=$((shot_n+1))
            local shot_path="${SESSION_DIR}/screenshot_$(date +%Y%m%d_%H%M%S)_${shot_n}.bmp"
            if python3 "$FB_SCREENSHOT_BIN" "$shot_path" >> "$LOG_FILE" 2>&1; then
                LOG green "Screenshot saved: ${shot_path##*/}"
                ringtone_play "Achievement"
            else
                LOG red "Screenshot failed (see log)"
            fi
        fi

        sleep 0.15
    done
    wait "$RENDERER_PID" 2>/dev/null
    RENDERER_PID=""
    pineapple_ensure_running   # belt-and-suspenders: renderer's own SIGCONT may not have fired

    stop_bridge
    killall evtest 2>/dev/null || true
    EVTEST_PID=""
    clear_btn_evt
    clear_dpad_evt
    clear_screenshot_evt

    if [ "$current_save_loot" = "true" ] && [ -f "$EVENTS_FILE" ]; then
        cp "$EVENTS_FILE" "${SESSION_DIR}/events.jsonl" 2>/dev/null || true
    fi
    mark_session_success "$SESSION_DIR" "graphical"
    led_safe R 0 G 0 B 128
    LOG green "Graphical waterfall stopped"
    total_scans=$((total_scans+1))
    show_menu_end_OK=2
}

# ── Channel Analysis (Wi-Fi 2.4 / 5 GHz utilization) ──────────────────────
channel_analysis() {
    make_session_dir "${current_session_name:-channel}"
    mark_session_started "$SESSION_DIR" "channel"
    show_ansi channel_analysis
    LOG blue "── Channel Analysis ──"
    local dur
    dur=$(NUMBER_PICKER "Capture duration (s)" "10")
    [ -z "$dur" ] && dur=10
    LOG       "Capturing ${dur} seconds for band: ${current_band}"

    if ! start_bridge "$SESSION_DIR"; then
        mark_session_failed "$SESSION_DIR" "channel"
        LOG yellow "Session log: $SESSION_DIR"
        show_menu_end_OK=2
        return 1
    fi
    start_evtest
    ringtone_play "GlitchHack"
    led_safe R 0 G 0 B 255

    local deadline=$(( $(date +%s) + dur ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        check_cancel
        if is_btn_stopped; then break; fi
        sleep 0.5
    done
    stop_bridge
    killall evtest 2>/dev/null || true
    EVTEST_PID=""
    clear_btn_evt

    LOG       "Computing channel utilization..."

    SPECPINE_EVENTS="$EVENTS_FILE" \
    SPECPINE_BAND="$current_band" \
    SPECPINE_OUT="${SESSION_DIR}/channel_report.txt" \
    python3 - <<'PYEOF' >/dev/null 2>&1
import os, json
from collections import defaultdict

EVENTS = os.environ["SPECPINE_EVENTS"]
BAND   = os.environ["SPECPINE_BAND"]
OUT    = os.environ["SPECPINE_OUT"]
THR    = -75.0   # dBm threshold for "busy"

ch24 = [(n, 2412 + (n-1)*5) for n in range(1, 12)]
ch5  = [(n, 5000 + n*5) for n in range(36, 166, 4)]

if BAND == "2.4":
    channels = ch24
elif BAND == "5":
    channels = ch5
else:
    channels = ch24 + ch5

cfg = None
sweeps = []
try:
    with open(EVENTS) as f:
        for line in f:
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("type") == "device_config" and cfg is None:
                cfg = e
            elif e.get("type") == "sweep":
                sweeps.append(e)
except FileNotFoundError:
    pass

with open(OUT, "w") as out:
    if not cfg or not sweeps:
        out.write("No data captured\n")
    else:
        fs = float(cfg.get("freq_start_khz", 0))
        fe = float(cfg.get("freq_end_khz",   0))
        nb = int(cfg.get("bin_count", 1))
        if nb < 1 or fe <= fs:
            out.write("Bad device_config\n")
        else:
            step = (fe - fs) / nb
            stats = defaultdict(lambda: {"sum":0.0, "n":0, "max":-200.0, "busy":0})
            n_sweeps = len(sweeps)
            for sw in sweeps:
                bins = sw.get("rssi_bins") or []
                if not bins:
                    continue
                for ch_num, ch_mhz in channels:
                    centre_khz = ch_mhz * 1000
                    if centre_khz < fs or centre_khz > fe:
                        continue
                    idx = int((centre_khz - fs) / step)
                    if 0 <= idx < len(bins):
                        v = float(bins[idx])
                        s = stats[ch_num]
                        s["sum"] += v
                        s["n"]   += 1
                        if v > s["max"]: s["max"] = v
                        if v > THR:      s["busy"] += 1
            rows = []
            for ch_num, _ in channels:
                s = stats[ch_num]
                if s["n"] == 0: continue
                avg  = s["sum"] / s["n"]
                util = 100.0 * s["busy"] / max(1, n_sweeps)
                rows.append((ch_num, avg, s["max"], util))
            rows.sort(key=lambda r: r[3], reverse=True)
            out.write(f"# Channels for band={BAND}, sweeps={n_sweeps}\n")
            out.write(f"{'Ch':>4} {'avg':>7} {'max':>7} {'util%':>7}\n")
            for ch, avg, mx, util in rows:
                out.write(f"{ch:>4} {avg:>7.1f} {mx:>7.1f} {util:>7.1f}\n")
PYEOF

    if [ -s "${SESSION_DIR}/channel_report.txt" ]; then
        while IFS= read -r row; do LOG green "$row"; done < "${SESSION_DIR}/channel_report.txt"
    else
        LOG yellow "No channels in band, or capture empty"
    fi

    if [ "$current_save_loot" = "true" ] && [ -f "$EVENTS_FILE" ]; then
        cp "$EVENTS_FILE" "${SESSION_DIR}/events.jsonl" 2>/dev/null || true
    fi
    mark_session_success "$SESSION_DIR" "channel"
    led_safe R 0 G 0 B 128
    ringtone_play "ScaleTrill"
    total_scans=$((total_scans+1))
    show_menu_end_OK=2
}

# ── Anomaly / Jammer Detection ────────────────────────────────────────────
anomaly_detection() {
    make_session_dir "${current_session_name:-anomaly}"
    mark_session_started "$SESSION_DIR" "anomaly"
    show_ansi anomaly
    LOG blue "── Anomaly Detection ──"
    LOG       "Watching for sudden RSSI spikes (Δ > ${anomaly_threshold_db} dB)"
    if ! start_bridge "$SESSION_DIR"; then
        mark_session_failed "$SESSION_DIR" "anomaly"
        LOG yellow "Session log: $SESSION_DIR"
        show_menu_end_OK=2
        return 1
    fi
    start_evtest
    ringtone_play "GlitchHack"
    led_safe R 0 G 255 B 255
    LOG green "Hold OK ≥0.8s to stop"
    LOG       "_____________________________________________"

    export SPECPINE_EVENTS="$EVENTS_FILE"
    export SPECPINE_BTN="$BTN_EVT_FILE"
    export SPECPINE_THR="$anomaly_threshold_db"
    export SPECPINE_WIN="$anomaly_window"

    while IFS= read -r line; do
        if [ "${line:0:7}" = "ANOMALY" ]; then
            led_safe R 255 G 0 B 0
            ringtone_play "Warning"
            LOG red "$line"
            echo "$line" >> "${SESSION_DIR}/anomaly_log.txt"
            local g
            g=$(gps_get_wrapper)
            echo "  gps=${g}" >> "${SESSION_DIR}/anomaly_log.txt"
            total_anomalies=$((total_anomalies+1))
            sleep 0.5
            led_safe R 0 G 255 B 255
        fi
        check_cancel
        if is_btn_stopped; then break; fi
    done < <(python3 - <<'PYEOF'
import os, json, time, sys, collections
EVENTS = os.environ["SPECPINE_EVENTS"]
BTN    = os.environ["SPECPINE_BTN"]
THR    = float(os.environ.get("SPECPINE_THR", "15"))
WIN    = int(os.environ.get("SPECPINE_WIN", "10"))

baseline = collections.deque(maxlen=WIN)
try:
    fh = open(EVENTS, "r")
except FileNotFoundError:
    sys.exit(0)
fh.seek(0, 2)
while True:
    if os.path.exists(BTN):
        try:
            v = open(BTN).read().strip()
            if v == "stop":
                break
        except Exception:
            pass
    line = fh.readline()
    if not line:
        time.sleep(0.05)
        continue
    try:
        e = json.loads(line)
    except Exception:
        continue
    if e.get("type") != "sweep":
        continue
    stats = e.get("stats") or {}
    mx = stats.get("max")
    if mx is None:
        continue
    if len(baseline) == WIN:
        avg = sum(baseline) / WIN
        delta = float(mx) - avg
        if delta >= THR:
            ts = e.get("timestamp", "")
            print(f"ANOMALY {ts} max={mx} baseline={avg:.1f} delta={delta:.1f}", flush=True)
    baseline.append(float(mx))
PYEOF
)

    stop_bridge
    killall evtest 2>/dev/null || true
    EVTEST_PID=""
    clear_btn_evt

    if [ "$current_save_loot" = "true" ] && [ -f "$EVENTS_FILE" ]; then
        cp "$EVENTS_FILE" "${SESSION_DIR}/events.jsonl" 2>/dev/null || true
    fi
    mark_session_success "$SESSION_DIR" "anomaly"
    LOG       "──────────────────────────────────────────"
    if [ -f "${SESSION_DIR}/anomaly_log.txt" ]; then
        local hits
        hits=$(grep -c '^ANOMALY' "${SESSION_DIR}/anomaly_log.txt")
        LOG green "Anomalies in this session: ${hits}"
    else
        LOG green "No anomalies detected"
    fi
    led_safe R 0 G 0 B 128
    total_scans=$((total_scans+1))
    show_menu_end_OK=2
}
