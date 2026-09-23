"""Windows 95, as the garage window wears it.

Grey three-dimensional faces lit from the top left, a navy title bar, and
the two-ring bevel round every button and panel. Qt's own "Windows" style
already draws buttons, menus and scroll bars the Win95 way; this supplies the
frame, the dialogs and the palette, since the window draws its own frame (on
Wayland a window may only move or resize itself by asking the compositor).
"""

import os

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPalette, QPen, QPolygonF
from PyQt6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel,
                             QLineEdit, QPlainTextEdit, QPushButton,
                             QVBoxLayout, QWidget)

from digicarlo.cartoon import icon_pixmap

FACE = QColor("#C0C0C0")
LIGHT = QColor("#DFDFDF")
WHITE = QColor("#FFFFFF")
SHADOW = QColor("#808080")
DARK = QColor("#000000")
NAVY = QColor("#000080")
TIP = QColor("#FFFFE1")

# Tahoma is Microsoft's own successor to MS Sans Serif, drawn to the same
# metrics; the rest are what a Linux desktop is likely to have.
UI_FAMILIES = ["Tahoma", "Microsoft Sans Serif", "MS Sans Serif",
               "Liberation Sans", "Arimo", "DejaVu Sans"]


def ui_font(size=9.0, bold=False):
    f = QFont()
    f.setFamilies(UI_FAMILIES)
    f.setPointSizeF(size)
    f.setBold(bold)
    return f


def palette():
    pal = QPalette()
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive,
                  QPalette.ColorGroup.Disabled):
        for role, colour in ((QPalette.ColorRole.Window, FACE),
                             (QPalette.ColorRole.Button, FACE),
                             (QPalette.ColorRole.Base, WHITE),
                             (QPalette.ColorRole.AlternateBase, LIGHT),
                             (QPalette.ColorRole.Light, WHITE),
                             (QPalette.ColorRole.Midlight, LIGHT),
                             (QPalette.ColorRole.Mid, SHADOW),
                             (QPalette.ColorRole.Dark, SHADOW),
                             (QPalette.ColorRole.Shadow, DARK),
                             (QPalette.ColorRole.Highlight, NAVY),
                             (QPalette.ColorRole.HighlightedText, WHITE),
                             (QPalette.ColorRole.ToolTipBase, TIP),
                             (QPalette.ColorRole.ToolTipText, DARK)):
            pal.setColor(group, role, colour)
        text = SHADOW if group == QPalette.ColorGroup.Disabled else DARK
        for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                     QPalette.ColorRole.ButtonText):
            pal.setColor(group, role, text)
    return pal


def bevel(p, rect, kind="raised"):
    """Windows 95's bevels, drawn inside rect; returns what is left inside.
    raised: windows and buttons. sunken: fields and wells. panel: the
    single-ring sunken panels of a status bar."""
    r = QRect(rect)
    rings = {"raised": [(LIGHT, DARK), (WHITE, SHADOW)],
             "sunken": [(SHADOW, WHITE), (DARK, LIGHT)],
             "panel": [(SHADOW, WHITE)]}[kind]
    for tl, br in rings:
        p.setPen(QPen(tl, 1))
        p.drawLine(r.left(), r.bottom() - 1, r.left(), r.top())
        p.drawLine(r.left(), r.top(), r.right() - 1, r.top())
        p.setPen(QPen(br, 1))
        p.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
        p.drawLine(r.right(), r.bottom(), r.right(), r.top())
        r.adjust(1, 1, -1, -1)
    return r


# ---------------------------------------------------------------------------
# The frame
# ---------------------------------------------------------------------------

