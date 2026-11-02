#!/usr/bin/env python3
"""Draw the article favicon (icon.ico): a 32x32 pixel-art Kindle with a cracked e-ink
screen showing a shell prompt, and the amber charge LED. Same style as the other articles'
icons (dark tile, cut corners, flat greys). Usage: tools/make-icon.py [out.ico] [preview.png]"""
import sys
from PIL import Image

BG, EDGE = (49, 49, 49), (35, 30, 34)
BODY, BODY_HI, BODY_LO = (24, 24, 27), (70, 72, 78), (12, 12, 14)
PAPER, PAPER_HI, INK, INK_LT = (204, 214, 222), (225, 232, 238), (60, 66, 74), (138, 153, 164)
CRACK = (100, 110, 119)
LED = (255, 160, 20)

im = Image.new("RGBA", (32, 32), BG + (255,))
px = im.load()


def rect(x0, y0, x1, y1, c):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            px[x, y] = c + (255,)


# tile border with cut corners
for i in range(32):
    for p in ((i, 0), (i, 31), (0, i), (31, i)):
        px[p] = EDGE + (255,)
for x, y in ((1, 1), (30, 1), (1, 30), (30, 30)):
    px[x, y] = EDGE + (255,)

# device body (portrait), rounded corners, highlight top-left, shade bottom-right
rect(7, 3, 24, 28, BODY)
rect(8, 3, 23, 3, BODY_HI); rect(7, 4, 7, 27, BODY_HI)
rect(8, 28, 23, 28, BODY_LO); rect(24, 4, 24, 27, BODY_LO)
for x, y in ((7, 3), (24, 3), (7, 28), (24, 28)):
    px[x, y] = BG + (255,)

# e-ink screen
rect(9, 5, 22, 23, PAPER)
rect(9, 5, 22, 5, PAPER_HI); rect(9, 5, 9, 23, PAPER_HI)

# shell prompt ">_" and a few text lines
for x, y in ((11, 7), (12, 8), (11, 9)):
    px[x, y] = INK + (255,)
rect(14, 9, 16, 9, INK)
for y, x1 in ((12, 20), (14, 18), (16, 20), (18, 16)):
    rect(11, y, x1, y, INK_LT)

# crack from the lower-left corner (the broken panel)
for x, y in ((9, 22), (10, 21), (11, 21), (12, 20), (13, 20), (14, 19), (15, 18), (16, 18),
             (17, 17), (18, 16), (12, 21), (12, 22)):
    px[x, y] = CRACK + (255,)

# amber charge LED on the bottom bezel
rect(15, 26, 16, 26, LED)

out = sys.argv[1] if len(sys.argv) > 1 else "icon.ico"
im.save(out, sizes=[(32, 32)])
if len(sys.argv) > 2:
    im.resize((256, 256), Image.NEAREST).save(sys.argv[2])
