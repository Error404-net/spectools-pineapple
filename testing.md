# SpecPine on-device testing cheatsheet

Pager dev target: `172.16.52.1`, password `qwerty`. The Pager shell is BusyBox
`ash` — no `pkill`, and `kill` does not support `-f`. Always find PIDs via
`ps w | grep ... | awk '{print $1}'` and kill those directly.

Run all of these from the repo root on your machine (where `pine-spectools.zip`
gets built).

## 1. Rebuild the zip after any code change

```bash
bash scripts/package.sh
```

Sanity checks worth running before deploying (from CLAUDE.md):

```bash
bash -n payloads/specpine/payload.sh \
        payloads/specpine/include/funcs_main.sh \
        payloads/specpine/include/funcs_menu.sh \
        payloads/specpine/include/funcs_scan.sh
python3 -m py_compile payloads/specpine/bin/*.py scripts/generate_theme_images.py
```

## 2. Push a fresh copy to the device

One line, no backslash continuations (multi-line backslash commands have
broken when pasted into zsh before — keep this as a single line):

```bash
sshpass -p qwerty scp -o PreferredAuthentications=password -o PubkeyAuthentication=no pine-spectools.zip root@172.16.52.1:/root/ && sshpass -p qwerty ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no root@172.16.52.1 'cd /tmp && unzip -o /root/pine-spectools.zip && rm -rf /root/payloads/user/reconnaissance/specpine && cp -r pine-spectools/specpine /root/payloads/user/reconnaissance/specpine && chmod 755 /root/payloads/user/reconnaissance/specpine/payload.sh && chmod 755 /root/payloads/user/reconnaissance/specpine/bin/*.py && chmod 755 /root/payloads/user/reconnaissance/specpine/bin/spectool_raw && chmod 755 /root/payloads/user/reconnaissance/specpine/bin/spectool_net && rm -f /tmp/specpine_hud_debug.log /tmp/specpine.log /tmp/specpine_hud.lock && for p in $(ps w | grep -E "payload-.*\.sh|specpine_hud" | grep -v grep | awk "{print \$1}"); do kill -9 "$p" 2>/dev/null; done'
```

Confirm the `scp` half actually ran (you should see a transfer
progress/percentage line) before the `unzip` output — if scp silently fails,
this command will redeploy whatever old zip is already sitting in `/root/`
instead of your new build.

## 3. Pull diagnostic logs after a test launch

```bash
sshpass -p qwerty ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no root@172.16.52.1 'echo ---LOCK---; cat /tmp/specpine_hud.lock 2>&1; echo ---PS---; ps w | grep -E "specpine|evtest|payload" | grep -v grep; echo ---SPECLOG---; tail -n 40 /tmp/specpine.log 2>&1; echo ---HUDLOG---; tail -n 60 /tmp/specpine_hud_debug.log 2>&1'
```

- `specpine.log` is `payload.sh`'s own log (`LOG_FILE`) plus stderr from
  `specpine_hud.py` when invoked through the real menu path.
- `specpine_hud_debug.log` is the HUD script's own trail (every raw evtest
  line + every parsed up/down/ok event) — the most reliable way to tell
  "evtest never started" apart from "events came in but didn't match" apart
  from "menu logic never got reached at all."
- An empty/missing `specpine_hud_debug.log` after a real launch attempt means
  `specpine_hud.py` never even started — look upstream in `payload.sh`
  (include sourcing, `PAYLOAD_ROOT` resolution, `main_menu_hud()`'s
  `[ -x "$HUD_BIN" ]` check) rather than inside the HUD script itself.

## 4. Recover a frozen / unresponsive screen

The framebuffer renderers (`specpine_splash.py`, `specpine_hud.py`,
`spectools_waterfall_fb.py`) all `SIGSTOP` the firmware's own UI process
(`/pineapple/pineapple`) while they own the screen, and are supposed to
`SIGCONT` it again on every exit path. If one of them dies without resuming
it, the whole Pager UI (display *and* input) appears permanently frozen —
that's not a hang in the firmware, it's a suspended process. Resume it and
clear any stuck payload process:

