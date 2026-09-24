"""The Photo Board: the shots waiting for the library, pinned up to be dated.

The board is the pre-rendered cork (stage.Picture "board"); on it the
program pins a print of every shot waiting, in the order taken, each
session led by an index card saying what the camera's clock said and what
dates the shots will get. Two rows fill the cork above the tools on the
ledge; more than that go on further pages, turned with the radio's knobs,
the mouse wheel, Page Up and Page Down, or the page note in the corner.

Everything is laid out in the cork's own space (its "size" in scenes.json,
half-centimetre units) and drawn through its perspective, so the prints sit
on the cork the way the rendered tools sit on the ledge.
"""

import hashlib
import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QColor, QPainterPath, QPen,
                         QPolygonF, QTransform)

from digicarlo import media
from digicarlo.stage import HANDWRITTEN, PRINTED, font, sprite

COLS, ROWS = 11, 2
SLOT_W, SLOT_H = 114, 124
LEFT, TOP = 9, 78                   # below the banner, above the tools
PRINT_W, PRINT_H = 100, 112
PER_PAGE = COLS * ROWS
PINS = ("red", "blue", "yellow", "green", "purple")

INK = QColor(40, 34, 30)
AUTO = QColor(29, 79, 154)          # dated when it came off the camera
SET = QColor(192, 40, 30)           # a date given
CAMERA = QColor(140, 90, 0)         # the camera's own date
GLOW = QColor(255, 214, 70)


def short_time(dt):
    return dt.strftime("%I:%M %p").lstrip("0").lower() if dt else ""


def short_day(dt):
    return dt.strftime("%b %d %Y").replace(" 0", " ") if dt else ""


def times_between(a, b):
    """'1:59 - 2:05 pm', or '11:50 am - 12:05 pm'."""
    if a == b:
        return short_time(a)
    ta, tb = short_time(a), short_time(b)
    if ta[-2:] == tb[-2:]:
        ta = ta[:-3]
    return "%s - %s" % (ta, tb)


def span_lines(a, b):
    """Two lines for a card: the day(s), then the times."""
    if a is None:
        return "no clock", ""
    if a.date() == b.date():
        return short_day(a), times_between(a, b)
    return "%s -" % short_day(a), short_day(b)


def span_line(a, b, year=None):
    """One line: 'Sep 23, 1:59 - 2:00 pm', with the year if not `year`."""
    day = a.strftime("%b %d").replace(" 0", " ")
    if a.year != (year or a.year):
        day += " %d" % a.year
    if a.date() == b.date():
        return "%s, %s" % (day, times_between(a, b))
    return "%s - %s" % (day, b.strftime("%b %d").replace(" 0", " "))


class Item:
    def __init__(self, kind, page, slot, span=1):
        self.kind = kind            # "card", "shot", "note"
        self.page = page
        self.slot = slot
        self.session = None
        self.shot = None
        self.number = 0
        self.continued = False
        self.text = ""
        col, row = slot % COLS, slot // COLS
        w = span * SLOT_W - (SLOT_W - PRINT_W)
        self.rect = QRectF(LEFT + col * SLOT_W + (SLOT_W - PRINT_W) / 2,
                           TOP + row * SLOT_H + (SLOT_H - PRINT_H) / 2, w, PRINT_H)
        self.tilt = 0.0

    @property
    def name(self):
        if self.kind == "shot":
            return "shot:" + self.shot.key
        if self.kind == "card":
            return "card:%d:%d" % (id(self.session), self.page)
        return "note:" + self.text

    def contains(self, pt):
        c = self.rect.center()
        a = math.radians(-self.tilt)
        dx, dy = pt.x() - c.x(), pt.y() - c.y()
        x = c.x() + dx * math.cos(a) - dy * math.sin(a)
        y = c.y() + dx * math.sin(a) + dy * math.cos(a)
        return self.rect.adjusted(-3, -12, 3, 3).contains(QPointF(x, y))

    def frame(self):
        """This item's own drawing space: origin at its top left, tilted."""
        c = self.rect.center()
        t = QTransform()
        t.translate(c.x(), c.y())
        t.rotate(self.tilt)
        t.translate(-self.rect.width() / 2, -self.rect.height() / 2)
        return t


