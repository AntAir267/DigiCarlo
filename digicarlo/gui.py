#!/usr/bin/env python3
"""digicarlo-gui - the DigiCarlo window.

The look is Windows 95 dressed as a Nash Metropolitan. From Windows 95: the
bevelled controls, the classic scroll bars and menus (Qt's own "Windows"
style, which is the real Win9x drawing code), Microsoft Sans Serif at 8 points
without anti-aliasing, and the caption buttons. From the Metropolitan, in
moderation: two-tone paint -- powder blue below, Snowberry white above -- a
chrome beltline under the title bar, and a dashboard with a speedometer whose
odometer counts every photo DigiCarlo has ever brought in.

All camera and file work happens in the other modules, on worker threads; this
file only draws and dispatches.
"""

import math
import os
import queue
import subprocess
import sys
import threading

from PyQt6.QtCore import (QDateTime, QPoint, QPointF, QRect, QRectF, QSize,
                          Qt, QThread, QTimer, pyqtSignal)
from PyQt6.QtGui import (QAction, QBrush, QColor, QConicalGradient, QFont,
                         QFontDatabase, QIcon, QImage, QImageReader,
                         QLinearGradient, QPainter, QPainterPath, QPalette,
                         QPen, QPixmap, QPolygonF, QRadialGradient)
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup,
                             QDateTimeEdit, QDialog, QFileDialog, QFrame,
                             QHBoxLayout, QLabel, QLineEdit, QListView,
                             QListWidget, QListWidgetItem, QMenu, QMenuBar,
                             QPlainTextEdit, QPushButton, QRadioButton,
                             QScrollArea, QSizePolicy, QStyle,
                             QStyledItemDelegate, QVBoxLayout, QWidget)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from digicarlo import (__version__, archive, blinky, config,   # noqa: E402
                       develop, media, sources, timeplan, update)

# ---------------------------------------------------------------------------
# Palette
#
# Windows 95's grey (#C0C0C0) becomes Snowberry white, a warm cream; its
# bevel shadows are warmed to match so the 3D still reads. Navy selection
# becomes the Metropolitan's blue at its deepest. Paint gradients are kept
# gentle: this is a 1995 program that happens to own a 1956 car.
# ---------------------------------------------------------------------------

CREAM = QColor("#ECE7DA")           # button face / window
CREAM_LIGHT = QColor("#F7F4EC")     # inner highlight
WHITE = QColor("#FFFFFF")
SHADOW = QColor("#8E887A")          # inner shadow
DARK = QColor("#23201B")            # outer shadow
FIELD = QColor("#FFFFFF")
INK = QColor("#1B1A17")
INK_SOFT = QColor("#5E5A50")

PAINT = ["#C3DDEF", "#9CC3DF", "#7FACCF", "#6497BF", "#4F83AE"]  # Metropolitan
PAINT_DEEP = QColor("#2E5E8A")      # selection, primary button text shadow
PAINT_INK = QColor("#244B70")
CHROME = [(0.00, "#FFFFFF"), (0.30, "#E3E7EB"), (0.48, "#A2AAB2"),
          (0.52, "#8A929B"), (0.70, "#D5DADF"), (1.00, "#F7F8FA")]
NEEDLE = QColor("#D0402B")
GOOD = QColor("#2F7D3B")
BAD = QColor("#B3261E")

THUMB_W, THUMB_H = 96, 72
CELL_W, CELL_H = 116, 122


def ui_font(size=8, bold=False):
    """MS Sans Serif's TrueType heir, unsmoothed, as Windows 95 drew it."""
    for name in ("Microsoft Sans Serif", "MS Sans Serif", "Tahoma",
                 "Liberation Sans", "DejaVu Sans"):
        if name in QFontDatabase.families():
            f = QFont(name)
            f.setPointSizeF(size)
            f.setBold(bold)
            f.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
            f.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
            return f
    f = QFont()
    f.setPointSizeF(size)
    f.setBold(bold)
    return f


def win95_palette():
    pal = QPalette()
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive,
                  QPalette.ColorGroup.Disabled):
        pal.setColor(group, QPalette.ColorRole.Window, CREAM)
        pal.setColor(group, QPalette.ColorRole.Button, CREAM)
        pal.setColor(group, QPalette.ColorRole.Base, FIELD)
        pal.setColor(group, QPalette.ColorRole.AlternateBase, CREAM_LIGHT)
        pal.setColor(group, QPalette.ColorRole.Light, WHITE)
        pal.setColor(group, QPalette.ColorRole.Midlight, CREAM_LIGHT)
        pal.setColor(group, QPalette.ColorRole.Mid, SHADOW)
        pal.setColor(group, QPalette.ColorRole.Dark, SHADOW)
        pal.setColor(group, QPalette.ColorRole.Shadow, DARK)
        pal.setColor(group, QPalette.ColorRole.Highlight, PAINT_DEEP)
        pal.setColor(group, QPalette.ColorRole.HighlightedText, WHITE)
        pal.setColor(group, QPalette.ColorRole.ToolTipBase, QColor("#FFFFE1"))
        pal.setColor(group, QPalette.ColorRole.ToolTipText, INK)
        text = SHADOW if group == QPalette.ColorGroup.Disabled else INK
        for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                     QPalette.ColorRole.ButtonText):
            pal.setColor(group, role, text)
    return pal


def vgrad(rect, stops):
    g = QLinearGradient(QPointF(rect.left(), rect.top()),
                        QPointF(rect.left(), rect.bottom()))
    n = len(stops)
    for i, s in enumerate(stops):
        if isinstance(s, tuple):
            g.setColorAt(s[0], QColor(s[1]))
        else:
            g.setColorAt(i / max(1, n - 1), QColor(s))
    return g


def bevel(p, rect, raised=True, deep=True):
    """The Windows 95 two-pixel bevel, drawn inside rect."""
    r = QRect(rect)
    if raised:
        outer_tl, outer_br, inner_tl, inner_br = CREAM_LIGHT, DARK, WHITE, SHADOW
    else:
        outer_tl, outer_br, inner_tl, inner_br = SHADOW, WHITE, DARK, CREAM_LIGHT
    rings = [(outer_tl, outer_br), (inner_tl, inner_br)] if deep \
        else [(inner_tl if raised else outer_tl, outer_br if raised else outer_br)]
    for tl, br in rings:
        p.setPen(QPen(tl, 1))
        p.drawLine(r.left(), r.bottom() - 1, r.left(), r.top())
        p.drawLine(r.left(), r.top(), r.right() - 1, r.top())
        p.setPen(QPen(br, 1))
        p.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
        p.drawLine(r.right(), r.bottom(), r.right(), r.top())
        r.adjust(1, 1, -1, -1)
    return r


