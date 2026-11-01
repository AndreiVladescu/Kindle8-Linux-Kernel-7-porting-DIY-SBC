#!/usr/bin/env python3
"""Minimal mkimage replacement: wrap a kernel (zImage/Image) in a legacy U-Boot uImage header.
usage: mkuimage.py <in> <out> [load=0x80008000] [name]"""
import struct, sys, time, zlib
src, dst = sys.argv[1], sys.argv[2]
load = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x80008000
name = (sys.argv[4] if len(sys.argv) > 4 else "Linux mainline").encode()[:32]
data = open(src, 'rb').read()
# magic, hcrc, time, size, load, ep, dcrc, os=linux(5), arch=arm(2), type=kernel(2), comp=none(0), name
def hdr(hcrc):
    return struct.pack('>IIIIIIIBBBB32s', 0x27051956, hcrc, int(time.time()), len(data),
                       load, load, zlib.crc32(data) & 0xffffffff, 5, 2, 2, 0, name)
h = hdr(0); h = hdr(zlib.crc32(h) & 0xffffffff)
open(dst, 'wb').write(h + data)
print(f"{dst}: {len(data)} bytes payload, load/entry 0x{load:08x}")
