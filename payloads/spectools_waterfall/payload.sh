#!/bin/bash
# Title: Spectools Waterfall
# Description: Live RF waterfall and spectrum view from Spectools devices
# Author: Codex
# Category: reconnaissance
# Version: 0.1

set -u

PAYLOAD_ROOT="/root/payloads/user/reconnaissance/spectools_waterfall"
BRIDGE_BIN="${PAYLOAD_ROOT}/bin/spectools_bridge.py"
RENDER_BIN="${PAYLOAD_ROOT}/bin/spectools_render_tui.py"
CONFIG_FILE="${PAYLOAD_ROOT}/config/spectools_bridge.conf"

LOCK_FILE="/tmp/spectools_waterfall.lock"
PID_FILE="/tmp/spectools_waterfall.pid"
LOG_FILE="/tmp/spectools_waterfall.log"
EVENTS_FILE="/tmp/spectools_bridge_events.jsonl"
LOOT_ROOT="/root/loot/spectools_waterfall"
SESSION_TS="$(date +%Y%m%d_%H%M%S)"
SESSION_DIR="${LOOT_ROOT}/session_${SESSION_TS}"

SOURCE_MODE="usb"
SOURCE_COMMAND="spectool_raw"
MODE="waterfall"
BRIDGE_PID=""
RENDER_PID=""

log_msg() {
	if command -v LOG >/dev/null 2>&1; then
		LOG "$*"
	else
		echo "$*"
	fi
	echo "[$(date -Iseconds)] $*" >> "$LOG_FILE"
}

led_state() {
	if command -v LED >/dev/null 2>&1; then
		LED "$1"
	fi
}

dialog_msg() {
	if command -v DIALOG >/dev/null 2>&1; then
		DIALOG "$*"
	else
		log_msg "$*"
	fi
}

load_config() {
	[ -f "$CONFIG_FILE" ] && . "$CONFIG_FILE"
}

ensure_singleton() {
	if [ -f "$LOCK_FILE" ] || [ -f "$PID_FILE" ]; then
		OLDPID=""
		[ -f "$PID_FILE" ] && OLDPID="$(cat "$PID_FILE" 2>/dev/null)"
		if [ -n "$OLDPID" ] && kill -0 "$OLDPID" 2>/dev/null; then
			dialog_msg "Spectools Waterfall already running (pid ${OLDPID})"
			exit 1
		fi
		log_msg "Removing stale lock/pid files"
		rm -f "$LOCK_FILE" "$PID_FILE"
	fi
	touch "$LOCK_FILE"
	echo $$ > "$PID_FILE"
}

cleanup() {
	led_state FINISH
	[ -n "$RENDER_PID" ] && kill "$RENDER_PID" 2>/dev/null || true
	[ -n "$BRIDGE_PID" ] && kill "$BRIDGE_PID" 2>/dev/null || true
	pkill -f "spectools_bridge.py" 2>/dev/null || true
	rm -f "$LOCK_FILE" "$PID_FILE"
}
trap cleanup EXIT INT TERM

preflight() {
	if [ ! -x "$BRIDGE_BIN" ]; then
		led_state FAIL
		dialog_msg "Bridge missing: $BRIDGE_BIN"
		exit 1
	fi
	if [ ! -x "$RENDER_BIN" ]; then
		led_state FAIL
		dialog_msg "Renderer missing: $RENDER_BIN"
		exit 1
	fi
	mkdir -p "$SESSION_DIR"
	: > "$LOG_FILE"
	log_msg "Session: ${SESSION_DIR}"
}

pick_source() {
	if command -v NUMBER_PICKER >/dev/null 2>&1; then
		choice="$(NUMBER_PICKER 'Source: 0=USB local, 1=net host' 0)"
	else
		choice=0
	fi
	if [ "$choice" = "1" ]; then
		SOURCE_MODE="net"
		SOURCE_COMMAND="spectool_raw --connect 127.0.0.1:30569"
	else
		SOURCE_MODE="usb"
		SOURCE_COMMAND="spectool_raw"
	fi
	log_msg "Selected source mode: ${SOURCE_MODE}"
}

start_scan() {
	led_state ATTACK
	log_msg "Starting bridge"
	"$BRIDGE_BIN" \
		--input-command "$SOURCE_COMMAND" \
		--events-file "$EVENTS_FILE" \
		--export-dir "$SESSION_DIR" >> "$LOG_FILE" 2>&1 &
	BRIDGE_PID=$!
	sleep 1
	if ! kill -0 "$BRIDGE_PID" 2>/dev/null; then
		led_state FAIL
		dialog_msg "Bridge failed to start"
		return 1
	fi

	log_msg "Bridge started pid=${BRIDGE_PID}; starting renderer mode=${MODE}"
	"$RENDER_BIN" --input-file "$EVENTS_FILE" --snapshot-dir "$SESSION_DIR" >> "$LOG_FILE" 2>&1 &
	RENDER_PID=$!
	wait "$RENDER_PID"
	RENDER_PID=""
	return 0
}

stop_scan() {
	log_msg "Stopping scan"
	[ -n "$RENDER_PID" ] && kill "$RENDER_PID" 2>/dev/null || true
	[ -n "$BRIDGE_PID" ] && kill "$BRIDGE_PID" 2>/dev/null || true
	RENDER_PID=""
	BRIDGE_PID=""
	led_state SETUP
}

show_summary() {
	if compgen -G "$SESSION_DIR/*.summary.csv" > /dev/null; then
		tail -n 5 "$SESSION_DIR"/*.summary.csv | while read -r line; do log_msg "$line"; done
	else
		log_msg "No summary available yet"
	fi
}

main_loop() {
	while true; do
		log_msg "A=start B=exit C=mode"
		if command -v WAIT_FOR_BUTTON >/dev/null 2>&1; then
			btn="$(WAIT_FOR_BUTTON)"
		else
			read -r -p "[a]start [b]exit [c]mode [s]summary > " btn
		fi
		case "$btn" in
			A|a)
				start_scan || { dialog_msg "Source failed: retry/change source/exit"; }
				stop_scan
				;;
			B|b)
				break
				;;
			C|c)
				if [ "$MODE" = "waterfall" ]; then
					MODE="stats"
				elif [ "$MODE" = "stats" ]; then
					MODE="peak-hold"
				else
					MODE="waterfall"
				fi
				log_msg "Mode changed: ${MODE}"
				;;
			S|s)
				show_summary
				;;
			*)
				log_msg "Unknown input: ${btn}"
				;;
		esac
	done
}

load_config
ensure_singleton
preflight
pick_source
led_state SETUP
main_loop
