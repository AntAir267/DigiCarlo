"""The Photo Board's dialogs, in Windows 95 grey.

    DateDialog      how picked shots should be dated
    NameDialog      a title for them
    PlaceDialog     where they were taken, from saved places or a new one
    TrustDialog     after a pull from a camera whose clock can be right:
                    which of its sessions to date by the camera
    Viewer          a shot at full size, stepping through the picked ones
    RedEyeDialog    the red-eye pen: each photo with its fixes, to keep,
                    drop, or add to by pointing at an eye
"""

import datetime
import os
import re
import subprocess

from PyQt6.QtCore import QDateTime, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QTransform
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QDateTimeEdit,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QRadioButton, QVBoxLayout, QWidget)

from digicarlo import media, timeplan
from digicarlo.stage import sprite
from digicarlo.win95 import Dialog, bevel, message, ui_font


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


def note(text, parent):
    lab = QLabel(text, parent)
    lab.setWordWrap(True)
    lab.setStyleSheet("color: #404040;")
    return lab


class DateDialog(Dialog):
    """How the picked shots should be dated."""

    def __init__(self, parent, shots, plan, stamp=None):
        super().__init__("Set a date", parent)
        first = plan.times[shots[0].key]
        cams = [s.camera_time for s in shots if s.camera_time]
        intro = QLabel("%s picked." % describe_numbers([s.number for s in shots])
                       .capitalize(), self)
        intro.setFont(ui_font(9, bold=True))
        self.lay.addWidget(intro)
        self.group = QButtonGroup(self)
        self.start = QRadioButton("Taken starting at:", self)
        self.when = QDateTimeEdit(self)
        self.when.setDisplayFormat("yyyy-MM-dd  HH:mm:ss")
        self.when.setCalendarPopup(True)
        self.when.setDateTime(QDateTime(stamp or first))
        row = QHBoxLayout()
        row.addWidget(self.start)
        row.addWidget(self.when)
        row.addStretch(1)
        self.lay.addLayout(row)
        n = note("The rest follow with the gaps the camera's clock recorded "
                 "between them.", self)
        n.setContentsMargins(22, 0, 0, 0)
        self.lay.addWidget(n)
        self.camera = QRadioButton("Keep the camera's own dates  (%s)" % (
            timeplan.fmt_span(min(cams), max(cams)) if cams else
            "this camera keeps no clock"), self)
        self.camera.setEnabled(bool(cams))
        self.auto = QRadioButton("Automatic: dated when they came off the camera", self)
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


class NameDialog(Dialog):
    def __init__(self, parent, count, current=""):
        super().__init__("Name", parent)
        self.lay.addWidget(QLabel("A name for %s, such as \"Grandma's birthday\":"
                                  % ("this shot" if count == 1 else "these %d shots" % count),
                                  self))
        self.edit = QLineEdit(current, self)
        self.edit.setMinimumWidth(340)
        self.lay.addWidget(self.edit)
        self.lay.addWidget(note("It goes into the pictures as their title and "
                                "description, which Google Photos shows. Leave it "
                                "empty to take a name off.", self))
        self.buttons(("OK", "accept"), ("Cancel", "reject"))
        self.edit.selectAll()

    def value(self):
        return self.edit.text().strip()


def parse_coordinates(text):
    """'45.5231, -122.6765' (as Google Maps gives them), or with N/S/E/W:
    (lat, lon), or None."""
    t = text.strip().replace("°", " ")
    nums = re.findall(r"[-+]?\d+(?:\.\d+)?\s*[NSEWnsew]?", t)
    if len(nums) != 2:
        return None
    out = []
    for part in nums:
        part = part.strip()
        sign = -1 if part[-1:] in "SsWw" else 1
        value = float(part.rstrip("NSEWnsew").strip())
        out.append(value * sign)
    lat, lon = out
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


