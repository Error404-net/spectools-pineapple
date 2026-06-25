create a break to attempt to kill specpine running:

sshpass -p qwerty ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no root@172.16.52.1 'for p in $(ps w | grep "/pineapple/pineapple" | grep -v grep | awk "{print \$1}"); do kill -CONT "$p"; done; for p in $(ps w | grep -E "payload-.*\.sh|specpine_hud" | grep -v grep | awk "{print \$1}"); do kill -9 "$p" 2>/dev/null; done's


what each script does that I know:
specpine_hud.py — draws only the main menu. That's it.
spectools_waterfall_fb.py — draws the graphical waterfall. Separate script, separate code path.
spectools_waterfall_pager.py — the text waterfall, which doesn't touch the framebuffer at all — it just prints to the Pager's normal LOG.


remove sessions, anomoly detection, channel analysis 


Questions:
Does the Virtual Pager mirrors raw /dev/fb0 or mirrors pineapple's own internal state, since that determines whether physical and Virtual Pager testing are even exercising the same code path. Post this to their Discord (#wifi-pineapple-pager) for the fastest read from someone who'd know.