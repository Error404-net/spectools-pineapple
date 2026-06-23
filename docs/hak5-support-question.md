# Question for Hak5: official framebuffer/display takeover + Virtual Pager interaction

**Where to post:** [Hak5 Discord](https://hak5.org/discord) (#wifi-pineapple-pager channel) or the
[forum](https://forums.hak5.org/forum/113-wifi-pineapple-pager/). Discord is faster for a back-and-forth;
the forum is better if it needs to go to firmware engineering and get a real answer over a few days.

---

## Context

I'm building a payload (SpecPine, a Wi-Spy DBx spectrum analyzer bridge) for the WiFi Pineapple Pager
(firmware 24.10.1, mipsel_24kc). It needs to draw its own custom screens — a main menu and a live
graphical waterfall — instead of using `LIST_PICKER`/`LOG`. The official docs don't cover any API for a
payload to draw to the display directly (the Payloads section notes "documentation about writing
payloads will be coming soon"), so I reverse-engineered the only mechanism that's worked so far:

- `/dev/fb0` is a raw RGB565 framebuffer, physical 222×480 portrait.
- It's normally owned and repainted by the device's own `/pineapple/pineapple` process roughly every
  ~750ms.
- To get a custom frame to stick, the payload sends `SIGSTOP` to `pineapple` first, writes directly to
  `/dev/fb0`, and sends `SIGCONT` back on exit (or a signal trap).
- Button input is read by backgrounding `evtest /dev/input/event0` and parsing its output — this
  continues to work fine while `pineapple` is stopped, since it's a separate kernel input device, not
  routed through the UI process.
- `/sys/class/vtconsole/vtcon1` doesn't exist on this firmware (only `vtcon0`) — so any "unbind the
  console" trick that assumes vtcon1 is wrong on this build; SpecPine guards for that.

This works often enough to be useful, but it's clearly undocumented and fragile (process-name lookup for
`pineapple` can fail silently depending on how it's launched; behaves differently menu-launched vs.
SSH-launched).

## What's actually broken right now

The fallback path itself is working as designed (when the custom screen can't draw, it cleanly falls
back to the firmware's own `LIST_PICKER`/`LOG` UI with a "HUD unavailable" message) — but the *custom*
screen is failing both:

1. **On the physical device**, via real button presses.
2. **In the Virtual Pager** (the documented remote-view feature at
   `documentation.hak5.org/.../virtual-pager`), driving it through the web UI.

Same failure in both places, same screenshot. That strongly suggests the SIGSTOP+raw-fb-write approach
either isn't reliably taking the framebuffer at all on this firmware build, or something about how the
UI process re-asserts itself (timing, a watchdog, a second repaint path) is racing it — and that the
Virtual Pager is mirroring whatever `/pineapple/pineapple` itself last drew (or some other internal
state), not the raw `/dev/fb0` bytes, since it shows the exact same fallback as the physical screen.

## Specific questions

1. **Is there an official, supported way for a payload to draw custom content to the screen** (full frame
   or partial), rather than the SIGSTOP+raw-`/dev/fb0`-write approach? Is "documentation coming soon"
   for writing payloads going to cover this?
2. **What actually owns `/dev/fb0` writes**, and is `SIGSTOP`/`SIGCONT` on `pineapple` a safe/intended way
   to pause its repaint loop, or is there a cleaner IPC/signal a payload should send instead (one that
   won't race a watchdog or get silently ignored)?
3. **How does Virtual Pager source the frames it displays?** Does it mirror `/dev/fb0` directly, or does
   it read state from `pineapple` itself (e.g. over some internal socket/IPC)? If it's the latter, a
   payload that writes directly to `/dev/fb0` while `pineapple` is stopped would never show up in Virtual
   Pager even if the physical screen *did* update correctly — which would mean physical-hardware and
   Virtual-Pager testing aren't actually testing the same code path today.
4. **Is there an officially exposed input-event API** for payloads (vs. parsing `evtest /dev/input/event0`
   output), and does Virtual Pager's on-screen button UI generate real events on that same device node, or
   a separate path a payload listening on `/dev/input/event0` would never see?
5. If raw framebuffer takeover genuinely isn't supported on 24.10.1, **is there a firmware version or
   upcoming release where it is** — and is there a minimal reference example (even just "send signal X,
   write Y bytes here") we could build against instead of guessing from observed behavior?

Happy to share the actual code (it's open — `spectools_waterfall_fb.py` / `specpine_hud.py`) if that's
useful for someone on your end to look at directly.
