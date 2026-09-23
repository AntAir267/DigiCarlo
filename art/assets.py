# Turn the renders in out/ into what the program ships, in
# ../digicarlo/scenes/: each background, the pieces it swaps in (a card in
# the reader, a key pushed in, a counter digit), a glow for every clickable
# thing and a map saying which thing is where, and scenes.json saying where
# each piece goes and where the program paints its own text.
#
# The variants are rendered with the bounced light of one saved pass, so they
# differ from the background only where something changed, give or take a
# few shades. A piece is the variant's pixels over the thing that changed
# and its surroundings (its shadow, the light it throws), feathered at the
# edge; everywhere else the background stands, so the few shades of
# difference never show.
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from camera import Camera, face

OUT = "out"
DEST = os.path.join("..", "digicarlo", "scenes")
CHECK = len(sys.argv) > 1 and sys.argv[1] == "check"


def load(name):
    return np.asarray(Image.open(os.path.join(OUT, name)).convert("RGB")).astype(np.int16)


def mask_image(m):
    return Image.fromarray((m * 255).astype(np.uint8))


def bbox(a, floor=0):
    ys, xs = np.nonzero(a > floor)
    if not len(xs):
        raise SystemExit("assets: a variant came out the same as its background")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def grow(m, px):
    """A mask grown by about px pixels (in steps, as big filters are slow)."""
    while px > 0:
        step = min(px, 12)
        m = m.filter(ImageFilter.MaxFilter(2 * step + 1))
        px -= step
    return m


def piece(variant, base, where, soft=8):
    """`variant` over the mask `where`, feathered, as an RGBA image and
    where it goes. Checks that something did change there."""
    inside = np.asarray(where) > 127
    if not (np.abs(variant - base).max(axis=2)[inside] > 24).any():
        raise SystemExit("assets: a variant came out the same as its background")
    alpha = np.asarray(where.filter(ImageFilter.GaussianBlur(soft)))
    x0, y0, x1, y1 = bbox(alpha, 2)
    rgba = np.dstack([variant[y0:y1, x0:x1].astype(np.uint8), alpha[y0:y1, x0:x1]])
    return Image.fromarray(rgba, "RGBA"), (x0, y0)


def disc(size, centre, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).ellipse([centre[0] - radius, centre[1] - radius,
                               centre[0] + radius, centre[1] + radius], fill=255)
    return m


def quad(size, corners):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).polygon([tuple(c) for c in corners], fill=255)
    return m


def union(*masks):
    out = masks[0]
    for m in masks[1:]:
        out = Image.fromarray(np.maximum(np.asarray(out), np.asarray(m)))
    return out


def outline(everything, without):
    """The visible outline of the one thing left out of `without`."""
    m = mask_image(np.abs(everything - without).max(axis=2) > 6)
    return m.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))


def glow(m):
    """A warm glow around a thing and a little light on it, to be screened
    over the picture while the mouse is on it."""
    inside = np.asarray(m.filter(ImageFilter.GaussianBlur(1))) / 255.0
    halo = np.asarray(m.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(12))) / 255.0
    halo = np.clip(halo * 1.8, 0, 1) * (1 - inside)
    a_in, a_halo = inside * 0.30, halo * 0.80
    alpha = np.maximum(a_in, a_halo)
    warm = np.array([255, 208, 84], float)
    cream = np.array([255, 246, 220], float)
    t = (a_in / np.maximum(alpha, 1e-6))[..., None]
    rgb = cream * t + warm * (1 - t)
    img = np.dstack([rgb, alpha * 255]).round().astype(np.uint8)
    x0, y0, x1, y1 = bbox(img[..., 3], 1)
    return Image.fromarray(img[y0:y1, x0:x1], "RGBA"), (x0, y0)


class Scene:
    def __init__(self, name, size):
        self.name = name
        self.size = size
        self.info = {"size": list(size), "pieces": {}, "hotspots": {}, "surfaces": {}}
        os.makedirs(DEST, exist_ok=True)

    def background(self, render):
        img = Image.open(os.path.join(OUT, render)).convert("RGB")
        img.save(os.path.join(DEST, "%s.jpg" % self.name), quality=95, subsampling=0)
        self.info["background"] = "%s.jpg" % self.name

    def add_piece(self, key, img, at):
        fn = "%s-%s.png" % (self.name, key)
        img.save(os.path.join(DEST, fn), optimize=True)
        self.info["pieces"][key] = {"file": fn, "at": list(at)}

    def hotspots(self, spots, quick_all, quick_hidden):
        """spots: [(number, name)]; the map is at half size, one byte a pixel."""
        everything = load(quick_all)
        hitmap = np.zeros(everything.shape[:2], np.uint8)
        self.outlines = {}
        for number, name in spots:
            m = outline(everything, load(quick_hidden % number))
            self.outlines[name] = m
            a = np.asarray(m) > 127
            hitmap[a & (hitmap == 0)] = number
            img, at = glow(m)
            fn = "%s-glow-%s.png" % (self.name, name)
            img.save(os.path.join(DEST, fn), optimize=True)
            self.info["hotspots"][str(number)] = {"name": name, "glow": fn, "at": list(at)}
        fn = "%s-map.png" % self.name
        Image.fromarray(hitmap[1::2, 1::2]).save(os.path.join(DEST, fn), optimize=True)
        self.info["map"] = fn
        return hitmap

    def surface(self, key, corners, tex):
        """Somewhere the program paints: corners top-left, top-right,
        bottom-right, bottom-left, and the size it lays text out in."""
        self.info["surfaces"][key] = {"corners": [[round(x, 1), round(y, 1)] for x, y in corners],
                                      "size": list(tex)}

    def check(self, render, hitmap=None):
        """A picture to look at: surfaces outlined, hotspots tinted."""
        img = Image.open(os.path.join(OUT, render)).convert("RGB")
        if hitmap is not None:
            tint = np.asarray(img).astype(float)
            colours = [(255, 60, 60), (60, 200, 60), (60, 120, 255), (255, 200, 0),
                       (220, 60, 220), (0, 200, 200), (255, 120, 0), (140, 90, 255),
                       (120, 255, 120), (255, 255, 255)]
            for n in range(1, int(hitmap.max()) + 1):
                sel = hitmap == n
                tint[sel] = tint[sel] * 0.5 + np.array(colours[(n - 1) % len(colours)]) * 0.5
            img = Image.fromarray(tint.astype(np.uint8))
        d = ImageDraw.Draw(img)
        for key, s in self.info["surfaces"].items():
            pts = [tuple(p) for p in s["corners"]]
            d.line(pts + [pts[0]], fill=(255, 0, 255), width=3)
            d.ellipse([pts[0][0] - 5, pts[0][1] - 5, pts[0][0] + 5, pts[0][1] + 5], fill=(0, 255, 0))
        img.save(os.path.join(OUT, "check-%s.png" % self.name))