def chrome_strip(p, rect):
    p.fillRect(rect, QBrush(vgrad(rect, CHROME)))
    p.setPen(QPen(QColor(255, 255, 255, 200), 1))
    p.drawLine(rect.left(), rect.top(), rect.right(), rect.top())
    p.setPen(QPen(QColor(60, 66, 72, 160), 1))
    p.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())


def paint_panel(p, rect):
    """Metropolitan paint: a soft vertical gloss, lighter at the shoulder."""
    p.fillRect(rect, QBrush(vgrad(rect, [(0.0, PAINT[0]), (0.18, PAINT[1]),
                                         (0.55, PAINT[2]), (1.0, PAINT[4])])))


# ---------------------------------------------------------------------------
# The icon: a camera in two-tone paint, its lens a chrome-ringed headlight
# ---------------------------------------------------------------------------

def paint_icon(p, size):
    s = size / 64.0
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, size >= 24)
    p.scale(s, s)
    outline = QPen(QColor("#1D2A36"), 2.0 if size >= 32 else 3.0)
    body = QRectF(4, 16, 56, 38)
    path = QPainterPath()
    path.addRoundedRect(body, 9, 9)
    # lower body: blue paint
    p.setClipPath(path)
    p.fillRect(QRectF(4, 16, 56, 38), QBrush(vgrad(QRectF(4, 30, 56, 24),
                                                   [PAINT[1], PAINT[3]])))
    # upper body: Snowberry white
    p.fillRect(QRectF(4, 16, 56, 15), QColor("#F4F0E4"))
    # chrome beltline
    p.fillRect(QRectF(4, 30, 56, 3.5), QBrush(vgrad(QRectF(4, 30, 56, 3.5),
                                                    CHROME)))
    p.setClipping(False)
    p.setPen(outline)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    # viewfinder hump and shutter button
    p.setBrush(QColor("#F4F0E4"))
    p.drawRoundedRect(QRectF(12, 9, 16, 9), 3, 3)
    p.setBrush(QBrush(vgrad(QRectF(44, 10, 9, 7), CHROME)))
    p.drawRoundedRect(QRectF(44, 11, 9, 6), 2, 2)
    # the lens: a headlight in a chrome bezel
    c = QPointF(33, 36)
    g = QConicalGradient(c, 30)
    for at, col in ((0.0, "#FFFFFF"), (0.25, "#8B939C"), (0.5, "#F2F4F6"),
                    (0.75, "#7C858E"), (1.0, "#FFFFFF")):
        g.setColorAt(at, QColor(col))
    p.setBrush(QBrush(g))
    p.drawEllipse(c, 14, 14)
    if size >= 24:
        lens = QRadialGradient(QPointF(29, 32), 12)
        lens.setColorAt(0.0, QColor("#E8F4FF"))
        lens.setColorAt(0.35, QColor("#5E8FB8"))
        lens.setColorAt(1.0, QColor("#12293F"))
        p.setBrush(QBrush(lens))
        p.setPen(QPen(QColor("#1D2A36"), 1.5))
        p.drawEllipse(c, 9, 9)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 210))
        p.drawEllipse(QPointF(29.5, 32.5), 2.6, 2.6)
    else:
        p.setBrush(QColor("#1E3D5C"))
        p.drawEllipse(c, 8, 8)
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
# Window chrome
# ---------------------------------------------------------------------------

class CaptionButton(QWidget):
    """Windows 95's little bevelled minimise / maximise / close buttons."""

    clicked = pyqtSignal()

    def __init__(self, glyph, parent=None):
        super().__init__(parent)
        self.glyph = glyph
        self.down = False
        self.setFixedSize(16, 14)

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
        p.fillRect(self.rect(), CREAM)
        inner = bevel(p, self.rect(), raised=not self.down)
        o = 1 if self.down else 0
        p.setPen(QPen(INK, 1))
        p.setBrush(INK)
        cx, cy = inner.center().x() + o, inner.center().y() + o
        if self.glyph == "close":
            for d in (0, 1):
                p.drawLine(cx - 3 + d, cy - 3, cx + 3 + d - 1, cy + 3)
                p.drawLine(cx + 3 + d - 1, cy - 3, cx - 3 + d, cy + 3)
        elif self.glyph == "min":
            p.fillRect(QRect(cx - 3, cy + 2, 6, 2), INK)
        elif self.glyph == "max":
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRect(cx - 4, cy - 4, 8, 7))
            p.drawLine(cx - 4, cy - 3, cx + 4, cy - 3)
        elif self.glyph == "restore":
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRect(cx - 2, cy - 4, 6, 5))
            p.drawRect(QRect(cx - 4, cy - 1, 6, 5))
            p.fillRect(QRect(cx - 3, cy, 5, 4), CREAM)
            p.drawRect(QRect(cx - 4, cy - 1, 6, 5))


class TitleBar(QWidget):
    """Metropolitan blue with a gloss, a chrome beltline beneath, and the
    Windows 95 caption: icon at left, bold white title, buttons at right."""

    close_clicked = pyqtSignal()
    minimise_clicked = pyqtSignal()
    zoom_clicked = pyqtSignal()

    def __init__(self, text, parent=None, buttons=("min", "max", "close")):
        super().__init__(parent)
        self.text = text
        self.active = True
        self.setFixedHeight(24)
        self._drag = None
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 3, 4, 7)
        row.setSpacing(0)
        row.addSpacing(20)
        row.addStretch(1)
        self.buttons = {}
        for g in buttons:
            b = CaptionButton(g, self)
            self.buttons[g] = b
            if g == "close" and len(buttons) > 1:
                row.addSpacing(2)
            row.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        if "close" in self.buttons:
            self.buttons["close"].clicked.connect(self.close_clicked)
        if "min" in self.buttons:
            self.buttons["min"].clicked.connect(self.minimise_clicked)
        if "max" in self.buttons:
            self.buttons["max"].clicked.connect(self.zoom_clicked)

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
        p = QPainter(self)
        r = self.rect()
        paint_rect = QRect(r.left(), r.top(), r.width(), r.height() - 4)
        if self.active:
            paint_panel(p, paint_rect)
            # a highlight line along the top, like light on a curved roof
            p.setPen(QPen(QColor(255, 255, 255, 150), 1))
            p.drawLine(paint_rect.left(), paint_rect.top() + 1,
                       paint_rect.right(), paint_rect.top() + 1)
        else:
            p.fillRect(paint_rect, QBrush(vgrad(paint_rect,
                                                ["#C9CCCF", "#A8ADB2"])))
        chrome_strip(p, QRect(r.left(), r.bottom() - 3, r.width(), 4))
        p.drawPixmap(4, (paint_rect.height() - 16) // 2, icon_pixmap(16))
        p.setFont(ui_font(8, bold=True))
        text_rect = QRect(24, 0, r.width() - 90, paint_rect.height())
        p.setPen(QColor(20, 40, 60, 120) if self.active else QColor(0, 0, 0, 0))
        p.drawText(text_rect.translated(1, 1),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   self.text)
        p.setPen(WHITE if self.active else QColor("#EEF0F2"))
        p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter |
                   Qt.AlignmentFlag.AlignLeft, self.text)


