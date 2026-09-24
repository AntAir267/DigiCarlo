"""The pre-rendered pictures, and the widget that shows them.

Each picture (the garage, the Photo Board, the console) is a background
rendered in POV-Ray at twice the window's logical size, plus pieces rendered
with the same light that the program switches on and off: a card in the
reader, a radio key pushed in, a digit on the counter. A map says which clickable thing is under
each pixel, and every clickable thing has a glow to screen over it while the
mouse is on it. All of it is made by art/render.sh; scenes.json says where
everything goes.

The program also paints onto some surfaces in the pictures -- the calendar's
date, the card's name, the green screen's text -- through the perspective of
the render, so the ink sits on the paper.
"""

import json
import os

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QImage, QPainter, QPixmap, QPolygonF,
                         QTransform)
from PyQt6.QtWidgets import QToolTip, QWidget

SCENES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenes")

_catalogue = None


def catalogue():
    global _catalogue
    if _catalogue is None:
        with open(os.path.join(SCENES, "scenes.json")) as fh:
            _catalogue = json.load(fh)
    return _catalogue


def sprite(name):
    """One of the things drawn on their own -- a map pin, the dialog's alarm
    clock -- as an image at twice its logical size."""
    return QImage(os.path.join(SCENES, catalogue()["sprites"][name]))


def font(families, px, bold=False):
    f = QFont()
    f.setFamilies(families)
    f.setPixelSize(max(1, int(round(px))))
    f.setBold(bold)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


# What the program writes with. Each list falls back to fonts a Linux desktop
# is likely to have; the first of each is what the .deb recommends.
PRINTED = ["Nunito Black", "Nunito", "DejaVu Sans"]
HANDWRITTEN = ["Comic Neue", "Gloria Hallelujah", "Comic Sans MS", "Nunito"]
TERMINAL = ["Glass TTY VT220", "OCR A Extended", "DejaVu Sans Mono"]