class PlaceDialog(Dialog):
    def __init__(self, parent, settings, count, current=None):
        super().__init__("Place", parent)
        self.settings = settings
        self.lay.addWidget(QLabel("Where %s taken?" % ("was this shot" if count == 1
                                                         else "were these %d shots" % count), self))
        self.group = QButtonGroup(self)
        self.choices = []
        for name, lat, lon in settings.places():
            b = QRadioButton("%s   (%.4f, %.4f)" % (name, lat, lon), self)
            self.group.addButton(b)
            self.lay.addWidget(b)
            self.choices.append((b, (name, lat, lon)))
            if current and current[0] == name:
                b.setChecked(True)
        self.new = QRadioButton("A new place:", self)
        self.group.addButton(self.new)
        self.lay.addWidget(self.new)
        grid = QVBoxLayout()
        grid.setContentsMargins(22, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(QLabel("Name:", self))
        self.name = QLineEdit(self)
        self.name.setPlaceholderText("Home")
        row.addWidget(self.name, 1)
        grid.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Latitude, longitude:", self))
        self.coords = QLineEdit(self)
        self.coords.setPlaceholderText("45.5231, -122.6765")
        row.addWidget(self.coords, 1)
        grid.addLayout(row)
        grid.addWidget(note("In Google Maps, right-click the spot: the first line "
                            "of the menu is its latitude and longitude, and clicking "
                            "it copies them.", self))
        self.lay.addLayout(grid)
        self.none = QRadioButton("No place", self)
        self.group.addButton(self.none)
        self.lay.addWidget(self.none)
        for w in (self.name, self.coords):
            w.textEdited.connect(lambda _: self.new.setChecked(True))
        if self.group.checkedButton() is None:
            (self.choices[0][0] if self.choices and not current else self.new).setChecked(True)
        self.buttons(("OK", "accept"), ("Cancel", "reject"))

    def accept(self):
        if self.new.isChecked():
            where = parse_coordinates(self.coords.text())
            if not self.name.text().strip() or where is None:
                message(self, "Place", "Give the new place a name, and its latitude "
                        "and longitude as two numbers, such as 45.5231, -122.6765.",
                        "warning")
                return
            self.settings.add_place(self.name.text().strip(), *where)
            self.settings.save()
        super().accept()

    def value(self):
        """(name, lat, lon), or None for no place."""
        if self.none.isChecked():
            return None
        if self.new.isChecked():
            lat, lon = parse_coordinates(self.coords.text())
            return (self.name.text().strip(), lat, lon)
        for b, place in self.choices:
            if b.isChecked():
                return place
        return None


def plausible(c0, c1, now=None):
    """Whether a session's camera dates look like a clock that was set: not
    before 2010 (where these cameras reset to), not in the future, and not
    the stroke of midnight or noon on New Year's Day."""
    if c0 is None:
        return False
    now = now or datetime.datetime.now()
    if c0.year < 2010 or c1 > now + datetime.timedelta(days=1):
        return False
    if c0.month == 1 and c0.day == 1 and c0.hour in (0, 12) and c0.minute < 10:
        return False
    return True


class TrustDialog(Dialog):
    """Which sessions from a camera whose clock can be right to date by it."""

    def __init__(self, parent, camera, sessions, now=None):
        super().__init__("Trust the camera's clock?", parent)
        row = QHBoxLayout()
        row.setSpacing(14)
        icon = QLabel(self)
        pm = QPixmap.fromImage(sprite("clock-icon"))
        pm.setDevicePixelRatio(2.0)
        icon.setPixmap(pm)
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        row.addWidget(icon)
        col = QVBoxLayout()
        head = QLabel("%s's clock can be right. Date these by it?" % camera, self)
        head.setFont(ui_font(9, bold=True))
        col.addWidget(head)
        col.addWidget(note("Ticked sessions keep the dates the camera gave them. The "
                           "rest are dated from when they came off the camera, as "
                           "usual.", self))
        self.boxes = []
        for sess in sessions:
            c0, c1 = sess.camera_range()
            ok = plausible(c0, c1, now)
            from digicarlo.photoboard import span_line
            text = "Session %d: %s, %s" % (
                sess.number, span_line(c0, c1, 0) if c0 else "no clock",
                "looks right" if ok else "the clock was reset")
            b = QCheckBox(text, self)
            b.setChecked(ok)
            b.setEnabled(c0 is not None)
            col.addWidget(b)
            self.boxes.append((b, sess))
        self.again = QCheckBox("Ask about this camera's clock every time", self)
        self.again.setChecked(True)
        col.addSpacing(6)
        col.addWidget(self.again)
        row.addLayout(col, 1)
        self.lay.addLayout(row)
        self.buttons(("OK", "accept"), ("Cancel", "reject"))

    def trusted(self):
        return {s.key for b, sess in self.boxes if b.isChecked() for s in sess.shots}


# ---------------------------------------------------------------------------
# Pictures
# ---------------------------------------------------------------------------

class Canvas(QWidget):
    """A picture, fitted and centred, sunken like a Win95 well. Reports
    clicks in the picture's own pixels."""

    clicked = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = QImage()
        self.quarters = 0
        self.marks = []                 # (x, y, w, h) circled
        self.caption = ""
        self.setMinimumSize(640, 440)

    def set_image(self, image, quarters=0, marks=(), caption=""):
        self.image, self.quarters, self.marks, self.caption = image, quarters, list(marks), caption
        self.update()

    def _placement(self):
        """(transform from picture pixels to the widget, drawn size)."""
        r = self.rect().adjusted(4, 4, -4, -4)
        w, h = self.image.width(), self.image.height()
        tw, th = (h, w) if self.quarters % 2 else (w, h)
        k = min(r.width() / tw, r.height() / th) if tw and th else 1
        t = QTransform()
        t.translate(r.center().x(), r.center().y())
        t.scale(k, k)
        t.rotate(90 * self.quarters)
        t.translate(-w / 2, -h / 2)
        return t

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#404040"))
        bevel(p, self.rect(), "sunken")
        if self.image.isNull():
            p.setPen(QColor("#E0E0E0"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.caption or "No picture")
            return
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._placement()
        p.setTransform(t)
        p.drawImage(0, 0, self.image)
        pen = QPen(QColor(90, 255, 120), 2.5)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for x, y, w, h in self.marks:
            p.drawEllipse(QRectF(x, y, w, h))

    def mousePressEvent(self, e):
        if self.image.isNull() or e.button() != Qt.MouseButton.LeftButton:
            return
        inv, ok = self._placement().inverted()
        if ok:
            pt = inv.map(e.position())
            if 0 <= pt.x() < self.image.width() and 0 <= pt.y() < self.image.height():
                self.clicked.emit(pt.x(), pt.y())


class Viewer(Dialog):
    """entries: [(caption, path, kind, quarters)], shown one at a time."""

    def __init__(self, parent, entries, start=0, loader=None):
        super().__init__("View", parent)
        self.entries, self.i, self.loader = entries, start, loader
        self.canvas = Canvas(self)
        self.canvas.setMinimumSize(760, 540)
        self.lay.addWidget(self.canvas, 1)
        row = QHBoxLayout()
        self.prev = QPushButton("< Previous", self)
        self.next = QPushButton("Next >", self)
        self.open = QPushButton("Open", self)
        self.label = QLabel(self)
        for b in (self.prev, self.next):
            b.setMinimumWidth(90)
        row.addWidget(self.prev)
        row.addWidget(self.next)
        row.addSpacing(12)
        row.addWidget(self.label, 1)
        row.addWidget(self.open)
        close = QPushButton("Close", self)
        close.clicked.connect(self.accept)
        row.addWidget(close)
        self.lay.addLayout(row)
        self.prev.clicked.connect(lambda: self.show_entry(self.i - 1))
        self.next.clicked.connect(lambda: self.show_entry(self.i + 1))
        self.open.clicked.connect(self._open)
        self.show_entry(start)

    def show_entry(self, i):
        self.i = max(0, min(len(self.entries) - 1, i))
        caption, path, kind, quarters = self.entries[self.i]
        img = self.loader(path, kind) if self.loader else QImage(path)
        self.canvas.set_image(img, quarters, caption="Cannot show this one")
        self.label.setText("%s   (%d of %d)" % (caption, self.i + 1, len(self.entries)))
        self.prev.setEnabled(self.i > 0)
        self.next.setEnabled(self.i < len(self.entries) - 1)
        self.open.setText("Play" if kind in ("video", media.SIPIX_CLIP) else "Open")

    def _open(self):
        path = self.entries[self.i][1]
        if os.path.exists(path):
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Left:
            self.show_entry(self.i - 1)
        elif e.key() == Qt.Key.Key_Right:
            self.show_entry(self.i + 1)
        else:
            super().keyPressEvent(e)


class RedEyeDialog(Dialog):
    """photos: [{"key", "caption", "path", "boxes"}]: each photo's fixes,
    as found (or as kept before). Click a circled eye to leave it be; click
    a red eye that was missed to fix it."""

    def __init__(self, parent, photos):
        super().__init__("Red-eye pen", parent)
        from PIL import Image
        from digicarlo import redeye
        self.Image, self.redeye = Image, redeye
        self.photos = photos
        self.boxes = {ph["key"]: list(ph["boxes"]) for ph in photos}
        self.i = 0
        self.before = False
        self._pil = {}
        self.canvas = Canvas(self)
        self.canvas.setMinimumSize(760, 540)
        self.canvas.clicked.connect(self._clicked)
        self.lay.addWidget(self.canvas, 1)
        self.help = note("", self)
        self.lay.addWidget(self.help)
        row = QHBoxLayout()
        self.prev = QPushButton("< Previous", self)
        self.next = QPushButton("Next >", self)
        self.compare = QPushButton("Hold to see before", self)
        self.label = QLabel(self)
        row.addWidget(self.prev)
        row.addWidget(self.next)
        row.addSpacing(12)
        row.addWidget(self.label, 1)
        row.addWidget(self.compare)
        self.lay.addLayout(row)
        self.prev.clicked.connect(lambda: self.show_photo(self.i - 1))
        self.next.clicked.connect(lambda: self.show_photo(self.i + 1))
        self.compare.pressed.connect(lambda: self._before(True))
        self.compare.released.connect(lambda: self._before(False))
        self.buttons(("Fix these", "accept"), ("Cancel", "reject"))
        self.show_photo(0)

    def _original(self, key, path):
        if key not in self._pil:
            with self.Image.open(path) as im:
                self._pil[key] = im.convert("RGB")
        return self._pil[key]

    @staticmethod
    def _qimage(pil):
        data = pil.tobytes("raw", "RGB")
        return QImage(data, pil.width, pil.height, pil.width * 3,
                      QImage.Format.Format_RGB888).copy()

    def show_photo(self, i):
        self.i = max(0, min(len(self.photos) - 1, i))
        ph = self.photos[self.i]
        orig = self._original(ph["key"], ph["path"])
        boxes = self.boxes[ph["key"]]
        shown = orig if self.before else self.redeye.apply_fixes(orig, boxes)[0]
        self.canvas.set_image(self._qimage(shown), 0, [] if self.before else boxes)
        n = len(boxes)
        self.label.setText("%s: %s   (%d of %d)" % (
            ph["caption"], "no eyes fixed" if not n else
            "%d eye%s fixed" % (n, "" if n == 1 else "s"), self.i + 1, len(self.photos)))
        self.help.setText("Green circles are eyes the pen will fix. Click one to "
                          "leave that eye alone; click a red eye it missed to fix it.")
        self.prev.setEnabled(self.i > 0)
        self.next.setEnabled(self.i < len(self.photos) - 1)

    def _before(self, on):
        self.before = on
        self.show_photo(self.i)

    def _clicked(self, x, y):
        ph = self.photos[self.i]
        boxes = self.boxes[ph["key"]]
        for b in boxes:
            bx, by, bw, bh = b
            if bx <= x <= bx + bw and by <= y <= by + bh:
                boxes.remove(b)
                self.show_photo(self.i)
                return
        orig = self._original(ph["key"], ph["path"])
        box = self.redeye.box_at(orig.size, x, y)
        if self.redeye.apply_fixes(orig, [box])[1]:
            boxes.append(box)
            self.show_photo(self.i)
        else:
            self.help.setText("No flash-red pupil there. Click right on the red of "
                              "the eye.")

    def fixes(self):
        """{key: [(x, y, w, h)] or None}"""
        return {k: (b or None) for k, b in self.boxes.items()}
