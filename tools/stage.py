#!/usr/bin/env python3
"""Stage a test kernel+DTB into the Kindle's *diags* slot on eMMC, then boot it.

  ./tools/stage.py build/out/uImage build/out/imx6sl-amazon-heisenberg.dtb [--log logs/x.log]
  ./tools/stage.py --boot-only            # just boot whatever is already in the diags slot

Flow (wait for U-Boot → stock kernel ro init=/bin/sh → RAM staging disk over USB → PC writes it →
Kindle verifies md5 and dd's it into the diags slot → reboot → U-Boot boots the diags slot).

Writes ONLY eMMC user-area sectors 0x7208 .. 0xE207 (stock diags DTB + diags kernel; zero elsewhere).
Sector 0xE208+ holds unrelated data and is never written. Restore stock with:
  dd if=dumps/mmcblk0.img bs=512 skip=$((0x7208)) count=$((0x7000)) of=<that region>
Normal boot (sectors 0x208 / 0x2D0) is never touched.
"""
import argparse, hashlib, os, sys, time
import serial

PORT, BAUD = '/dev/ttyACM0', 115200
SLOT = 0x7208                 # first sector of staging region = diags DTB
DTB_MAX = 0x72D0 - 0x7208     # 0xC8 sectors (100 KiB) before diags kernel
SLOT_END = 0xE208             # exclusive; foreign data starts here
SECTORS = SLOT_END - SLOT     # 0x7000 sectors = 14 MiB
KOFF = DTB_MAX                # kernel at sector 0x72D0
STAGE_DEV = '/dev/kindle-stage'
STAGE_DIR = '/dev/stage'          # tmpfs on the Kindle (its /tmp is a dangling symlink in init=/bin/sh)
DEFAULT_ARGS = ('console=ttymxc0,115200 earlycon=ec_imx6q,0x02020000 '
                'root=/dev/mmcblk0p1 rootwait ro init=/bin/sh loglevel=8 '
                'g_ether.dev_addr=02:4b:38:00:00:02 g_ether.host_addr=02:4b:38:00:00:01')
GADGET = '/lib/modules/3.10.53-lab126/kernel/drivers/usb/gadget'

ap = argparse.ArgumentParser()
ap.add_argument('kernel', nargs='?'); ap.add_argument('dtb', nargs='?')
ap.add_argument('--boot-only', action='store_true')
ap.add_argument('--uboot-cmd', action='append', default=[], help='extra U-Boot command(s) run right before bootm (repeatable)')
ap.add_argument('--reset-on-fail', action='store_true', help='if the test boot resets (watchdog), send `reset` at U-Boot so the normal slot autoboots')
ap.add_argument('--ssh-reboot', action='store_true', help='Kindle runs Alpine: reboot it via tools/ssh.sh, then catch U-Boot')
ap.add_argument('--sysrq', action='store_true', help='try serial BREAK + SysRq-b to reboot a fully booted stock Kindle')
ap.add_argument('--reboot-cmd', default='sync; reboot -f', help='command typed on the serial shell for --from-linux')
ap.add_argument('--from-linux', action='store_true', help='Kindle is sitting in the stock init=/bin/sh: reboot it first')
ap.add_argument('--bootargs', default=DEFAULT_ARGS)
ap.add_argument('--log', default='logs/stage.log')
ap.add_argument('--watch', type=float, default=120)
ap.add_argument('--wdt', type=float, default=60, help='arm i.MX WDOG1 in U-Boot before bootm (s, 0=off); auto-resets a hung test kernel')
ap.add_argument('--wait-uboot', type=float, default=600, help='seconds to wait for a reset into U-Boot')
a = ap.parse_args()
if not a.boot_only and not (a.kernel and a.dtb):
    ap.error('kernel and dtb required unless --boot-only')

log = open(a.log, 'wb')
os.makedirs('logs', exist_ok=True)
live = open('logs/live.log', 'ab')          # one fixed file, never truncated: tools/console.sh follows it
import builtins
def print(*args, **kw):                       # status lines go to stdout AND both logs
    msg = ' '.join(str(x) for x in args)
    builtins.print(msg, flush=True, **{k: v for k, v in kw.items() if k != 'flush'})
    b = ('\n' + msg.strip('\n') + '\n').encode()
    for f in (log, live): f.write(b); f.flush()

def action(msg):  print('\n' + '>' * 70 + f'\n>>> ACTION: {msg}\n' + '>' * 70)
def hands_off(msg): print('\n' + '-' * 70 + f'\n--- DO NOT TOUCH THE KINDLE: {msg}\n' + '-' * 70)
print(f'\n#################### stage.py run {time.strftime("%H:%M:%S")} -> {a.log} ####################')
_t0 = time.time()
while True:
    try:
        s = serial.Serial(PORT, BAUD, timeout=0.05); break
    except (serial.SerialException, OSError):
        if time.time() - _t0 > a.wait_uboot: raise SystemExit(f'!! {PORT} never appeared')
        if int(time.time() - _t0) % 30 == 0: print(f'== waiting for {PORT} (Bus Pirate plugged in?)', flush=True)
        time.sleep(1)


