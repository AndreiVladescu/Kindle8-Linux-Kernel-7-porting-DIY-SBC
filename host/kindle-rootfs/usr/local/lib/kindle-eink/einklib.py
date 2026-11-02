"""Shared drawing code for the Kindle 8 e-ink panel (used by kindle-eink.py and eink-say).

Panel: 600x800 portrait as read; the EPDC framebuffer /dev/fb0 is native 800x600 XRGB8888 and the
panel is mounted rotated, so a portrait image goes to the framebuffer with Pillow's ROTATE_90.

Updates: the mxc-epdc driver sends every damaged area as a partial GC16 update (only pixels that
change are driven, no full-screen flash). Panel.show() writes only the framebuffer rows that differ
from the previous frame, so a clock tick redraws a small band. Partial updates leave faint ghosting
over time; Panel.flash() clears it with a black and a white frame before the next image.
"""
import fcntl
import json
import os
import struct
import time

from PIL import Image, ImageDraw, ImageFont

FB = os.environ.get("EINK_FB", "/dev/fb0")
W, H = 600, 800                                   # portrait, as the panel is read
FB_W, FB_H = 800, 600                             # framebuffer (native scan orientation)
ROW = FB_W * 4                                    # bytes per framebuffer row (XRGB8888)
FONT_DIR = os.environ.get("EINK_FONT_DIR", "/usr/share/fonts/dejavu")
MSG_FILE = os.environ.get("EINK_MSG_FILE", "/var/lib/kindle-eink/message.json")

# Rows (portrait y) where this unit's e-ink layer is damaged: nothing is drawn there.
SKIP = tuple(int(v) for v in os.environ.get("EINK_SKIP", "495-595").split("-"))
MARGIN_L = int(os.environ.get("EINK_MARGIN_LEFT", "60"))     # clears a dead spot at the left edge
MARGIN_R = int(os.environ.get("EINK_MARGIN_RIGHT", "40"))

FBIOGET_VSCREENINFO, FBIOPUT_VSCREENINFO = 0x4600, 0x4601
FB_ACTIVATE_FORCE = 128


def font(name, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)


SANS, SANS_BOLD, MONO = "DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSansMono.ttf"


# ---------------------------------------------------------------- framebuffer