class SizeGrip(QWidget):
    """The diagonal ridges in the corner of a Windows 95 status bar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemResize(Qt.Edge.BottomEdge | Qt.Edge.RightEdge)

    def paintEvent(self, _):
        p = QPainter(self)
        w, h = self.width(), self.height()
        for off in (3, 7, 11):
            p.setPen(QPen(WHITE, 1))
            p.drawLine(w - off - 1, h - 1, w - 1, h - off - 1)
            p.setPen(QPen(SHADOW, 1))
            p.drawLine(w - off, h - 1, w - 1, h - off)
            p.drawLine(w - off + 1, h - 1, w - 1, h - off + 1)


class Sunken(QFrame):
    """A Windows 95 sunken field around another widget."""

    def __init__(self, child=None, parent=None, margin=2):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(margin, margin, margin, margin)
        lay.setSpacing(0)
        if child is not None:
            lay.addWidget(child)

    def paintEvent(self, _):
        p = QPainter(self)
        bevel(p, self.rect(), raised=False)


class StatusPanel(QLabel):
    """One shallow-sunken compartment of the status bar."""

    clicked = pyqtSignal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setContentsMargins(4, 1, 4, 1)
        self.setMinimumWidth(60)
        self._full = text

    def setText(self, text):
        self._full = text
        self._apply()

    def _apply(self):
        shown = self.fontMetrics().elidedText(
            self._full, Qt.TextElideMode.ElideMiddle, max(20, self.width() - 10))
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

class Speedometer(QWidget):
    """A Metropolitan-style dial reading percent done, with an odometer
    window below the hub counting every photo DigiCarlo has brought in."""

    SWEEP = 220.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(150, 150)
        self.value = 0.0
        self.target = 0.0
        self.odometer = 0
        self.lit = False
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._step)

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
        # The needle eases toward its reading rather than jumping to it.
        d = self.target - self.value
        if abs(d) < 0.002:
            self.value = self.target
            self._timer.stop()
        else:
            self.value += d * 0.22
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        c = QPointF(self.width() / 2, self.height() / 2)
        R = side / 2 - 2

        # chrome bezel
        g = QConicalGradient(c, 45)
        for at, col in ((0.0, "#FFFFFF"), (0.2, "#9BA3AC"), (0.45, "#F4F6F8"),
                        (0.7, "#7E8790"), (1.0, "#FFFFFF")):
            g.setColorAt(at, QColor(col))
        p.setPen(QPen(QColor("#3A4048"), 1.2))
        p.setBrush(QBrush(g))
        p.drawEllipse(c, R, R)

        # the face: cream, faintly domed
        face = QRadialGradient(QPointF(c.x() - R * 0.25, c.y() - R * 0.3), R * 1.3)
        face.setColorAt(0.0, QColor("#FFFDF6") if not self.lit else QColor("#FFFBEA"))
        face.setColorAt(1.0, QColor("#E3DCC8") if not self.lit else QColor("#EFE3BE"))
        p.setPen(QPen(QColor("#5B6168"), 1))
        p.setBrush(QBrush(face))
        rf = R - 8
        p.drawEllipse(c, rf, rf)

        start = 90 + self.SWEEP / 2      # degrees, 0 at 3 o'clock, CCW

        def at(frac, radius):
            ang = math.radians(start - frac * self.SWEEP)
            return QPointF(c.x() + radius * math.cos(ang),
                           c.y() - radius * math.sin(ang))

        # ticks and numerals
        for i in range(0, 21):
            frac = i / 20.0
            major = i % 4 == 0
            p.setPen(QPen(PAINT_INK, 2.0 if major else 1.0))
            p.drawLine(at(frac, rf - 3), at(frac, rf - (11 if major else 7)))
        num_font = ui_font(7, bold=True)
        num_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        p.setFont(num_font)
        p.setPen(PAINT_INK)
        for i in range(0, 6):
            frac = i / 5.0
            pt = at(frac, rf - 21)
            p.drawText(QRectF(pt.x() - 14, pt.y() - 7, 28, 14),
                       Qt.AlignmentFlag.AlignCenter, str(i * 20))

        label_font = ui_font(6)
        label_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        p.setFont(label_font)
        p.setPen(QColor("#6B6453"))
        p.drawText(QRectF(c.x() - 30, c.y() - rf * 0.36, 60, 12),
                   Qt.AlignmentFlag.AlignCenter, "PERCENT")

        # odometer window
        digits = "%06d" % (self.odometer % 1000000)
        dw, dh = 9, 13
        ow = dw * len(digits) + 4
        orect = QRectF(c.x() - ow / 2, c.y() + rf * 0.40, ow, dh + 4)
        p.setPen(QPen(QColor("#3A3A3A"), 1))
        p.setBrush(QColor("#1A1A1A"))
        p.drawRect(orect)
        odo = ui_font(7, bold=True)
        odo.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        p.setFont(odo)
        for i, ch in enumerate(digits):
            cell = QRectF(orect.left() + 2 + i * dw, orect.top() + 2, dw - 1, dh)
            last = i == len(digits) - 1
            p.fillRect(cell, QBrush(vgrad(cell, ["#DADADA", "#FFFFFF", "#BDBDBD"]
                                          if last else
                                          ["#000000", "#3A3A3A", "#000000"])))
            p.setPen(QColor("#111111") if last else QColor("#F2F2F2"))
            p.drawText(cell, Qt.AlignmentFlag.AlignCenter, ch)
        p.setFont(label_font)
        p.setPen(QColor("#6B6453"))
        p.drawText(QRectF(c.x() - 30, orect.bottom() + 1, 60, 11),
                   Qt.AlignmentFlag.AlignCenter, "PHOTOS")

        # the needle
        tip = at(self.value, rf - 6)
        tail = at(self.value + 0.5, 12)
        ang = math.radians(start - self.value * self.SWEEP)
        nx, ny = -math.sin(ang) * 2.4, -math.cos(ang) * 2.4
        poly = QPolygonF([QPointF(c.x() + nx, c.y() + ny), tip,
                          QPointF(c.x() - nx, c.y() - ny), tail])
        p.setPen(QPen(QColor(0, 0, 0, 60), 1))
        p.setBrush(QColor(0, 0, 0, 45))
        p.drawPolygon(poly.translated(1.5, 2))
        p.setPen(QPen(QColor("#7A1D10"), 0.8))
        p.setBrush(NEEDLE)
        p.drawPolygon(poly)
        hub = QRadialGradient(QPointF(c.x() - 2, c.y() - 2), 8)
        hub.setColorAt(0, QColor("#FFFFFF"))
        hub.setColorAt(1, QColor("#7C858E"))
        p.setBrush(QBrush(hub))
        p.setPen(QPen(QColor("#3A4048"), 1))
        p.drawEllipse(c, 6.5, 6.5)

        # glass
        glare = QPainterPath()
        glare.addEllipse(QPointF(c.x() - R * 0.18, c.y() - R * 0.36),
                         R * 0.62, R * 0.36)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 34))
        p.drawPath(glare)


class PaintButton(QWidget):
    """The one important button: Windows 95 bevels, Metropolitan paint."""

    clicked = pyqtSignal()

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = text
        self.sub = ""
        self.down = False
        self.hover = False
        self.setMinimumSize(170, 52)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_text(self, text, sub=""):
        self.text, self.sub = text, sub
        self.update()

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

    def paintEvent(self, _):
        p = QPainter(self)
        r = self.rect()
        # Windows 95's default button wears an extra black ring.
        p.setPen(QPen(DARK, 1))
        p.drawRect(r.adjusted(0, 0, -1, -1))
        inner = r.adjusted(1, 1, -1, -1)
        if self.isEnabled():
            face = [PAINT[0], PAINT[1], PAINT[2], PAINT[3]] if not self.hover \
                else ["#D2E7F6", "#AACFE8", "#8DBAD9", "#72A4C9"]
            p.fillRect(inner, QBrush(vgrad(inner, face)))
        else:
            p.fillRect(inner, CREAM)
        body = bevel(p, inner, raised=not self.down)
        o = 1 if self.down else 0
        text_rect = body.translated(o, o)
        if self.isEnabled():
            p.setPen(QColor(20, 45, 70, 140))
            p.setFont(ui_font(10, bold=True))
            main = text_rect.adjusted(0, 0, 0, -14 if self.sub else 0)
            p.drawText(main.translated(1, 1), Qt.AlignmentFlag.AlignCenter,
                       self.text)
            p.setPen(WHITE)
            p.drawText(main, Qt.AlignmentFlag.AlignCenter, self.text)
            if self.sub:
                p.setFont(ui_font(8))
                p.setPen(QColor("#F2F8FC"))
                p.drawText(text_rect.adjusted(0, 22, 0, 0),
                           Qt.AlignmentFlag.AlignCenter, self.sub)
        else:
            p.setFont(ui_font(10, bold=True))
            # Windows 95's etched disabled text
            p.setPen(WHITE)
            p.drawText(text_rect.translated(1, 1), Qt.AlignmentFlag.AlignCenter,
                       self.text)
            p.setPen(SHADOW)
            p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.text)
        if self.hasFocus():
            pen = QPen(INK, 1, Qt.PenStyle.DotLine)
            p.setPen(pen)
            p.drawRect(body.adjusted(2, 2, -3, -3))


def script_font(size):
    """Something cursive for the nameplate, as the car wore its name."""
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


class Nameplate(QWidget):
    """'DigiCarlo' in chrome script, fixed to the bodywork."""

    def __init__(self, text="DigiCarlo", parent=None):
        super().__init__(parent)
        self.text = text
        self.setFixedHeight(40)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = script_font(21)
        path = QPainterPath()
        path.addText(0, 0, font, self.text)
        box = path.boundingRect()
        scale = min(1.0, (self.width() - 8) / max(1.0, box.width()))
        p.translate((self.width() - box.width() * scale) / 2 - box.left() * scale,
                    (self.height() - box.height() * scale) / 2
                    - box.top() * scale)
        p.scale(scale, scale)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(20, 45, 70, 110))
        p.drawPath(path.translated(1.2, 1.6))
        g = QLinearGradient(QPointF(0, box.top()), QPointF(0, box.bottom()))
        for at, col in CHROME:
            g.setColorAt(at, QColor(col))
        p.setBrush(QBrush(g))
        p.setPen(QPen(QColor("#3B4550"), 0.9))
        p.drawPath(path)


class Dashboard(QWidget):
    """The strip along the bottom: painted body, chrome trim, the dial,
    a cream placard for what is happening, and the go button."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(166)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 11, 14, 8)
        row.setSpacing(14)
        self.gauge = Speedometer(self)
        row.addWidget(self.gauge, 0, Qt.AlignmentFlag.AlignVCenter)

        self.placard = QFrame(self)
        pl = QVBoxLayout(self.placard)
        pl.setContentsMargins(10, 8, 10, 8)
        pl.setSpacing(3)
        self.caption = QLabel("Ready", self.placard)
        self.caption.setFont(ui_font(8, bold=True))
        self.detail = QLabel("", self.placard)
        self.detail.setWordWrap(True)
        self.detail.setAlignment(Qt.AlignmentFlag.AlignTop |
                                 Qt.AlignmentFlag.AlignLeft)
        self.detail.setSizePolicy(QSizePolicy.Policy.Expanding,
                                  QSizePolicy.Policy.Expanding)
        pl.addWidget(self.caption)
        pl.addWidget(self.detail, 1)
        self.stop = QPushButton("Stop", self.placard)
        self.stop.setVisible(False)
        self.stop.setFixedWidth(75)
        pl.addWidget(self.stop, 0, Qt.AlignmentFlag.AlignRight)
        self.placard.paintEvent = self._paint_placard
        row.addWidget(self.placard, 1)

        col = QVBoxLayout()
        col.setSpacing(6)
        col.addStretch(1)
        col.addWidget(Nameplate("DigiCarlo", self))
        self.go = PaintButton("Put in library", self)
        self.go.setFixedWidth(200)
        col.addWidget(self.go)
        col.addStretch(1)
        row.addLayout(col)

    def _paint_placard(self, _):
        p = QPainter(self.placard)
        r = self.placard.rect()
        p.fillRect(r, CREAM_LIGHT)
        bevel(p, r, raised=False)

    def say(self, caption, detail=""):
        self.caption.setText(caption)
        self.detail.setText(detail)

    def paintEvent(self, _):
        p = QPainter(self)
        r = self.rect()
        chrome_strip(p, QRect(r.left(), r.top(), r.width(), 5))
        body = QRect(r.left(), r.top() + 5, r.width(), r.height() - 5)
        paint_panel(p, body)
        # a second, thinner spear of chrome low on the body
        chrome_strip(p, QRect(r.left(), r.bottom() - 3, r.width(), 3))


