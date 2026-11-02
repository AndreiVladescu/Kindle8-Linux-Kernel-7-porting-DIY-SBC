#!/usr/bin/env python3
"""zForce (TI MSP430 + NN1101) userspace probe over /dev/i2c-1 @0x51, classic protocol as used by
the Lab126 zforce2 driver with deviceType=1. Run with zforce_ts unloaded.
Frames: host writes EE <len> <cmd> [args]; the controller pulls TOUCH_INTB (gpio4 3) low when it
has a frame, which is read as a 2-byte header EE <len>, then <len> payload bytes."""
import fcntl, os, subprocess, sys, time

I2C_SLAVE_FORCE = 0x0706
CHIP = "gpiochip3"          # gpio4
INT, RST = 3, 5

def gpio_get(line):
    out = subprocess.run(["gpioget", "-c", CHIP, str(line)], capture_output=True, text=True).stdout
    return 0 if "inactive" in out else 1

def gpio_set(line, val):
    subprocess.run(["gpioset", "-c", CHIP, "-t0", f"{line}={val}"], check=True)

fd = os.open("/dev/i2c-1", os.O_RDWR)
fcntl.ioctl(fd, I2C_SLAVE_FORCE, 0x51)

def read_frame(timeout=1.0):
    end = time.time() + timeout
    while time.time() < end:
        if gpio_get(INT) == 0:          # data ready (active low)
            try:
                hdr = os.read(fd, 2)
                if hdr[0] != 0xEE:
                    return ("bad header", hdr.hex())
                return os.read(fd, hdr[1])
            except OSError as e:
                return ("i2c error", str(e))
        time.sleep(0.01)
    return None

def cmd(name, *b, timeout=1.0):
    os.write(fd, bytes([0xEE, len(b)] + list(b)))
    r = read_frame(timeout)
    print(f"{name:14s} -> {r.hex(' ') if isinstance(r, bytes) else r}")
    return r

print("INT before reset:", gpio_get(INT))
gpio_set(RST, 0); time.sleep(0.05); gpio_set(RST, 1)
r = read_frame(2.0)
print("boot complete  ->", r.hex(" ") if isinstance(r, bytes) else r)
cmd("status 1E", 0x1E)
cmd("initialize 01", 0x01)
cmd("ledlevel X", 0x1C, 0x00)
cmd("ledlevel Y", 0x1C, 0x01)
cmd("resolution", 0x02, 600 & 0xff, 600 >> 8, 800 & 0xff, 800 >> 8)
cmd("scanfreq", 0x08, 45, 0, 60, 0, 60, 0)
cmd("setconfig", 0x03, 0x01, 0, 0, 0)
t = float(sys.argv[1]) if len(sys.argv) > 1 else 0
if t:
    os.write(fd, bytes([0xEE, 1, 0x04]))      # touch data request
    end = time.time() + t; n = 0
    while time.time() < end:
        r = read_frame(0.5)
        if r is not None:
            n += 1; print(time.strftime("%H:%M:%S"), "frame", r.hex(" ") if isinstance(r, bytes) else r, flush=True)
    print("frames:", n)
