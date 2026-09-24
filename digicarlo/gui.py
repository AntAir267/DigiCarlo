#!/usr/bin/env python3
"""digicarlo-gui --classic - the DigiCarlo window of 1.1 and 1.2.

(digicarlo-gui on its own opens the garage: see garage.py.)

A Windows 95 program that happens to be a cartoon car. The frame, the menus
and the dialogs are Windows 95 (Qt's own "Windows" style is the real Win9x
drawing code). Inside, it plays like a Humongous Entertainment game: the
shots sit in a sunny landscape seen through the windshield, and everything
you do is on the dashboard of a Caribbean Blue Nash Metropolitan, the way
Putt-Putt's dashboard carried his horn, radio and glove compartment.

    glove box      the cameras and cards plugged in; click one to pull it
    horn           honk to look for cameras again
    radio          says what is going on; its preset keys date the shots
                   you have selected
    speedometer    how far the current job has got; the odometer counts
                   every file ever put in the library
    fuel gauge     free space where the library lives
    clock          now, which is when a pull's newest shot will be dated
    starter        puts the shots in the library (and stops a job)

All camera and file work happens in the other modules, on worker threads;
this file only draws and dispatches. The drawing helpers live in cartoon.py.
"""

import datetime
import math
import os
import shutil
import subprocess
import sys

from PyQt6 import sip
from PyQt6.QtCore import (QDateTime, QPointF, QRect, QRectF, QSize, Qt,
                          QTimer, pyqtSignal)
from PyQt6.QtGui import (QAction, QBrush, QColor, QFont, QIcon,
                         QPainter, QPainterPath, QPalette, QPen,
                         QPixmap, QPolygonF, QRadialGradient)
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup,
                             QDateTimeEdit, QDialog, QFileDialog,
                             QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                             QListView, QListWidget, QListWidgetItem, QMenu,
                             QMenuBar, QPlainTextEdit, QPushButton,
                             QRadioButton, QSizePolicy, QStyle,
                             QStyledItemDelegate, QVBoxLayout, QWidget)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from digicarlo import (__version__, archive, blinky, config,   # noqa: E402
                       develop, media, sources, timeplan, update)
from digicarlo import cartoon as toon                           # noqa: E402
from digicarlo.jobs import GuiLog, Job, ThumbLoader             # noqa: E402
from digicarlo.cartoon import (CARIBBEAN, GREY, INK, INK_SOFT,  # noqa: E402
                               MARDI_GRAS, OUTLINE, PAPER, SNOWBERRY,
                               SUNBURST, WOOD, app_icon, icon_pixmap)

THUMB_W, THUMB_H = 100, 75
CELL_W, CELL_H = 128, 142

# Windows 95's bevel colours, warmed to sit next to Snowberry White.
FACE = QColor(SNOWBERRY["base"])
FACE_LIGHT = QColor(SNOWBERRY["light"])
WHITE = QColor("#FFFFFF")
SHADOW = QColor("#958C74")
DARK = QColor("#2A2721")


def ui_font(size=9.0, bold=False):
    return toon.body_font(size, QFont.Weight.Bold if bold
                          else QFont.Weight.DemiBold)


def win95_palette():
    pal = QPalette()
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive,
                  QPalette.ColorGroup.Disabled):
        pal.setColor(group, QPalette.ColorRole.Window, FACE)
        pal.setColor(group, QPalette.ColorRole.Button, FACE)
        pal.setColor(group, QPalette.ColorRole.Base, PAPER)
        pal.setColor(group, QPalette.ColorRole.AlternateBase, FACE_LIGHT)
        pal.setColor(group, QPalette.ColorRole.Light, WHITE)
        pal.setColor(group, QPalette.ColorRole.Midlight, FACE_LIGHT)
        pal.setColor(group, QPalette.ColorRole.Mid, SHADOW)
        pal.setColor(group, QPalette.ColorRole.Dark, SHADOW)
        pal.setColor(group, QPalette.ColorRole.Shadow, DARK)
        pal.setColor(group, QPalette.ColorRole.Highlight,
                     QColor(CARIBBEAN["deep"]))
        pal.setColor(group, QPalette.ColorRole.HighlightedText, WHITE)
        pal.setColor(group, QPalette.ColorRole.ToolTipBase, QColor("#FFFBE0"))
        pal.setColor(group, QPalette.ColorRole.ToolTipText, INK)
        text = SHADOW if group == QPalette.ColorGroup.Disabled else INK
        for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                     QPalette.ColorRole.ButtonText):
            pal.setColor(group, role, text)
    return pal


def bevel(p, rect, raised=True):
    """The Windows 95 two-pixel bevel, drawn inside rect."""
    r = QRect(rect)
    if raised:
        rings = [(FACE_LIGHT, DARK), (WHITE, SHADOW)]
    else:
        rings = [(SHADOW, WHITE), (DARK, FACE_LIGHT)]
    for tl, br in rings:
        p.setPen(QPen(tl, 1))
        p.drawLine(r.left(), r.bottom() - 1, r.left(), r.top())
        p.drawLine(r.left(), r.top(), r.right() - 1, r.top())
        p.setPen(QPen(br, 1))
        p.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
        p.drawLine(r.right(), r.bottom(), r.right(), r.top())
        r.adjust(1, 1, -1, -1)
    return r


def aa(widget):
    p = QPainter(widget)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    return p


# ---------------------------------------------------------------------------
# Window chrome: Windows 95, painted Caribbean Blue
# ---------------------------------------------------------------------------

