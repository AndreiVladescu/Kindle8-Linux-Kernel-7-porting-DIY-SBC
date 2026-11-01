#!/bin/sh
# After the Kindle has booted the mainline kernel to init=/bin/sh (tools/stage.py ... --bootargs with g_ether MACs):
# bring up usb0 over serial, serve the files, run the in-RAM Alpine+dropbear setup, then you can `tools/ssh.sh`.
# Needs: NetworkManager profile kindle8-usb (192.168.7.1/24 on enx024b38000001), key ~/.ssh/kindle8_ed25519.
set -e
R=$(cd "$(dirname "$0")/.." && pwd); cd "$R"
pgrep -f 'tools/(stage|ramboot)[.]py' >/dev/null && { echo "!! a stage/ramboot run owns the serial port"; exit 1; }
S() { python3 -I tools/ser.py "$@" | tr -d '\r'; }
echo "== usb0 up on the Kindle"
S "mount -t proc p /proc 2>/dev/null; mount -t sysfs s /sys 2>/dev/null; ifconfig lo 127.0.0.1 up; ifconfig usb0 192.168.7.2 netmask 255.255.255.0 up" 4 >/dev/null
for i in $(seq 1 15); do ping -c1 -W1 192.168.7.2 >/dev/null 2>&1 && break; sleep 1; done
ping -c1 -W1 192.168.7.2 >/dev/null || { echo "!! no ping to 192.168.7.2 (USB cable / NM profile kindle8-usb?)"; exit 1; }
echo "== serving build/serve on 192.168.7.1:8000"
pgrep -f 'http.server 8000 --bind 192.168.7.1' >/dev/null || { ./tools/serve.sh >build/serve.log 2>&1 & sleep 1; }
echo "== running setup on the Kindle (≈20 s)"
S "wget -q -O - http://192.168.7.1:8000/setup.sh | sh" 120 25 | grep -E '^== \[kindle\]|ERROR' || true
exec "$R/tools/ssh.sh" 'echo "== SSH OK: $(cat /etc/alpine-release) on $(uname -r)"'