def emit(d):
    live.write(d); live.flush()
    log.write(d); log.flush(); sys.stdout.write(d.decode(errors='replace')); sys.stdout.flush()


def read_until(tokens, tmo, poke=None, every=0.1):
    tokens = [tokens] if isinstance(tokens, bytes) else tokens
    buf = b''; t0 = time.time(); last = 0
    while time.time() - t0 < tmo:
        if poke and time.time() - last > every:
            s.write(poke); last = time.time()
        d = s.read(4096)
        if d:
            buf += d; emit(d)
            for t in tokens:
                if t in buf[-4096:]:
                    return buf
    raise SystemExit(f'\n!! timeout waiting for {tokens!r}')


def typ(line):
    """type slowly — the Bus Pirate bridge is happiest that way"""
    for ch in (line + '\r').encode():
        s.write(bytes([ch])); time.sleep(0.003)


def ub(line, tmo=15):
    typ(line); return read_until(b'uboot > ', tmo)


def sh(line, tmo=30, check=True):
    """run a command in the stock init=/bin/sh; never let anything kill PID 1.
    Waits for the exit-status marker AND the next prompt in one buffer; aborts on non-zero status."""
    import re
    typ(f'{line}; echo __O""K__ $?')
    buf = b''; t0 = time.time()
    while time.time() - t0 < tmo:
        d = s.read(4096)
        if d:
            buf += d; emit(d)
            m = re.search(rb'__OK__ (\d+)\s*\r?\n.*?/ # ', buf, re.S)
            if m:
                if check and m.group(1) != b'0':
                    raise SystemExit(f'\n!! shell step failed (rc={m.group(1).decode()}): {line}')
                return buf
    raise SystemExit(f'\n!! timeout in shell step: {line}')

def get_uboot(reboot):
    global s
    if reboot:
        typ(a.reboot_cmd)
    elif a.sysrq:
        print('\n== trying serial BREAK + SysRq b (reboot)')
        for _ in range(3):
            s.send_break(0.5); time.sleep(0.2); s.write(b'b'); time.sleep(1.5)
    else:
        s.write(b'\x03\r')
    if reboot:
        hands_off('rebooting it from the shell — no button needed')
    elif a.ssh_reboot:
        hands_off('rebooted over SSH — waiting for U-Boot on the serial line, no button needed')
    else:
        action(f'reset the Kindle now (USB unplugged, hold power until it restarts, release, replug). Waiting up to {a.wait_uboot:.0f}s')
    t0 = time.time()
    while True:
        try:
            read_until(b'uboot > ', a.wait_uboot - (time.time() - t0), poke=b' ', every=0.05)
            break
        except (serial.SerialException, OSError) as e:
            # Bus Pirate unplugged/reset: wait for the port to come back and reopen it
            print(f'\n== serial port lost ({e.__class__.__name__}); waiting for {PORT} to return')
            try: s.close()
            except Exception: pass
            while time.time() - t0 < a.wait_uboot:
                time.sleep(1)
                try:
                    s = serial.Serial(PORT, BAUD, timeout=0.05); print('== port reopened'); break
                except (serial.SerialException, OSError):
                    pass
            else:
                raise SystemExit('!! port never came back')
    time.sleep(0.3); s.reset_input_buffer(); ub('')
    hands_off('U-Boot caught — script is driving the Kindle now')


def boot_stock_shell():
    ub('run setmmcdev; run loadkernel; run loaddt')
    ub('setenv bootargs console=ttymxc0,115200 root=/dev/mmcblk0p1 rootwait ro init=/bin/sh')
    typ('bootm 0x80800000 - 0x83000000')
    read_until(b'/ # ', 90)
    time.sleep(1)
    sh('mount -t proc p /proc; mount -t sysfs s /sys; mount -t devtmpfs d /dev; dmesg -n 1', check=False)
    sh(f'mkdir -p {STAGE_DIR} && mount -t tmpfs -o size=20m stage {STAGE_DIR}')


def build_stage():
    k = open(a.kernel, 'rb').read(); d = open(a.dtb, 'rb').read()
    if len(d) > DTB_MAX * 512: raise SystemExit('DTB too big for slot')
    if len(k) > (SECTORS - KOFF) * 512: raise SystemExit('kernel too big for slot')
    img = bytearray(SECTORS * 512)
    img[0:len(d)] = d
    img[KOFF * 512:KOFF * 512 + len(k)] = k
    return bytes(img)


