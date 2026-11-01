#!/usr/bin/env python3
"""Small YMODEM (CRC, 128/1K) sender over an already-open pyserial port.
Used instead of lrzsz `sb` so the transfer can be paced/inspected through the Bus Pirate bridge."""
import os, time

SOH, STX, EOT, ACK, NAK, CAN, CRC = 0x01, 0x02, 0x04, 0x06, 0x15, 0x18, ord('C')


def crc16(data):
    c = 0
    for b in data:
        c ^= b << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) if c & 0x8000 else (c << 1)
    return c & 0xffff


def _wait(s, wanted, tmo):
    t0 = time.time()
    while time.time() - t0 < tmo:
        b = s.read(1)
        if b and b[0] in wanted:
            return b[0]
    return None


def _block(seq, payload, size):
    payload = payload.ljust(size, b'\x1a' if seq else b'\x00')
    hdr = bytes([STX if size == 1024 else SOH, seq & 0xff, 0xff - (seq & 0xff)])
    c = crc16(payload)
    return hdr + payload + bytes([c >> 8, c & 0xff])


def send(s, path, size=1024, chunk=0, gap=0.0, progress=None, retries=10):
    """chunk/gap: write the block in `chunk`-byte pieces with `gap` s pauses (0 = one write)."""
    data = open(path, 'rb').read()

    def tx(seq, payload, sz):
        blk = _block(seq, payload, sz)
        for _ in range(retries):
            if chunk:
                for i in range(0, len(blk), chunk):
                    s.write(blk[i:i + chunk]); s.flush(); time.sleep(gap)
            else:
                s.write(blk)
            r = _wait(s, (ACK, NAK, CAN), 10)
            if r == ACK:
                return True
            if r == CAN:
                raise IOError('receiver cancelled')
        raise IOError(f'block {seq} failed {retries}x (last reply {r})')

    if _wait(s, (CRC,), 60) is None:
        raise IOError("receiver never sent 'C'")
    name = os.path.basename(path).encode()
    tx(0, name + b'\x00' + str(len(data)).encode() + b'\x00', 128)
    _wait(s, (CRC,), 10)
    seq, t0 = 1, time.time()
    for off in range(0, len(data), size):
        tx(seq, data[off:off + size], size)
        seq += 1
        if progress and seq % 64 == 0:
            progress(off + size, len(data), time.time() - t0)
    for _ in range(retries):
        s.write(bytes([EOT]))
        if _wait(s, (ACK, NAK), 5) == ACK:
            break
    _wait(s, (CRC,), 5)
    tx(0, b'', 128)  # empty block 0 = end of batch
    return len(data), time.time() - t0
