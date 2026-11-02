#!/usr/bin/env python3
"""E-ink status screen for the Kindle 8 SBC.

Every minute (on the minute) it redraws the panel with either
  - the status page: hostname, IP, uptime, load, memory, disk, SoC temperature, battery, WiFi
    (from the local web server's /status.json), or
  - a message set with `eink-say` (until it is cleared or expires).
Only the rows that changed are sent to the panel (partial update, no flash). A clean black/white
refresh against ghosting runs every EINK_CLEAN_MIN minutes (0 = never).

Signals: SIGUSR1 = redraw now (eink-say sends it), SIGUSR2 = clean refresh now.
Settings (environment, see /etc/conf.d/kindle-eink): EINK_INTERVAL (s, default 60),
EINK_CLEAN_MIN (default 60), EINK_STATUS_URL, EINK_SKIP, EINK_MARGIN_LEFT/RIGHT.
"""
import json
import os
import signal
import socket
import sys
import threading
import time
import urllib.request

sys.path.insert(0, "/usr/local/lib/kindle-eink")
from PIL import Image, ImageDraw                                    # noqa: E402
import einklib as E                                                 # noqa: E402

INTERVAL = int(os.environ.get("EINK_INTERVAL", "60"))
CLEAN_MIN = int(os.environ.get("EINK_CLEAN_MIN", "60"))
STATUS_URL = os.environ.get("EINK_STATUS_URL", "http://127.0.0.1/status.json")

F_TITLE = E.font(E.SANS_BOLD, 64)
F_SUB = E.font(E.SANS, 24)
F_LABEL = E.font(E.SANS, 26)
F_VALUE = E.font(E.SANS_BOLD, 30)

wake = threading.Event()
clean_now = threading.Event()


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


def fetch():
    with urllib.request.urlopen(STATUS_URL, timeout=10) as r:
        return json.load(r)


def render_status(st):
    img = Image.new("L", (E.W, E.H), 255)
    d = ImageDraw.Draw(img)
    m = E.MARGIN_L

    d.text((m, 30), st.get("hostname", "kindle8"), font=F_TITLE, fill=0)
    d.text((m, 108), "Linux " + st.get("kernel", "?").split()[0] + " · " + time.strftime("%a %d %b %H:%M"),
           font=F_SUB, fill=80)
    d.line((m, 150, E.W - m, 150), fill=0, width=3)

    b = st.get("battery", {})
    w = st.get("wifi") or {}
    rows = [
        ("IP", wifi_ip()),
        ("Uptime", fmt_uptime(st.get("uptime_s", 0))),
        ("Load", " ".join(st.get("load", [])[:2])),
        ("Memory", f'{st.get("mem_available_mb", "?")} MB free'),
        ("Disk", f'{st.get("disk_free_mb", 0) / 1024:.1f} GB free'),
        ("SoC", f'{st.get("soc_temp_c", "?")} °C'),
        ("Battery", f'{b.get("capacity_pct", "?")} % {b.get("status", "")}'),
        ("WiFi", f'{w.get("signal_dbm", "?")} dBm' if w else "off"),
    ]
    row_h, y = 58, 172
    for label, value in rows:
        if y + row_h > E.SKIP[0] and y < E.SKIP[1]:                # jump over the damaged band
            y = E.SKIP[1] + 12
        d.text((m, y + 6), label, font=F_LABEL, fill=90)
        tw = d.textlength(str(value), font=F_VALUE)
        d.text((E.W - m - tw, y + 2), str(value), font=F_VALUE, fill=0)
        y += row_h
        d.line((m, y - 6, E.W - m, y - 6), fill=200, width=1)
    return img


def render_message(msg):
    footer = None
    if msg.get("footer", True):
        footer = f"{socket.gethostname()} · {wifi_ip()} · {time.strftime('%H:%M')}"
    return E.render_text(msg.get("text", ""), title=msg.get("title"), size=msg.get("size"),
                         mono=msg.get("mono", False), center=msg.get("center", False), footer=footer)


def frame():
    msg = E.read_message()
    if msg:
        return render_message(msg)
    return render_status(fetch())


def sleep_until_next_tick():
    """Sleep to the next INTERVAL boundary (on the minute for 60 s); SIGUSR1/2 wake early."""
    now = time.time()
    wake.wait(INTERVAL - (now % INTERVAL) + 0.2)
    wake.clear()


def main():
    signal.signal(signal.SIGUSR1, lambda *_: wake.set())
    signal.signal(signal.SIGUSR2, lambda *_: (clean_now.set(), wake.set()))
    panel = E.Panel()
    panel.activate()
    last_clean = 0.0
    while True:
        try:
            img = frame()
            due = CLEAN_MIN > 0 and time.time() - last_clean >= CLEAN_MIN * 60
            if due or clean_now.is_set():
                clean_now.clear()
                panel.flash(img)
                last_clean = time.time()
            else:
                panel.show(img)
        except Exception as e:                                     # keep the service alive
            print("update failed:", repr(e), flush=True)
        sleep_until_next_tick()


if __name__ == "__main__":
    main()