# ---------------------------------------------------------------------------
# Cameras and cards
# ---------------------------------------------------------------------------

def paint_source_glyph(p, rect, kind):
    """A tiny Windows 95-style icon for a card or a camera."""
    p.save()
    p.translate(rect.topLeft())
    p.setPen(QPen(INK, 1))
    if kind in ("volume", "folder"):
        if kind == "folder":
            p.setBrush(QColor("#E8C55A"))
            p.drawRect(2, 8, 26, 17)
            p.drawRect(2, 5, 10, 3)
        else:
            card = QPolygonF([QPointF(6, 3), QPointF(22, 3), QPointF(26, 7),
                              QPointF(26, 28), QPointF(6, 28)])
            p.setBrush(QColor("#3F4A56"))
            p.drawPolygon(card)
            p.setBrush(QColor(PAINT[1]))
            p.drawRect(9, 12, 14, 11)
            p.setPen(QPen(QColor("#E6C04A"), 1))
            for x in range(9, 23, 3):
                p.drawLine(x, 5, x, 9)
    else:
        p.setBrush(QColor("#F4F0E4"))
        p.drawRect(3, 9, 25, 17)
        p.fillRect(QRect(4, 18, 24, 8), QColor(PAINT[2]))
        p.drawLine(3, 18, 28, 18)
        p.setBrush(QColor("#F4F0E4"))
        p.drawRect(7, 6, 7, 3)
        p.setBrush(QColor("#9AA3AC"))
        p.drawEllipse(QPointF(16, 17), 6, 6)
        p.setBrush(QColor("#1E3D5C"))
        p.drawEllipse(QPointF(16, 17), 3.5, 3.5)
    p.restore()