```bash
sshpass -p qwerty ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no root@172.16.52.1 'for p in $(ps w | grep "/pineapple/pineapple" | grep -v grep | awk "{print \$1}"); do kill -CONT "$p"; done; for p in $(ps w | grep -E "payload-.*\.sh|specpine_hud" | grep -v grep | awk "{print \$1}"); do kill -9 "$p" 2>/dev/null; done'
```

If the device doesn't recover after that (e.g. it hard-crashed rather than
just freezing), power-cycle the Pager — that's always safe and is the
fallback when SSH itself is unreachable.

## 4b. Kill every SpecPine-related process (nuclear option)

One-liner, BusyBox-`ash`-safe (no `pkill`, no `kill -f`). Catches the payload
shell, the HUD, both renderers, the bridge, `spectool_raw`/`spectool_net`,
and the `evtest` watcher in one pass, then clears the lock/log files so the
next launch starts clean:

```bash
sshpass -p qwerty ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no root@172.16.52.1 'for p in $(ps w | grep -E "payload-.*\.sh|specpine_hud|spectools_bridge|spectools_waterfall|spectool_raw|spectool_net|evtest /dev/input" | grep -v grep | awk "{print \$1}"); do kill -9 "$p" 2>/dev/null; done; for p in $(ps w | grep "/pineapple/pineapple" | grep -v grep | awk "{print \$1}"); do kill -CONT "$p"; done; rm -f /tmp/specpine_hud.lock /tmp/specpine_btn_evt /tmp/specpine_dpad_evt /tmp/specpine_screenshot_evt /tmp/specpine_keyck.tmp; echo done'
```

Run this any time the screen is stuck, Back/OK stop working, or you just
want a guaranteed-clean slate before the next test launch. It also
SIGCONTs `pineapple` in case a killed renderer left it suspended.


sshpass -p qwerty ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no root@172.16.52.1 'for p in $(ps w | grep -E "payload-.*\.sh|specpine_hud|spectools_bridge|spectools_waterfall|spectool_raw|spectool_net|evtest /dev/input" | grep -v grep | awk "{print \$1}"); do kill -9 "$p" 2>/dev/null; done; for p in $(ps w | grep "/pineapple/pineapple" | grep -v grep | awk "{print \$1}"); do kill -CONT "$p"; done; rm -f /tmp/specpine_hud.lock /tmp/specpine_btn_evt /tmp/specpine_dpad_evt /tmp/specpine_screenshot_evt /tmp/specpine_keyck.tmp; echo done'

## 5. Smoke-test `spectool_raw` directly (no payload involved)

```bash
LD_LIBRARY_PATH=/root/payloads/user/reconnaissance/specpine/lib \
  /root/payloads/user/reconnaissance/specpine/bin/spectool_raw --list
```

Useful for confirming the Wi-Spy DBx and binary/libusb are working
independent of any payload.sh or menu bug.

## Known gotchas already hit during testing

- **Multi-line backslash commands break when pasted into zsh.** Always use
  the single-line forms above.
- **The firmware stages `payload.sh` into `/tmp/payload-<rand>.sh` before
  executing it**, without copying `include/`/`bin/`/`data/` alongside it. A
  naive `PAYLOAD_ROOT="$(cd "$(dirname "$0")" && pwd)"` breaks under this —
  `payload.sh` now falls back to the known install path
  (`/root/payloads/user/reconnaissance/specpine`) when `include/funcs_main.sh`
  isn't found next to `$0`.
- **Never manually run `specpine_hud.py` directly on the device for
  debugging and leave it running.** If it's still alive when you later
  launch the payload for real, it can intercept real button presses meant
  for the new launch. `specpine_hud.py` now takes a PID lockfile
  (`/tmp/specpine_hud.lock`) and refuses to start a second instance, but the
  safest approach is still: don't leave manual test invocations running.
- **Splash animation must always resume `pineapple`.** The prebuilt-frame
  animation path in `specpine_splash.py` is the one actually shipped (since
  `package.sh` builds `data/theme/boot_animation/frame_*.fb`) — it must call
  `_pineapple_cont()` before returning, same as the inline-drawing fallback
  does. Missing that call is what caused the device to freeze on the
  "READY" splash screen with no way to back out.