class CaptionButton(QWidget):
    clicked = pyqtSignal()

    def __init__(self, glyph, parent=None):
        super().__init__(parent)
        self.glyph = glyph
        self.down = False
        self.setFixedSize(20, 18)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.down = True
            self.update()

    def mouseReleaseEvent(self, e):
        if self.down:
            self.down = False
            self.update()
            if self.rect().contains(e.position().toPoint()):
                self.clicked.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), FACE)
        inner = bevel(p, self.rect(), raised=not self.down)
        o = 1 if self.down else 0
        cx, cy = inner.center().x() + o + 1, inner.center().y() + o + 1
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(toon.pen(INK, 2.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self.glyph == "close":
            p.drawLine(QPointF(cx - 4, cy - 4), QPointF(cx + 4, cy + 4))
            p.drawLine(QPointF(cx + 4, cy - 4), QPointF(cx - 4, cy + 4))
        elif self.glyph == "min":
            p.drawLine(QPointF(cx - 4, cy + 4), QPointF(cx + 3, cy + 4))
        elif self.glyph == "max":
            p.drawRect(QRectF(cx - 4.5, cy - 4.5, 9, 8))
            p.drawLine(QPointF(cx - 4.5, cy - 3.5), QPointF(cx + 4.5, cy - 3.5))
        else:
            p.drawRect(QRectF(cx - 2, cy - 5, 7, 6))
            p.fillRect(QRectF(cx - 5, cy - 1, 7, 6), FACE)
            p.drawRect(QRectF(cx - 5, cy - 1, 7, 6))


class TitleBar(QWidget):
    close_clicked = pyqtSignal()
    minimise_clicked = pyqtSignal()
    zoom_clicked = pyqtSignal()

    def __init__(self, text, parent=None, buttons=("min", "max", "close")):
        super().__init__(parent)
        self.text = text
        self.active = True
        self.setFixedHeight(30)
        self._drag = None
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 3, 5, 8)
        row.setSpacing(0)
        row.addStretch(1)
        self.buttons = {}
        for g in buttons:
            b = CaptionButton(g, self)
            self.buttons[g] = b
            if g == "close" and len(buttons) > 1:
                row.addSpacing(3)
            row.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        for g, sig in (("close", self.close_clicked),
                       ("min", self.minimise_clicked),
                       ("max", self.zoom_clicked)):
            if g in self.buttons:
                self.buttons[g].clicked.connect(sig)

    def set_active(self, on):
        self.active = on
        self.update()

    def set_maximised(self, on):
        if "max" in self.buttons:
            self.buttons["max"].glyph = "restore" if on else "max"
            self.buttons["max"].update()

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        # Wayland will not let a client place its own window; ask the
        # compositor to move it, and only drag by hand where it refuses.
        handle = self.window().windowHandle()
        if handle is not None and handle.startSystemMove():
            self._drag = None
            return
        self._drag = e.globalPosition().toPoint() - \
            self.window().frameGeometry().topLeft()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.zoom_clicked.emit()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None

    def paintEvent(self, _):
        p = aa(self)
        r = QRectF(self.rect())
        body = QRectF(r.left(), r.top(), r.width(), r.height() - 5)
        tone = CARIBBEAN if self.active else GREY
        p.fillRect(body, QBrush(toon.vgrad(body, [(0.0, tone["light"]),
                                                  (0.5, tone["base"]),
                                                  (1.0, tone["shade"])])))
        p.fillRect(QRectF(body.left(), body.top() + 2, body.width(),
                          body.height() * 0.35),
                   QBrush(toon.vgrad(QRectF(0, 2, 1, body.height() * 0.35),
                                     [QColor(255, 255, 255, 90),
                                      QColor(255, 255, 255, 0)])))
        strip = QRectF(r.left(), r.bottom() - 5, r.width(), 5)
        p.fillRect(strip, toon.chrome_brush(strip))
        p.setPen(toon.pen(OUTLINE, 1.5))
        p.drawLine(QPointF(r.left(), r.bottom() - 0.75),
                   QPointF(r.right(), r.bottom() - 0.75))
        p.drawPixmap(QRectF(5, (body.height() - 20) / 2, 20, 20),
                     icon_pixmap(40), QRectF(0, 0, 40, 40))
        toon.outlined_text(p, QRectF(31, 0, r.width() - 120, body.height()),
                           Qt.AlignmentFlag.AlignVCenter |
                           Qt.AlignmentFlag.AlignLeft, self.text,
                           toon.display_font(10.5),
                           WHITE if self.active else QColor("#F2F4F5"),
                           OUTLINE, 2.6)


class SizeGrip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemResize(Qt.Edge.BottomEdge | Qt.Edge.RightEdge)

    def paintEvent(self, _):
        p = aa(self)
        w, h = self.width(), self.height()
        for off in (4, 8, 12):
            p.setPen(QPen(WHITE, 1.5))
            p.drawLine(QPointF(w - off - 1, h - 1), QPointF(w - 1, h - off - 1))
            p.setPen(QPen(SHADOW, 1.5))
            p.drawLine(QPointF(w - off + 0.5, h - 1), QPointF(w - 1, h - off + 0.5))


class StatusPanel(QLabel):
    clicked = pyqtSignal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setContentsMargins(6, 1, 6, 1)
        self.setMinimumWidth(60)
        self.setFont(ui_font(8.5))
        self._full = text

    def setText(self, text):
        self._full = text
        self._apply()

    def _apply(self):
        shown = self.fontMetrics().elidedText(
            self._full, Qt.TextElideMode.ElideMiddle, max(20, self.width() - 14))
        super().setText(shown)
        self.setToolTip(self._full if shown != self._full else "")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        p.setPen(QPen(SHADOW, 1))
        p.drawLine(r.left(), r.bottom(), r.left(), r.top())
        p.drawLine(r.left(), r.top(), r.right(), r.top())
        p.setPen(QPen(WHITE, 1))
        p.drawLine(r.left() + 1, r.bottom(), r.right(), r.bottom())
        p.drawLine(r.right(), r.bottom(), r.right(), r.top() + 1)
        p.end()
        super().paintEvent(e)


# ---------------------------------------------------------------------------
# The dashboard
# ---------------------------------------------------------------------------

class Pressable(QWidget):
    """A dashboard part that can be pressed."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.down = False
        self.hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def setEnabled(self, on):
        super().setEnabled(on)
        self.setCursor(Qt.CursorShape.PointingHandCursor if on
                       else Qt.CursorShape.ArrowCursor)
        self.update()

    def enterEvent(self, e):
        self.hover = True
        self.update()

    def leaveEvent(self, e):
        self.hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.down = True
            self.update()

    def mouseReleaseEvent(self, e):
        if self.down:
            self.down = False
            self.update()
            if self.rect().contains(e.position().toPoint()):
                self.clicked.emit()


def dial_face(p, c, r):
    face = QRadialGradient(QPointF(c.x() - r * 0.3, c.y() - r * 0.35), r * 1.4)
    face.setColorAt(0.0, QColor("#FFFEF8"))
    face.setColorAt(1.0, QColor("#EDE3C8"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(face))
    p.drawEllipse(c, r, r)


def needle(p, c, angle, length, tail=8, width=3.4, tone=MARDI_GRAS):
    a = math.radians(angle)
    tip = QPointF(c.x() + length * math.cos(a), c.y() - length * math.sin(a))
    back = QPointF(c.x() - tail * math.cos(a), c.y() + tail * math.sin(a))
    nx, ny = -math.sin(a) * width, -math.cos(a) * width
    poly = QPolygonF([QPointF(c.x() + nx, c.y() + ny), tip,
                      QPointF(c.x() - nx, c.y() - ny), back])
    path = QPainterPath()
    path.addPolygon(poly)
    path.closeSubpath()
    toon.drop_shadow(p, path, 1.5, 2.5, 50)
    toon.paint(p, path, tone, gloss=False, outline=1.8)


def hub(p, c, r):
    g = QRadialGradient(QPointF(c.x() - r * 0.3, c.y() - r * 0.3), r * 1.3)
    g.setColorAt(0, QColor("#FFFFFF"))
    g.setColorAt(1, QColor("#7C858E"))
    p.setBrush(QBrush(g))
    p.setPen(toon.pen(OUTLINE, 2.0))
    p.drawEllipse(c, r, r)


def glass(p, c, r):
    glare = QPainterPath()
    glare.addEllipse(QPointF(c.x() - r * 0.2, c.y() - r * 0.42), r * 0.62,
                     r * 0.32)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 46))
    p.drawPath(glare)


class Speedometer(QWidget):
    """Percent done on the dial; files ever developed on the odometer."""

    SWEEP = 220.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(156, 156)
        self.value = 0.0
        self.target = 0.0
        self.odometer = 0
        self.lit = False
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._step)
        self.setToolTip("How far the current job has got. The odometer counts "
                        "every file DigiCarlo has put in the library.")

    def set_value(self, frac):
        self.target = max(0.0, min(1.0, frac))
        if not self._timer.isActive():
            self._timer.start()

    def set_odometer(self, n):
        self.odometer = n
        self.update()

    def set_lit(self, on):
        self.lit = on
        self.update()

    def _step(self):
        d = self.target - self.value
        if abs(d) < 0.002:
            self.value = self.target
            self._timer.stop()
        else:
            self.value += d * 0.22
        self.update()

    def paintEvent(self, _):
        p = aa(self)
        c = QPointF(self.width() / 2, self.height() / 2)
        R = min(self.width(), self.height()) / 2 - 3
        rf = R - 11
        toon.drop_shadow(p, toon.circle(c, R), 3, 4, 60)
        dial_face(p, c, rf)
        if self.lit:
            p.setBrush(QColor(255, 220, 120, 45))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(c, rf, rf)
        toon.chrome_ring(p, c, R, rf)
        start = 90 + self.SWEEP / 2

        def at(frac, radius):
            ang = math.radians(start - frac * self.SWEEP)
            return QPointF(c.x() + radius * math.cos(ang),
                           c.y() - radius * math.sin(ang))
        for i in range(21):
            frac = i / 20.0
            major = i % 4 == 0
            p.setPen(toon.pen(CARIBBEAN["deep"], 3.0 if major else 1.8))
            p.drawLine(at(frac, rf - 4), at(frac, rf - (13 if major else 8)))
        p.setFont(toon.display_font(8.5))
        p.setPen(INK)
        for i in range(6):
            pt = at(i / 5.0, rf - 25)
            p.drawText(QRectF(pt.x() - 16, pt.y() - 8, 32, 16),
                       Qt.AlignmentFlag.AlignCenter, str(i * 20))
        p.setFont(toon.body_font(6.5, QFont.Weight.Black))
        p.setPen(QColor(CARIBBEAN["deep"]))
        p.drawText(QRectF(c.x() - 30, c.y() + 10, 60, 12),
                   Qt.AlignmentFlag.AlignCenter, "% DONE")
        digits = "%06d" % (self.odometer % 1000000)
        dw, dh = 10, 15
        ow = dw * len(digits) + 4
        orect = QRectF(c.x() - ow / 2, c.y() + rf * 0.40, ow, dh + 4)
        p.setPen(toon.pen(OUTLINE, 1.8))
        p.setBrush(QColor("#161616"))
        p.drawRoundedRect(orect, 3, 3)
        p.setFont(toon.body_font(8, QFont.Weight.Black))
        for i, ch in enumerate(digits):
            cell = QRectF(orect.left() + 2 + i * dw, orect.top() + 2, dw - 1, dh)
            last = i == len(digits) - 1
            p.fillRect(cell, QBrush(toon.vgrad(cell, ["#DADADA", "#FFFFFF",
                                                      "#BDBDBD"] if last else
                                               ["#000000", "#3A3A3A",
                                                "#000000"])))
            p.setPen(QColor("#111111") if last else QColor("#F2F2F2"))
            p.drawText(cell, Qt.AlignmentFlag.AlignCenter, ch)
        p.setFont(toon.body_font(6.5, QFont.Weight.Black))
        p.setPen(QColor(CARIBBEAN["deep"]))
        p.drawText(QRectF(c.x() - 30, orect.bottom() + 1, 60, 12),
                   Qt.AlignmentFlag.AlignCenter, "PHOTOS")
        needle(p, c, start - self.value * self.SWEEP, rf - 8, tail=12)
        hub(p, c, 8)
        glass(p, c, rf)


class FuelGauge(QWidget):
    """Free space on the disk the library is on, E to F."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(80, 80)
        self.frac = 0.5

    def set_space(self, free, total):
        self.frac = free / total if total else 0.0
        self.setToolTip("Fuel: %.1f GB free of %.0f GB where the library is"
                        % (free / 1e9, total / 1e9))
        self.update()

    def paintEvent(self, _):
        p = aa(self)
        c = QPointF(self.width() / 2, self.height() / 2)
        R = self.width() / 2 - 3
        rf = R - 7
        toon.drop_shadow(p, toon.circle(c, R), 2, 3, 55)
        dial_face(p, c, rf)
        # a red band where the tank is nearly empty
        p.setPen(toon.pen(MARDI_GRAS["base"], 4.0))
        p.drawArc(QRectF(c.x() - rf + 6, c.y() - rf + 6, 2 * rf - 12,
                         2 * rf - 12), 150 * 16, -22 * 16)
        for i in range(5):
            ang = math.radians(150 - i * 30)
            p.setPen(toon.pen(INK, 2.2))
            p.drawLine(QPointF(c.x() + (rf - 3) * math.cos(ang),
                               c.y() - (rf - 3) * math.sin(ang)),
                       QPointF(c.x() + (rf - 9) * math.cos(ang),
                               c.y() - (rf - 9) * math.sin(ang)))
        toon.chrome_ring(p, c, R, rf, outline=2.0)
        p.setFont(toon.display_font(8))
        p.setPen(INK)
        p.drawText(QRectF(c.x() - rf + 4, c.y() + 2, 16, 14),
                   Qt.AlignmentFlag.AlignCenter, "E")
        p.drawText(QRectF(c.x() + rf - 20, c.y() + 2, 16, 14),
                   Qt.AlignmentFlag.AlignCenter, "F")
        p.setFont(toon.body_font(5.5, QFont.Weight.Black))
        p.setPen(QColor(CARIBBEAN["deep"]))
        p.drawText(QRectF(c.x() - 20, c.y() + 12, 40, 10),
                   Qt.AlignmentFlag.AlignCenter, "SPACE")
        needle(p, c, 150 - 120 * max(0.0, min(1.0, self.frac)), rf - 7,
               tail=5, width=2.6)
        hub(p, c, 5)


class DashClock(QWidget):
    """The time now -- the date a pull's newest shot will be given."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(80, 80)
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(15000)
        self._tick()

    def _tick(self):
        now = datetime.datetime.now()
        self.setToolTip("It is %s. Pull now, and the newest shot is dated "
                        "with this time." % now.strftime("%H:%M"))
        self.update()

    def paintEvent(self, _):
        p = aa(self)
        c = QPointF(self.width() / 2, self.height() / 2)
        R = self.width() / 2 - 3
        rf = R - 7
        toon.drop_shadow(p, toon.circle(c, R), 2, 3, 55)
        dial_face(p, c, rf)
        for i in range(12):
            ang = math.radians(90 - i * 30)
            major = i % 3 == 0
            p.setPen(toon.pen(INK, 2.4 if major else 1.4))
            p.drawLine(QPointF(c.x() + (rf - 3) * math.cos(ang),
                               c.y() - (rf - 3) * math.sin(ang)),
                       QPointF(c.x() + (rf - (9 if major else 6)) * math.cos(ang),
                               c.y() - (rf - (9 if major else 6)) * math.sin(ang)))
        toon.chrome_ring(p, c, R, rf, outline=2.0)
        p.setFont(toon.body_font(5.5, QFont.Weight.Black))
        p.setPen(QColor(CARIBBEAN["deep"]))
        p.drawText(QRectF(c.x() - 20, c.y() + 9, 40, 10),
                   Qt.AlignmentFlag.AlignCenter, "NOW")
        now = datetime.datetime.now()
        hours = (now.hour % 12 + now.minute / 60.0) * 30
        minutes = now.minute * 6
        for ang, length, width in ((hours, rf * 0.50, 3.4),
                                   (minutes, rf * 0.78, 2.4)):
            a = math.radians(90 - ang)
            p.setPen(toon.pen(INK, width))
            p.drawLine(c, QPointF(c.x() + length * math.cos(a),
                                  c.y() - length * math.sin(a)))
        hub(p, c, 4)


class SteeringWheel(Pressable):
    """Snowberry rim, chrome spokes, and a horn that honks when pressed --
    and, while it is at it, looks for cameras again."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(176, 176)
        self.burst = 0
        self._t = QTimer(self)
        self._t.setSingleShot(True)
        self._t.timeout.connect(self._quiet)
        self.setToolTip("Honk! Looks for cameras and cards again.")
        self.clicked.connect(self._honked)

    def _honked(self):
        self.burst = 1
        self._t.start(750)
        self.update()

    def _quiet(self):
        self.burst = 0
        self.update()

    def paintEvent(self, _):
        p = aa(self)
        c = QPointF(self.width() / 2, self.height() / 2 + 2)
        R, r = 82, 67
        rim = toon.circle(c, R).subtracted(toon.circle(c, r))
        toon.drop_shadow(p, rim, 3, 5, 55)
        # two chrome spokes, down and out, as on the Metropolitan
        for ang in (215, 325):
            a = math.radians(ang)
            end = QPointF(c.x() + (r + 4) * math.cos(a), c.y() - (r + 4) * math.sin(a))
            spoke = QPainterPath()
            nx, ny = -math.sin(a) * 9, -math.cos(a) * 9
            spoke.addPolygon(QPolygonF([
                QPointF(c.x() + nx, c.y() + ny), QPointF(end.x() + nx * 0.7,
                                                         end.y() + ny * 0.7),
                QPointF(end.x() - nx * 0.7, end.y() - ny * 0.7),
                QPointF(c.x() - nx, c.y() - ny)]))
            spoke.closeSubpath()
            p.setBrush(toon.chrome_brush(spoke.boundingRect()))
            p.setPen(toon.pen(OUTLINE, 2.2))
            p.drawPath(spoke)
        toon.paint(p, rim, SNOWBERRY, outline=2.6)
        # finger grips on the inside of the rim
        p.setPen(toon.pen(SNOWBERRY["deep"], 2.0))
        for i in range(14):
            a = math.radians(i * 360 / 14 + 8)
            p.drawLine(QPointF(c.x() + (r + 1) * math.cos(a), c.y() - (r + 1) * math.sin(a)),
                       QPointF(c.x() + (r + 5) * math.cos(a), c.y() - (r + 5) * math.sin(a)))
        # the horn: a chrome ring round a face
        pressed = self.down
        hr = 33
        toon.chrome_ring(p, c, hr, hr - 7)
        cap_r = (hr - 7) * (0.92 if pressed else 1.0)
        tone = dict(CARIBBEAN)
        if self.hover and not pressed:
            tone = {"light": "#9BE3EC", "base": "#45B6CA", "shade": "#258CA0"}
        if not self.isEnabled():
            tone = GREY
        cc = QPointF(c.x(), c.y() + (1.5 if pressed else 0))
        toon.paint(p, toon.circle(cc, cap_r), tone, outline=2.2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(WHITE)
        for dx in (-8, 8):
            p.drawEllipse(QPointF(cc.x() + dx, cc.y() - 5), 5, 6.5)
        p.setBrush(INK)
        for dx in (-7, 9):
            p.drawEllipse(QPointF(cc.x() + dx, cc.y() - 4), 2.4, 3.2)
        p.setPen(toon.pen(INK, 2.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if pressed or self.burst:
            p.setBrush(QColor(MARDI_GRAS["shade"]))
            p.drawEllipse(QPointF(cc.x(), cc.y() + 9), 5, 5.5)
        else:
            p.drawArc(QRectF(cc.x() - 11, cc.y() - 2, 22, 16), 200 * 16, 140 * 16)
        if self.burst:
            self._paint_burst(p, QPointF(self.width() - 42, 30))

    def _paint_burst(self, p, c):
        pts = []
        for i in range(18):
            rad = 34 if i % 2 == 0 else 22
            a = math.radians(i * 20 + 5)
            pts.append(QPointF(c.x() + rad * math.cos(a), c.y() - rad * 0.72 * math.sin(a)))
        path = QPainterPath()
        path.addPolygon(QPolygonF(pts))
        path.closeSubpath()
        toon.paint(p, path, SUNBURST, gloss=False, outline=2.2)
        toon.outlined_text(p, QRectF(c.x() - 34, c.y() - 12, 68, 24),
                           Qt.AlignmentFlag.AlignCenter, "HONK!",
                           toon.display_font(10), MARDI_GRAS["base"], OUTLINE, 2.4)


class PresetKey(Pressable):
    """One of a 1950s car radio's chrome push-button presets."""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = text
        self.setFixedHeight(38)
        self.setMinimumWidth(52)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    def paintEvent(self, _):
        p = aa(self)
        o = 2.5 if self.down else 0.0
        r = QRectF(2, 2 + o, self.width() - 4, self.height() - 7)
        path = toon.rounded(r, 7)
        if not self.down:
            toon.drop_shadow(p, path, 0, 3.5, 70)
        p.setBrush(toon.chrome_brush(r))
        p.setPen(toon.pen(OUTLINE, 2.2))
        p.drawPath(path)
        if self.hover and self.isEnabled():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 230, 120, 70))
            p.drawPath(path)
        p.setFont(toon.body_font(8, QFont.Weight.Black))
        p.setPen(INK if self.isEnabled() else QColor(0, 0, 0, 80))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.text)


class Knob(Pressable):
    def __init__(self, tip, parent=None):
        super().__init__(parent)
        self.setFixedSize(38, 38)
        self.setToolTip(tip)

    def paintEvent(self, _):
        p = aa(self)
        c = QPointF(self.width() / 2, self.height() / 2)
        r = 16 if not self.down else 15
        toon.drop_shadow(p, toon.circle(c, r), 1.5, 3, 60)
        g = QRadialGradient(QPointF(c.x() - 5, c.y() - 6), r * 1.4)
        g.setColorAt(0, QColor("#FFFFFF"))
        g.setColorAt(0.5, QColor("#C9CFD5"))
        g.setColorAt(1, QColor("#7A838C"))
        p.setBrush(QBrush(g))
        p.setPen(toon.pen(OUTLINE, 2.2))
        p.drawEllipse(c, r, r)
        p.setPen(toon.pen(QColor("#6A737C"), 1.4))
        for i in range(16):
            a = math.radians(i * 22.5)
            p.drawLine(QPointF(c.x() + (r - 4) * math.cos(a), c.y() - (r - 4) * math.sin(a)),
                       QPointF(c.x() + (r - 1.5) * math.cos(a), c.y() - (r - 1.5) * math.sin(a)))
        p.setBrush(QColor(MARDI_GRAS["base"]) if self.hover else QColor(INK))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(c.x(), c.y() - r + 7), 2.4, 2.4)


