root@pager:~# ls
loot      payloads  recon
root@pager:~# cd payloads/
root@pager:~/payloads# ls
alerts  recon   user
root@pager:~/payloads# cd user/
root@pager:~/payloads/user# ls
evil_portal                      prank
exfiltration                     reconnaissance
games                            remote_access
general                          spectools-pineapple-payload
incident_response                spectools-pineapple-payload.zip
interception                     virtual_pager
known_unstable
root@pager:~/payloads/user# cd spectools-pineapple-payload
root@pager:~/payloads/user/spectools-pineapple-payload# ls
INSTALL.md  payloads
root@pager:~/payloads/user/spectools-pineapple-payload# cd payloads/
root@pager:~/payloads/user/spectools-pineapple-payload/payloads# ls
spectools_install              spectools_waterfall_graphical
spectools_waterfall
root@pager:~/payloads/user/spectools-pineapple-payload/payloads# cd spectools_install/
root@pager:~/payloads/user/spectools-pineapple-payload/payloads/spectools_install# ls
99-wispy.rules  bin             lib             payload.sh
root@pager:~/payloads/user/spectools-pineapple-payload/payloads/spectools_install# ./payload.sh 
root@pager:~/payloads/user/spectools-pineapple-payload/payloads/spectools_install# ls
99-wispy.rules  bin             lib             payload.sh
root@pager:~/payloads/user/spectools-pineapple-payload/payloads/spectools_install# cd ..
root@pager:~/payloads/user/spectools-pineapple-payload/payloads# ls
spectools_install              spectools_waterfall_graphical
spectools_waterfall
root@pager:~/payloads/user/spectools-pineapple-payload/payloads# cd spectools_
bash: cd: spectools_: No such file or directory
root@pager:~/payloads/user/spectools-pineapple-payload/payloads# cd spectools_waterfall_graphical/
root@pager:~/payloads/user/spectools-pineapple-payload/payloads/spectools_waterfall_graphical# ls
bin         payload.sh
root@pager:~/payloads/user/spectools-pineapple-payload/payloads/spectools_waterfall_graphical# ./payload.sh 
./payload.sh: line 37: /sys/class/vtconsole/vtcon1/bind: No such file or directory
root@pager:~/payloads/user/spectools-pineapple-payload/payloads/spectools_waterfall_graphical# 