def _tilt(key, most=3.0):
    h = int(hashlib.sha1(key.encode()).hexdigest()[:8], 16)
    return (h / 0xFFFFFFFF * 2 - 1) * most


def layout(plan):
    """The board's pages: [[Item]]. Each session starts with its card (two
    slots, in one row); a session running onto a new page gets its card
    again there."""
    pages = [[]]
    slot = 0
    number = 0
    if plan is None or not plan.shots:
        return pages

    def new_page():
        pages.append([])
        return 0

    for n, sess in enumerate(plan.sessions):
        if slot % COLS == COLS - 1:
            slot += 1
        if slot + 3 > PER_PAGE:
            slot = new_page()
        card = Item("card", len(pages) - 1, slot, span=2)
        card.session = sess
        card.number = n
        card.tilt = _tilt("card%d" % n, 1.5)
        pages[-1].append(card)
        slot += 2
        for shot in sess.shots:
            if slot >= PER_PAGE:
                slot = new_page()
                again = Item("card", len(pages) - 1, slot, span=2)
                again.session, again.number, again.continued = sess, n, True
                pages[-1].append(again)
                slot += 2
            number += 1
            it = Item("shot", len(pages) - 1, slot)
            it.session, it.shot, it.number = sess, shot, shot.number or number
            it.tilt = _tilt(shot.key)
            pages[-1].append(it)
            slot += 1
    return pages


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def _pin(p, x, y, colour, size=22):
    img = sprite("pin-" + colour)
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 70))
    p.drawEllipse(QPointF(x + size * 0.28, y + size * 0.36), size * 0.34, size * 0.22)
    p.restore()
    p.drawImage(QRectF(x - size / 2, y - size / 2, size, size), img)


def _paper(p, w, h, lifted, picked):
    off = 7 if lifted else 3
    if picked:
        for i, a in ((12, 40), (8, 70), (4, 110)):
            c = QColor(GLOW)
            c.setAlpha(a)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(QRectF(-i, -i, w + 2 * i, h + 2 * i), i + 2, i + 2)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 55 if lifted else 70))
    p.drawRect(QRectF(off * 0.6, off, w, h))


def _cover(img, w, h, quarters):
    """img turned by quarter turns and cropped to fill w x h."""
    if quarters:
        img = img.transformed(QTransform().rotate(90 * quarters),
                              Qt.TransformationMode.SmoothTransformation)
    k = max(w / img.width(), h / img.height())
    sw, sh = w / k, h / k
    return img, QRectF((img.width() - sw) / 2, (img.height() - sh) / 2, sw, sh)


