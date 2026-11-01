#!/usr/bin/env python3
"""RAM-boot a test kernel on the Kindle through stock U-Boot — writes nothing to eMMC.

usage: ramboot.py <uImage> <dtb> [--bootargs "..."] [--from-linux] [--log FILE] [--watch SECONDS]

  --from-linux   device is sitting in a Linux shell: send `reboot -f` first
  Flow: catch autoboot -> loady kernel @0x80800000 -> loady dtb @0x83000000 -> setenv bootargs -> bootm
"""
import argparse, os, subprocess, sys, time
import serial

PORT, BAUD = '/dev/ttyACM0', 115200
KADDR, DADDR = 0x80800000, 0x83000000
DEFAULT_ARGS = ('console=ttymxc0,115200 earlycon=ec_imx6q,0x02020000 '
                'root=/dev/mmcblk0p1 rootwait ro init=/bin/sh loglevel=8')

ap = argparse.ArgumentParser()
ap.add_argument('kernel'); ap.add_argument('dtb')
ap.add_argument('--bootargs', default=DEFAULT_ARGS)
ap.add_argument('--from-linux', action='store_true')
ap.add_argument('--log', default='boot.log')
ap.add_argument('--watch', type=float, default=90)
ap.add_argument('--1k', dest='onek', action='store_true', help='YMODEM 1K blocks (overflows the Bus Pirate bridge)')
a = ap.parse_args()

log = open(a.log, 'wb')
def opn(): return serial.Serial(PORT, BAUD, timeout=0.05)
s = opn()

def read_until(token, tmo, poke=None):
    buf = b''; t0 = time.time(); lastpoke = 0
    while time.time() - t0 < tmo:
        if poke and time.time() - lastpoke > 0.1:
            s.write(poke); lastpoke = time.time()
        d = s.read(4096)
        if d:
            buf += d; log.write(d); log.flush()
            sys.stdout.write(d.decode(errors='replace')); sys.stdout.flush()
            if token in buf: return buf
    raise SystemExit(f'\n!! timeout waiting for {token!r}')

def cmd(line, wait=b'uboot > ', tmo=10):
    s.write(line.encode() + b'\r')
    return read_until(wait, tmo)

def ymodem(addr, path):
    global s
    cmd(f'loady 0x{addr:08x}', wait=b'C', tmo=10)
    s.close()
    subprocess.run(['stty', '-F', PORT, str(BAUD), 'raw', '-echo', '-echoe', '-echok',
                    '-ixon', '-ixoff', '-crtscts'], check=True)
    t0 = time.time()
    with open(PORT, 'rb', buffering=0) as rx, open(PORT, 'wb', buffering=0) as tx:
        r = subprocess.run(['sb'] + (['-k'] if a.onek else []) + [path], stdin=rx, stdout=tx)
    print(f'\n== sb {os.path.basename(path)} rc={r.returncode} in {time.time()-t0:.0f}s')
    if r.returncode: raise SystemExit('!! ymodem failed')
    s = opn()
    read_until(b'uboot > ', 15, poke=None)

if a.from_linux:
    s.write(b'\rsync; reboot -f\r')
else:
    s.write(b'\x03\r')   # already in U-Boot: clear line (Ctrl-C) and get a fresh prompt
# spam keys to stop the 3 s autoboot
read_until(b'uboot > ', 120 if a.from_linux else 30, poke=b' ')
time.sleep(0.3); s.reset_input_buffer()
cmd('')
ymodem(KADDR, a.kernel)
ymodem(DADDR, a.dtb)
cmd(f'iminfo 0x{KADDR:08x}')
cmd(f'setenv bootargs {a.bootargs}')
s.write(f'bootm 0x{KADDR:08x} - 0x{DADDR:08x}\r'.encode())
# watch the boot
t0 = time.time()
while time.time() - t0 < a.watch:
    d = s.read(4096)
    if d:
        log.write(d); log.flush(); sys.stdout.write(d.decode(errors='replace')); sys.stdout.flush()
print(f'\n== watch ended, log in {a.log}')