# ---------------------------------------------------------------------------
# The garage
# ---------------------------------------------------------------------------

W, H = 2544, 1080
g = Scene("garage", (W, H))
g.background("garage.png")
base = load("garage.png")
gmap = g.hotspots([(1, "card"), (2, "blink"), (3, "door"), (4, "board"), (5, "crate"), (6, "car")],
                  "garage-q.png", "garage-q-hide%d.png")
cam = Camera((-10, 138, -150), (0, 118, 400), W, H, angle=72)
# the card and camera with their shadows (and the reader's light), and the
# red the safelight throws
reader = disc((W, H), cam.project((-231, 100, 342.3)), 24)
g.add_piece("card", *piece(load("garage-card.png"), base,
                           grow(union(g.outlines["card"], reader), 40)))
g.add_piece("blink", *piece(load("garage-blink.png"), base, grow(g.outlines["blink"], 40)))
g.add_piece("safelight", *piece(load("garage-safelight.png"), base,
                                disc((W, H), cam.project((-27, 219, 392)), 230)))
g.surface("card", face(cam, 13, 18, -0.9, [("rotate", (-8, 0, 0)), ("translate", (-252, 99, 352))]), (240, 320))
g.surface("tag", face(cam, 26, 11.5, -0.2, [("rotate", (0, 0, 8)), ("rotate", (0, -12, 0)),
                                              ("translate", (-214, 88, 343))]), (360, 160))
g.surface("calendar", face(cam, 42, 59, -0.3, [("translate", (232, 150, 399.2))]), (400, 560))
g.surface("sticky", face(cam, 27, 27, -0.2, [("rotate", (0, 0, -5)), ("translate", (44 + 136, 106 + 16, 395.3))]), (300, 300))
if CHECK:
    g.check("garage-card.png", gmap)

# ---------------------------------------------------------------------------
# The console
# ---------------------------------------------------------------------------

W, H = 2544, 460
c = Scene("console-garage", (W, H))
c.background("console-garage.png")
base = load("console-garage.png")
cmap = c.hotspots([(1, "key1"), (2, "key2"), (3, "key3"), (4, "key4"), (5, "key5"),
                   (6, "knob-left"), (7, "knob-right"), (8, "start"), (9, "screen"), (10, "counter")],
                  "console-garage-q.png", "console-garage-q-hide%d.png")
cam = Camera((0, 150, -800), (0, 0, 0), W, H, ortho=(1272, 230))
# a key pushed in lights its station on the dial and swings the needle there
RC = 34
dial = quad((W, H), face(cam, 380, 66, -21.5, [("translate", (RC - 190, 17, 0))]))
for k in range(1, 6):
    c.add_piece("key%d" % k, *piece(load("console-garage-key%d.png" % k), base,
                                    union(grow(c.outlines["key%d" % k], 24), dial)))
lamp = grow(c.outlines["start"], 70)
c.add_piece("start", *piece(load("console-garage-start.png"), base, lamp))
c.add_piece("stop", *piece(load("console-garage-stop.png"), base, lamp))
SX = -412
c.surface("screen", face(cam, 358, 146, -1, [("translate", (SX - 179, -71, 0))]), (716, 292))
# the counter's drums, each cut from the render showing that digit
KX = 372
for d in range(10):
    img = Image.open(os.path.join(OUT, "console-garage.png" if d == 0 else
                                  "console-garage-digit%d.png" % d)).convert("RGBA")
    for i in range(4):
        x = KX - 60 + i * 40
        (x0, y0), (x1, y1) = cam.project((x - 19, 44, -4)), cam.project((x + 19, -12, -4))
        box = (int(x0), int(y0), int(x1 + 0.999), int(y1 + 0.999))
        c.add_piece("drum%d-%d" % (i, d), img.crop(box), box[:2])
if CHECK:
    c.check("console-garage.png", cmap)

with open(os.path.join(DEST, "scenes.json"), "w") as fh:
    json.dump({"garage": g.info, "console-garage": c.info}, fh, indent=1)
print("assets ok: %s" % os.path.abspath(DEST))
