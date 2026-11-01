#!/usr/bin/env python3
"""E-ink status screen for the Kindle 8 SBC.

Renders the device stats (from the local web server's /status.json) as a portrait
600x800 image and writes it to the EPDC framebuffer /dev/fb0 (native 800x600, XRGB8888).
The panel keeps the image without power, so it is only redrawn every INTERVAL seconds;
between updates the EPDC driver switches the panel's high voltage and VCOM off.

Orientation: the panel is mounted rotated relative to the EPDC scan, so a portrait pixel
(px, py) goes to framebuffer (x=py, y=599-px) — Pillow's ROTATE_90 (counter-clockwise).
"""
import json
import os
import socket
import time
import urllib.request

from PIL import Image, ImageDraw, ImageFont

FB = "/dev/fb0"
W, H = 600, 800                       # portrait, as the panel is read
INTERVAL = int(os.environ.get("EINK_INTERVAL", "300"))
STATUS_URL = os.environ.get("EINK_STATUS_URL", "http://127.0.0.1/status.json")
FONT_DIR = os.environ.get("EINK_FONT_DIR", "/usr/share/fonts/dejavu")


def font(name, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)


F_TITLE = font("DejaVuSans-Bold.ttf", 64)
F_SUB = font("DejaVuSans.ttf", 24)
F_LABEL = font("DejaVuSans.ttf", 26)
F_VALUE = font("DejaVuSans-Bold.ttf", 30)
F_SMALL = font("DejaVuSans.ttf", 20)


def wifi_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))   # TEST-NET address: no packet is sent, only routing
        return s.getsockname()[0]
    except OSError:
        return "offline"
    finally:
        s.close()


def fmt_uptime(sec):
    d, sec = divmod(int(sec), 86400)
    h, sec = divmod(sec, 3600)
    return f"{d}d {h}h {sec // 60}m" if d else f"{h}h {sec // 60}m"


def render(st):
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    m = 36                                                    # margin

    d.text((m, 36), st.get("hostname", "kindle8"), font=F_TITLE, fill=0)
    d.text((m, 116), "Kindle 8 · Linux " + st.get("kernel", "?").split()[0], font=F_SUB, fill=80)
    d.line((m, 160, W - m, 160), fill=0, width=3)

    b = st.get("battery", {})
    w = st.get("wifi") or {}
    rows = [
        ("IP address", wifi_ip()),
        ("Uptime", fmt_uptime(st.get("uptime_s", 0))),
        ("Load", " ".join(st.get("load", []))),
        ("Memory free", f'{st.get("mem_available_mb", "?")} / {st.get("mem_total_mb", "?")} MB'),
        ("Disk free", f'{st.get("disk_free_mb", 0) / 1024:.1f} / {st.get("disk_total_mb", 0) / 1024:.1f} GB'),
        ("SoC temp", f'{st.get("soc_temp_c", "?")} °C'),
        ("Battery", f'{b.get("capacity_pct", "?")} %  {b.get("status", "")}'),
        ("WiFi", f'{w.get("signal_dbm", "?")} dBm' if w else "not connected"),
    ]
    y = 180
    for label, value in rows:
        d.text((m, y), label, font=F_LABEL, fill=90)
        d.text((m, y + 32), str(value), font=F_VALUE, fill=0)
        y += 68
        d.line((m, y - 6, W - m, y - 6), fill=200, width=1)

    d.text((m, H - 44), "updated " + time.strftime("%Y-%m-%d %H:%M"), font=F_SMALL, fill=80)
    return img


def show(img):
    fb = img.transpose(Image.Transpose.ROTATE_90).convert("RGB")   # -> 800x600
    raw = fb.tobytes()                                             # R,G,B per pixel
    out = bytearray(len(raw) // 3 * 4)                             # XRGB8888 LE = B,G,R,X
    out[0::4] = raw[2::3]
    out[1::4] = raw[1::3]
    out[2::4] = raw[0::3]
    with open(FB, "wb") as f:
        f.write(out)


def fetch():
    with urllib.request.urlopen(STATUS_URL, timeout=10) as r:
        return json.load(r)


def main():
    while True:
        try:
            show(render(fetch()))
        except Exception as e:                                     # keep the service alive
            print("update failed:", repr(e), flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