class SourceRow(QWidget):
    pull = pyqtSignal(object)

    def __init__(self, src, parent=None):
        super().__init__(parent)
        self.src = src
        self.setMinimumHeight(52)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(40, 4, 6, 4)
        lay.setSpacing(6)
        col = QVBoxLayout()
        col.setSpacing(1)
        name = QLabel(src.label, self)
        name.setFont(ui_font(8, bold=True))
        detail = QLabel(src.detail or src.kind, self)
        detail.setStyleSheet("color: #5E5A50;")
        col.addWidget(name)
        col.addWidget(detail)
        lay.addLayout(col, 1)
        self.button = QPushButton("Pull", self)
        self.button.setFixedWidth(52)
        self.button.setToolTip("Copy the new pictures on %s into the archive"
                               % src.label)
        self.button.clicked.connect(lambda: self.pull.emit(self.src))
        lay.addWidget(self.button, 0, Qt.AlignmentFlag.AlignVCenter)

    def paintEvent(self, _):
        p = QPainter(self)
        paint_source_glyph(p, QRect(5, (self.height() - 30) // 2, 30, 30),
                           self.src.kind)
        p.setPen(QPen(QColor("#D9D3C3"), 1))
        p.drawLine(4, self.height() - 1, self.width() - 4, self.height() - 1)


class SourcePanel(QWidget):
    pull = pyqtSignal(object)
    rescan = pyqtSignal()
    pull_folder = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        head = QLabel("Cameras and cards", self)
        head.setFont(ui_font(8, bold=True))
        lay.addWidget(head)
        self.inner = QWidget()
        self.inner.setAutoFillBackground(True)
        pal = self.inner.palette()
        pal.setColor(QPalette.ColorRole.Window, FIELD)
        self.inner.setPalette(pal)
        self.rows = QVBoxLayout(self.inner)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(0)
        self.rows.addStretch(1)
        lay.addWidget(Sunken(self.inner, self), 1)
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.look = QPushButton("Look again", self)
        self.look.clicked.connect(self.rescan)
        self.folder = QPushButton("Folder...", self)
        self.folder.setToolTip("Pull from a folder as if it were a card")
        self.folder.clicked.connect(self.pull_folder)
        buttons.addWidget(self.look)
        buttons.addWidget(self.folder)
        lay.addLayout(buttons)

    def set_sources(self, found, busy=False):
        while self.rows.count() > 1:
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not found:
            empty = QLabel("Nothing plugged in.\n\nPut a card in the reader, "
                           "or connect a camera by USB.", self.inner)
            empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #5E5A50; padding: 12px;")
            self.rows.insertWidget(0, empty)
            return
        for n, src in enumerate(found):
            row = SourceRow(src, self.inner)
            row.pull.connect(self.pull)
            row.button.setEnabled(not busy)
            self.rows.insertWidget(n, row)

    def set_busy(self, busy):
        for i in range(self.rows.count()):
            w = self.rows.itemAt(i).widget()
            if isinstance(w, SourceRow):
                w.button.setEnabled(not busy)
        self.folder.setEnabled(not busy)


# ---------------------------------------------------------------------------
# The shots
# ---------------------------------------------------------------------------

KIND_ROLE = Qt.ItemDataRole.UserRole
KEY_ROLE = Qt.ItemDataRole.UserRole + 1
DATA_ROLE = Qt.ItemDataRole.UserRole + 2


def short_time(dt):
    return dt.strftime("%b %d  %H:%M:%S") if dt else "?"


class ShotDelegate(QStyledItemDelegate):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner

    def sizeHint(self, option, index):
        kind = index.data(KIND_ROLE)
        if kind in ("batch", "session"):
            w = max(200, self.owner.viewport().width() - 14)
            return QSize(w, 34 if kind == "batch" else
                         20 + 14 * len(index.data(DATA_ROLE)["lines"]))
        return QSize(CELL_W, CELL_H)

    def paint(self, p, option, index):
        kind = index.data(KIND_ROLE)
        p.save()
        if kind == "batch":
            self._batch(p, option.rect, index.data(DATA_ROLE))
        elif kind == "session":
            self._session(p, option.rect, index.data(DATA_ROLE))
        else:
            self._shot(p, option, index)
        p.restore()

    def _batch(self, p, r, d):
        box = QRect(r.left() + 2, r.top() + 6, r.width() - 4, r.height() - 8)
        paint_panel(p, box)
        chrome_strip(p, QRect(box.left(), box.bottom() - 2, box.width(), 3))
        p.setPen(QPen(DARK, 1))
        p.drawRect(box.adjusted(0, 0, -1, -1))
        p.setFont(ui_font(8, bold=True))
        p.setPen(QColor(20, 45, 70, 130))
        tr = box.adjusted(10, 0, -10, -3)
        p.drawText(tr.translated(1, 1), Qt.AlignmentFlag.AlignVCenter, d["title"])
        p.setPen(WHITE)
        p.drawText(tr, Qt.AlignmentFlag.AlignVCenter, d["title"])
        p.setFont(ui_font(8))
        p.drawText(tr, Qt.AlignmentFlag.AlignVCenter |
                   Qt.AlignmentFlag.AlignRight, d["right"])

    def _session(self, p, r, d):
        # Windows 95's etched separator with the session's story on it.
        y = r.top() + 9
        p.setFont(ui_font(8, bold=True))
        title = d["title"]
        tw = p.fontMetrics().horizontalAdvance(title)
        p.setPen(QPen(SHADOW, 1))
        p.drawLine(r.left() + tw + 12, y, r.right() - 4, y)
        p.setPen(QPen(WHITE, 1))
        p.drawLine(r.left() + tw + 12, y + 1, r.right() - 4, y + 1)
        p.setPen(PAINT_INK)
        p.drawText(QRect(r.left() + 4, r.top(), tw + 4, 18),
                   Qt.AlignmentFlag.AlignVCenter, title)
        p.setFont(ui_font(8))
        for n, (text, colour) in enumerate(d["lines"]):
            p.setPen(QColor(colour))
            p.drawText(QRect(r.left() + 18, r.top() + 18 + 14 * n,
                             r.width() - 24, 14),
                       Qt.AlignmentFlag.AlignVCenter, text)

    def _shot(self, p, option, index):
        r = option.rect
        d = index.data(DATA_ROLE)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        frame = QRect(r.left() + (r.width() - THUMB_W - 6) // 2, r.top() + 4,
                      THUMB_W + 6, THUMB_H + 6)
        p.fillRect(frame, FIELD)
        inner = bevel(p, frame, raised=False)
        img = self.owner.thumb(d["key"])
        area = inner.adjusted(1, 1, -1, -1)
        if img is not None and img.isNull():
            # Windows' broken-picture mark: the file is not a readable image
            # (a card that is failing often leaves a few of these).
            p.fillRect(area, QColor("#F4F1E8"))
            mark = QRect(area.center().x() - 8, area.center().y() - 14, 16, 16)
            p.setPen(QPen(SHADOW, 1))
            p.setBrush(WHITE)
            p.drawRect(mark)
            p.setPen(QPen(BAD, 2))
            p.drawLine(mark.left() + 4, mark.top() + 4,
                       mark.right() - 3, mark.bottom() - 3)
            p.drawLine(mark.right() - 3, mark.top() + 4,
                       mark.left() + 4, mark.bottom() - 3)
            p.setPen(INK_SOFT)
            p.setFont(ui_font(7))
            p.drawText(area.adjusted(0, 22, 0, 0), Qt.AlignmentFlag.AlignCenter,
                       "cannot show")
        elif img is not None:
            scaled = img.scaled(area.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
            x = area.left() + (area.width() - scaled.width()) // 2
            y = area.top() + (area.height() - scaled.height()) // 2
            p.drawImage(x, y, scaled)
        else:
            p.fillRect(area, QColor("#E9E5D8"))
            p.setPen(SHADOW)
            p.setFont(ui_font(7))
            p.drawText(area, Qt.AlignmentFlag.AlignCenter, "...")
        if d["video"]:
            # sprocket holes: this one moves
            p.fillRect(QRect(area.left(), area.top(), 7, area.height()),
                       QColor(20, 20, 20, 200))
            p.fillRect(QRect(area.right() - 6, area.top(), 7, area.height()),
                       QColor(20, 20, 20, 200))
            for yy in range(area.top() + 3, area.bottom() - 3, 8):
                p.fillRect(QRect(area.left() + 2, yy, 3, 4), QColor("#F0EBDD"))
                p.fillRect(QRect(area.right() - 4, yy, 3, 4), QColor("#F0EBDD"))
        if selected:
            p.fillRect(area, QColor(46, 94, 138, 90))
        # shot number, as 'digicarlo plan' prints it
        p.setFont(ui_font(7))
        num = str(d["number"])
        nw = p.fontMetrics().horizontalAdvance(num) + 6
        badge = QRect(frame.left() + 3, frame.top() + 3, nw, 12)
        p.fillRect(badge, QColor(255, 255, 225, 230))
        p.setPen(QPen(INK, 1))
        p.drawRect(badge.adjusted(0, 0, -1, -1))
        p.drawText(badge, Qt.AlignmentFlag.AlignCenter, num)
        if d["pinned"]:
            pin = QRect(frame.right() - 13, frame.top() + 3, 10, 10)
            p.setPen(QPen(INK, 1))
            p.setBrush(QColor("#E0A526") if d["pinned"] == "set" else
                       QColor("#9AA3AC"))
            p.drawEllipse(pin)
        # caption: name, then the date it will get
        p.setFont(ui_font(8))
        name_rect = QRect(r.left() + 2, frame.bottom() + 4, r.width() - 4, 14)
        name = p.fontMetrics().elidedText(d["name"], Qt.TextElideMode.ElideMiddle,
                                          name_rect.width() - 4)
        if selected:
            nw = p.fontMetrics().horizontalAdvance(name) + 6
            hl = QRect(name_rect.center().x() - nw // 2, name_rect.top(), nw, 14)
            p.fillRect(hl, PAINT_DEEP)
            p.setPen(WHITE)
        else:
            p.setPen(INK)
        p.drawText(name_rect, Qt.AlignmentFlag.AlignCenter, name)
        p.setPen(PAINT_INK if d["pinned"] else INK_SOFT)
        p.setFont(ui_font(7))
        p.drawText(QRect(r.left(), name_rect.bottom() + 1, r.width(), 12),
                   Qt.AlignmentFlag.AlignCenter, d["when"])


class ShotList(QListWidget):
    """Every shot waiting for the library, grouped by pull and session.

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
        self.setSpacing(2)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setItemDelegate(ShotDelegate(self))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.itemSelectionChanged.connect(self.selection_changed)
        self.itemClicked.connect(self._clicked)
        self.empty_text = ""

    def thumb(self, key):
        return self.owner.thumb(key)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # Headers are as wide as the view; tell the layout they changed.
        self.doItemsLayout()

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
        super().paintEvent(e)
        if self.count() == 0 and self.empty_text:
            p = QPainter(self.viewport())
            p.setPen(INK_SOFT)
            p.setFont(ui_font(8))
            p.drawText(self.viewport().rect().adjusted(30, 30, -30, -30),
                       Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                       self.empty_text)


# ---------------------------------------------------------------------------
# Background work
# ---------------------------------------------------------------------------

class GuiLog(blinky.Log):
    """The shared logger, rerouted into the window."""

    def __init__(self, sink):
        super().__init__(verbose=False, quiet=True)
        self.sink = sink

    def _emit(self, msg, stream=None):
        self.sink("info", str(msg))

    def out(self, msg=""):
        self._record("OUT", msg)
        if str(msg).strip():
            self.sink("out", str(msg))

    def warn(self, msg):
        self._record("WARN", msg)
        self.sink("warn", str(msg))

    def error(self, msg):
        self._record("ERROR", msg)
        self.sink("error", str(msg))


class Job(QThread):
    line = pyqtSignal(str, str)
    step = pyqtSignal(int, int, str)
    ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn
        self.cancel = threading.Event()

    def progress(self, done, total, caption):
        self.step.emit(int(done), int(total), str(caption))

    def run(self):
        log = GuiLog(self.line.emit)
        try:
            self.ok.emit(self.fn(self, log))
        except Exception as exc:                      # never take the UI down
            self.failed.emit(str(exc) if isinstance(
                exc, (RuntimeError, OSError, blinky.CameraError,
                      archive.ArchiveBusy)) else
                "%s: %s" % (type(exc).__name__, exc))


class ThumbLoader(QThread):
    """Makes thumbnails from the archive copies, newest request first."""

    loaded = pyqtSignal(str, QImage)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.q = queue.LifoQueue()
        self.stopping = False

    def request(self, key, path, kind):
        self.q.put((key, path, kind))

    def stop(self):
        self.stopping = True
        self.q.put(None)

    def run(self):
        while not self.stopping:
            job = self.q.get()
            if job is None:
                continue
            key, path, kind = job
            try:
                img = self.make(path, kind)
            except Exception:
                img = QImage()
            self.loaded.emit(key, img)

    @staticmethod
    def make(path, kind):
        box = QSize(THUMB_W * 2, THUMB_H * 2)
        if kind in ("still", "raw"):
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            size = reader.size()
            if size.isValid():
                reader.setScaledSize(size.scaled(box,
                                                 Qt.AspectRatioMode.KeepAspectRatio))
            img = reader.read()
            if not img.isNull():
                return img
            if kind == "raw":
                # Most raws carry a JPEG preview; exiftool can lift it out.
                res = subprocess.run(["exiftool", "-b", "-PreviewImage", path],
                                     capture_output=True, timeout=30)
                if res.stdout:
                    img = QImage.fromData(res.stdout)
                    return img.scaled(box, Qt.AspectRatioMode.KeepAspectRatio)
            return QImage()
        if kind == "video":
            res = subprocess.run(
                ["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-frames:v",
                 "1", "-vf", "scale=%d:-2" % (THUMB_W * 2), "-f", "image2pipe",
                 "-c:v", "png", "-"], capture_output=True, timeout=30)
            return QImage.fromData(res.stdout) if res.stdout else QImage()
        if kind in (media.SIPIX_STILL, media.SIPIX_CLIP):
            with open(path, "rb") as fh:
                data = fh.read()
            if kind == media.SIPIX_CLIP:
                frames = blinky.split_clip_frames(data)
                if not frames:
                    return QImage()
                data = frames[0]
            w, h, raster, _ = blinky.decode_still(data, blinky.Log(quiet=True))
            img = QImage(raster, w, h, w * 3, QImage.Format.Format_RGB888).copy()
            return img.scaled(box, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
        return QImage()


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------

class Win95Dialog(QDialog):
    """A frameless dialog wearing the same title bar as the main window."""

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
        self.lay.setContentsMargins(12, 12, 12, 12)
        self.lay.setSpacing(10)
        outer.addWidget(self.body)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), CREAM)
        bevel(p, self.rect(), raised=True)

    def buttons(self, *specs):
        row = QHBoxLayout()
        row.addStretch(1)
        made = []
        for text, role in specs:
            b = QPushButton(text, self)
            b.setMinimumWidth(75)
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
    """Windows 95's message-box icons, redrawn."""
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(INK, 1))
    if kind == "error":
        p.setBrush(QColor("#E0301E"))
        p.drawEllipse(QRectF(2, 2, 28, 28))
        p.setPen(QPen(WHITE, 3.2))
        p.drawLine(QPointF(10, 10), QPointF(22, 22))
        p.drawLine(QPointF(22, 10), QPointF(10, 22))
    elif kind == "question":
        p.setBrush(WHITE)
        p.drawEllipse(QRectF(2, 2, 28, 28))
        p.setPen(PAINT_DEEP)
        p.setFont(ui_font(15, bold=True))
        p.drawText(QRectF(2, 2, 28, 28), Qt.AlignmentFlag.AlignCenter, "?")
    else:
        p.setBrush(WHITE)
        p.drawEllipse(QRectF(2, 2, 28, 28))
        p.setPen(PAINT_DEEP)
        p.setFont(ui_font(15, bold=True))
        p.drawText(QRectF(2, 2, 28, 28), Qt.AlignmentFlag.AlignCenter, "i")
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
    lab.setMinimumWidth(320)
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
        intro.setFont(ui_font(8, bold=True))
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
        note.setContentsMargins(22, 0, 0, 0)
        note.setStyleSheet("color: #5E5A50;")
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
            hello.setFont(ui_font(8, bold=True))
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
            lab.setFont(ui_font(8, bold=True))
            self.lay.addWidget(lab)
            row = QHBoxLayout()
            edit = QLineEdit(getattr(settings, key), self)
            edit.setMinimumWidth(360)
            browse = QPushButton("Browse...", self)
            browse.clicked.connect(lambda _, e=edit, t=title: self._browse(e, t))
            row.addWidget(edit, 1)
            row.addWidget(browse)
            self.lay.addLayout(row)
            h = QLabel(help_, self)
            h.setWordWrap(True)
            h.setStyleSheet("color: #5E5A50;")
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
        view.setMinimumSize(620, 360)
        f = QFont("DejaVu Sans Mono")
        f.setPointSizeF(8)
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
        self.resize(1040, 720)
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

        body = QHBoxLayout()
        body.setContentsMargins(8, 8, 8, 8)
        body.setSpacing(8)
        self.sources_panel = SourcePanel(self)
        self.sources_panel.setFixedWidth(250)
        self.sources_panel.pull.connect(self.pull)
        self.sources_panel.rescan.connect(self.rescan)
        self.sources_panel.pull_folder.connect(self.pull_folder)
        body.addWidget(self.sources_panel)

        right = QVBoxLayout()
        right.setSpacing(6)
        tools = QHBoxLayout()
        tools.setSpacing(6)
        head = QLabel("Waiting for the library", self)
        head.setFont(ui_font(8, bold=True))
        tools.addWidget(head)
        tools.addStretch(1)
        self.sel_label = QLabel("", self)
        self.sel_label.setStyleSheet("color: #5E5A50;")
        tools.addWidget(self.sel_label)
        self.b_date = QPushButton("Set date...", self)
        self.b_date.clicked.connect(self.set_date)
        self.b_camera = QPushButton("Camera's date", self)
        self.b_camera.clicked.connect(lambda: self.apply_rule("camera"))
        self.b_auto = QPushButton("Automatic", self)
        self.b_auto.clicked.connect(lambda: self.apply_rule("auto"))
        self.b_skip = QPushButton("Leave out", self)
        self.b_skip.clicked.connect(self.leave_out)
        for b in (self.b_date, self.b_camera, self.b_auto, self.b_skip):
            tools.addWidget(b)
        right.addLayout(tools)
        self.list = ShotList(self)
        self.list.selection_changed.connect(self._selection_changed)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.itemDoubleClicked.connect(self._open_item)
        right.addWidget(Sunken(self.list, self), 1)
        body.addLayout(right, 1)
        outer.addLayout(body, 1)

        self.dash = Dashboard(self)
        self.dash.go.clicked.connect(self.develop)
        self.dash.stop.clicked.connect(self.stop_job)
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
        """A one-shot timer owned by the window, so it dies with it."""
        t = QTimer(self)
        t.setSingleShot(True)
        t.timeout.connect(fn)
        t.timeout.connect(t.deleteLater)
        t.start(ms)

    # -- construction --------------------------------------------------------

    def _menus(self):
        bar = QMenuBar(self)
        f = bar.addMenu("&File")
        self._act(f, "Pull from a &folder...", self.pull_folder)
        self._act(f, "&Look for cameras again", self.rescan, "F5")
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
        self.st_count.setFixedWidth(170)
        row.addWidget(self.st_lib, 1)
        row.addWidget(self.st_arc, 1)
        row.addWidget(self.st_count)
        row.addWidget(SizeGrip(w), 0, Qt.AlignmentFlag.AlignBottom)
        w.setFixedHeight(22)
        return w

    # -- window frame ---------------------------------------------------------

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), CREAM)
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
        self.sources_panel.set_sources(found, busy)

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
                "Nothing is waiting for the library.\n\nPull from a camera or "
                "card on the left. Its pictures are copied into the archive "
                "untouched, then shown here with the dates they will get.")
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
                "title": "%s  -  %d shot%s" % (batch.label, n,
                                               "" if n == 1 else "s"),
                "right": "taken off %s  (%s)" % (
                    batch.anchor.strftime("%Y-%m-%d %H:%M"),
                    brec.get("source_label") or "")})
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
            lines.append(("This camera keeps no clock; shots are a second "
                          "apart in the order they were taken.", "#5E5A50"))
        else:
            lines.append(("Camera's clock said %s" % timeplan.fmt_span(c0, c1),
                          "#5E5A50"))
        for g in [g for g in plan.groups if g.session is sess]:
            a, b = g.shots[0].number, g.shots[-1].number
            which = "" if len(g.shots) == n else (
                "%s: " % describe_numbers([s.number for s in g.shots]).capitalize())
            if g.rule is None:
                how, colour = "dated when taken off the camera", "#244B70"
            elif g.rule.when == "camera":
                how, colour = "keeping the camera's dates", "#7A5A12"
            else:
                how, colour = "set by you", "#7A5A12"
            lines.append(("%sWill be dated %s   (%s)" % (
                which, timeplan.fmt_span(g.start, g.end), how), colour))
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        item.setData(KIND_ROLE, "session")
        item.setData(DATA_ROLE, {
            "title": "Session %d  -  %d shot%s" % (sess.number, n,
                                                   "" if n == 1 else "s"),
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

    def _selection_changed(self):
        shots = self._selected_shots()
        busy = self.job is not None and self.job.isRunning()
        for b in (self.b_date, self.b_camera, self.b_auto, self.b_skip):
            b.setEnabled(bool(shots) and not busy)
        self.sel_label.setText("%d selected" % len(shots) if shots else
                               "Select shots to date them")

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
            self.dash.say(self.dash.caption.text(), text)

    def _busy(self, on, caption=""):
        self.sources_panel.set_busy(on)
        self.dash.stop.setVisible(on)
        self.dash.stop.setEnabled(on)
        self.dash.gauge.set_lit(on)
        if on:
            self.dash.say(caption, "")
            self.dash.gauge.set_value(0)
        self._selection_changed()
        self._update_go()

    def _update_go(self):
        n = len(self.plan.shots) if self.plan else 0
        busy = self.job is not None and self.job.isRunning()
        self.dash.go.set_text("Put in library",
                              "%d shot%s" % (n, "" if n == 1 else "s")
                              if n else "")
        self.dash.go.setEnabled(bool(n) and not busy)
        if not busy:
            if n:
                self.dash.say("%d shot%s waiting" % (n, "" if n == 1 else "s"),
                              "Check the dates above, change any that are "
                              "wrong, then put them in the library.")
            else:
                self.dash.say("Ready", "Pull from a camera or card to begin.")

    def run(self, fn, done, caption):
        if self.job is not None and self.job.isRunning():
            return
        job = Job(fn, self)
        job.line.connect(self._log)
        job.step.connect(self._step)
        job.ok.connect(done)
        job.failed.connect(self._failed)
        job.finished.connect(self._finished)
        self.job = job
        self._busy(True, caption)
        job.start()

    def stop_job(self):
        if self.job is not None and self.job.isRunning():
            self.job.cancel.set()
            self.dash.stop.setEnabled(False)
            self.dash.say(self.dash.caption.text(), "Stopping after this file...")

    def _step(self, done, total, caption):
        self.dash.gauge.set_value(done / total if total else 1.0)
        self.dash.detail.setText(caption)

    def _failed(self, msg):
        self._log("error", msg)
        message(self, "DigiCarlo", msg, "error")

    def _finished(self):
        self._busy(False)
        self.dash.gauge.set_value(0)
        self.replan()
        self.rescan()

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
        self.later(0, lambda: self.dash.say("Pulled", text))

    def develop(self):
        if not self.plan or not self.plan.shots:
            return
        if self.job is not None and self.job.isRunning():
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
        self.later(0, lambda: self.dash.say("Done", text))

    # -- menus -----------------------------------------------------------------------

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
        icon.setPixmap(icon_pixmap(64))
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        row.addWidget(icon)
        text = QLabel(
            "<b>DigiCarlo %s</b><br><br>Gets the pictures off old digital "
            "cameras, dated when they came off the camera instead of by its "
            "wrong clock, with the camera's gaps between shots kept.<br><br>"
            "Clips are remuxed to MP4 with the video untouched.<br><br>"
            "The SiPix Blink II is driven by Blinky %s.<br><br>"
            "Licensed under the GNU LGPL, version 2.1." % (
                __version__, blinky.__version__), dlg)
        text.setWordWrap(True)
        text.setMinimumWidth(320)
        row.addWidget(text, 1)
        dlg.lay.addLayout(row)
        dlg.buttons(("OK", "accept"))
        dlg.exec()


def main(argv=None):
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("DigiCarlo")
    app.setApplicationDisplayName("DigiCarlo")
    app.setDesktopFileName("digicarlo")
    app.setStyle("Windows")
    app.setPalette(win95_palette())
    app.setFont(ui_font(8))
    themed = QIcon.fromTheme("digicarlo")
    app.setWindowIcon(themed if not themed.isNull() else app_icon())
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