def paint_shot(p, it, ctx):
    shot = it.shot
    picked = shot.key in ctx.selected
    w, h = it.rect.width(), it.rect.height()
    p.save()
    p.setTransform(it.frame() * p.transform())
    if picked:
        p.translate(-2, -4)
    _paper(p, w, h, picked, picked)
    p.fillRect(QRectF(0, 0, w, h), QColor(250, 248, 240))
    p.setPen(QPen(QColor(215, 210, 196), 0.8))
    p.drawRect(QRectF(0, 0, w, h))
    win = QRectF(6, 6, w - 12, 66)
    edit = ctx.edits.get(shot.key)
    thumb = ctx.thumb(shot.key)
    if thumb is not None and not thumb.isNull():
        img, src = _cover(thumb, win.width(), win.height(), edit.rotate if edit else 0)
        p.drawImage(win, img, src)
    else:
        p.fillRect(win, QColor(200, 196, 186))
        p.setPen(QColor(150, 144, 132))
        p.setFont(font(PRINTED, 11))
        p.drawText(win, Qt.AlignmentFlag.AlignCenter, "developing...")
    rec = ctx.record(shot.key)
    if rec.get("kind") in ("video", media.SIPIX_CLIP):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(20, 20, 22))
        p.drawRect(QRectF(win.left(), win.top(), 7, win.height()))
        p.drawRect(QRectF(win.right() - 7, win.top(), 7, win.height()))
        p.setBrush(QColor(240, 238, 230))
        for y in range(int(win.top()) + 3, int(win.bottom()) - 3, 8):
            p.drawRect(QRectF(win.left() + 2, y, 3, 4))
            p.drawRect(QRectF(win.right() - 5, y, 3, 4))
        p.setBrush(QColor(255, 255, 255, 210))
        c = win.center()
        p.drawPolygon(QPolygonF([QPointF(c.x() - 7, c.y() - 10), QPointF(c.x() - 7, c.y() + 10),
                                 QPointF(c.x() + 11, c.y())]))
    # when it will be dated, in the colour of how
    rule = ctx.plan.rules.get(shot.key)
    colour = AUTO if rule is None else (CAMERA if rule.when == "camera" else SET)
    p.setPen(colour)
    p.setFont(font(HANDWRITTEN, 16, bold=True))
    p.drawText(QRectF(4, 74, w - 8, 34), Qt.AlignmentFlag.AlignCenter,
               short_time(ctx.plan.times.get(shot.key)))
    # tabs on the photo's corner for what else was decided
    marks = []
    if edit is not None and edit.title:
        marks.append("title")
    if edit is not None and edit.place:
        marks.append("place")
    if edit is not None and edit.redeye:
        marks.append("redeye")
    x = win.right() - 8
    for m in marks:
        c = QPointF(x, win.bottom() - 8)
        p.setPen(QPen(QColor(60, 50, 40), 0.8))
        p.setBrush(QColor(255, 255, 250, 235))
        p.drawEllipse(c, 7, 7)
        if m == "title":
            p.setPen(QColor(30, 120, 60))
            p.setFont(font(PRINTED, 10))
            p.drawText(QRectF(c.x() - 7, c.y() - 7, 14, 14), Qt.AlignmentFlag.AlignCenter, "T")
        elif m == "place":
            path = QPainterPath()
            path.moveTo(c.x(), c.y() + 5)
            path.arcTo(QRectF(c.x() - 3.5, c.y() - 5, 7, 7), 210, -240)
            path.closeSubpath()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(210, 40, 40))
            p.drawPath(path)
            p.setBrush(QColor(255, 255, 255))
            p.drawEllipse(QPointF(c.x(), c.y() - 1.5), 1.3, 1.3)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(205, 30, 30))
            p.drawEllipse(c, 4, 4)
            p.setBrush(QColor(30, 26, 26))
            p.drawEllipse(c, 1.8, 1.8)
        x -= 16
    # its number, on a round sticker
    p.setPen(QPen(INK, 1.4))
    p.setBrush(QColor(255, 255, 255))
    p.drawEllipse(QPointF(4, 4), 10, 10)
    p.setPen(INK)
    p.setFont(font(PRINTED, 11 if it.number < 100 else 8.5))
    p.drawText(QRectF(-6, -6, 20, 20), Qt.AlignmentFlag.AlignCenter, str(it.number))
    _pin(p, w / 2, -1, PINS[(it.session.number - 1) % len(PINS)])
    p.restore()