class CaptionButton(QWidget):
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
        p.fillRect(self.rect(), FACE)
        bevel(p, self.rect(), "sunken" if self.down else "raised")
        o = 1 if self.down else 0
        x, y = 4 + o, 3 + o
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(DARK, 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self.glyph == "close":
            p.drawLine(QPointF(x, y), QPointF(x + 7, y + 7))
            p.drawLine(QPointF(x + 7, y), QPointF(x, y + 7))
        elif self.glyph == "min":
            p.fillRect(QRectF(x, y + 6, 6, 2), DARK)
        elif self.glyph == "max":
            p.setPen(QPen(DARK, 1))
            p.drawRect(QRectF(x - 0.5, y - 0.5, 8, 7))
            p.fillRect(QRectF(x - 0.5, y - 0.5, 8.5, 2), DARK)
        else:                                   # restore
            p.setPen(QPen(DARK, 1))
            p.drawRect(QRectF(x + 1.5, y - 0.5, 6, 5))
            p.fillRect(QRectF(x + 1.5, y - 0.5, 6.5, 1.5), DARK)
            p.fillRect(QRectF(x - 0.5, y + 2.5, 6.5, 5.5), FACE)
            p.drawRect(QRectF(x - 0.5, y + 2.5, 6, 5))
            p.fillRect(QRectF(x - 0.5, y + 2.5, 6.5, 1.5), DARK)


class TitleBar(QWidget):
    close_clicked = pyqtSignal()
    minimise_clicked = pyqtSignal()
    zoom_clicked = pyqtSignal()

    def __init__(self, text, parent=None, buttons=("min", "max", "close")):
        super().__init__(parent)
        self.text = text
        self.active = True
        self.setFixedHeight(20)
        row = QHBoxLayout(self)
        row.setContentsMargins(2, 3, 3, 3)
        row.setSpacing(0)
        row.addStretch(1)
        self.buttons = {}
        for g in buttons:
            if g == "close" and len(buttons) > 1:
                row.addSpacing(2)
            b = CaptionButton(g, self)
            self.buttons[g] = b
            row.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        for g, sig in (("close", self.close_clicked),
                       ("min", self.minimise_clicked),
                       ("max", self.zoom_clicked)):
            if g in self.buttons:
                self.buttons[g].clicked.connect(sig)

    def set_text(self, text):
        self.text = text
        self.update()

    def set_active(self, on):
        self.active = on
        self.update()

    def set_maximised(self, on):
        if "max" in self.buttons:
            self.buttons["max"].glyph = "restore" if on else "max"
            self.buttons["max"].update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemMove()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.zoom_clicked.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = self.rect().adjusted(0, 1, 0, -1)
        p.fillRect(r, NAVY if self.active else SHADOW)
        p.drawPixmap(QRectF(3, r.top() + 1, 16, 16), icon_pixmap(64),
                     QRectF(0, 0, 64, 64))
        p.setPen(WHITE if self.active else FACE)
        p.setFont(ui_font(9, bold=True))
        used = sum(b.width() + 2 for b in self.buttons.values()) + 30
        p.drawText(QRectF(23, r.top(), r.width() - used, r.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   self.text)


class SizeGrip(QWidget):
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


class StatusPanel(QLabel):
    clicked = pyqtSignal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setContentsMargins(4, 1, 4, 1)
        self.setMinimumWidth(60)
        self.setFont(ui_font(8.5))
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
        bevel(p, self.rect(), "panel")
        p.end()
        super().paintEvent(e)


class Window(QWidget):
    """A top-level window with a Windows 95 frame, title bar and menu bar
    slot. Subclasses fill self.lay."""

    BORDER = 4

    def __init__(self, title):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Window |
                            Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle(title)
        self.setMouseTracking(True)
        outer = QVBoxLayout(self)
        m = self.BORDER
        outer.setContentsMargins(m, m, m, m)
        outer.setSpacing(0)
        self.bar = TitleBar(title, self)
        self.bar.close_clicked.connect(self.close)
        self.bar.minimise_clicked.connect(self.showMinimized)
        self.bar.zoom_clicked.connect(self.toggle_zoom)
        outer.addWidget(self.bar)
        self.lay = outer

    def set_title(self, text):
        self.setWindowTitle(text)
        self.bar.set_text(text)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), FACE)
        bevel(p, self.rect(), "raised")

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

    def toggle_zoom(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------

class Dialog(QDialog):
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
        p.fillRect(self.rect(), FACE)
        bevel(p, self.rect(), "raised")

    def buttons(self, *specs):
        row = QHBoxLayout()
        row.addStretch(1)
        made = []
        for text, role in specs:
            b = QPushButton(text, self)
            b.setMinimumWidth(80)
            b.setMinimumHeight(24)
            if role == "accept":
                b.setDefault(True)
                b.clicked.connect(self.accept)
            elif role == "reject":
                b.clicked.connect(self.reject)
            row.addWidget(b)
            made.append(b)
        if len(specs) == 1:
            row.addStretch(1)
        self.lay.addLayout(row)
        return made


class MessageIcon(QWidget):
    """Windows 95's message-box pictures: i, ?, ! and the red stop."""

    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(34, 34)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        f = QFont("Times New Roman")
        f.setFamilies(["Times New Roman", "Liberation Serif", "DejaVu Serif"])
        f.setBold(True)
        if self.kind == "error":
            p.setPen(QPen(DARK, 1.2))
            p.setBrush(QColor("#FF0000"))
            p.drawEllipse(QRectF(1, 1, 30, 30))
            p.setPen(QPen(WHITE, 3.2))
            p.drawLine(QPointF(10, 10), QPointF(22, 22))
            p.drawLine(QPointF(22, 10), QPointF(10, 22))
            return
        if self.kind == "warning":
            p.setPen(QPen(DARK, 1.2))
            p.setBrush(QColor("#FFFF00"))
            p.drawPolygon(QPolygonF([QPointF(16, 1), QPointF(31, 30),
                                     QPointF(1, 30)]))
            text, colour = "!", DARK
        else:
            # the speech balloon of Windows 95's information and question
            p.setPen(QPen(DARK, 1.2))
            p.setBrush(WHITE)
            p.drawEllipse(QRectF(1, 1, 30, 26))
            p.drawPolygon(QPolygonF([QPointF(9, 23), QPointF(7, 32),
                                     QPointF(16, 26)]))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(QRectF(9, 22, 6, 4))
            text, colour = ("?" if self.kind == "question" else "i"), QColor("#0000FF")
        f.setPixelSize(20)
        p.setFont(f)
        p.setPen(colour)
        p.drawText(QRectF(1, 2, 30, 26), Qt.AlignmentFlag.AlignCenter, text)


def message(parent, title, text, kind="info", ask=None):
    """A Windows 95 message box. With ask=('Yes text', 'No text') it asks,
    and says whether the first was chosen."""
    dlg = Dialog(title, parent)
    row = QHBoxLayout()
    row.setSpacing(14)
    icon = MessageIcon(kind, dlg)
    row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
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


class TextDialog(Dialog):
    def __init__(self, parent, title, text):
        super().__init__(title, parent)
        view = QPlainTextEdit(self)
        view.setReadOnly(True)
        view.setPlainText(text)
        view.setMinimumSize(620, 360)
        f = QFont()
        f.setFamilies(["Courier New", "Liberation Mono", "DejaVu Sans Mono"])
        f.setPointSizeF(9)
        view.setFont(f)
        self.lay.addWidget(view)
        self.buttons(("Close", "accept"))
        view.moveCursor(view.textCursor().MoveOperation.End)


class FoldersDialog(Dialog):
    def __init__(self, parent, settings, first_run=False):
        super().__init__("Folders", parent)
        if first_run:
            hello = QLabel("Welcome to DigiCarlo. Where should pictures go?", self)
            hello.setFont(ui_font(9, bold=True))
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
            lab.setFont(ui_font(9, bold=True))
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
            self.lay.addWidget(h)
            self.fields[key] = edit
        self.buttons(("OK", "accept"), ("Cancel", "reject"))

    def _browse(self, edit, title):
        start = edit.text() if os.path.isdir(edit.text()) else \
            os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(
            self, "Choose the %s folder" % title.lower(), start)
        if path:
            edit.setText(path)

    def values(self):
        return {k: os.path.expanduser(e.text().strip())
                for k, e in self.fields.items()}