class Radio(QWidget):
    """The status display, and the preset keys that date selected shots."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(300, 176)
        self.caption = "Ready"
        self.detail = ""
        self.keys = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 104, 16, 14)
        row = QHBoxLayout()
        row.setSpacing(7)
        for key, text, tip in (
                ("date", "Set date", "Date the selected shots from a time "
                                     "you choose"),
                ("camera", "Camera", "Keep the camera's own dates for the "
                                     "selected shots"),
                ("auto", "Auto", "Date the selected shots from when they "
                                 "came off the camera"),
                ("skip", "Leave out", "Keep the selected shots out of the "
                                      "library")):
            k = PresetKey(text, self)
            k.setToolTip(tip)
            self.keys[key] = k
            row.addWidget(k)
        lay.addLayout(row)
        self.left = Knob("Activity log", self)
        self.right = Knob("Folders...", self)
        self.left.move(12, 38)
        self.right.move(self.width() - 50, 38)

    def say(self, caption, detail=""):
        self.caption, self.detail = caption, detail
        self.update()

    def paintEvent(self, _):
        p = aa(self)
        face = QRectF(3, 6, self.width() - 6, self.height() - 12)
        path = toon.rounded(face, 18)
        toon.drop_shadow(p, path, 3, 5, 60)
        p.setBrush(toon.chrome_brush(face))
        p.setPen(toon.pen(OUTLINE, 2.6))
        p.drawPath(path)
        inset = face.adjusted(8, 8, -8, -8)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(CARIBBEAN["deep"]))
        p.drawRoundedRect(inset, 12, 12)
        # the dial window
        win = QRectF(58, 16, self.width() - 116, 80)
        wp = toon.rounded(win, 9)
        p.setBrush(QBrush(toon.vgrad(win, ["#FFF6D6", "#FFFBEA", "#F5E7B8"])))
        p.setPen(toon.pen(OUTLINE, 2.2))
        p.drawPath(wp)
        p.save()
        p.setClipPath(wp)
        p.setPen(toon.pen(QColor("#B89B5E"), 1.4))
        p.setFont(toon.body_font(5.5, QFont.Weight.Bold))
        for i, mark in enumerate(("55", "60", "70", "80", "100", "130", "160")):
            x = win.left() + 10 + i * (win.width() - 20) / 6
            p.drawLine(QPointF(x, win.top() + 3), QPointF(x, win.top() + 8))
            p.drawText(QRectF(x - 10, win.top() + 8, 20, 9),
                       Qt.AlignmentFlag.AlignCenter, mark)
        text_r = win.adjusted(10, 20, -8, -4)
        p.setFont(toon.display_font(10))
        p.setPen(INK)
        cap = p.fontMetrics().elidedText(self.caption, Qt.TextElideMode.ElideRight,
                                         int(text_r.width()))
        p.drawText(QRectF(text_r.left(), text_r.top(), text_r.width(), 18),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, cap)
        p.setFont(toon.body_font(8, QFont.Weight.Bold))
        p.setPen(INK_SOFT)
        p.drawText(QRectF(text_r.left(), text_r.top() + 19, text_r.width(),
                          text_r.height() - 19),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop |
                   Qt.TextFlag.TextWordWrap, self.detail)
        p.restore()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 60))
        p.drawRoundedRect(QRectF(win.left() + 6, win.top() + 3, win.width() - 12, 6), 3, 3)


def paint_item_glyph(p, rect, kind, detail=""):
    """A cartoon of what is in the glove box."""
    r = QRectF(rect)
    cx, cy = r.center().x(), r.center().y()
    if kind == "map":
        path = QPainterPath()
        w, h = r.width() * 0.8, r.height() * 0.66
        x0, y0 = cx - w / 2, cy - h / 2
        path.addPolygon(QPolygonF([QPointF(x0, y0 + 3), QPointF(x0 + w / 3, y0),
                                   QPointF(x0 + 2 * w / 3, y0 + 3),
                                   QPointF(x0 + w, y0),
                                   QPointF(x0 + w, y0 + h - 3),
                                   QPointF(x0 + 2 * w / 3, y0 + h),
                                   QPointF(x0 + w / 3, y0 + h - 3),
                                   QPointF(x0, y0 + h)]))
        path.closeSubpath()
        toon.paint(p, path, {"light": "#FFF8D8", "base": "#F6E7B0",
                             "shade": "#E3CD86"}, gloss=False, outline=2.0)
        p.setPen(toon.pen(QColor("#C9B06A"), 1.4))
        p.drawLine(QPointF(x0 + w / 3, y0), QPointF(x0 + w / 3, y0 + h - 3))
        p.drawLine(QPointF(x0 + 2 * w / 3, y0 + 3), QPointF(x0 + 2 * w / 3, y0 + h))
        route = QPainterPath(QPointF(x0 + 6, y0 + h - 8))
        route.cubicTo(QPointF(x0 + w * 0.3, y0 + 6), QPointF(x0 + w * 0.6, y0 + h),
                      QPointF(x0 + w - 7, y0 + 9))
        p.setPen(toon.pen(MARDI_GRAS["base"], 2.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(route)
        return
    if kind == "sd":
        w, h = r.width() * 0.58, r.height() * 0.78
        x0, y0 = cx - w / 2, cy - h / 2
        path = QPainterPath()
        path.addPolygon(QPolygonF([QPointF(x0, y0), QPointF(x0 + w - 8, y0),
                                   QPointF(x0 + w, y0 + 8), QPointF(x0 + w, y0 + h),
                                   QPointF(x0, y0 + h)]))
        path.closeSubpath()
        toon.paint(p, path, {"light": "#6B7883", "base": "#4B5660",
                             "shade": "#333B43"}, outline=2.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(SUNBURST["base"]))
        for i in range(5):
            p.drawRect(QRectF(x0 + 4 + i * (w - 10) / 5, y0 + 3, 3, 7))
        label = QRectF(x0 + 4, y0 + h * 0.38, w - 8, h * 0.52)
        toon.paint(p, toon.rounded(label, 3), SNOWBERRY, gloss=False, outline=1.6)
        p.setFont(toon.display_font(7))
        p.setPen(QColor(CARIBBEAN["deep"]))
        p.drawText(label, Qt.AlignmentFlag.AlignCenter, "SD")
        return
    # a camera: two-tone like everything else here
    small = kind == "sipix"
    w, h = r.width() * (0.62 if small else 0.82), r.height() * (0.5 if small else 0.58)
    x0, y0 = cx - w / 2, cy - h / 2 + 3
    body = toon.rounded(QRectF(x0, y0, w, h), 6)
    toon.drop_shadow(p, body, 1.5, 2.5, 60)
    tone = GREY if small else CARIBBEAN
    toon.paint(p, body, tone, outline=2.0)
    toon.paint(p, toon.rounded(QRectF(x0 + 5, y0 - 5, w * 0.3, 7), 2), SNOWBERRY,
               gloss=False, outline=1.8)
    lr = h * 0.36
    toon.chrome_ring(p, QPointF(cx + (0 if not small else 0), y0 + h / 2), lr,
                     lr * 0.62, outline=1.8)
    p.setBrush(QColor("#12303A"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(cx, y0 + h / 2), lr * 0.62, lr * 0.62)
    p.setBrush(QColor(255, 255, 255, 210))
    p.drawEllipse(QPointF(cx - lr * 0.2, y0 + h / 2 - lr * 0.2), lr * 0.18, lr * 0.18)
    if small:
        p.setBrush(QColor(MARDI_GRAS["base"]))
        p.setPen(toon.pen(OUTLINE, 1.4))
        p.drawEllipse(QPointF(x0 + w - 6, y0 - 1), 3, 3)


class GloveItem(Pressable):
    def __init__(self, glyph, label, tip, parent=None):
        super().__init__(parent)
        self.glyph = glyph
        self.label = label
        self.setToolTip(tip)
        self.setFixedSize(84, 70)

    def paintEvent(self, _):
        p = aa(self)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        if self.hover and self.isEnabled():
            p.setPen(toon.pen(SUNBURST["base"], 2.4))
            p.setBrush(QColor(255, 210, 63, 60))
            p.drawRoundedRect(r, 10, 10)
        if not self.isEnabled():
            p.setOpacity(0.45)
        o = 1.5 if self.down else 0
        paint_item_glyph(p, QRectF(r.left() + 14, r.top() + 2 + o, r.width() - 28,
                                   38), self.glyph)
        p.setFont(toon.body_font(7.5, QFont.Weight.Black))
        text = p.fontMetrics().elidedText(self.label, Qt.TextElideMode.ElideRight,
                                          int(r.width()))
        tr = QRectF(r.left(), r.bottom() - 20, r.width(), 18)
        toon.outlined_text(p, tr, Qt.AlignmentFlag.AlignCenter, text,
                           toon.body_font(7.5, QFont.Weight.Black), WHITE,
                           OUTLINE, 2.4)


class GloveBox(QWidget):
    """Putt-Putt kept what he found in his glove compartment. DigiCarlo keeps
    the cameras and cards plugged in -- and a road map, for folders."""

    pull = pyqtSignal(object)
    pull_folder = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(214, 176)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(16, 46, 16, 14)
        self.grid.setHorizontalSpacing(2)
        self.grid.setVerticalSpacing(0)
        self.items = []
        self.found = []
        self.busy = False
        self.set_sources([])

    def set_sources(self, found, busy=False):
        self.found = list(found)
        self.busy = busy
        self._rebuild()

    def set_busy(self, busy):
        self.busy = busy
        for it in self.items:
            it.setEnabled(not busy)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._rebuild()

    def _rebuild(self):
        for it in self.items:
            self.grid.removeWidget(it)
            it.deleteLater()
        self.items = []
        entries = []
        for src in self.found:
            if src.kind in ("volume", "folder"):
                glyph = "sd" if "SD card" in (src.detail or "") else "camera"
            else:
                glyph = "sipix" if src.kind == "sipix" else "camera"
            entries.append((glyph, src.label, "Pull the new pictures from %s"
                            % src.describe(), src))
        entries.append(("map", "A folder...", "Pull from a folder on this "
                        "computer, as if it were a card", None))
        cols = max(1, (self.width() - 32) // 86)
        for n, (glyph, label, tip, src) in enumerate(entries):
            it = GloveItem(glyph, label, tip, self)
            if src is None:
                it.clicked.connect(self.pull_folder)
            else:
                it.clicked.connect(lambda s=src: self.pull.emit(s))
            it.setEnabled(not self.busy)
            self.grid.addWidget(it, n // cols, n % cols,
                                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            it.show()
            self.items.append(it)
        self.grid.setColumnStretch(cols, 1)
        self.grid.setRowStretch((len(entries) - 1) // cols + 1, 1)
        self.update()

    def paintEvent(self, _):
        p = aa(self)
        r = QRectF(self.rect()).adjusted(3, 6, -3, -6)
        frame = toon.rounded(r, 16)
        toon.drop_shadow(p, frame, 3, 5, 60)
        toon.paint(p, frame, SNOWBERRY, outline=2.6)
        # the chrome script on the lid
        plate = QRectF(r.left() + 12, r.top() + 5, r.width() - 24, 30)
        font = toon.script_font(17)
        path = QPainterPath()
        path.addText(0, 0, font, "DigiCarlo")
        box = path.boundingRect()
        scale = min(1.0, plate.height() / max(1.0, box.height()))
        p.save()
        p.translate(plate.center().x() - box.center().x() * scale,
                    plate.center().y() - box.center().y() * scale)
        p.scale(scale, scale)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(20, 45, 55, 90))
        p.drawPath(path.translated(1.2, 1.6))
        p.setBrush(toon.chrome_brush(box))
        p.setPen(toon.pen(QColor("#3B4550"), 1.0))
        p.drawPath(path)
        p.restore()
        inside = QRectF(r.left() + 9, r.top() + 38, r.width() - 18,
                        r.height() - 46)
        ip = toon.rounded(inside, 11)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(toon.vgrad(inside, ["#0B2F37", "#155A69", "#1B6C7D"])))
        p.drawPath(ip)
        p.setPen(toon.pen(OUTLINE, 2.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(ip)
        if not self.found:
            p.setFont(toon.body_font(7.5, QFont.Weight.Bold))
            p.setPen(QColor(255, 255, 255, 150))
            p.drawText(inside.adjusted(96, 8, -8, -8),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter |
                       Qt.TextFlag.TextWordWrap,
                       "No camera plugged in. Put a card in the reader or "
                       "connect a camera.")


class Starter(Pressable):
    """The big red starter button. When a job is running it says STOP."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(136, 176)
        self.count = 0
        self.busy = False

    def set_state(self, count, busy):
        self.count, self.busy = count, busy
        self.setEnabled(busy or count > 0)
        self.setToolTip("Stop after the file being worked on" if busy else
                        "Put the %d waiting shot%s in the library"
                        % (count, "" if count == 1 else "s") if count else
                        "Nothing is waiting")
        self.update()

    def paintEvent(self, _):
        p = aa(self)
        c = QPointF(self.width() / 2, 70)
        R, r = 60, 48
        toon.drop_shadow(p, toon.circle(c, R), 3, 5, 65)
        toon.chrome_ring(p, c, R, r)
        tone = SUNBURST if self.busy else MARDI_GRAS if self.isEnabled() else GREY
        if self.hover and self.isEnabled() and not self.busy:
            tone = {"light": "#FF8C7C", "base": "#E84A3E", "shade": "#B32F25"}
        cr = r * (0.93 if self.down else 1.0)
        cc = QPointF(c.x(), c.y() + (2 if self.down else 0))
        toon.paint(p, toon.circle(cc, cr), tone, outline=2.6)
        word = "STOP" if self.busy else "START"
        toon.outlined_text(p, QRectF(cc.x() - cr, cc.y() - 14, 2 * cr, 28),
                           Qt.AlignmentFlag.AlignCenter, word,
                           toon.display_font(15),
                           WHITE if self.isEnabled() else QColor("#EEF0F2"),
                           OUTLINE, 3.2)
        label = "stop the job" if self.busy else "put in library"
        toon.outlined_text(p, QRectF(0, c.y() + R + 6, self.width(), 18),
                           Qt.AlignmentFlag.AlignCenter, label,
                           toon.display_font(9), WHITE, OUTLINE, 2.8)
        if self.count and not self.busy:
            b = QPointF(c.x() + R * 0.72, c.y() - R * 0.72)
            text = str(self.count) if self.count < 1000 else "999+"
            p.setFont(toon.display_font(9))
            w = max(28, p.fontMetrics().horizontalAdvance(text) + 14)
            badge = toon.rounded(QRectF(b.x() - w / 2, b.y() - 14, w, 28), 14)
            toon.paint(p, badge, SUNBURST, outline=2.4)
            p.setPen(INK)
            p.drawText(badge.boundingRect(), Qt.AlignmentFlag.AlignCenter, text)