def wait_dev(present, tmo=30):
    t0 = time.time()
    while time.time() - t0 < tmo:
        if os.path.exists(STAGE_DEV) == present:
            return
        time.sleep(0.5)
    raise SystemExit(f'!! {STAGE_DEV} did not {"appear" if present else "go away"} '
                     '(is host/99-kindle8-stage.rules installed?)')


def stage_and_flash():
    img = build_stage(); md5 = hashlib.md5(img).hexdigest()
    sh(f'dd if=/dev/zero of={STAGE_DIR}/stage.img bs=512 count={SECTORS} 2>/dev/null')
    sh(f'insmod {GADGET}/libcomposite.ko', check=False)  # may already be loaded
    sh(f'insmod {GADGET}/g_mass_storage.ko '
       f'file={STAGE_DIR}/stage.img ro=0 removable=0 iSerialNumber=KINDLE8STAGE iProduct=Stage', 20)
    wait_dev(True)
    print(f'\n== writing {len(img)} B to {STAGE_DEV} (md5 {md5})')
    with open(STAGE_DEV, 'r+b', buffering=0) as f:
        f.write(img); os.fsync(f.fileno())
    time.sleep(1)
    sh('rmmod g_mass_storage', 20)
    wait_dev(False)
    out = sh(f'md5sum {STAGE_DIR}/stage.img', 60).decode(errors='replace')
    if md5 not in out:
        raise SystemExit('!! md5 mismatch on device — NOT writing to eMMC')
    print('\n== md5 verified on device; writing diags slot')
    sh(f'dd if={STAGE_DIR}/stage.img of=/dev/mmcblk0 bs=512 seek={SLOT} count={SECTORS} conv=fsync 2>/dev/null', 120)
    out = sh(f'echo 3 > /proc/sys/vm/drop_caches; dd if=/dev/mmcblk0 bs=512 skip={SLOT} count={SECTORS} 2>/dev/null | md5sum', 120)
    if md5.encode() not in out:
        raise SystemExit('!! eMMC readback md5 mismatch — diags slot may be bad; normal boot unaffected. '
                         'Do NOT reboot into diags; investigate.')
    print('\n== eMMC readback md5 verified')


def boot_diags():
    ub('run setmmcdev')
    ub('run loaddt_diags')
    ub('run loadkernel_diags', 30)
    ub('iminfo 0x80800000')
    ub(f'setenv bootargs {a.bootargs}')
    if a.wdt:
        # WDOG1 WCR @0x020BC000: WT[15:8]=(secs*2-1), WDA|SRS (no ext/sw reset), WDT, WDE=enable.
        # Once enabled it cannot be stopped; mainline imx2_wdt sees it running and keeps feeding it.
        wt = max(1, min(255, int(a.wdt * 2) - 1))
        ub(f'mw.w 0x020bc000 0x{(wt << 8) | 0x3c:04x}')
        print(f'\n== WDOG1 armed: reset in {(wt + 1) / 2:.0f}s unless the kernel takes over')
    for c in a.uboot_cmd:
        ub(c)
        print(f'== U-Boot: {c}')
    typ('bootm 0x80800000 - 0x83000000')
    t0 = time.time(); buf = b''
    while time.time() - t0 < a.watch:
        d = s.read(4096)
        if d:
            emit(d); buf = (buf + d)[-8192:]
            if b'U-Boot 2014' in buf:
                # watchdog (or crash) reset: stop autoboot so the next run starts from U-Boot, not stock OS
                print('\n== board reset (watchdog?) during test boot; parking at U-Boot prompt')
                read_until(b'uboot > ', 30, poke=b' ', every=0.05)
                time.sleep(0.3); s.reset_input_buffer(); ub('')
                print('== parked at uboot > (next run: no --from-linux needed)')
                if a.reset_on_fail:
                    print('!! TEST KERNEL FAILED (watchdog reset). Sending `reset` -> normal slot autoboots.')
                    typ('reset')
                return
    print(f'\n== watch ended, log in {a.log}')


try:
    if a.ssh_reboot:
        import subprocess
        hands_off('rebooting the Kindle over SSH')
        subprocess.run(['tools/ssh.sh', '(sleep 1; reboot) >/dev/null 2>&1 &'], check=False)
    if a.boot_only:
        get_uboot(reboot=a.from_linux)
    else:
        get_uboot(reboot=a.from_linux)
        boot_stock_shell()
        stage_and_flash()
        get_uboot(reboot=True)
    boot_diags()
except SystemExit as e:
    print(f'\n!!!!!!!!!! RUN STOPPED: {e} !!!!!!!!!!\n--- leave the Kindle alone; Claude will tell you what to do next')
    raise
except BaseException as e:
    print(f'\n!!!!!!!!!! RUN CRASHED: {e!r} !!!!!!!!!!\n--- leave the Kindle alone; Claude will tell you what to do next')
    raise
else:
    print('\n==================== RUN FINISHED — leave the Kindle alone, Claude is reading the log ====================')