class Picture:
    """One pre-rendered picture, the pieces switched on in it, and a
    callback that paints on its surfaces."""

    def __init__(self, name):
        self.name = name
        info = catalogue()[name]
        self.info = info
        self.size = QSize(*info["size"])
        self.base = QImage(os.path.join(SCENES, info["background"]))
        self.map = QImage(os.path.join(SCENES, info["map"])).convertToFormat(
            QImage.Format.Format_Grayscale8)
        self.spots = {int(n): s for n, s in info["hotspots"].items()}
        self.names = {s["name"]: int(n) for n, s in info["hotspots"].items()}
        self.on = []
        self.painter = None
        self._images = {}
        self._composed = None
        self._scaled = {}

    # -- assets ----------------------------------------------------------------

    def _image(self, fn):
        img = self._images.get(fn)
        if img is None:
            img = QImage(os.path.join(SCENES, fn))
            self._images[fn] = img
        return img

    def piece(self, key):
        p = self.info["pieces"][key]
        return self._image(p["file"]), QPoint(*p["at"])

    def glow(self, spot):
        s = self.spots[self.names[spot]]
        return self._image(s["glow"]), QPoint(*s["at"])

    def surface(self, key):
        """A transform from the surface's own layout space (its "size") to
        the picture's pixels."""
        s = self.info["surfaces"][key]
        w, h = s["size"]
        src = QPolygonF([QPointF(0, 0), QPointF(w, 0), QPointF(w, h), QPointF(0, h)])
        dst = QPolygonF([QPointF(x, y) for x, y in s["corners"]])
        t = QTransform()
        if not QTransform.quadToQuad(src, dst, t):
            raise ValueError("surface %s cannot be mapped" % key)
        return t, QRectF(0, 0, w, h)

    # -- state -----------------------------------------------------------------

    def set_pieces(self, keys):
        keys = list(keys)
        if keys != self.on:
            self.on = keys
            self.invalidate()

    def invalidate(self):
        self._composed = None
        self._scaled.clear()

    def composed(self):
        if self._composed is None:
            img = self.base.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
            p = QPainter(img)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            for key in self.on:
                piece, at = self.piece(key)
                p.drawImage(at, piece)
            if self.painter is not None:
                self.painter(p, self)
            p.end()
            self._composed = img
        return self._composed

    def scaled(self, size):
        """The picture as it is now, at `size` device pixels."""
        key = (size.width(), size.height())
        pm = self._scaled.get(key)
        if pm is None:
            pm = QPixmap.fromImage(self.composed().scaled(
                size, Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            self._scaled = {key: pm}
        return pm

    def spot_at(self, x, y):
        """The clickable thing at picture pixel (x, y), or None."""
        mx, my = int(x) // 2, int(y) // 2
        if not (0 <= mx < self.map.width() and 0 <= my < self.map.height()):
            return None
        n = self.map.pixelColor(mx, my).red()
        return self.spots[n]["name"] if n in self.spots else None


class Stage(QWidget):
    """Pictures stacked top to bottom, scaled together to fit, with the
    things in them that can be clicked.

    `live(picture, spot)` says whether a spot can be clicked now, and
    `tip(picture, spot)` what its tooltip says; `overlays` are painted over
    the pictures at the screen's own resolution, for text that changes too
    often to go into a picture (the green screen)."""

    clicked = pyqtSignal(str, str)          # picture, spot
    double_clicked = pyqtSignal(str, str)
    context = pyqtSignal(str, str, QPoint)  # picture, spot or "", global position
    wheeled = pyqtSignal(str, int)          # picture, +1 / -1 a notch
    hovered = pyqtSignal()

    def __init__(self, pictures, parent=None):
        super().__init__(parent)
        self.pictures = pictures
        self.live = lambda pic, spot: True
        self.tip = lambda pic, spot: ""
        # things drawn by the program rather than rendered (prints on the
        # board): items(picture, x, y) -> a name, or None
        self.items = lambda pic, x, y: None
        # spots that can be clicked but are no thing in particular (the
        # bare cork): no hand, no glow
        self.quiet = set()
        self.overlays = []
        self.hot = None
        self.pressed = None
        self._glows = {}
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        w = pictures[0].size.width()
        h = sum(pic.size.height() for pic in pictures)
        self.canvas = QSize(w // 2, h // 2)         # logical size, unscaled
        self.setMinimumSize(self.canvas.width() // 2, self.canvas.height() // 2)

    def sizeHint(self):
        return self.canvas

    def set_picture(self, i, picture):
        """Show another picture in place i (walking from room to room)."""
        self.pictures[i] = picture
        self.hot = self.pressed = None
        self._glows.clear()
        self.update()

    def refresh(self, picture=None):
        for pic in self.pictures:
            if picture is None or pic is picture:
                pic.invalidate()
        self.update()

    # -- geometry ----------------------------------------------------------------

    def _dpr(self):
        return self.devicePixelRatioF() or 1.0

    def placements(self):
        """[(picture, rect in device pixels)], whole pixels so nothing is
        drawn between them, centred in the widget."""
        dpr = self._dpr()
        W, H = int(self.width() * dpr), int(self.height() * dpr)
        s = min(W / self.canvas.width(), H / self.canvas.height())
        cw = int(self.canvas.width() * s)
        heights = [int(round(pic.size.height() / 2 * s)) for pic in self.pictures]
        ch = sum(heights)
        x, y = (W - cw) // 2, (H - ch) // 2
        out = []
        for pic, h in zip(self.pictures, heights):
            out.append((pic, QRect(x, y, cw, h)))
            y += h
        return out

    def to_picture(self, pos):
        """(picture, x, y in picture pixels) under a widget position."""
        dpr = self._dpr()
        px, py = pos.x() * dpr, pos.y() * dpr
        for pic, r in self.placements():
            if r.contains(int(px), int(py)):
                k = pic.size.width() / r.width()
                return pic, (px - r.x()) * k, (py - r.y()) * k
        return None, 0, 0

    def picture_transform(self, pic):
        """Picture pixels to widget (logical) coordinates."""
        dpr = self._dpr()
        for p, r in self.placements():
            if p is pic:
                k = r.width() / pic.size.width() / dpr
                return QTransform(k, 0, 0, k, r.x() / dpr, r.y() / dpr)
        return QTransform()

    def spot_under(self, pos):
        pic, x, y = self.to_picture(pos)
        if pic is None:
            return None
        spot = pic.spot_at(x, y)
        if spot is None:
            spot = self.items(pic.name, x, y)
        if spot is None or not self.live(pic.name, spot):
            return None
        return pic, spot

    # -- painting ------------------------------------------------------------------

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#000000"))
        dpr = self._dpr()
        for pic, r in self.placements():
            pm = pic.scaled(r.size())
            pm.setDevicePixelRatio(dpr)
            p.drawPixmap(QPointF(r.x() / dpr, r.y() / dpr), pm)
            if self.hot is not None and self.hot[0] is pic and self.hot[1] in pic.names:
                self._paint_glow(p, pic, r, self.hot[1])
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        for paint in self.overlays:
            p.save()
            paint(p, self)
            p.restore()

    def _paint_glow(self, p, pic, r, spot):
        dpr = self._dpr()
        k = r.width() / pic.size.width()
        key = (pic.name, spot, r.width())
        cached = self._glows.get(key)
        if cached is None:
            img, at = pic.glow(spot)
            size = QSize(max(1, int(img.width() * k)), max(1, int(img.height() * k)))
            pm = QPixmap.fromImage(img.scaled(
                size, Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            cached = (pm, QPointF(r.x() + at.x() * k, r.y() + at.y() * k))
            self._glows = {k2: v for k2, v in self._glows.items() if k2[2] == r.width()}
            self._glows[key] = cached
        pm, at = cached
        pm.setDevicePixelRatio(dpr)
        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        p.drawPixmap(QPointF(at.x() / dpr, at.y() / dpr), pm)
        p.restore()

    # -- the mouse -------------------------------------------------------------------

    def _set_hot(self, hot):
        if hot != self.hot:
            self.hot = hot
            self.setCursor(Qt.CursorShape.PointingHandCursor
                           if hot and hot[1] not in self.quiet
                           else Qt.CursorShape.ArrowCursor)
            self.hovered.emit()
            self.update()

    def mouseMoveEvent(self, e):
        self._set_hot(self.spot_under(e.position()))

    def leaveEvent(self, e):
        self._set_hot(None)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.pressed = self.spot_under(e.position())

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        was, self.pressed = self.pressed, None
        now = self.spot_under(e.position())
        if was is not None and now == was:
            QToolTip.hideText()
            self.clicked.emit(was[0].name, was[1])

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            hit = self.spot_under(e.position())
            if hit is not None:
                self.double_clicked.emit(hit[0].name, hit[1])

    def contextMenuEvent(self, e):
        pic, _, _ = self.to_picture(QPointF(e.pos()))
        hit = self.spot_under(QPointF(e.pos()))
        if pic is not None:
            self.context.emit(pic.name, hit[1] if hit else "", e.globalPos())

    def wheelEvent(self, e):
        pic, _, _ = self.to_picture(e.position())
        steps = e.angleDelta().y() // 120
        if pic is not None and steps:
            self.wheeled.emit(pic.name, -1 if steps > 0 else 1)

    def event(self, e):
        if e.type() == e.Type.ToolTip:
            hit = self.spot_under(e.position() if hasattr(e, "position")
                                  else QPointF(e.pos()))
            text = self.tip(hit[0].name, hit[1]) if hit else ""
            if text:
                QToolTip.showText(e.globalPos(), text, self)
            else:
                QToolTip.hideText()
                e.ignore()
            return True
        return super().event(e)
