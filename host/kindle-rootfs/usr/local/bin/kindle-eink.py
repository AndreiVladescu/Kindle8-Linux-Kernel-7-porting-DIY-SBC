#!/usr/bin/env python3
"""E-ink status screen for the Kindle 8 SBC.

Every minute (on the minute) it redraws the panel with, in this order of priority,
  - a message set with `eink-say` (until it is cleared or expires; the WiFi setup wizard uses it),
  - the USB screen for EINK_USB_SCREEN_MIN minutes after a PC attaches over USB (0 = while attached),
  - the status page: hostname, IP, uptime, load, memory, disk, SoC temperature, battery, WiFi
    (from the local web server's /status.json).
The USB state is checked every 2 s, so attaching shows the USB screen right away.
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
USB_SCREEN_MIN = int(os.environ.get("EINK_USB_SCREEN_MIN", "3"))
UDC_STATE = "/sys/class/udc/ci_hdrc.0/state"
USB_IP = "192.168.7.2"

F_TITLE = E.font(E.SANS_BOLD, 64)
F_SUB = E.font(E.SANS, 24)
F_LABEL = E.font(E.SANS, 26)
F_VALUE = E.font(E.SANS_BOLD, 30)

wake = threading.Event()
clean_now = threading.Event()
usb_since = None                                   # time the PC attached over USB, None if not attached


def usb_attached():
    try:
        with open(UDC_STATE) as f:
            return f.read().strip() == "configured"
    except OSError:
        return False


def update_usb():
    """Track attach/detach; True if the state changed."""
    global usb_since
    att = usb_attached()
    if att and usb_since is None:
        usb_since = time.time()
        return True
    if not att and usb_since is not None:
        usb_since = None
        return True
    return False


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
    sub = "Linux " + st.get("kernel", "?").split()[0] + " · " + time.strftime("%a %d %b %H:%M")
    if usb_since is not None:
        sub += " · USB"
    d.text((m, 108), sub, font=F_SUB, fill=80)
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


def usb_icon(d, cx, top, h, w=12):
    """USB trident, h px tall, starting at y=top."""
    tip, base = top, top + h
    d.polygon([(cx, tip), (cx - 30, tip + 48), (cx + 30, tip + 48)], fill=0)            # arrow head
    d.line((cx, tip + 40, cx, base - 30), fill=0, width=w)                               # stem
    d.ellipse((cx - 30, base - 60, cx + 30, base), fill=0)                               # base
    ly, ry = top + h * 0.68, top + h * 0.52                                              # branch joints
    d.line((cx, ly, cx - 75, ly - 60, cx - 75, ly - 105), fill=0, width=w, joint="curve")
    d.ellipse((cx - 75 - 20, ly - 125, cx - 75 + 20, ly - 85), fill=0)                   # round end
    d.line((cx, ry, cx + 75, ry - 60, cx + 75, ry - 95), fill=0, width=w, joint="curve")
    d.rectangle((cx + 75 - 20, ry - 130, cx + 75 + 20, ry - 90), fill=0)                 # square end


def render_usb():
    img = Image.new("L", (E.W, E.H), 255)
    d = ImageDraw.Draw(img)
    width = E.W - E.MARGIN_L - E.MARGIN_R
    cx = E.MARGIN_L + width // 2
    top, bottom = E.regions()[0]
    usb_icon(d, cx, top + 30, 300)
    f = E.font(E.SANS_BOLD, 54)
    t = "USB connected"
    d.text((cx - d.textlength(t, font=f) / 2, bottom - 90), t, font=f, fill=0)
    y = E.SKIP[1] + 16
    for text, fnt, fill in (("Drive KINDLE8: WiFi setup", E.font(E.SANS, 27), 40),
                            (f"ssh root@{USB_IP}", E.font(E.MONO, 27), 0),
                            (f"http://{USB_IP}/setup", E.font(E.MONO, 27), 0)):
        d.text((cx - d.textlength(text, font=fnt) / 2, y), text, font=fnt, fill=fill)
        y += 46
    ff = E.font(E.SANS, 20)
    d.line((E.MARGIN_L, E.H - 42, E.W - E.MARGIN_R, E.H - 42), fill=170, width=1)
    d.text((E.MARGIN_L, E.H - 36), f"{socket.gethostname()} · WiFi {wifi_ip()} · {time.strftime('%H:%M')}",
           font=ff, fill=90)
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
    if usb_since is not None and (USB_SCREEN_MIN == 0 or time.time() - usb_since < USB_SCREEN_MIN * 60):
        return render_usb()
    return render_status(fetch())


def sleep_until_next_tick():
    """Sleep to the next INTERVAL boundary (on the minute for 60 s); SIGUSR1/2, a USB attach/detach
    and the end of the USB screen period wake early."""
    end = time.time() + INTERVAL - (time.time() % INTERVAL) + 0.2
    msg = E.read_message()
    if msg and msg.get("expires") and msg["expires"] + 0.2 < end:
        end = msg["expires"] + 0.2                  # an expiring message goes away on time
    usb_end = usb_since + USB_SCREEN_MIN * 60 if usb_since is not None and USB_SCREEN_MIN else None
    while time.time() < end:
        if wake.wait(min(2.0, max(end - time.time(), 0.05))):
            break
        if update_usb() or (usb_end and time.time() >= usb_end):
            break
    wake.clear()


def main():
    signal.signal(signal.SIGUSR1, lambda *_: wake.set())
    signal.signal(signal.SIGUSR2, lambda *_: (clean_now.set(), wake.set()))
    panel = E.Panel()
    panel.activate()
    update_usb()
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
