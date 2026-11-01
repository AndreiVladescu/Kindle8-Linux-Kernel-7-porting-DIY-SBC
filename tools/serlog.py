#!/usr/bin/env python3
"""Read-only serial capture: /dev/ttyACM0 -> <log> and logs/live.log (shown by tools/console.sh).
usage: serlog.py <log> [seconds=120] [--until REGEX]   (never writes to the Kindle)"""
import re, sys, time, serial
log = sys.argv[1]; secs = float(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else 120
until = re.compile(sys.argv[sys.argv.index('--until') + 1].encode()) if '--until' in sys.argv else None
s = serial.Serial('/dev/ttyACM0', 115200, timeout=0.1)
f, live = open(log, 'ab'), open('logs/live.log', 'ab')
live.write(f'\n== serlog: capturing to {log} for {secs:.0f}s (read-only)\n'.encode()); live.flush()
t0 = time.time(); buf = b''
while time.time() - t0 < secs:
    d = s.read(4096)
    if d:
        for x in (f, live): x.write(d); x.flush()
        sys.stdout.buffer.write(d); sys.stdout.flush()
        buf = (buf + d)[-4096:]
        if until and until.search(buf): break
live.write(b'\n== serlog: done\n'); live.flush()
