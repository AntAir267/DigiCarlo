import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter
F = {
    "cooper": "/home/antair/.local/share/fonts/COOPBL.TTF",
    "hand": "/home/antair/.local/share/fonts/Gloria Hallelujah regular.ttf",
    "nunito": "/usr/share/fonts/truetype/nunito/Nunito-Black.ttf",
    "franklin": "/home/antair/.local/share/fonts/FRAHV.TTF",
}
def font(k, s): return ImageFont.truetype(F[k], s)

# snapshots: little landscapes in a white border, as prints
random.seed(4)
for n in range(8):
    W, H = 240, 290
    im = Image.new("RGB", (W, H), (250, 248, 240))
    d = ImageDraw.Draw(im)
    night = n in (1, 5)
    sky = (43, 45, 99) if night else random.choice([(143, 211, 244), (166, 200, 240), (158, 217, 234), (244, 178, 106)])
    hill = (39, 64, 74) if night else random.choice([(79, 174, 74), (98, 184, 76), (63, 158, 85)])
    px0, py0, px1, py1 = 16, 16, W - 16, 216
    for y in range(py0, py1):
        t = (y - py0) / (py1 - py0)
        col = tuple(int(c * (1 - 0.25 * t) + 255 * 0.25 * t) for c in sky)
        d.line([(px0, y), (px1, y)], fill=col)
    sx = random.randint(60, 180)
    d.ellipse([sx - 18, 50, sx + 18, 86], fill=(246, 241, 216) if night else (255, 210, 63))
    pts = [(px0, py1)] + [(x, 160 - 25 * __import__("math").sin(x / 35 + n)) for x in range(px0, px1 + 1, 6)] + [(px1, py1)]
    d.polygon(pts, fill=hill)
    if n % 3 != 2:
        hx = random.randint(60, 150)
        d.rectangle([hx, 160, hx + 34, 190], fill=(244, 239, 225))
        d.polygon([(hx - 6, 162), (hx + 17, 140), (hx + 40, 162)], fill=(192, 57, 43))
    d.text((W / 2, 252), random.choice(["8:54", "9:04", "9:07", "summer!", "Sep 23"]), font=font("hand", 24), fill=(29, 79, 154), anchor="mm")
    im.save(f"tex/snap{n}.png")

# calendar page, left blank: the program prints today's date on it
im = Image.new("RGB", (400, 560), (252, 250, 244))
d = ImageDraw.Draw(im)
d.rectangle([0, 0, 400, 120], fill=(216, 50, 42))
for y in range(135, 150, 6):
    d.line([(20, y), (380, y)], fill=(230, 226, 214), width=2)
im.save("tex/calendar.png")

# sticky note, blank: the program writes how many shots are waiting
im = Image.new("RGB", (300, 300), (255, 238, 120))
im.save("tex/sticky.png")

# luggage tag on the card reader, blank: the program writes how many are new
im = Image.new("RGB", (360, 160), (255, 216, 58))
d = ImageDraw.Draw(im)
d.ellipse([18, 62, 50, 94], fill=(250, 250, 250), outline=(60, 40, 20), width=4)
im.save("tex/tag.png")

# SD card, its label blank: the program writes the card's name
im = Image.new("RGB", (240, 320), (30, 64, 132))
d = ImageDraw.Draw(im)
d.rounded_rectangle([20, 110, 220, 300], 16, fill=(244, 239, 225))
for i in range(7):
    d.rectangle([22 + i * 28, 10, 38 + i * 28, 60], fill=(255, 205, 60))
im.save("tex/sdcard.png")

# crate label
im = Image.new("RGB", (480, 110), (250, 250, 246))
d = ImageDraw.Draw(im)
d.text((240, 56), "ORIGINALS", font=font("nunito", 70), fill=(40, 30, 20), anchor="mm")
im.save("tex/originals.png")

# "develop me!" note on the darkroom door
im = Image.new("RGB", (340, 130), (250, 250, 246))
d = ImageDraw.Draw(im)
d.text((170, 64), "develop me!", font=font("hand", 54), fill=(40, 30, 20), anchor="mm")
im.save("tex/develop.png")

# paper tags for the tools on the Photo Board's ledge, handwritten
for name, text in (("t_stamp", "set a date"), ("t_clock", "camera's date"), ("t_eraser", "automatic"), ("t_bin", "leave out")):
    im = Image.new("RGB", (340, 90), (251, 249, 242))
    d = ImageDraw.Draw(im)
    d.text((170, 44), text, font=font("hand", 44), fill=(40, 30, 20), anchor="mm")
    im.save(f"tex/{name}.png")
print("textures ok")
