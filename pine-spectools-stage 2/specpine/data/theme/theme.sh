# theme.sh — SpecPine theme tokens and LOG colour wrappers.
# Sourced by funcs_main.sh. Pure shell; no side-effects beyond defining
# variables and functions. All existing LOG green/red/etc. calls remain
# valid; the LOG_* wrappers below are the recommended path for new code
# so a future palette swap re-skins everything in one place.

# ── LOG colour tokens (Pager firmware accepts: blue cyan green magenta
#    red white yellow). These are the SpecPine canonical mappings. ──
THEME_TITLE_COLOR=blue       # section headers, splash bars
THEME_GOOD=green             # success / nominal output
THEME_WARN=yellow            # cautionary / borderline
THEME_ALERT=red              # error / strong RF / anomaly
THEME_HINT=cyan              # secondary / "Press OK" prompts
THEME_BRAND=magenta          # SpecPine identity touches

# ── Framebuffer RGB tuples (used by generate_theme_fb.py and any future
#    on-device .fb generators). Matches the WarGames CRT phosphor-green
#    palette plus a Hackers '95 amber accent. ──
THEME_FB_BG="8,12,8"
THEME_FB_BG_DARK="3,6,3"
THEME_FB_GREEN="0,220,100"
THEME_FB_GREEN_D="0,140,60"
THEME_FB_GREEN_DD="0,70,30"
THEME_FB_AMBER="255,180,40"
THEME_FB_RED="220,50,60"
THEME_FB_CYAN="60,220,220"
THEME_FB_WHITE="220,255,220"

# ── LOG wrappers ──
# Use these when authoring new menus/screens. Existing LOG calls are
# unaffected; future themes can override the THEME_* tokens above and
# every wrapped call updates simultaneously.
LOG_TITLE() { LOG "$THEME_TITLE_COLOR" "$*"; }
LOG_GOOD()  { LOG "$THEME_GOOD"        "$*"; }
LOG_WARN()  { LOG "$THEME_WARN"        "$*"; }
LOG_ALERT() { LOG "$THEME_ALERT"       "$*"; }
LOG_HINT()  { LOG "$THEME_HINT"        "$*"; }
LOG_BRAND() { LOG "$THEME_BRAND"       "$*"; }

# ── Section divider — consistent visual rhythm across screens ──
LOG_DIVIDER() {
    local label="${1:-}"
    if [ -n "$label" ]; then
        LOG "$THEME_TITLE_COLOR" "── ${label} ──"
    else
        LOG "$THEME_TITLE_COLOR" "──────────────────────────────"
    fi
}