def paint_card(p, it, ctx):
    sess = it.session
    w, h = it.rect.width(), it.rect.height()
    picked = bool(sess.shots) and all(s.key in ctx.selected for s in sess.shots)
    p.save()
    p.setTransform(it.frame() * p.transform())
    _paper(p, w, h, False, picked)
    p.fillRect(QRectF(0, 0, w, h), QColor(252, 250, 242))
    p.setPen(QPen(QColor(220, 90, 90), 1.2))
    p.drawLine(QPointF(0, 27), QPointF(w, 27))
    p.setPen(QPen(QColor(150, 190, 225), 0.9))
    y = 44.5
    while y < h:
        p.drawLine(QPointF(0, y), QPointF(w, y))
        y += 16.5
    title = "Session %d" % sess.number
    if ctx.many_batches:
        title += "  -  %s" % (sess.batch.label or "")
    if it.continued:
        title += " (more)"
    p.setPen(INK)
    p.setFont(font(PRINTED, 15))
    p.drawText(QRectF(8, 3, w - 16, 24), Qt.AlignmentFlag.AlignVCenter, title)
    c0, c1 = sess.camera_range()
    lines = []
    if c0 is None:
        lines.append(("camera keeps no clock", INK))
    else:
        a, b = span_lines(c0, c1)
        lines.append(("camera said " + a, INK))
        if b:
            lines.append((b, INK))
    groups = [g for g in ctx.plan.groups if g.session is sess]
    year = ctx.plan.times and max(ctx.plan.times.values()).year
    for i, g in enumerate(groups):
        colour = AUTO if g.rule is None else (CAMERA if g.rule.when == "camera" else SET)
        if len(lines) == 4 and len(groups) - i > 1:
            lines.append(("and %d more dates" % (len(groups) - i), INK))
            break
        lines.append((("dated " if i == 0 else "") + span_line(g.start, g.end, year), colour))
    p.setFont(font(HANDWRITTEN, 12.5, bold=True))
    for i, (text, colour) in enumerate(lines[:5]):
        p.setPen(colour)
        p.drawText(QRectF(9, 28 + i * 16.5, w - 14, 16.5),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
    _pin(p, w / 2, -1, PINS[(sess.number - 1) % len(PINS)])
    p.restore()


def paint_note(p, rect, text, pin="red"):
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawRect(rect.translated(2, 3))
    p.fillRect(rect, QColor(255, 238, 120))
    p.setPen(QColor(40, 40, 50))
    p.setFont(font(HANDWRITTEN, 17, bold=True))
    p.drawText(rect.adjusted(6, 8, -6, -4), Qt.AlignmentFlag.AlignCenter |
               Qt.TextFlag.TextWordWrap, text)
    _pin(p, rect.center().x(), rect.top() + 2, pin)
    p.restore()


PAGE_NOTE = QRectF(1146, 8, 112, 58)
EMPTY_NOTE = QRectF(486, 180, 300, 110)


def paint_board(p, cork, items, ctx, page, pages):
    """Everything on the cork, through `cork`, its layout-to-picture
    transform."""
    p.setTransform(cork)
    for it in items:
        if it.kind == "card":
            paint_card(p, it, ctx)
    for it in items:
        if it.kind == "shot" and it.shot.key not in ctx.selected:
            paint_shot(p, it, ctx)
    for it in items:
        if it.kind == "shot" and it.shot.key in ctx.selected:
            paint_shot(p, it, ctx)
    if pages > 1:
        paint_note(p, PAGE_NOTE, "page %d of %d" % (page + 1, pages), "blue")
    if not items:
        paint_note(p, EMPTY_NOTE, "Nothing waiting.\nPull a card in the garage!")


def hit(items, pt, pages):
    """The item under a point on the cork, topmost first."""
    if pages > 1 and PAGE_NOTE.adjusted(-4, -10, 4, 4).contains(pt):
        return "note:page"
    for it in reversed(items):
        if it.kind == "shot" and it.contains(pt):
            return it.name
    for it in reversed(items):
        if it.kind == "card" and it.contains(pt):
            return it.name
    return None


def outline(it):
    """The item's outline, in cork units, for the hover highlight."""
    t = it.frame()
    r = QRectF(0, 0, it.rect.width(), it.rect.height()).adjusted(-3, -3, 3, 3)
    return t.map(QPolygonF([r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]))
