"""How DigiCarlo's window is drawn: colours, fonts, the cartoon paint helpers,
the scenery, the icon and the horn.

The look is a Humongous Entertainment point-and-click game -- Putt-Putt's
dashboard in particular -- built on the factory colours of the Nash
Metropolitan. Everything has a thick dark outline, flat paint with a soft
gloss, and a slightly toy-like chunkiness. Strokes are never thinner than two
pixels and all text is anti-aliased, because the window is drawn at the
screen's scale and a hairline or an unsmoothed glyph falls apart at 150%.
"""

import math
import os
import shutil
import struct
import subprocess
import wave

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QConicalGradient, QFont,
                         QFontDatabase, QIcon, QLinearGradient, QPainter,
                         QPainterPath, QPen, QPixmap, QRadialGradient)

# ---------------------------------------------------------------------------
# Paint
#
# The Metropolitan's only factory blue was Caribbean Blue (PPG P-905, Nash
# P-44, Ditzler 41161, 1954-56), a turquoise aqua; photographs of cars in it
# sit around hue 190. It was paired with Snowberry White (P-909, Ditzler
# 8017). Mardi Gras Red (P-913) is the accent.
# ---------------------------------------------------------------------------

OUTLINE = QColor("#1B2A30")
INK = QColor("#1B2A30")
INK_SOFT = QColor("#4A5A60")

CARIBBEAN = {"hi": "#CFF4F8", "light": "#74D2DF", "base": "#2EA3B9",
             "shade": "#1E8094", "deep": "#145A69"}
SNOWBERRY = {"hi": "#FFFFFF", "light": "#FBF8EE", "base": "#F2ECDC",
             "shade": "#D8CFB7", "deep": "#B4A98C"}
MARDI_GRAS = {"hi": "#FFB0A3", "light": "#F0604F", "base": "#D8392E",
              "shade": "#A6261E", "deep": "#7A1913"}
SUNBURST = {"hi": "#FFF6C2", "light": "#FFE27A", "base": "#FFD23F",
            "shade": "#E3A91C", "deep": "#B07D0E"}
WOOD = {"light": "#E9B77A", "base": "#D49A5B", "shade": "#AE7039"}
GRASS = {"light": "#A6DE74", "base": "#7CC755", "shade": "#56A23A"}
GREY = {"light": "#E4E6E8", "base": "#C5CACE", "shade": "#9CA3A9"}
CHROME = [(0.00, "#FFFFFF"), (0.30, "#E6EAEE"), (0.47, "#A9B1B9"),
          (0.53, "#8C959E"), (0.72, "#D8DDE2"), (1.00, "#FAFBFC")]

CREAM = QColor(SNOWBERRY["base"])
PAPER = QColor("#FFFDF7")


def c(value):
    return value if isinstance(value, QColor) else QColor(value)


def alpha(color, a):
    col = QColor(c(color))
    col.setAlpha(a)
    return col


# ---------------------------------------------------------------------------
# Type
# ---------------------------------------------------------------------------

def _family(names):
    have = set(QFontDatabase.families())
    for name in names:
        if name in have:
            return name
    return None


def _font(names, size, weight, fallback_bold=True):
    fam = _family(names)
    f = QFont(fam) if fam else QFont()
    if not fam and fallback_bold:
        weight = max(weight, QFont.Weight.Bold)
    f.setPointSizeF(size)
    f.setWeight(weight)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def body_font(size=9.0, weight=QFont.Weight.Bold):
    """Rounded and sturdy: Nunito (fonts-nunito) wherever it is installed."""
    return _font(("Nunito", "Arial Rounded MT Bold", "Ubuntu", "Noto Sans",
                  "DejaVu Sans"), size, weight, fallback_bold=False)


def display_font(size=12.0):
    """Big friendly labels: Nunito at its heaviest."""
    return _font(("Nunito Black", "Nunito", "Arial Rounded MT Bold",
                  "Berlin Sans FB Demi", "Ubuntu", "DejaVu Sans"),
                 size, QFont.Weight.Black)