class Dash(QWidget):
    """Snowberry padded rail over a Caribbean Blue dash, chrome between."""

    HEIGHT = 238

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 44, 14, 12)
        row.setSpacing(10)
        small = QVBoxLayout()
        small.setSpacing(6)
        self.fuel = FuelGauge(self)
        self.clock = DashClock(self)
        small.addWidget(self.fuel)
        small.addWidget(self.clock)
        small.addStretch(1)
        row.addLayout(small)
        self.wheel = SteeringWheel(self)
        row.addWidget(self.wheel, 0, Qt.AlignmentFlag.AlignTop)
        self.gauge = Speedometer(self)
        row.addWidget(self.gauge, 0, Qt.AlignmentFlag.AlignVCenter)
        self.radio = Radio(self)
        row.addWidget(self.radio, 0, Qt.AlignmentFlag.AlignTop)
        self.glove = GloveBox(self)
        row.addWidget(self.glove, 1, Qt.AlignmentFlag.AlignTop)
        self.go = Starter(self)
        row.addWidget(self.go, 0, Qt.AlignmentFlag.AlignTop)

    def say(self, caption, detail=""):
        self.radio.say(caption, detail)

    def paintEvent(self, _):
        p = aa(self)
        w, h = float(self.width()), float(self.height())
        top = QPainterPath(QPointF(0, 26))
        top.quadTo(QPointF(w / 2, -6), QPointF(w, 26))
        rail_bottom = QPainterPath(QPointF(w, 46))
        rail_bottom.quadTo(QPointF(w / 2, 14), QPointF(0, 46))
        rail = QPainterPath(top)
        rail.connectPath(rail_bottom)
        rail.closeSubpath()
        body = QPainterPath(QPointF(0, 40))
        body.quadTo(QPointF(w / 2, 8), QPointF(w, 40))
        body.lineTo(w, h + 4)
        body.lineTo(0, h + 4)
        body.closeSubpath()
        toon.paint(p, body, CARIBBEAN, gloss=False, outline=2.6)
        # soft gloss along the curve of the dash
        p.save()
        p.setClipPath(body)
        g = QPainterPath(QPointF(0, 58))
        g.quadTo(QPointF(w / 2, 26), QPointF(w, 58))
        g.lineTo(w, 84)
        g.quadTo(QPointF(w / 2, 52), QPointF(0, 84))
        g.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 40))
        p.drawPath(g)
        p.restore()
        toon.paint(p, rail, SNOWBERRY, outline=2.6)
        # chrome trim under the rail
        trim = QPainterPath(QPointF(0, 45))
        trim.quadTo(QPointF(w / 2, 13), QPointF(w, 45))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(toon.pen(OUTLINE, 7.0))
        p.drawPath(trim)
        p.setPen(QPen(toon.chrome_brush(QRectF(0, 20, w, 30)), 4.4,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        p.drawPath(trim)


# ---------------------------------------------------------------------------
# The shots, seen through the windshield
# ---------------------------------------------------------------------------

KIND_ROLE = Qt.ItemDataRole.UserRole
KEY_ROLE = Qt.ItemDataRole.UserRole + 1
DATA_ROLE = Qt.ItemDataRole.UserRole + 2


def short_time(dt):
    return dt.strftime("%b %d, %H:%M") if dt else "?"


class ShotDelegate(QStyledItemDelegate):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner

    def sizeHint(self, option, index):
        kind = index.data(KIND_ROLE)
        if kind in ("batch", "session"):
            w = max(260, self.owner.viewport().width() - 18)
            if kind == "batch":
                return QSize(w, 70)
            return QSize(w, 42 + 17 * len(index.data(DATA_ROLE)["lines"]))
        return QSize(CELL_W, CELL_H)

    def paint(self, p, option, index):
        kind = index.data(KIND_ROLE)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if kind == "batch":
            self._plate(p, QRectF(option.rect), index.data(DATA_ROLE))
        elif kind == "session":
            self._sign(p, QRectF(option.rect), index.data(DATA_ROLE))
        else:
            self._print(p, option, index)
        p.restore()

    def _plate(self, p, r, d):
        """Each pull wears a 1950s licence plate."""
        plate = QRectF(r.left() + 6, r.top() + 10, min(r.width() - 12, 470), 52)
        path = toon.rounded(plate, 9)
        toon.drop_shadow(p, path, 3, 4, 70)
        toon.paint(p, path, {"light": "#FFFDF3", "base": SNOWBERRY["base"],
                             "shade": SNOWBERRY["shade"]}, outline=2.6)
        inner = plate.adjusted(5, 5, -5, -5)
        p.setPen(toon.pen(CARIBBEAN["deep"], 2.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(inner, 6, 6)
        for x in (plate.left() + 22, plate.right() - 22):
            p.setBrush(toon.chrome_brush(QRectF(x - 5, plate.top() + 8, 10, 10)))
            p.setPen(toon.pen(OUTLINE, 1.6))
            p.drawEllipse(QPointF(x, plate.top() + 13), 4.2, 4.2)
        p.setFont(toon.body_font(6.5, QFont.Weight.Black))
        p.setPen(QColor(MARDI_GRAS["base"]))
        p.drawText(QRectF(inner.left(), inner.top() + 1, inner.width(), 10),
                   Qt.AlignmentFlag.AlignCenter, d["top"])
        font = toon.display_font(15)
        p.setFont(font)
        text = p.fontMetrics().elidedText(d["title"], Qt.TextElideMode.ElideRight,
                                          int(inner.width() - 40))
        p.setPen(QColor(CARIBBEAN["deep"]))
        p.drawText(QRectF(inner.left(), inner.top() + 10, inner.width(),
                          inner.height() - 10), Qt.AlignmentFlag.AlignCenter, text)
        toon.outlined_text(p, QRectF(plate.right() + 14, plate.top(),
                                     r.right() - plate.right() - 18, plate.height()),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           d["right"], toon.display_font(10), WHITE, OUTLINE, 2.8)

    def _sign(self, p, r, d):
        """A wooden signpost for each session, and a ticket saying how it
        will be dated."""
        p.setFont(toon.display_font(11))
        tw = p.fontMetrics().horizontalAdvance(d["title"])
        board = QRectF(r.left() + 10, r.top() + 6, tw + 30, 28)
        post = QRectF(board.left() + 12, board.bottom() - 2, 8, 12)
        p.setBrush(QColor(WOOD["shade"]))
        p.setPen(toon.pen(OUTLINE, 2.0))
        p.drawRoundedRect(post, 2, 2)
        path = QPainterPath()
        path.addPolygon(QPolygonF([
            QPointF(board.left(), board.top() + 3), QPointF(board.right() - 12,
                                                            board.top()),
            QPointF(board.right(), board.center().y()),
            QPointF(board.right() - 12, board.bottom()),
            QPointF(board.left(), board.bottom() - 2)]))
        path.closeSubpath()
        toon.drop_shadow(p, path, 2, 3, 60)
        toon.paint(p, path, WOOD, outline=2.4)
        p.setPen(toon.pen(QColor(WOOD["shade"]), 1.2))
        for i in range(2):
            y = board.top() + 9 + i * 10
            p.drawLine(QPointF(board.left() + 6, y), QPointF(board.left() + 14, y))
        p.setPen(QColor("#4A2C12"))
        p.drawText(QRectF(board.left() + 10, board.top(), tw + 10, board.height()),
                   Qt.AlignmentFlag.AlignVCenter, d["title"])
        count = QRectF(board.right() + 10, board.top(), 160, board.height())
        toon.outlined_text(p, count, Qt.AlignmentFlag.AlignVCenter |
                           Qt.AlignmentFlag.AlignLeft, d["count"],
                           toon.display_font(10), WHITE, OUTLINE, 2.6)
        lines = d["lines"]
        p.setFont(toon.body_font(8.5, QFont.Weight.Bold))
        fm = p.fontMetrics()
        width = max(fm.horizontalAdvance(t) for t, _ in lines) + 24
        ticket = QRectF(r.left() + 30, board.bottom() + 6,
                        min(width, r.width() - 40), 8 + 17 * len(lines))
        tp = toon.rounded(ticket, 7)
        toon.drop_shadow(p, tp, 2, 3, 45)
        p.setBrush(QColor(255, 253, 244, 240))
        p.setPen(toon.pen(OUTLINE, 2.0))
        p.drawPath(tp)
        for n, (text, colour) in enumerate(lines):
            p.setPen(QColor(colour))
            p.drawText(QRectF(ticket.left() + 12, ticket.top() + 4 + 17 * n,
                              ticket.width() - 18, 17),
                       Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(text, Qt.TextElideMode.ElideRight,
                                     int(ticket.width() - 18)))

    def _print(self, p, option, index):
        """A snapshot print: white border, the date written on it in pen."""
        r = QRectF(option.rect)
        d = index.data(DATA_ROLE)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        lift = -3 if selected else (-1 if hover else 0)
        card = QRectF(r.left() + 8, r.top() + 10 + lift, r.width() - 16,
                      r.height() - 16)
        cp = toon.rounded(card, 5)
        toon.drop_shadow(p, cp, 3, 5 - lift, 70)
        if selected:
            p.setPen(toon.pen(SUNBURST["base"], 8))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(cp)
        p.setBrush(QColor("#FFFEFA"))
        p.setPen(toon.pen(OUTLINE, 2.2))
        p.drawPath(cp)
        photo = QRectF(card.left() + 6, card.top() + 6, card.width() - 12, THUMB_H)
        img = self.owner.thumb(d["key"])
        if img is not None and img.isNull():
            p.fillRect(photo, QColor("#EDE6D6"))
            face = photo.center()
            p.setPen(toon.pen(INK_SOFT, 2.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(face, 15, 15)
            for dx in (-5, 5):
                p.drawLine(QPointF(face.x() + dx - 2, face.y() - 6),
                           QPointF(face.x() + dx + 2, face.y() - 2))
                p.drawLine(QPointF(face.x() + dx + 2, face.y() - 6),
                           QPointF(face.x() + dx - 2, face.y() - 2))
            p.drawArc(QRectF(face.x() - 7, face.y() + 3, 14, 10), 20 * 16, 140 * 16)
            p.setFont(toon.body_font(7, QFont.Weight.Bold))
            p.drawText(QRectF(photo.left(), photo.bottom() - 16, photo.width(), 14),
                       Qt.AlignmentFlag.AlignCenter, "can't show this one")
        elif img is not None:
            scaled = img.scaled(int(photo.width() * 2), int(photo.height() * 2),
                                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                Qt.TransformationMode.SmoothTransformation)
            p.save()
            p.setClipRect(photo)
            sw, sh = scaled.width() / 2, scaled.height() / 2
            p.drawImage(QRectF(photo.center().x() - sw / 2,
                               photo.center().y() - sh / 2, sw, sh), scaled)
            p.restore()
        else:
            p.fillRect(photo, QColor("#E7EEF0"))
            p.setFont(toon.display_font(12))
            p.setPen(QColor(CARIBBEAN["shade"]))
            p.drawText(photo, Qt.AlignmentFlag.AlignCenter, "...")
        if d["video"]:
            for x in (photo.left(), photo.right() - 8):
                p.fillRect(QRectF(x, photo.top(), 8, photo.height()),
                           QColor(15, 20, 22, 215))
                y = photo.top() + 3
                while y < photo.bottom() - 5:
                    p.fillRect(QRectF(x + 2.5, y, 3, 4), QColor("#F4EFE1"))
                    y += 9
            play = QPainterPath()
            cx, cy = photo.center().x(), photo.center().y()
            play.addPolygon(QPolygonF([QPointF(cx - 7, cy - 10), QPointF(cx + 11, cy),
                                       QPointF(cx - 7, cy + 10)]))
            play.closeSubpath()
            toon.paint(p, play, SNOWBERRY, gloss=False, outline=2.0)
        p.setPen(toon.pen(OUTLINE, 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(photo)
        # the shot number, as 'digicarlo plan' prints it
        num = str(d["number"])
        p.setFont(toon.display_font(8))
        nw = max(22, p.fontMetrics().horizontalAdvance(num) + 12)
        badge = toon.rounded(QRectF(card.left() - 6, card.top() - 8, nw, 20), 10)
        toon.paint(p, badge, SUNBURST, gloss=False, outline=2.0)
        p.setPen(INK)
        p.drawText(badge.boundingRect(), Qt.AlignmentFlag.AlignCenter, num)
        if d["pinned"]:
            pin = QPointF(card.center().x(), card.top() - 1)
            tone = MARDI_GRAS if d["pinned"] == "set" else GREY
            p.setPen(toon.pen(OUTLINE, 1.8))
            p.drawLine(pin, QPointF(pin.x(), pin.y() + 9))
            toon.paint(p, toon.circle(QPointF(pin.x(), pin.y() - 2), 6.5), tone,
                       outline=2.0)
        p.setFont(toon.body_font(8, QFont.Weight.Black))
        name = p.fontMetrics().elidedText(d["name"], Qt.TextElideMode.ElideMiddle,
                                          int(card.width() - 8))
        p.setPen(INK)
        p.drawText(QRectF(card.left(), photo.bottom() + 4, card.width(), 15),
                   Qt.AlignmentFlag.AlignCenter, name)
        p.setFont(toon.hand_font(8.5))
        p.setPen(QColor(MARDI_GRAS["shade"]) if d["pinned"] == "set"
                 else QColor("#1D4F9A"))
        p.drawText(QRectF(card.left(), photo.bottom() + 18, card.width(), 18),
                   Qt.AlignmentFlag.AlignCenter, d["when"])


class ShotList(QListWidget):
    """Every shot waiting for the library, grouped by pull and session, in
    front of the scenery.

    One list, so a shift-click can run across sessions. Headers are full-width
    items, which makes the icon view start a fresh row after each.
    """

    selection_changed = pyqtSignal()

    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self.owner = owner
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setUniformItemSizes(False)
        self.setSpacing(3)
        self.setMouseTracking(True)
        self.setFrameShape(QListWidget.Shape.NoFrame)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(24)
        self.setItemDelegate(ShotDelegate(self))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.viewport().setAutoFillBackground(False)
        self.itemSelectionChanged.connect(self.selection_changed)
        self.itemClicked.connect(self._clicked)
        self.empty_text = ""
        self._scene = None

    def thumb(self, key):
        return self.owner.thumb(key)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._scene = None
        # Headers are as wide as the view; tell the layout they changed.
        self.doItemsLayout()

    def scrollContentsBy(self, dx, dy):
        # The scenery stays put while the prints scroll past it, so the
        # whole view repaints rather than being shifted.
        super().scrollContentsBy(dx, dy)
        self.viewport().update()

    def _clicked(self, item):
        if item.data(KIND_ROLE) != "session":
            return
        keys = set(item.data(DATA_ROLE)["keys"])
        mods = QApplication.keyboardModifiers()
        if not mods & Qt.KeyboardModifier.ControlModifier:
            self.clearSelection()
        for i in range(self.count()):
            it = self.item(i)
            if it.data(KIND_ROLE) == "shot" and it.data(KEY_ROLE) in keys:
                it.setSelected(True)

    def selected_keys(self):
        return [it.data(KEY_ROLE) for it in self.selectedItems()
                if it.data(KIND_ROLE) == "shot"]

    def paintEvent(self, e):
        vp = self.viewport()
        size = vp.size()
        if self._scene is None or self._scene.size() != size:
            self._scene = toon.scenery(size.width(), size.height())
        p = QPainter(vp)
        p.drawPixmap(0, 0, self._scene)
        if self.count() == 0 and self.empty_text:
            self._bubble(p, QRectF(vp.rect()))
        p.end()
        super().paintEvent(e)

    def _bubble(self, p, r):
        """DigiCarlo, the camera, says what to do next."""
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = min(430.0, r.width() - 160)
        p.setFont(toon.body_font(10, QFont.Weight.Bold))
        fm = p.fontMetrics()
        text_rect = fm.boundingRect(QRect(0, 0, int(w - 40), 1000),
                                    Qt.TextFlag.TextWordWrap, self.empty_text)
        h = text_rect.height() + 36
        bubble = QRectF(r.center().x() - w / 2 + 50, r.top() + max(20, r.height() * 0.18),
                        w, h)
        path = toon.rounded(bubble, 22)
        tail = QPainterPath()
        tail.addPolygon(QPolygonF([QPointF(bubble.left() + 30, bubble.bottom() - 8),
                                   QPointF(bubble.left() - 26, bubble.bottom() + 34),
                                   QPointF(bubble.left() + 62, bubble.bottom() - 8)]))
        shape = path.united(tail)
        toon.drop_shadow(p, shape, 3, 5, 60)
        p.setBrush(QColor("#FFFFFF"))
        p.setPen(toon.pen(OUTLINE, 2.6))
        p.drawPath(shape)
        p.setPen(INK)
        p.drawText(bubble.adjusted(20, 16, -20, -16), Qt.TextFlag.TextWordWrap |
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   self.empty_text)
        p.drawPixmap(QRectF(bubble.left() - 120, bubble.bottom() + 6, 96, 96),
                     icon_pixmap(192), QRectF(0, 0, 192, 192))


class Windshield(QWidget):
    """A chrome-framed view of the scenery with the shots in it."""

    def __init__(self, child, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(9, 9, 9, 6)
        lay.addWidget(child)

    def paintEvent(self, _):
        p = aa(self)
        r = QRectF(self.rect()).adjusted(2, 2, -2, 1)
        frame = toon.rounded(r, 16)
        hole = toon.rounded(r.adjusted(7, 7, -7, -4), 10)
        ring = frame.subtracted(hole)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(toon.chrome_brush(r))
        p.drawPath(ring)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(toon.pen(OUTLINE, 2.6))
        p.drawPath(frame)
        p.setPen(toon.pen(OUTLINE, 2.0))
        p.drawPath(hole)


# ---------------------------------------------------------------------------
# Background work
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Dialogs: Windows 95, in Caribbean Blue
# ---------------------------------------------------------------------------

class Win95Dialog(QDialog):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog |
                            Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle(title)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(3, 3, 3, 3)
        outer.setSpacing(0)
        self.bar = TitleBar(title, self, buttons=("close",))
        self.bar.close_clicked.connect(self.reject)
        outer.addWidget(self.bar)
        self.body = QWidget(self)
        self.lay = QVBoxLayout(self.body)
        self.lay.setContentsMargins(14, 14, 14, 14)
        self.lay.setSpacing(10)
        outer.addWidget(self.body)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), FACE)
        bevel(p, self.rect(), raised=True)

    def buttons(self, *specs):
        row = QHBoxLayout()
        row.addStretch(1)
        made = []
        for text, role in specs:
            b = QPushButton(text, self)
            b.setMinimumWidth(84)
            b.setMinimumHeight(28)
            if role == "accept":
                b.setDefault(True)
                b.clicked.connect(self.accept)
            elif role == "reject":
                b.clicked.connect(self.reject)
            row.addWidget(b)
            made.append(b)
        self.lay.addLayout(row)
        return made


def glyph_label(kind):
    pm = QPixmap(72, 72)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = QPointF(18, 18)
    if kind == "error":
        toon.paint(p, toon.circle(c, 15), MARDI_GRAS, outline=2.2)
        p.setPen(toon.pen(WHITE, 3.4))
        p.drawLine(QPointF(12, 12), QPointF(24, 24))
        p.drawLine(QPointF(24, 12), QPointF(12, 24))
    else:
        toon.paint(p, toon.circle(c, 15), SUNBURST if kind == "question"
                   else CARIBBEAN, outline=2.2)
        toon.outlined_text(p, QRectF(3, 3, 30, 30), Qt.AlignmentFlag.AlignCenter,
                           "?" if kind == "question" else "i",
                           toon.display_font(13), WHITE, OUTLINE, 2.6)
    p.end()
    lab = QLabel()
    lab.setPixmap(pm)
    lab.setAlignment(Qt.AlignmentFlag.AlignTop)
    return lab


def message(parent, title, text, kind="info", ask=None):
    """A Windows 95 message box. With ask=('Yes text', 'No text') it asks."""
    dlg = Win95Dialog(title, parent)
    row = QHBoxLayout()
    row.setSpacing(14)
    row.addWidget(glyph_label(kind))
    lab = QLabel(text, dlg)
    lab.setWordWrap(True)
    lab.setMinimumWidth(340)
    lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    row.addWidget(lab, 1)
    dlg.lay.addLayout(row)
    if ask:
        dlg.buttons((ask[0], "accept"), (ask[1], "reject"))
    else:
        dlg.buttons(("OK", "accept"))
    return dlg.exec() == QDialog.DialogCode.Accepted


class DateDialog(Win95Dialog):
    """How the selected shots should be dated."""

    def __init__(self, parent, shots, plan):
        super().__init__("Date the selected shots", parent)
        n = len(shots)
        first = plan.times[shots[0].key]
        cams = [s.camera_time for s in shots if s.camera_time]
        intro = QLabel("%d shot%s selected (%s)." % (
            n, "" if n == 1 else "s", describe_numbers([s.number for s in shots])),
            self)
        intro.setFont(ui_font(9.5, bold=True))
        self.lay.addWidget(intro)
        self.group = QButtonGroup(self)
        self.start = QRadioButton("Taken starting at:", self)
        self.when = QDateTimeEdit(self)
        self.when.setDisplayFormat("yyyy-MM-dd  HH:mm:ss")
        self.when.setCalendarPopup(True)
        self.when.setDateTime(QDateTime(first))
        row = QHBoxLayout()
        row.addWidget(self.start)
        row.addWidget(self.when)
        row.addStretch(1)
        self.lay.addLayout(row)
        note = QLabel("The rest follow with the gaps the camera's clock "
                      "recorded between them.", self)
        note.setWordWrap(True)
        note.setContentsMargins(24, 0, 0, 0)
        note.setStyleSheet("color: #4A5A60;")
        self.lay.addWidget(note)
        self.camera = QRadioButton("Keep the camera's own dates  (%s)" % (
            timeplan.fmt_span(min(cams), max(cams)) if cams else
            "this camera has no clock"), self)
        self.camera.setEnabled(bool(cams))
        self.auto = QRadioButton("Automatic: dated when they came off the camera",
                                 self)
        for b in (self.start, self.camera, self.auto):
            self.group.addButton(b)
            if b is not self.start:
                self.lay.addWidget(b)
        self.start.setChecked(True)
        self.when.dateTimeChanged.connect(lambda _: self.start.setChecked(True))
        self.buttons(("OK", "accept"), ("Cancel", "reject"))

    def choice(self):
        if self.camera.isChecked():
            return "camera"
        if self.auto.isChecked():
            return "auto"
        return self.when.dateTime().toPyDateTime().replace(microsecond=0)


class FoldersDialog(Win95Dialog):
    def __init__(self, parent, settings, first_run=False):
        super().__init__("Folders", parent)
        if first_run:
            hello = QLabel("Welcome to DigiCarlo. Where should pictures go?",
                           self)
            hello.setFont(ui_font(9.5, bold=True))
            self.lay.addWidget(hello)
        self.fields = {}
        for key, title, help_ in (
                ("library", "Library",
                 "Re-dated copies, ready for a phone or a photo service. "
                 "A synced folder is fine."),
                ("archive", "Archive",
                 "The camera's untouched originals. Keep this out of anything "
                 "that syncs, or every photo arrives twice.")):
            lab = QLabel(title, self)
            lab.setFont(ui_font(9.5, bold=True))
            self.lay.addWidget(lab)
            row = QHBoxLayout()
            edit = QLineEdit(getattr(settings, key), self)
            edit.setMinimumWidth(380)
            browse = QPushButton("Browse...", self)
            browse.clicked.connect(lambda _, e=edit, t=title: self._browse(e, t))
            row.addWidget(edit, 1)
            row.addWidget(browse)
            self.lay.addLayout(row)
            h = QLabel(help_, self)
            h.setWordWrap(True)
            h.setStyleSheet("color: #4A5A60;")
            self.lay.addWidget(h)
            self.fields[key] = edit
        self.buttons(("OK", "accept"), ("Cancel", "reject"))

    def _browse(self, edit, title):
        start = edit.text() if os.path.isdir(edit.text()) else \
            os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, "Choose the %s folder"
                                                % title.lower(), start)
        if path:
            edit.setText(path)

    def values(self):
        return {k: os.path.expanduser(e.text().strip())
                for k, e in self.fields.items()}


class TextDialog(Win95Dialog):
    def __init__(self, parent, title, text):
        super().__init__(title, parent)
        view = QPlainTextEdit(self)
        view.setReadOnly(True)
        view.setPlainText(text)
        view.setMinimumSize(640, 380)
        f = QFont("DejaVu Sans Mono")
        f.setPointSizeF(9)
        view.setFont(f)
        self.lay.addWidget(view)
        self.buttons(("Close", "accept"))
        view.moveCursor(view.textCursor().MoveOperation.End)


def describe_numbers(nums):
    nums = sorted(nums)
    runs, start, prev = [], None, None
    for n in nums:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            runs.append((start, prev))
            start = prev = n
    if start is not None:
        runs.append((start, prev))
    text = ", ".join(str(a) if a == b else "%d-%d" % (a, b) for a, b in runs)
    return ("shot " if len(nums) == 1 else "shots ") + text


# ---------------------------------------------------------------------------
# The main window
# ---------------------------------------------------------------------------

class MainWindow(QWidget):
    BORDER = 4

    def __init__(self, settings=None):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Window |
                            Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle("DigiCarlo")
        self.setMouseTracking(True)
        self.setMinimumSize(1100, 640)
        self.resize(1180, 800)
        self.settings = settings or config.Settings()
        self.arc = archive.Archive(self.settings.archive)
        self.overrides = []
        self.plan = None
        self.found = []
        self.job = None
        self.scan_job = None
        self.lines = []
        self.thumbs = {}
        self.asked = set()
        self.signature = None
        self.last_ok = False

        outer = QVBoxLayout(self)
        m = self.BORDER
        outer.setContentsMargins(m, m, m, m)
        outer.setSpacing(0)
        self.bar = TitleBar("DigiCarlo", self)
        self.bar.close_clicked.connect(self.close)
        self.bar.minimise_clicked.connect(self.showMinimized)
        self.bar.zoom_clicked.connect(self._toggle_zoom)
        outer.addWidget(self.bar)
        outer.addWidget(self._menus())

        self.list = ShotList(self)
        self.list.selection_changed.connect(self._selection_changed)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.itemDoubleClicked.connect(self._open_item)
        outer.addWidget(Windshield(self.list, self), 1)

        self.dash = Dash(self)
        self.dash.go.clicked.connect(self._starter)
        self.dash.wheel.clicked.connect(self.honk)
        self.dash.glove.pull.connect(self.pull)
        self.dash.glove.pull_folder.connect(self.pull_folder)
        keys = self.dash.radio.keys
        keys["date"].clicked.connect(self.set_date)
        keys["camera"].clicked.connect(lambda: self.apply_rule("camera"))
        keys["auto"].clicked.connect(lambda: self.apply_rule("auto"))
        keys["skip"].clicked.connect(self.leave_out)
        self.dash.radio.left.clicked.connect(self.show_log)
        self.dash.radio.right.clicked.connect(self.choose_folders)
        outer.addWidget(self.dash)
        outer.addWidget(self._status_bar())

        self.loader = ThumbLoader(self)
        self.loader.loaded.connect(self._thumb_loaded)
        self.loader.start()

        self.poll = QTimer(self)
        self.poll.setInterval(2500)
        self.poll.timeout.connect(self._poll_devices)
        self.poll.start()

        self._selection_changed()
        self.later(0, self.startup)

    def later(self, ms, fn):
        """A one-shot timer owned by the window, and a no-op if the window
        has gone by the time it fires."""
        t = QTimer(self)
        t.setSingleShot(True)

        def fire():
            if not sip.isdeleted(self) and not sip.isdeleted(self.st_lib):
                fn()
        t.timeout.connect(fire)
        t.timeout.connect(t.deleteLater)
        t.start(ms)

    # -- construction --------------------------------------------------------

    def _menus(self):
        bar = QMenuBar(self)
        bar.setFont(ui_font(9))
        f = bar.addMenu("&File")
        self._act(f, "Pull from a &folder...", self.pull_folder)
        self._act(f, "&Look for cameras again", self.honk, "F5")
        f.addSeparator()
        self._act(f, "F&olders...", self.choose_folders)
        self._act(f, "Open the &library folder",
                  lambda: self._open_path(self.settings.library))
        self._act(f, "Open the &archive folder",
                  lambda: self._open_path(self.settings.archive))
        f.addSeparator()
        self._act(f, "&Close", self.close, "Ctrl+Q")
        s = bar.addMenu("&Shots")
        self._act(s, "Select &all", self.list_select_all, "Ctrl+A")
        s.addSeparator()
        self._act(s, "Set &date...", self.set_date, "Ctrl+D")
        self._act(s, "Keep the &camera's date", lambda: self.apply_rule("camera"))
        self._act(s, "&Automatic date", lambda: self.apply_rule("auto"))
        s.addSeparator()
        self._act(s, "&Leave out", self.leave_out, "Del")
        self._act(s, "&Bring back left-out shots", self.bring_back)
        s.addSeparator()
        self._act(s, "&Put in library", self.develop, "Ctrl+Return")
        v = bar.addMenu("&View")
        snd = self._act(v, "&Sounds", self._toggle_sounds)
        snd.setCheckable(True)
        snd.setChecked(self.settings.sounds)
        h = bar.addMenu("&Help")
        self._act(h, "&Activity log", self.show_log)
        self._act(h, "Check for &updates...", self.check_updates)
        h.addSeparator()
        self._act(h, "&About DigiCarlo", self.about)
        return bar

    def _act(self, menu, text, fn, shortcut=None):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(shortcut)
        a.triggered.connect(fn)
        menu.addAction(a)
        self.addAction(a)
        return a

    def _status_bar(self):
        w = QWidget(self)
        row = QHBoxLayout(w)
        row.setContentsMargins(2, 3, 0, 0)
        row.setSpacing(3)
        self.st_lib = StatusPanel("", w)
        self.st_lib.clicked.connect(self.choose_folders)
        self.st_arc = StatusPanel("", w)
        self.st_arc.clicked.connect(self.choose_folders)
        self.st_count = StatusPanel("", w)
        self.st_count.setFixedWidth(190)
        row.addWidget(self.st_lib, 1)
        row.addWidget(self.st_arc, 1)
        row.addWidget(self.st_count)
        row.addWidget(SizeGrip(w), 0, Qt.AlignmentFlag.AlignBottom)
        w.setFixedHeight(25)
        return w

    # -- window frame ---------------------------------------------------------

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), FACE)
        bevel(p, self.rect(), raised=True)

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == e.Type.ActivationChange:
            self.bar.set_active(self.isActiveWindow())
        elif e.type() == e.Type.WindowStateChange:
            self.bar.set_maximised(self.isMaximized())

    def _edges(self, pos):
        m = self.BORDER + 2
        edges = Qt.Edge(0)
        if pos.x() <= m:
            edges |= Qt.Edge.LeftEdge
        if pos.x() >= self.width() - m:
            edges |= Qt.Edge.RightEdge
        if pos.y() <= m:
            edges |= Qt.Edge.TopEdge
        if pos.y() >= self.height() - m:
            edges |= Qt.Edge.BottomEdge
        return edges

    def mouseMoveEvent(self, e):
        edges = self._edges(e.position().toPoint())
        shapes = {
            Qt.Edge.LeftEdge: Qt.CursorShape.SizeHorCursor,
            Qt.Edge.RightEdge: Qt.CursorShape.SizeHorCursor,
            Qt.Edge.TopEdge: Qt.CursorShape.SizeVerCursor,
            Qt.Edge.BottomEdge: Qt.CursorShape.SizeVerCursor,
            Qt.Edge.LeftEdge | Qt.Edge.TopEdge: Qt.CursorShape.SizeFDiagCursor,
            Qt.Edge.RightEdge | Qt.Edge.BottomEdge: Qt.CursorShape.SizeFDiagCursor,
            Qt.Edge.RightEdge | Qt.Edge.TopEdge: Qt.CursorShape.SizeBDiagCursor,
            Qt.Edge.LeftEdge | Qt.Edge.BottomEdge: Qt.CursorShape.SizeBDiagCursor,
        }
        self.setCursor(shapes.get(edges, Qt.CursorShape.ArrowCursor))

    def mousePressEvent(self, e):
        edges = self._edges(e.position().toPoint())
        if e.button() == Qt.MouseButton.LeftButton and edges != Qt.Edge(0):
            handle = self.windowHandle()
            if handle is not None:
                handle.startSystemResize(edges)

    def _toggle_zoom(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def closeEvent(self, e):
        if self.job is not None and self.job.isRunning():
            if not message(self, "DigiCarlo", "DigiCarlo is still working. "
                           "Stop after the current file and close?",
                           "question", ("Stop and close", "Keep working")):
                e.ignore()
                return
            self.job.cancel.set()
            self.job.wait(30000)
        self.loader.stop()
        self.loader.wait(2000)
        super().closeEvent(e)

    # -- startup and scanning ---------------------------------------------------

    def startup(self):
        if not os.path.exists(self.settings.path):
            self.choose_folders(first_run=True)
        self._status()
        self.replan()
        self.rescan()

    def _status(self):
        self.st_lib.setText("Library: %s" % self._pretty(self.settings.library))
        self.st_arc.setText("Archive: %s" % self._pretty(self.settings.archive))
        n = len(self.plan.shots) if self.plan else 0
        left = len(self.arc.skipped)
        self.st_count.setText("%d waiting%s" % (
            n, ", %d left out" % left if left else ""))
        developed = sum(len(r.get("outputs") or [])
                        for r in self.arc.developed.values())
        self.dash.gauge.set_odometer(developed)
        probe = self.settings.library
        while probe and not os.path.exists(probe):
            probe = os.path.dirname(probe)
        try:
            usage = shutil.disk_usage(probe or "/")
            self.dash.fuel.set_space(usage.free, usage.total)
        except OSError:
            pass

    @staticmethod
    def _pretty(path):
        home = os.path.expanduser("~")
        return "~" + path[len(home):] if path.startswith(home + os.sep) else path

    def _device_signature(self):
        sig = []
        user = os.environ.get("USER") or ""
        for d in ("/dev/disk/by-path", "/run/media/%s" % user,
                  "/media/%s" % user, "/sys/bus/usb/devices"):
            try:
                sig.append(tuple(sorted(os.listdir(d))))
            except OSError:
                sig.append(())
        return tuple(sig)

    def _poll_devices(self):
        sig = self._device_signature()
        if self.signature is not None and sig != self.signature:
            # Leave a camera alone while it is being read.
            if self.job is None or not self.job.isRunning():
                self.later(1500, self.rescan)
        self.signature = sig

    def honk(self):
        if self.settings.sounds:
            toon.play("honk")
        self.rescan()

    def rescan(self):
        if self.scan_job is not None and self.scan_job.isRunning():
            return
        if self.job is not None and self.job.isRunning():
            return
        self.signature = self._device_signature()
        job = Job(lambda job, log: sources.find_sources(log), self)
        job.ok.connect(self._scanned)
        job.failed.connect(lambda msg: self._log("error", msg))
        self.scan_job = job
        job.start()

    def _scanned(self, found):
        self.found = found
        busy = self.job is not None and self.job.isRunning()
        self.dash.glove.set_sources(found, busy)

    # -- planning ---------------------------------------------------------------

    def replan(self):
        self.arc.reload()
        log = GuiLog(self._log)
        try:
            with self.arc.locked():
                sources.ensure_metadata(self.arc, log)
        except archive.ArchiveBusy:
            pass
        batches = develop.plan_batches(self.arc, log)
        pending = {s.key for b in batches for s in b.shots}
        for ov in self.overrides:
            ov.keys &= pending
        self.overrides = [ov for ov in self.overrides if ov.keys]
        self.plan = timeplan.build(batches, self.overrides,
                                   max_gap_days=self.settings.max_gap_days,
                                   spacing=self.settings.session_spacing)
        self._fill_list()
        self._status()
        self._update_go()

    def _fill_list(self):
        keep = set(self.list.selected_keys())
        scroll = self.list.verticalScrollBar().value()
        self.list.clear()
        plan = self.plan
        if not plan.shots:
            self.list.empty_text = (
                "Nothing's waiting for the library!\n\nPick a camera or card "
                "out of the glove box down there. Its pictures get copied "
                "into the archive untouched, then they show up here with the "
                "dates they'll get.")
            self.list.viewport().update()
            return
        self.list.empty_text = ""
        for batch in plan.batches:
            brec = self.arc.batches.get(batch.id, {})
            n = len(batch.shots)
            item = QListWidgetItem()
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item.setData(KIND_ROLE, "batch")
            item.setData(DATA_ROLE, {
                "title": batch.label,
                "top": "TAKEN OFF %s  -  %s" % (
                    batch.anchor.strftime("%b %d %Y  %H:%M").upper(),
                    (brec.get("source_label") or "").upper()),
                "right": "%d shot%s" % (n, "" if n == 1 else "s")})
            self.list.addItem(item)
            for sess in [s for s in plan.sessions if s.batch is batch]:
                self._add_session(sess, keep)
        self.list.doItemsLayout()
        self.list.verticalScrollBar().setValue(scroll)

    def _add_session(self, sess, keep):
        plan = self.plan
        c0, c1 = sess.camera_range()
        n = len(sess.shots)
        lines = []
        if c0 is None:
            lines.append(("This camera keeps no clock; its shots go a second "
                          "apart, in the order they were taken.", "#4A5A60"))
        else:
            lines.append(("The camera's clock said %s" % timeplan.fmt_span(c0, c1),
                          "#4A5A60"))
        for g in [g for g in plan.groups if g.session is sess]:
            which = "" if len(g.shots) == n else (
                "%s: " % describe_numbers([s.number for s in g.shots]).capitalize())
            if g.rule is None:
                how, colour = "when they came off the camera", CARIBBEAN["deep"]
            elif g.rule.when == "camera":
                how, colour = "keeping the camera's dates", "#8A5A00"
            else:
                how, colour = "set by you", MARDI_GRAS["shade"]
            lines.append(("%sWill be dated %s  (%s)" % (
                which, timeplan.fmt_span(g.start, g.end), how), colour))
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        item.setData(KIND_ROLE, "session")
        item.setData(DATA_ROLE, {
            "title": "Session %d" % sess.number,
            "count": "%d shot%s" % (n, "" if n == 1 else "s"),
            "lines": lines, "keys": [s.key for s in sess.shots]})
        item.setToolTip("Click to select this session's shots")
        self.list.addItem(item)
        for shot in sess.shots:
            rec = self.arc.files.get(shot.key, {})
            rule = plan.rules.get(shot.key)
            it = QListWidgetItem()
            it.setData(KIND_ROLE, "shot")
            it.setData(KEY_ROLE, shot.key)
            kind = rec.get("kind")
            it.setData(DATA_ROLE, {
                "key": shot.key, "number": shot.number,
                "name": shot.label if kind not in (media.SIPIX_STILL,
                                                   media.SIPIX_CLIP)
                else rec.get("orig", shot.label),
                "when": short_time(plan.times[shot.key]),
                "video": kind in ("video", media.SIPIX_CLIP),
                "pinned": None if rule is None else
                ("camera" if rule.when == "camera" else "set")})
            it.setToolTip("%s\nCamera's clock: %s\nWill be dated: %s\n%s" % (
                rec.get("orig", shot.label), timeplan.fmt(shot.camera_time),
                timeplan.fmt(plan.times[shot.key]),
                "Archived as %s" % self.arc.abspath(rec.get("path", ""))))
            self.list.addItem(it)
            if shot.key in keep:
                it.setSelected(True)

    def thumb(self, key):
        img = self.thumbs.get(key)
        if img is None and key not in self.asked:
            rec = self.arc.files.get(key)
            if rec:
                self.asked.add(key)
                self.loader.request(key, self.arc.abspath(rec["path"]),
                                    rec.get("kind"))
        return img

    def _thumb_loaded(self, key, img):
        self.thumbs[key] = img
        self.list.viewport().update()

    # -- choosing dates ------------------------------------------------------------

    def _selected_shots(self):
        keys = set(self.list.selected_keys())
        return [s for s in self.plan.shots if s.key in keys] if self.plan else []

    def _busy_now(self):
        return self.job is not None and self.job.isRunning()

    def _selection_changed(self):
        shots = self._selected_shots()
        busy = self._busy_now()
        for k in self.dash.radio.keys.values():
            k.setEnabled(bool(shots) and not busy)
        if not busy:
            self._idle_message()

    def _idle_message(self):
        shots = self._selected_shots()
        n = len(self.plan.shots) if self.plan else 0
        if shots:
            self.dash.say("%s selected" % describe_numbers(
                [s.number for s in shots]).capitalize(),
                "Push a button below to change how they're dated.")
        elif n:
            self.dash.say("%d shot%s waiting" % (n, "" if n == 1 else "s"),
                          "Check the dates up top. Pick shots to change them, "
                          "then hit START.")
        else:
            self.dash.say("All clear!", "Pick a camera or card from the "
                          "glove box to begin.")

    def list_select_all(self):
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(KIND_ROLE) == "shot":
                it.setSelected(True)

    def _context_menu(self, pos):
        item = self.list.itemAt(pos)
        if item is not None and item.data(KIND_ROLE) == "shot" \
                and not item.isSelected():
            self.list.clearSelection()
            item.setSelected(True)
        if not self._selected_shots():
            return
        menu = QMenu(self)
        menu.addAction("Set date...", self.set_date)
        menu.addAction("Keep the camera's date", lambda: self.apply_rule("camera"))
        menu.addAction("Automatic date", lambda: self.apply_rule("auto"))
        menu.addSeparator()
        menu.addAction("Leave out", self.leave_out)
        menu.exec(self.list.viewport().mapToGlobal(pos))

    def set_date(self):
        shots = self._selected_shots()
        if not shots:
            return
        dlg = DateDialog(self, shots, self.plan)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.apply_rule(dlg.choice(), shots)

    def apply_rule(self, when, shots=None):
        shots = shots if shots is not None else self._selected_shots()
        if not shots:
            return
        keys = {s.key for s in shots}
        for ov in self.overrides:
            ov.keys -= keys
        self.overrides = [ov for ov in self.overrides if ov.keys]
        if when != "auto":
            self.overrides.append(timeplan.Override("keys", None, None, when,
                                                    keys=keys))
        self.replan()

    def leave_out(self):
        shots = self._selected_shots()
        if not shots:
            return
        if not message(self, "Leave out", "Leave %s out of the library?\n\n"
                       "They stay in the archive, and Shots > Bring back "
                       "left-out shots puts them back." % describe_numbers(
                           [s.number for s in shots]), "question",
                       ("Leave out", "Cancel")):
            return
        try:
            with self.arc.locked():
                for s in shots:
                    self.arc.skip(s.key)
        except archive.ArchiveBusy as exc:
            message(self, "DigiCarlo", str(exc), "error")
        self.replan()

    def bring_back(self):
        if not self.arc.skipped:
            message(self, "DigiCarlo", "Nothing has been left out.")
            return
        try:
            with self.arc.locked():
                for sha in list(self.arc.skipped):
                    self.arc.unskip(sha)
        except archive.ArchiveBusy as exc:
            message(self, "DigiCarlo", str(exc), "error")
        self.replan()

    def _open_item(self, item):
        if item.data(KIND_ROLE) != "shot":
            return
        rec = self.arc.files.get(item.data(KEY_ROLE))
        if rec:
            self._open_path(self.arc.abspath(rec["path"]))

    def _open_path(self, path):
        if os.path.exists(path):
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)

    # -- jobs ----------------------------------------------------------------------

    def _log(self, level, text):
        self.lines.append(("%-5s %s" % (level.upper(), text)))
        if level in ("warn", "error"):
            self.dash.say(self.dash.radio.caption, text)

    def _busy(self, on, caption=""):
        self.dash.glove.set_busy(on)
        self.dash.wheel.setEnabled(not on)
        self.dash.gauge.set_lit(on)
        if on:
            self.dash.say(caption, "")
            self.dash.gauge.set_value(0)
        self._selection_changed()
        self._update_go()

    def _update_go(self):
        n = len(self.plan.shots) if self.plan else 0
        self.dash.go.set_state(n, self._busy_now())
        if not self._busy_now():
            self._idle_message()

    def _starter(self):
        if self._busy_now():
            self.stop_job()
        else:
            self.develop()

    def run(self, fn, done, caption):
        if self._busy_now():
            return
        job = Job(fn, self)
        job.line.connect(self._log)
        job.step.connect(self._step)
        job.ok.connect(done)
        job.failed.connect(self._failed)
        job.finished.connect(self._finished)
        self.job = job
        self.last_ok = False
        job.start()
        self._busy(True, caption)

    def stop_job(self):
        if self._busy_now():
            self.job.cancel.set()
            self.dash.go.setEnabled(False)
            self.dash.say(self.dash.radio.caption, "Stopping after this file...")

    def _step(self, done, total, caption):
        self.dash.gauge.set_value(done / total if total else 1.0)
        self.dash.say(self.dash.radio.caption, caption)

    def _failed(self, msg):
        self._log("error", msg)
        message(self, "DigiCarlo", msg, "error")

    def _finished(self):
        self._busy(False)
        self.dash.gauge.set_value(0)
        self.replan()
        self.rescan()
        if self.last_ok and self.settings.sounds:
            toon.play("beepbeep")

    def pull(self, src):
        arc_root = self.settings.archive

        def work(job, log):
            arc = archive.Archive(arc_root)
            with arc.locked():
                return sources.pull(src, arc, log, progress=job.progress,
                                    cancel=job.cancel)
        self.run(work, lambda res: self._pulled(src, res),
                 "Pulling from %s" % src.label)

    def pull_folder(self):
        path = QFileDialog.getExistingDirectory(
            self, "Pull from a folder", os.path.expanduser("~"))
        if path:
            try:
                sources.check_folder(path, self.settings)
            except ValueError as exc:
                message(self, "Pull from a folder", str(exc), "error")
                return
            self.pull(sources.folder_source(path))

    def _pulled(self, src, res):
        new, skipped, failed = len(res.new), len(res.skipped), len(res.failed)
        text = "%d new from %s%s." % (
            new, res.camera or src.label,
            ", %d already imported" % skipped if skipped else "")
        if failed:
            names = "\n".join("  %s: %s" % f for f in res.failed[:12])
            more = "\n  ...and %d more" % (failed - 12) if failed > 12 else ""
            message(self, "Some files could not be read",
                    "%s\n\n%d file%s could not be read from the camera:\n\n%s%s"
                    "\n\nThe rest are safe in the archive. A card that fails "
                    "like this may be wearing out." % (
                        text, failed, "" if failed == 1 else "s", names, more),
                    "error")
        self.lines.append("OUT   " + text)
        self.last_ok = not failed
        self.later(0, lambda: self.dash.say("Pulled!", text))

    def develop(self):
        if not self.plan or not self.plan.shots or self._busy_now():
            return
        n = len(self.plan.shots)
        first = min(self.plan.times.values())
        last = max(self.plan.times.values())
        if not message(self, "Put in library",
                       "Put %d shot%s in %s?\n\nThey will be dated %s. Clips "
                       "become MP4 with their video untouched. The originals "
                       "stay in the archive as they are." % (
                           n, "" if n == 1 else "s", self.settings.library,
                           timeplan.fmt_span(first, last)),
                       "question", ("Put in library", "Cancel")):
            return
        plan, settings = self.plan, self.settings

        def work(job, log):
            arc = archive.Archive(settings.archive)
            with arc.locked():
                return develop.Developer(arc, settings, log).develop(
                    plan, progress=job.progress, cancel=job.cancel)
        self.run(work, self._developed, "Putting shots in the library")

    def _developed(self, res):
        made = sum(len(p) for _, p in res.made)
        text = "%d file%s now in %s." % (made, "" if made == 1 else "s",
                                         self._pretty(self.settings.library))
        if res.failed:
            names = "\n".join("  %s: %s" % f for f in res.failed[:12])
            message(self, "Some shots were not put in the library",
                    "%s\n\nThese failed and are still waiting:\n\n%s"
                    % (text, names), "error")
        self.lines.append("OUT   " + text)
        self.last_ok = not res.failed
        self.later(0, lambda: self.dash.say("Done!", text))

    # -- menus -----------------------------------------------------------------------

    def _toggle_sounds(self, on):
        self.settings.set("window", "sounds", "yes" if on else "no")
        self.settings.save()

    def choose_folders(self, first_run=False):
        dlg = FoldersDialog(self, self.settings, first_run)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            if first_run:
                self.settings.save()
            return
        vals = dlg.values()
        lib, arc = os.path.abspath(vals["library"]), os.path.abspath(vals["archive"])
        if lib == arc or lib.startswith(arc + os.sep) or arc.startswith(lib + os.sep):
            message(self, "Folders", "The library and the archive have to be "
                    "separate folders, neither inside the other.", "error")
            return
        self.settings.set("folders", "library", vals["library"])
        self.settings.set("folders", "archive", vals["archive"])
        self.settings.save()
        self.arc = archive.Archive(self.settings.archive)
        self.thumbs.clear()
        self.asked.clear()
        self.replan()

    def show_log(self):
        TextDialog(self, "Activity log",
                   "\n".join(self.lines) or "Nothing has happened yet.").exec()

    def check_updates(self):
        def work(job, log):
            return update.latest()

        def done(result):
            version, info = result
            if version is None:
                message(self, "Updates", "No releases have been published yet.")
            elif update.newer(version):
                message(self, "Updates", "DigiCarlo %s is available (you have "
                        "%s).\n\nTo install it, run:\n\n    digicarlo update "
                        "--install" % (version, __version__))
            else:
                message(self, "Updates", "DigiCarlo %s is the latest." %
                        __version__)
        self.run(work, done, "Checking for updates")

    def about(self):
        dlg = Win95Dialog("About DigiCarlo", self)
        row = QHBoxLayout()
        row.setSpacing(16)
        icon = QLabel()
        pm = icon_pixmap(160)
        pm.setDevicePixelRatio(2.0)
        icon.setPixmap(pm)
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        row.addWidget(icon)
        text = QLabel(
            "<b>DigiCarlo %s</b><br><br>Gets the pictures off old digital "
            "cameras, dated when they came off the camera instead of by its "
            "wrong clock, with the camera's gaps between shots kept.<br><br>"
            "Clips are remuxed to MP4 with the video untouched.<br><br>"
            "The SiPix Blink II is driven by Blinky %s.<br><br>"
            "Painted Caribbean Blue and Snowberry White, the Nash "
            "Metropolitan's own colours.<br><br>"
            "Licensed under the GNU LGPL, version 2.1." % (
                __version__, blinky.__version__), dlg)
        text.setWordWrap(True)
        text.setMinimumWidth(340)
        row.addWidget(text, 1)
        dlg.lay.addLayout(row)
        dlg.buttons(("OK", "accept"))
        dlg.exec()


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv)
    if "--classic" not in argv:
        # The garage is the window now; this one stays a while as the
        # classic window (digicarlo-gui --classic, or View > Classic window).
        from digicarlo import garage
        return garage.main([a for a in argv if a != "--garage"])
    argv = [a for a in argv if a != "--classic"]
    app = QApplication(argv)
    app.setApplicationName("DigiCarlo")
    app.setApplicationDisplayName("DigiCarlo")
    app.setDesktopFileName("digicarlo")
    app.setStyle("Windows")
    app.setPalette(win95_palette())
    app.setFont(ui_font(9))
    themed = QIcon.fromTheme("digicarlo")
    app.setWindowIcon(themed if not themed.isNull() else app_icon())
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
