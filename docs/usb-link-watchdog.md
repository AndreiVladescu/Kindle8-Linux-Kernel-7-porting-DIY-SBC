# USB link watchdog — 2026-11-01
Problem: after a PC reboot the gadget stays `configured` on the Kindle but the PC never answers ARP → USB link dead.
Fix: `host/kindle-rootfs/usr/local/sbin/usb-link-watchdog` + OpenRC service (installed on the Kindle, runlevel default).
ARP-probes 192.168.7.1 on usb0 every 20 s; after 3 misses (and only if a host is attached) toggles
`/sys/class/udc/ci_hdrc.0/soft_connect` → PC re-enumerates → NetworkManager re-activates `kindle8-usb`.
Exponential backoff 60 s → 30 min. Tested: `nmcli con down kindle8-usb` → link back on its own after 59 s.
