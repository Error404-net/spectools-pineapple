# SpecPine — current known bugs

Draft for a GitHub issue / internal tracker. Grouped by area, with severity,
repro environment, and what's already been tried.

---

## 1. Custom framebuffer screens (HUD menu + graphical waterfall) fail to draw

**Severity: high — this is the main blocker.**

`specpine_hud.py` (custom main menu) falls back to the firmware's stock
`LIST_PICKER` menu with a "HUD unavailable — falling back to standard menu"
message, instead of drawing its own screen. Confirmed on:

- Physical Pager hardware, via real button presses.
- Virtual Pager (web UI), driving it through the simulator's own buttons.

Same failure, same message, in both environments. The graphical waterfall
(`spectools_waterfall_fb.py`) is reported unavailable too — on Virtual Pager
specifically, only the plain payload LOG screen shows, never the graphical
takeover.

**Mechanism in use (undocumented by Hak5):** `SIGSTOP` the `/pineapple/pineapple`
process, write RGB565 frames directly to `/dev/fb0`, `SIGCONT` on exit.
`/sys/class/vtconsole/vtcon1` doesn't exist on this firmware (only `vtcon0`),
so vtcon-unbind tricks don't apply here.

**Open questions (also drafted as a Hak5 support request,
`docs/hak5-support-question.md`):**
- Does Virtual Pager mirror raw `/dev/fb0`, or does it mirror `pineapple`'s
  own internal state? If the latter, a payload writing directly to `/dev/fb0`
  while `pineapple` is stopped would never show up there even if the physical
  screen updated correctly — meaning physical and Virtual Pager testing may
  not exercise the same code path at all.
- Is there an officially supported draw-to-screen API, or is SIGSTOP+raw-write
  the only mechanism, full stop?

**Status:** unresolved. Need a diagnostic pass capturing `$LOG_FILE` output
from `specpine_hud.py`'s stderr during a failed run to see *which* check is
failing (missing `/dev/fb0`, missing `evtest`, bad output format, pineapple
PID lookup failing).

---

## 2. Graphical waterfall: OK/Back doesn't stop the scan

**Severity: high.**

Pressing OK (long-press) or Back while the graphical waterfall is running
does not stop it / return to the menu. Reported after the awk-consolidation
fix to `check_cancel()`/`check_dpad()` in `funcs_main.sh` — **not yet
re-verified on hardware**, so it's unclear whether the fix helped, fully
fixed it, or didn't touch the real cause.

**Working theory:** CPU/fork contention on the single-core MIPS CPU between
the button-polling loop (`check_dpad`/`check_cancel`, called every ~150ms
tick) and `spectools_waterfall_fb.py`'s own per-pixel framebuffer writes.
Text waterfall (much lighter renderer, no SIGSTOP) was not reported broken,
which supports this — but it's unverified, not confirmed.

**Alternative theory not yet ruled out:** `/pineapple/pineapple` or the
kernel holds an exclusive grab (`EVIOCGRAB`) on `/dev/input/event0` during
framebuffer takeover, which would explain why buttons stop responding
regardless of CPU load. Distinguishing test: check whether
`$KEYCKTMP_FILE` (the evtest output buffer) grows at all during a stuck
graphical-waterfall session.

**Status:** fix attempted, unverified.

---

## 3. Graphical waterfall: LEFT/RIGHT band switch doesn't work

**Severity: high.**

Same symptom and same fix attempt as #2 (both live in `check_dpad()`/
`check_cancel()`, both poll the same evtest buffer). Not yet confirmed fixed
on hardware after the awk-consolidation change.

**Status:** fix attempted, unverified.

---

## 4. UP+DOWN screenshot combo doesn't fire reliably

**Severity: medium.**

Root cause identified and a fix already landed in `check_dpad()`: the old
code required both UP and DOWN to land in the *same* ~150ms poll tick, but
two separate physical button presses rarely do. Fix carries an unpaired
UP/DOWN through `$DPAD_PENDING_FILE` across ticks (expires after ~1s).

**Status:** fix landed, not yet re-verified on hardware since the latest
awk-consolidation rewrite touched the same function.

---

## 5. 2.4GHz graphical waterfall crashes on exit; 5GHz exits cleanly

**Severity: medium.**

Exiting the graphical waterfall while scanning 5GHz works correctly. Exiting
while scanning 2.4GHz crashes mid-process. No device-side logs have been
captured yet — need a live repro with `$LOG_FILE` and `dmesg`/`logread`
output from the moment of the crash.

**Status:** unreproduced/undiagnosed — needs a live SSH session during a
crash to get a stack trace or error output.

---

## 6. Intermittent missing menu / stuck splash after boot

**Severity: medium.**

Originally reported as: sometimes the boot splash shows, sometimes it
doesn't, and the app could get stuck unable to reach the main menu without a
long wait or holding a button. Partial fixes landed:

- Removed the tap-vs-hold landing gate and its auto-launched default
  waterfall (now always goes straight to the menu).
- Added a 5s watchdog around `specpine_splash.py` so a hung splash can't
  block the menu forever, and routed its stderr to `$LOG_FILE` instead of
  `/dev/null` so failures leave evidence.
- Removed the ASCII-art text logo entirely (per explicit request — not part
  of the splash watchdog fix, just cleanup).

**Status:** not yet retested on hardware since the splash-watchdog fix
landed — and now entangled with bug #1 (HUD unavailable), since the menu
itself is failing to draw via the custom screen regardless of splash timing.

---

## 7. Glitchy/frozen screen after manual stray-process recovery

**Severity: low-medium.**

After manually killing stray `spectools_bridge`/`spectool_raw`/renderer
processes via SSH to recover from a stuck state, the screen can come back
glitchy. `kill_stray_specpine_workers()` + `pineapple_ensure_running()` are
called on every fresh launch specifically to avoid inheriting this state,
but the glitch has been observed even after that path runs.

**Status:** unreproduced/undiagnosed.

---

## 8. Orphaned-renderer reaper — fix landed, not yet re-verified

**Severity: low (regression risk only).**

The orphaned-process reaper (`kill_stray_specpine_workers`, matches
`spectool_raw`/`spectool_net`/bridge/renderer via `ps w` + awk) was added to
fix "all bands return no data" caused by a stale `spectool_raw` left holding
the USB device from a previous crashed run. Logic looks correct on read but
hasn't been re-confirmed on hardware since the most recent payload.sh
changes (landing-gate removal, splash watchdog).

**Status:** fix landed, pending hardware re-verification.

---

## Suggested triage order

1. **#1 (HUD/graphical screen not drawing)** — blocks almost everything else
   from being testable through the intended UI at all.
2. **#2 / #3 (button stop / L-R switch)** — directly blocks normal use of the
   graphical waterfall once #1 is sorted.
3. **#5 (2.4GHz crash)** — needs a live capture, can run in parallel with #1.
4. **#6, #7, #8** — re-verification passes once #1–#3 are confirmed fixed,
   since several of these symptoms may turn out to share a root cause with
   #1 (framebuffer/process-state assumptions that don't hold on this
   firmware build).