def hand_font(size=8.5):
    """Handwriting, for what is jotted on the prints."""
    return _font(("Segoe Print", "Comic Sans MS", "Kristen ITC", "Nunito",
                  "DejaVu Sans"), size, QFont.Weight.Bold)


def script_font(size):
    """Cursive for the chrome nameplate, as the car wore its name."""
    for name in ("Script MT Bold", "Lobster", "Brush Script MT",
                 "Freestyle Script", "URW Chancery L", "Z003",
                 "TeX Gyre Chorus"):
        if name in QFontDatabase.families():
            f = QFont(name)
            f.setPointSizeF(size)
            return f
    f = QFont("DejaVu Serif")
    f.setPointSizeF(size * 0.8)
    f.setItalic(True)
    f.setBold(True)
    return f


# ---------------------------------------------------------------------------
# Cartoon paint
# ---------------------------------------------------------------------------

def pen(color=OUTLINE, width=2.4):
    p = QPen(c(color), width)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    return p


def vgrad(rect, stops):
    rect = QRectF(rect)
    g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    n = len(stops)
    for i, s in enumerate(stops):
        if isinstance(s, tuple):
            g.setColorAt(s[0], c(s[1]))
        else:
            g.setColorAt(i / max(1, n - 1), c(s))
    return g


def chrome_brush(rect):
    return QBrush(vgrad(rect, CHROME))


def paint(p, path, tone, gloss=True, outline=2.4, flat=False):
    """Fill a shape the cartoon way: a soft top-to-bottom shade, a glossy
    highlight across its upper part, and a thick dark outline."""
    r = path.boundingRect()
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    if flat:
        p.setBrush(c(tone["base"]))
    else:
        p.setBrush(QBrush(vgrad(r, [(0.0, tone["light"]), (0.45, tone["base"]),
                                    (1.0, tone["shade"])])))
    p.drawPath(path)
    if gloss and r.height() > 6:
        p.setClipPath(path)
        band = QRectF(r.left() + r.width() * 0.07, r.top() + r.height() * 0.06,
                      r.width() * 0.86, r.height() * 0.40)
        hp = QPainterPath()
        rad = min(band.height(), band.width()) / 2
        hp.addRoundedRect(band, rad, rad)
        p.setBrush(QBrush(vgrad(band, [(0.0, QColor(255, 255, 255, 150)),
                                       (1.0, QColor(255, 255, 255, 0))])))
        p.drawPath(hp)
        p.setClipping(False)
    if outline:
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(pen(OUTLINE, outline))
        p.drawPath(path)
    p.restore()


def rounded(rect, radius):
    path = QPainterPath()
    path.addRoundedRect(QRectF(rect), radius, radius)
    return path


def circle(center, radius):
    path = QPainterPath()
    path.addEllipse(QPointF(center), radius, radius)
    return path


def chrome_ring(p, center, outer, inner, outline=2.4):
    """A chrome bezel: a ring lit from the top left."""
    center = QPointF(center)
    ring = circle(center, outer).subtracted(circle(center, inner))
    g = QConicalGradient(center, 45)
    for at, col in ((0.0, "#FFFFFF"), (0.22, "#98A1AA"), (0.45, "#F4F6F8"),
                    (0.72, "#7B848D"), (1.0, "#FFFFFF")):
        g.setColorAt(at, QColor(col))
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawPath(ring)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(pen(OUTLINE, outline))
    p.drawEllipse(center, outer, outer)
    p.setPen(pen(OUTLINE, outline * 0.7))
    p.drawEllipse(center, inner, inner)
    p.restore()


def outlined_text(p, rect, flags, text, font, fill, outline=OUTLINE, width=3.0):
    """Text with a fat outline, the way game buttons label themselves."""
    rect = QRectF(rect)
    path = QPainterPath()
    p.save()
    p.setFont(font)
    fm = p.fontMetrics()
    lines = text.split("\n")
    lh = fm.height()
    total = lh * len(lines)
    if flags & Qt.AlignmentFlag.AlignVCenter:
        y = rect.top() + (rect.height() - total) / 2 + fm.ascent()
    elif flags & Qt.AlignmentFlag.AlignBottom:
        y = rect.bottom() - total + fm.ascent()
    else:
        y = rect.top() + fm.ascent()
    for line in lines:
        w = fm.horizontalAdvance(line)
        if flags & Qt.AlignmentFlag.AlignHCenter:
            x = rect.left() + (rect.width() - w) / 2
        elif flags & Qt.AlignmentFlag.AlignRight:
            x = rect.right() - w
        else:
            x = rect.left()
        path.addText(x, y, font, line)
        y += lh
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(pen(outline, width))
    p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c(fill))
    p.drawPath(path)
    p.restore()