class Panel:
    def __init__(self, path=FB):
        self.path = path
        self.last = None                          # last framebuffer contents written

    def activate(self):
        """Force fb_set_par once: the DRM fbdev emulation only does the EPDC modeset there.
        Without a framebuffer console nothing else calls it, and writes never reach the panel."""
        with open(self.path, "r+b", buffering=0) as f:
            var = bytearray(160)                  # struct fb_var_screeninfo
            fcntl.ioctl(f, FBIOGET_VSCREENINFO, var)
            activate = struct.unpack_from("<I", var, 84)[0]
            struct.pack_into("<I", var, 84, activate | FB_ACTIVATE_FORCE)
            fcntl.ioctl(f, FBIOPUT_VSCREENINFO, var)

    @staticmethod
    def to_fb(img):
        fb = img.convert("L").transpose(Image.Transpose.ROTATE_90).convert("RGB")   # -> 800x600
        raw = fb.tobytes()
        out = bytearray(len(raw) // 3 * 4)        # XRGB8888 little endian = B,G,R,X
        out[0::4] = raw[2::3]
        out[1::4] = raw[1::3]
        out[2::4] = raw[0::3]
        return bytes(out)

    def show(self, img, force=False):
        """Write img (600x800 portrait). Only changed framebuffer rows are written unless force.
        Returns the number of rows written."""
        out = self.to_fb(img)
        fd = os.open(self.path, os.O_WRONLY)
        try:
            if force or self.last is None:
                os.pwrite(fd, out, 0)
                n = FB_H
            else:
                n, y = 0, 0
                while y < FB_H:                   # contiguous bands of changed rows
                    if out[y * ROW:(y + 1) * ROW] == self.last[y * ROW:(y + 1) * ROW]:
                        y += 1
                        continue
                    y0 = y
                    while y < FB_H and out[y * ROW:(y + 1) * ROW] != self.last[y * ROW:(y + 1) * ROW]:
                        y += 1
                    os.pwrite(fd, out[y0 * ROW:y * ROW], y0 * ROW)
                    n += y - y0
        finally:
            os.close(fd)
        self.last = out
        return n

    def flash(self, img, pause=1.2):
        """Clean refresh: full black, full white, then img (removes ghosting from partial updates)."""
        self.show(Image.new("L", (W, H), 0), force=True)
        time.sleep(pause)
        self.show(Image.new("L", (W, H), 255), force=True)
        time.sleep(pause)
        self.show(img, force=True)


# ---------------------------------------------------------------- text layout

def regions(top=24, bottom=H - 46):
    """Usable vertical bands (y0, y1) between top and bottom, minus the damaged rows."""
    out = []
    if SKIP[0] > top:
        out.append((top, min(SKIP[0] - 8, bottom)))
    if SKIP[1] + 8 < bottom:
        out.append((max(SKIP[1] + 8, top), bottom))
    return [r for r in out if r[1] > r[0]]


def wrap(draw, text, fnt, width):
    """Word-wrap text to width px; keeps explicit line breaks, breaks over-long words."""
    lines = []
    for para in text.split("\n"):
        words, cur = para.split(" "), ""
        for w in words:
            cand = w if not cur else cur + " " + w
            if draw.textlength(cand, font=fnt) <= width:
                cur = cand
                continue
            if cur:
                lines.append(cur)
            while draw.textlength(w, font=fnt) > width:      # hard-break a long word
                i = len(w)
                while i > 1 and draw.textlength(w[:i], font=fnt) > width:
                    i -= 1
                lines.append(w[:i])
                w = w[i:]
            cur = w
        lines.append(cur)
    return lines


def layout(draw, items, regs):
    """items: list of (lines, font, line_height). Places lines top-down through the regions.
    Returns [(x_unused, y, text, font)] or None if it does not fit."""
    placed, ri = [], 0
    y = regs[0][0]
    for lines, fnt, lh in items:
        for ln in lines:
            while y + lh > regs[ri][1]:
                ri += 1
                if ri >= len(regs):
                    return None
                y = regs[ri][0]
            placed.append((y, ln, fnt))
            y += lh
    return placed


def render_text(text, title=None, size=None, mono=False, center=False, footer=None):
    """Render a message page. size=None picks the largest font that fits."""
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    width = W - MARGIN_L - MARGIN_R
    regs = regions()
    body_face = MONO if mono else SANS

    def attempt(sz, regs, nowrap):
        items = []
        if title:
            tf = font(SANS_BOLD, max(int(sz * 1.2), 16))
            items.append((wrap(d, title, tf, width), tf, int(tf.size * 1.25)))
            items.append(([""], tf, int(sz * 0.5)))           # gap under the title
        bf = font(body_face, sz)
        if nowrap:                                           # keep lines intact (tables, command output)
            lines = text.split("\n")
            if any(d.textlength(ln, font=bf) > width for ln in lines):
                return None
        else:
            lines = wrap(d, text, bf, width)
        items.append((lines, bf, int(sz * 1.22)))
        return layout(d, items, regs)

    def best(regs, nowrap):
        sz = 160
        while sz >= 12:
            placed = attempt(sz, regs, nowrap)
            if placed is not None:
                return sz, placed
            sz = int(sz * 0.92)
        return 0, None

    if size:
        placed = attempt(size, regs, False)
        if placed is None:
            raise ValueError(f"text does not fit at size {size}; omit --size to auto-fit")
    else:
        # monospace: first try without wrapping, so columns stay aligned
        modes = [True, False] if mono else [False]
        for nowrap in modes:
            sz_all, placed = best(regs, nowrap)
            if placed is None:
                continue
            # prefer keeping a short text above the damaged band if that costs < 30 % of the size
            if len(regs) > 1:
                sz_top, placed_top = best(regs[:1], nowrap)
                if placed_top is not None and sz_top >= 0.7 * sz_all:
                    placed = placed_top
            break
        if placed is None:
            raise ValueError("text does not fit even at size 12")

    if center and placed:                          # centre vertically if it all sits in the first band
        y0, y1 = regs[0]
        last_y = placed[-1][0] + int(placed[-1][2].size * 1.22)
        if last_y <= y1:
            shift = ((y1 - y0) - (last_y - y0)) // 2
            placed = [(y + shift, t, f) for y, t, f in placed]

    for y, t, f in placed:
        x = MARGIN_L
        if center:
            x = MARGIN_L + (width - d.textlength(t, font=f)) // 2
        d.text((x, y), t, font=f, fill=0)

    if footer:
        ff = font(SANS, 20)
        d.line((MARGIN_L, H - 42, W - MARGIN_R, H - 42), fill=170, width=1)
        d.text((MARGIN_L, H - 36), footer, font=ff, fill=90)
    return img


# ---------------------------------------------------------------- message file

def read_message():
    """Current message dict or None (missing, unreadable or expired)."""
    try:
        with open(MSG_FILE) as f:
            m = json.load(f)
    except (OSError, ValueError):
        return None
    if m.get("expires") and time.time() >= m["expires"]:
        return None
    return m


def write_message(m):
    os.makedirs(os.path.dirname(MSG_FILE), exist_ok=True)
    tmp = MSG_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(m, f)
    os.replace(tmp, MSG_FILE)


def clear_message():
    try:
        os.remove(MSG_FILE)
    except FileNotFoundError:
        pass


def daemon_pid():
    """PID of the running kindle-eink.py daemon, or None."""
    me = os.getpid()
    for p in os.listdir("/proc"):
        if not p.isdigit() or int(p) == me:
            continue
        try:
            with open(f"/proc/{p}/cmdline", "rb") as f:
                argv = f.read().split(b"\0")
        except OSError:
            continue
        if any(a.endswith(b"kindle-eink.py") for a in argv[:3]):
            return int(p)
    return None
