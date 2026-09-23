# The radio's dial faces: the stations are what the keys do.
from PIL import Image, ImageDraw, ImageFont
COND = "/home/antair/.local/share/fonts/FRADMCN.TTF"
NUN = "/usr/share/fonts/truetype/nunito/Nunito-Black.ttf"
import os
if not os.path.exists(COND):
    COND = NUN
W, H = 760, 132            # 2x the dial window (380 x 66)
KEYS = [-136, -68, 0, 68, 136]     # key centres, in console units
def dial(name, labels, lit):
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    for y in range(H):                      # warm backlit glass
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(255 - 18 * t), int(222 - 40 * t), int(140 - 60 * t)))
    for x in range(40, W - 40, 12):         # the frequency scale
        long = (x - 40) % 60 == 0
        d.line([(x, 14), (x, 24 if long else 19)], fill=(90, 55, 25), width=2)
    for i, kc in enumerate(("55", "60", "70", "80", "100", "130", "160")):
        x = 40 + i * (W - 80) / 6
        d.text((x, 34), kc, font=ImageFont.truetype(NUN, 15), fill=(120, 75, 35), anchor="mm")
    d.line([(30, 48), (W - 30, 48)], fill=(120, 75, 35), width=2)
    for i, lab in enumerate(labels):
        x = W / 2 + KEYS[i] * 2
        lines = lab.split("|")
        col = (180, 30, 20) if i + 1 == lit else (55, 32, 15)
        for k, line in enumerate(lines):
            y = 90 + (k - (len(lines) - 1) / 2) * 26
            d.text((x, y), line, font=ImageFont.truetype(COND, 26 if len(lines) == 1 else 22), fill=col, anchor="mm")
        d.line([(x, 52), (x, 60)], fill=(120, 75, 35), width=3)
    im.save(name)
# one face per key pushed in (0 = none), so the lit station matches the key
for lit in range(6):
    dial(f"tex/dial_garage_{lit}.png", ["CHECK|CARD", "EJECT", "ERASE|CARD", "SYNC", "LIBRARY"], lit)
    dial(f"tex/dial_board_{lit}.png", ["VIEW", "ROTATE", "NAME", "PLACE", "UNDO"], lit)
print("dials ok")