def drop_shadow(p, path, dx=3.0, dy=4.0, a=60):
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(20, 40, 50, a))
    p.drawPath(path.translated(dx, dy))
    p.restore()


# ---------------------------------------------------------------------------
# Scenery for the windshield view
# ---------------------------------------------------------------------------

def _cloud(cx, cy, s):
    path = QPainterPath()
    # Winding, so the overlaps fill in and simplified() leaves one puffy
    # outline rather than a ring of circles.
    path.setFillRule(Qt.FillRule.WindingFill)
    for dx, dy, r in ((-1.1, 0.25, 0.62), (-0.45, -0.25, 0.8), (0.35, -0.35,
                      0.9), (1.05, 0.15, 0.66), (0.0, 0.35, 0.75)):
        path.addEllipse(QPointF(cx + dx * s, cy + dy * s), r * s, r * s)
    return path.simplified()


def _hill(width, height, base_y, amp, phase, waves):
    path = QPainterPath()
    path.moveTo(0, height)
    path.lineTo(0, base_y)
    steps = 48
    for i in range(steps + 1):
        x = width * i / steps
        y = base_y - amp * (0.5 + 0.5 * math.sin(phase + waves * math.pi * i
                                                  / steps))
        path.lineTo(x, y)
    path.lineTo(width, height)
    path.closeSubpath()
    return path


def scenery(width, height):
    """A Cartown-ish afternoon: sky, sun, a few fat clouds, rolling hills and
    lollipop trees. Drawn once per size and kept."""
    pm = QPixmap(max(1, width), max(1, height))
    pm.fill(QColor("#BCE8F7"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    sky = QRectF(0, 0, width, height)
    p.fillRect(sky, QBrush(vgrad(sky, [(0.0, "#8FD6F2"), (0.6, "#D9F4FC"),
                                       (1.0, "#F1FBFE")])))
    # the sun, with stubby rays
    sx, sy, sr = width - 70, 60, 30
    p.setPen(pen(OUTLINE, 2.2))
    for i in range(10):
        a = i * math.pi / 5 + 0.2
        p.drawLine(QPointF(sx + math.cos(a) * (sr + 6), sy + math.sin(a) * (sr + 6)),
                   QPointF(sx + math.cos(a) * (sr + 16), sy + math.sin(a) * (sr + 16)))
    paint(p, circle(QPointF(sx, sy), sr), SUNBURST)
    for fx, fy, s in ((0.14, 70, 26), (0.42, 42, 20), (0.66, 96, 23)):
        cl = _cloud(width * fx, fy, s)
        drop_shadow(p, cl, 0, 5, 30)
        paint(p, cl, {"light": "#FFFFFF", "base": "#FFFFFF",
                      "shade": "#E3F2F8"}, gloss=False, outline=2.2)
    far = _hill(width, height, height - 70, 34, 0.6, 3.2)
    paint(p, far, {"light": "#C6EBA0", "base": "#AEDE86", "shade": "#93C96B"},
          gloss=False, outline=2.2)
    for fx in (0.08, 0.28, 0.83):
        x = width * fx
        base = height - 58
        p.setPen(pen(OUTLINE, 2.2))
        p.setBrush(c(WOOD["shade"]))
        p.drawRoundedRect(QRectF(x - 3.5, base - 26, 7, 30), 3, 3)
        paint(p, circle(QPointF(x, base - 34), 17), GRASS, outline=2.2)
    near = _hill(width, height, height - 24, 26, 2.1, 2.2)
    paint(p, near, GRASS, gloss=False, outline=2.4)
    p.end()
    return pm


# ---------------------------------------------------------------------------
# The icon: a camera in two-tone paint whose lens is a chrome-ringed
# headlight -- and, in a cartoon, an eye
# ---------------------------------------------------------------------------

def paint_icon(p, size):
    s = size / 64.0
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(s, s)
    w = 2.6 if size >= 32 else 3.4
    body = rounded(QRectF(4, 17, 56, 38), 11)
    p.save()
    p.setClipPath(body)
    p.fillRect(QRectF(4, 17, 56, 38), QBrush(vgrad(QRectF(4, 30, 56, 25),
                                                  [CARIBBEAN["light"],
                                                   CARIBBEAN["base"],
                                                   CARIBBEAN["shade"]])))
    p.fillRect(QRectF(4, 17, 56, 15), c(SNOWBERRY["base"]))
    p.fillRect(QRectF(4, 31, 56, 4), QBrush(vgrad(QRectF(4, 31, 56, 4), CHROME)))
    p.restore()
    p.setPen(pen(OUTLINE, w))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(body)
    paint(p, rounded(QRectF(11, 9, 17, 10), 4), SNOWBERRY, gloss=False, outline=w)
    p.setBrush(QBrush(vgrad(QRectF(43, 10, 11, 8), CHROME)))
    p.setPen(pen(OUTLINE, w))
    p.drawRoundedRect(QRectF(43, 11, 11, 7), 3, 3)
    chrome_ring(p, QPointF(33, 37), 15, 10, outline=w)
    lens = QRadialGradient(QPointF(29, 33), 12)
    lens.setColorAt(0.0, QColor("#E8FBFF"))
    lens.setColorAt(0.35, QColor(CARIBBEAN["base"]))
    lens.setColorAt(1.0, QColor("#0D2F38"))
    p.setBrush(QBrush(lens))
    p.setPen(pen(OUTLINE, w * 0.7))
    p.drawEllipse(QPointF(33, 37), 10, 10)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 230))
    p.drawEllipse(QPointF(29.5, 33.5), 3.0, 3.0)
    p.restore()


