#!/bin/sh
# Live, read-only view of the Kindle serial console + what the tools are doing.
#   tools/console.sh          follow logs/live.log (all tool runs append here, incl. status/ACTION banners)
#   tools/console.sh --port   read /dev/ttyACM0 directly (ONLY when no tool is running)
# Never writes to the Kindle. Ctrl-C to quit.
R=$(cd "$(dirname "$0")/.." && pwd)
LIVE="$R/logs/live.log"
if [ "$1" = "--port" ]; then
  if pgrep -f 'tools/(stage|ramboot)[.]py' >/dev/null; then
    echo "!! a Kindle tool owns the port — reading it would steal its bytes. Use: tools/console.sh" >&2; exit 1
  fi
  exec python3 -I -u -c '
import serial, sys
s = serial.Serial(sys.argv[1], 115200, timeout=0.2); o = sys.stdout.buffer
while True:
    d = s.read(4096)
    if d: o.write(d); o.flush()' /dev/ttyACM0
fi
mkdir -p "$R/logs"; touch "$LIVE"
echo "== following $LIVE (Ctrl-C to quit)" >&2
# strip CRs so lines render; highlight banners (stdbuf keeps it real-time)
tail -n 40 -F "$LIVE" | stdbuf -oL tr -d '\r' | stdbuf -oL sed -u \
  -e 's/^\(>>> ACTION.*\)$/\x1b[1;37;41m\1\x1b[0m/' \
  -e 's/^\(--- DO NOT TOUCH.*\)$/\x1b[1;30;43m\1\x1b[0m/' \
  -e 's/^\(!!.*\)$/\x1b[1;31m\1\x1b[0m/' \
  -e 's/^\(== .*\)$/\x1b[1;36m\1\x1b[0m/' \
  -e 's/^\(=\{10,\}.*\)$/\x1b[1;32m\1\x1b[0m/'
