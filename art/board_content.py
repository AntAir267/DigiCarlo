# What the program pins on the board: snapshots, session cards, pins.
import math, random
from PIL import Image, ImageDraw, ImageFont, ImageFilter
HAND = "/home/antair/.local/share/fonts/Gloria Hallelujah regular.ttf"
COOPER = "/home/antair/.local/share/fonts/COOPBL.TTF"
NUN = "/usr/share/fonts/truetype/nunito/Nunito-Black.ttf"
W, H = 1272, 540
layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
random.seed(12)

def photo(n, caption, colour, night):
    w, h = 184, 222
    im = Image.new("RGBA", (w, h), (252, 250, 243, 255))
    d = ImageDraw.Draw(im)
    sky = (43, 45, 99) if night else random.choice([(143, 211, 244), (166, 200, 240), (158, 217, 234), (244, 178, 106)])
    hill = (39, 64, 74) if night else random.choice([(79, 174, 74), (98, 184, 76), (63, 158, 85)])
    x0, y0, x1, y1 = 12, 12, w - 12, 164
    for y in range(y0, y1):
        t = (y - y0) / (y1 - y0)
        d.line([(x0, y), (x1, y)], fill=tuple(int(c * (1 - 0.25 * t) + 64 * t) for c in sky))
    sx = random.randint(50, 130)
    d.ellipse([sx - 14, 36, sx + 14, 64], fill=(246, 241, 216) if night else (255, 210, 63))
    pts = [(x0, y1)] + [(x, 120 - 18 * math.sin(x / 26 + n)) for x in range(x0, x1 + 1, 4)] + [(x1, y1)]
    d.polygon(pts, fill=hill)
    if n % 3 != 2:
        hx = random.randint(40, 120)
        d.rectangle([hx, 122, hx + 26, 146], fill=(244, 239, 225))
        d.polygon([(hx - 5, 124), (hx + 13, 106), (hx + 31, 124)], fill=(192, 57, 43))
    d.text((w / 2, 194), caption, font=ImageFont.truetype(HAND, 30), fill=colour, anchor="mm")
    return im

def place(im, cx, cy, rot, scale=0.5, lift=0, picked=False):
    im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    x, y = int(cx - im.width / 2), int(cy - im.height / 2 - lift)
    a = im.split()[3]
    sh = Image.new("RGBA", im.size, (40, 22, 8, 120 if not lift else 150))
    shadow.paste(sh, (x + 5 + lift // 2, y + 7 + lift), a)
    if picked:
        g = Image.new("RGBA", (im.width + 24, im.height + 24), (0, 0, 0, 0))
        ImageDraw.Draw(g).rounded_rectangle([0, 0, g.width - 1, g.height - 1], 16, fill=(255, 214, 60, 230))
        glow.paste(g, (x - 12, y - 12), g)
    layer.paste(im, (x, y), im)
    return x, y, im.width

def pin(x, y, col):
    d = ImageDraw.Draw(shadow)
    d.ellipse([x - 3, y + 3, x + 11, y + 11], fill=(30, 15, 5, 110))
    d = ImageDraw.Draw(layer)
    d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=col + (255,), outline=(60, 20, 10, 255), width=1)
    d.ellipse([x - 4, y - 5, x + 0, y - 1], fill=(255, 255, 255, 190))

def sticker(x, y, n):
    d = ImageDraw.Draw(layer)
    d.ellipse([x - 12, y - 12, x + 12, y + 12], fill=(255, 255, 255, 255), outline=(50, 40, 30, 255), width=2)
    d.text((x, y + 1), str(n), font=ImageFont.truetype(NUN, 13), fill=(40, 30, 20), anchor="mm")

def card(title, lines, cx, cy, rot):
    w, h = 400, 250
    im = Image.new("RGBA", (w, h), (253, 252, 246, 255))
    d = ImageDraw.Draw(im)
    d.line([(0, 62), (w, 62)], fill=(226, 107, 107), width=3)
    for k in range(5):
        d.line([(10, 100 + k * 34), (w - 10, 100 + k * 34)], fill=(156, 195, 230), width=2)
    d.text((22, 34), title, font=ImageFont.truetype(COOPER, 36), fill=(40, 26, 18), anchor="lm")
    for k, (t, col) in enumerate(lines):
        d.text((20, 88 + k * 34), t, font=ImageFont.truetype(HAND, 25), fill=col, anchor="lm")
    x, y, _ = place(im, cx, cy, rot, 0.47)
    pin(int(cx), int(y + 8), (255, 214, 60))

BLUE, RED, GREY = (29, 79, 154), (192, 57, 43), (90, 90, 90)
card("Session 1", [("camera said Jan 1, 2007", GREY), ("12:00 - 12:13 pm", GREY),
                   ("dated Sep 23", BLUE), ("8:54 - 9:08 am", BLUE)], 172, 158, -2)
card("Session 2", [("camera said Jan 1, 2007", GREY), ("12:00 - 12:05 pm", GREY),
                   ("9-12: Sep 20, 6:30 pm", RED), ("13-16: Sep 23, 9:11 am", BLUE)], 172, 292, 1.5)
pins = [(216, 50, 42), (30, 79, 208), (47, 168, 79), (124, 92, 201), (255, 214, 60)]
t1 = ["8:54", "8:55", "8:56", "8:56", "9:04", "9:06", "9:07", "9:08"]
for i, t in enumerate(t1):
    cx, cy = 340 + i * 108, 158
    rot = random.uniform(-4, 4)
    x, y, w = place(photo(i, t, BLUE, i in (0, 2)), cx, cy, rot)
    pin(int(cx), int(y + 6), random.choice(pins))
    sticker(x + 8, y + 14, i + 1)
t2 = ["6:30 pm", "6:30 pm", "6:30 pm", "6:31 pm", "9:11", "9:12", "9:13", "9:14"]
for i, t in enumerate(t2):
    n = i + 9
    picked = n <= 12
    cx, cy = 340 + i * 108, 292
    rot = 0 if picked else random.uniform(-4, 4)
    x, y, w = place(photo(n, t, RED if picked else BLUE, n in (9, 16)), cx, cy, rot,
                    lift=6 if picked else 0, picked=picked)
    pin(int(cx), int(y + 6), (216, 50, 42) if picked else random.choice(pins))
    sticker(x + 8, y + 14, n)
shadow = shadow.filter(ImageFilter.GaussianBlur(4))
glow = glow.filter(ImageFilter.GaussianBlur(7))
out = Image.alpha_composite(Image.alpha_composite(shadow, glow), layer)
out.save("out/board_content.png")
bg = Image.open("out/board_w.png").convert("RGBA")
Image.alpha_composite(bg, out).save("out/board_filled.png")
print("ok")