def icon_pixmap(size):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    paint_icon(p, size)
    p.end()
    return pm


def app_icon():
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(icon_pixmap(size))
    return icon


# ---------------------------------------------------------------------------
# The horn
# ---------------------------------------------------------------------------

def _cache_dir():
    d = os.path.join(os.environ.get("XDG_CACHE_HOME")
                     or os.path.expanduser("~/.cache"), "digicarlo")
    os.makedirs(d, exist_ok=True)
    return d


def _write_wav(path, notes, rate=22050):
    """notes: [(seconds, (freq, ...)), ...]; a frequency of 0 is silence.

    A car horn is two reeds a third apart; odd harmonics give the square,
    brassy edge a little bulb horn has.
    """
    frames = bytearray()
    for dur, freqs in notes:
        n = int(rate * dur)
        for i in range(n):
            t = i / rate
            env = min(1.0, t / 0.015) * min(1.0, (dur - t) / 0.04)
            s = 0.0
            for f in freqs:
                if f:
                    ph = 2 * math.pi * f * t
                    s += math.sin(ph) + math.sin(3 * ph) / 3 + math.sin(5 * ph) / 6
            v = max(-1.0, min(1.0, s * 0.22 * env))
            frames += struct.pack("<h", int(v * 32767 * 0.7))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


SOUNDS = {
    "honk": [(0.38, (392, 494))],
    "beepbeep": [(0.13, (440, 554)), (0.07, (0,)), (0.16, (440, 554))],
}


def play(name):
    """Play one of the SOUNDS without waiting for it."""
    player = next((shutil.which(x) for x in ("pw-play", "paplay", "aplay")
                   if shutil.which(x)), None)
    if not player or name not in SOUNDS:
        return
    try:
        path = os.path.join(_cache_dir(), "%s.wav" % name)
        if not os.path.exists(path):
            _write_wav(path + ".part", SOUNDS[name])
            os.replace(path + ".part", path)
        subprocess.Popen([player, path], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except OSError:
        pass
