"""digicarlo-gui: the pre-rendered window.

A Windows 95 window looking into a garage, pre-rendered the way a 1995 CD-ROM
game was, with a console of Nash Metropolitan hardware along the bottom.
Everything in the room that can be clicked does one thing:

    the card in the reader    pull its pictures (its tag says how many are new)
    the SiPix on the bench    pull from the camera
    the Photo Board           choose dates for the shots waiting
    the darkroom door         put the waiting shots in the library
    the crate of originals    open the archive folder
    the car                   honk, and look for cameras again

and a few things that do nothing useful at all: the light over the car
switches off (and on), and so do the car's headlights; the chrome script on
the console knows who it is.

and the console holds what has no place in the room:

    green screen    what is going on; click it for the activity log
    radio keys      CHECK CARD, EJECT, ERASE CARD, SYNC, LIBRARY; the key
                    stays pushed in while the screen shows what it found
    knobs           sound on and off; the activity log
    counter         how many shots are waiting for the library
    START           put them in the library (STOP while a job runs)

The calendar on the wall shows today, which is the date a pull's newest shot
gets; the safelight over the darkroom is on while anything is waiting.
"""

import copy
import datetime
import os
import re
import shutil
import subprocess
import sys
import threading
import time

from PyQt6 import sip
from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QFontMetricsF, QIcon, QPainter
from PyQt6.QtWidgets import (QApplication, QDialog, QFileDialog, QHBoxLayout,
                             QLabel, QMenu, QMenuBar, QWidget)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from digicarlo import (__version__, archive, blinky, cardtools, config,  # noqa: E402
                       develop, edits, sources, syncthing, timeplan, update)
from digicarlo import cartoon as toon                                   # noqa: E402
from digicarlo import win95                                             # noqa: E402
from digicarlo.boardroom import BoardRoom                               # noqa: E402
from digicarlo.dialogs import TrustDialog                               # noqa: E402
from digicarlo.jobs import GuiLog, Job                                  # noqa: E402
from digicarlo.stage import (HANDWRITTEN, PRINTED, TERMINAL, Picture,  # noqa: E402
                             Stage, font)

KEYS = {1: "check", 2: "eject", 3: "erase", 4: "sync", 5: "library"}
SCREEN_COLUMNS = 28
SCREEN_ROWS = 5
PHOSPHOR = QColor(140, 255, 160)


def plural(n, word, words=None):
    return "%d %s" % (n, word if n == 1 else (words or word + "s"))


def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1000 or unit == "TB":
            return ("%.0f %s" if unit in ("B", "KB") else "%.1f %s") % (n, unit)
        n /= 1000.0


def wrap(text, width=SCREEN_COLUMNS):
    """One screen message as lines: the first starts '> ', the rest are
    indented under it."""
    words, lines, line = text.upper().split(), [], "> "
    for w in words:
        if len(line) + len(w) + (0 if line.endswith(" ") else 1) > width \
                and line.strip(" >"):
            lines.append(line.rstrip())
            line = "  "
        line += ("" if line.endswith(" ") else " ") + w
    lines.append(line.rstrip())
    return lines


def screen(*messages):
    lines = []
    for m in messages:
        lines += wrap(m)
    return lines[:SCREEN_ROWS]


def fit(p, families, text, rect, max_px, bold=False):
    """The largest font up to max_px that fits text into rect's width."""
    px = max_px
    while px > 6:
        f = font(families, px, bold)
        if QFontMetricsF(f).horizontalAdvance(text) <= rect.width():
            break
        px -= 2
    p.setFont(font(families, px, bold))


class GarageWindow(win95.Window):
    def __init__(self, settings=None):
        super().__init__("DigiCarlo - The Garage")
        self.settings = settings or config.Settings()
        self.arc = archive.Archive(self.settings.archive)
        self.plan = None
        self.found = []
        self.counts = {}
        self.job = None
        self.scan_job = None
        self.lines = []
        self.signature = None
        self.last_ok = False
        self.key = 0
        self.lit_screen = []            # what the pushed key found, or a note
        self.note_until = 0.0           # when a note with no key pushed goes
        self.progress = None            # (done, total, caption) while busy
        self.caption = ""
        self.cursor_on = True
        self.classic = None
        self.today = datetime.date.today()
        self.room = "garage"            # or "board"
        self.lamp_on = True             # the light over the car
        self.beams = False              # the car's headlights
        self.board_key = 0              # a board key, while it is held down
        self.trust_next = None          # (batch id, camera) to ask about
        self.board = edits.Board(os.path.join(os.path.dirname(self.settings.path),
                                              "board.json"))

        self.lay.addWidget(self._menus())
        self.garage_pic = Picture("garage")
        self.garage_pic.painter = self._paint_room
        self.console = Picture("console")
        self.stage = Stage([self.garage_pic, self.console], self)
        self.stage.live = self._live
        self.stage.tip = self._tip
        self.stage.items = self._items
        self.stage.quiet = {"cork"}
        self.stage.overlays.append(self._paint_screen)
        self.stage.clicked.connect(self._clicked)
        self.stage.double_clicked.connect(self._double_clicked)
        self.stage.context.connect(self._context)
        self.stage.wheeled.connect(self._wheeled)
        self.boardroom = BoardRoom(self)
        self.stage.overlays.append(self.boardroom.paint_hover)
        self.lay.addWidget(self.stage, 1)
        self.lay.addWidget(self._status_bar())
        self._fit_to_screen()

        self.blink = QTimer(self)
        self.blink.setInterval(530)
        self.blink.timeout.connect(self._blink)
        self.blink.start()
        self.poll = QTimer(self)
        self.poll.setInterval(2500)
        self.poll.timeout.connect(self._poll_devices)
        self.poll.start()
        self.later(0, self.startup)

    def _fit_to_screen(self):
        """As big as the pictures were made for, or as the screen allows."""
        chrome = 4 * 2 + 20 + 22 + 22
        want_w, want_h = self.stage.canvas.width() + 8, self.stage.canvas.height() + chrome
        scr = self.screen().availableGeometry() if self.screen() else None
        if scr is not None:
            k = min(1.0, (scr.width() - 16) / want_w, (scr.height() - 16) / want_h)
            want_w, want_h = int(want_w * k), int(want_h * k)
        self.resize(want_w, want_h)
        self.setMinimumSize(640, 440)

    def later(self, ms, fn):
        t = QTimer(self)
        t.setSingleShot(True)

        def fire():
            if not sip.isdeleted(self) and not sip.isdeleted(self.st_lib):
                fn()
        t.timeout.connect(fire)
        t.timeout.connect(t.deleteLater)
        t.start(ms)

    # -- construction ------------------------------------------------------------

    def _menus(self):
        bar = QMenuBar(self)
        bar.setFont(win95.ui_font(9))
        f = bar.addMenu("&File")
        self._act(f, "Pull from a &folder...", self.pull_folder)
        self._act(f, "&Look for cameras again", self.honk, "F5")
        f.addSeparator()
        self._act(f, "F&olders...", self.choose_folders)
        self._act(f, "Open the &library folder", lambda: self._open(self.settings.library))
        self._act(f, "Open the &archive folder", lambda: self._open(self.settings.archive))
        f.addSeparator()
        self._act(f, "&Close", self.close, "Ctrl+Q")
        g = bar.addMenu("&Garage")
        self._act(g, "&Check card", lambda: self.push_key(1))
        self._act(g, "&Eject card", lambda: self.push_key(2))
        self._act(g, "E&rase card...", lambda: self.push_key(3))
        self._act(g, "&Sync", lambda: self.push_key(4))
        self._act(g, "Li&brary", lambda: self.push_key(5))
        g.addSeparator()
        self._act(g, "&Photo Board", lambda: self.go("board"), "Ctrl+B")
        self._act(g, "Back to the &garage", lambda: self.go("garage"), "Ctrl+G")
        self._act(g, "&Put in library", self.develop, "Ctrl+Return")
        s = bar.addMenu("&Shots")
        br = self.boardroom_do
        self._act(s, "Select &all", lambda: br("select_all"), "Ctrl+A")
        self._act(s, "Pick &none", lambda: br("clear"), "Esc")
        s.addSeparator()
        self._act(s, "Set a &date...", lambda: br("stamp"), "Ctrl+D")
        self._act(s, "Keep the &camera's date", lambda: br("clock"))
        self._act(s, "A&utomatic date", lambda: br("eraser"))
        s.addSeparator()
        self._act(s, "&View", lambda: br("view"), "Space")
        self._act(s, "Rotate &right", lambda: br("rotate", 1), "Ctrl+R")
        self._act(s, "Rotate &left", lambda: br("rotate", 3), "Ctrl+Shift+R")
        self._act(s, "&Name...", lambda: br("name"), "Ctrl+N")
        self._act(s, "&Place...", lambda: br("place"), "Ctrl+P")
        self._act(s, "Red &eye...", lambda: br("pen"), "Ctrl+E")
        s.addSeparator()
        self._act(s, "&Leave out", lambda: br("wastebasket"), "Del")
        self._act(s, "&Bring back left-out shots", self.bring_back)
        self._act(s, "&Undo", lambda: br("undo"), "Ctrl+Z")
        s.addSeparator()
        self._act(s, "Next pa&ge", lambda: br("turn_page", 1), "PgDown")
        self._act(s, "Previous pag&e", lambda: br("turn_page", -1), "PgUp")
        v = bar.addMenu("&View")
        self.sound_action = self._act(v, "&Sounds", self._toggle_sounds)
        self.sound_action.setCheckable(True)
        self.sound_action.setChecked(self.settings.sounds)
        self._act(v, "&Classic window", self.open_classic)
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
        row.setContentsMargins(0, 2, 0, 0)
        row.setSpacing(2)
        self.st_lib = win95.StatusPanel("", w)
        self.st_lib.clicked.connect(self.choose_folders)
        self.st_arc = win95.StatusPanel("", w)
        self.st_arc.clicked.connect(self.choose_folders)
        self.st_count = win95.StatusPanel("", w)
        self.st_count.setFixedWidth(170)
        row.addWidget(self.st_lib, 1)
        row.addWidget(self.st_arc, 1)
        row.addWidget(self.st_count)
        row.addWidget(win95.SizeGrip(w), 0, Qt.AlignmentFlag.AlignBottom)
        w.setFixedHeight(22)
        return w

    def closeEvent(self, e):
        if self.busy():
            if not win95.message(self, "DigiCarlo", "DigiCarlo is still working. "
                                 "Stop after the current file and close?",
                                 "question", ("Stop and close", "Keep working")):
                e.ignore()
                return
            self.job.cancel.set()
            self.job.wait(30000)
        if self.scan_job is not None:
            self.scan_job.wait(10000)
        self.boardroom.stop()
        super().closeEvent(e)

    # -- what is where ---------------------------------------------------------------

    def cards(self):
        return [s for s in self.found if s.kind == "volume"]

    def cameras(self):
        return [s for s in self.found if s.kind in ("sipix", "ptp")]

    def waiting(self):
        return len(self.plan.shots) if self.plan else 0

    def busy(self):
        return self.job is not None and self.job.isRunning()

    def show_state(self):
        """Switch the pictures' pieces to match what is plugged in and
        waiting, and say so."""
        n = self.waiting()
        room = [k for k, on in (("card", bool(self.cards())),
                                ("blink", bool(self.cameras())),
                                ("safelight", n > 0),
                                ("beams", self.beams)) if on]
        if not self.lamp_on:
            room = ["dark"] + ["dark-" + k for k in room]
        self.garage_pic.set_pieces(room)
        self.garage_pic.invalidate()          # the tag, sticky and calendar change
        self.boardroom.pic.set_pieces(["trash"] if self.arc.skipped else [])
        console = []
        if self.room == "board":
            console.append("board-key%d" % self.board_key if self.board_key else "board-dial")
        elif self.key:
            console.append("key%d" % self.key)
        if self.busy():
            console.append("stop")
        elif n:
            console.append("start")
        digits = "%04d" % min(n, 9999)
        console += ["drum%d-%s" % (i, d) for i, d in enumerate(digits)]
        self.console.set_pieces(console)
        self.st_lib.setText("Library: %s" % self._pretty(self.settings.library))
        self.st_arc.setText("Archive: %s" % self._pretty(self.settings.archive))
        left = len(self.arc.skipped)
        self.st_count.setText("%d waiting%s" % (n, ", %d left out" % left if left else ""))
        self.stage.update()

    @staticmethod
    def _pretty(path):
        home = os.path.expanduser("~")
        return "~" + path[len(home):] if path.startswith(home + os.sep) else path

    # -- the screen --------------------------------------------------------------------

    def screen_lines(self):
        if self.busy() and self.progress is not None:
            done, total, caption = self.progress
            lines = wrap(self.caption)[:2]
            if caption:
                lines.append("  " + caption.upper()[:SCREEN_COLUMNS - 2])
            if total:
                width = SCREEN_COLUMNS - 9
                filled = int(width * done / total)
                lines.append("  [%s%s] %3d%%" % ("#" * filled, "." * (width - filled),
                                                 int(100 * done / total)))
            return lines[:SCREEN_ROWS]
        if self.busy():
            return screen(self.caption)
        if self.lit_screen and (self.key or time.monotonic() < self.note_until):
            return self.lit_screen
        if self.room == "board":
            return screen(*self.boardroom.screen())
        return self.idle_screen()

    def idle_screen(self):
        n = self.waiting()
        msgs = []
        cards, cams = self.cards(), self.cameras()
        for src in cards[:1] + cams[:1]:
            c = self.counts.get(src.ident)
            if c is None:
                msgs.append("%s: ready." % src.label)
            else:
                msgs.append("%s: %s." % (src.label, "%d new" % c[1] if c[1] else "nothing new"))
        if n:
            msgs += ["%s waiting." % plural(n, "shot"), "START puts them in the library."]
        elif cards or cams:
            msgs.append("Click one to pull.")
        else:
            msgs += ["All clear.", "Put a card in the reader or plug in a camera."]
        return screen(*msgs)

    def say(self, *messages):
        """Show what the pushed key found; with no key pushed, a note that
        gives way to the usual screen after a while."""
        self.lit_screen = screen(*[m for m in messages if m])
        self.note_until = time.monotonic() + 8
        self.stage.update()

    def quiet_note(self):
        """Let the usual screen back now (the picks changed)."""
        if not self.key:
            self.note_until = 0.0

    def _blink(self):
        self.cursor_on = not self.cursor_on
        if datetime.date.today() != self.today:
            self.today = datetime.date.today()
            self.garage_pic.invalidate()
        self.stage.update()

    def _paint_screen(self, p, stage):
        t, rect = self.console.surface("screen")
        p.setTransform(t * stage.picture_transform(self.console))
        p.setClipRect(rect)
        lines = self.screen_lines()
        if self.cursor_on and lines:
            lines = lines[:-1] + [lines[-1] + "_"]
        f = font(TERMINAL, 38)
        m = QFontMetricsF(f)
        px = 38 * min(1.0, (rect.width() - 56) / max(1, m.horizontalAdvance("M" * SCREEN_COLUMNS)))
        f = font(TERMINAL, px)
        p.setFont(f)
        step = rect.height() / (SCREEN_ROWS + 0.6)
        glow = QColor(PHOSPHOR)
        glow.setAlpha(46)
        for i, line in enumerate(lines):
            box = QRectF(28, 16 + i * step, rect.width() - 40, step)
            p.setPen(glow)
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-1.4, -1.4), (1.4, 1.4)):
                p.drawText(box.translated(dx, dy), Qt.AlignmentFlag.AlignVCenter, line)
            p.setPen(PHOSPHOR)
            p.drawText(box, Qt.AlignmentFlag.AlignVCenter, line)
        y = 0.0
        while y < rect.height():
            p.fillRect(QRectF(0, y, rect.width(), 1.4), QColor(0, 0, 0, 60))
            y += 4

    # -- what the program writes in the room ----------------------------------------------

    def _paint_room(self, p, pic):
        today = datetime.date.today()
        ink = QColor(40, 30, 22)
        red = QColor(200, 40, 32)

        def on(surface):
            t, r = pic.surface(surface)
            p.save()
            p.setTransform(t)
            return r

        r = on("calendar")
        # white lettering is painted, not inked, so it has to dim itself
        p.setPen(QColor(255, 250, 240) if self.lamp_on else QColor(112, 100, 92))
        fit(p, PRINTED, today.strftime("%B").upper(), QRectF(0, 0, 360, 120), 52)
        p.drawText(QRectF(0, 0, 400, 120), Qt.AlignmentFlag.AlignCenter,
                   today.strftime("%B").upper())
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        p.setPen(ink)
        p.setFont(font(PRINTED, 250))
        p.drawText(QRectF(0, 150, 400, 290), Qt.AlignmentFlag.AlignCenter, str(today.day))
        p.setPen(red)
        fit(p, PRINTED, today.strftime("%A").upper(), QRectF(0, 0, 340, 80), 46)
        p.drawText(QRectF(0, 445, 400, 90), Qt.AlignmentFlag.AlignCenter,
                   today.strftime("%A").upper())
        p.restore()

        n = self.waiting()
        on("sticky")
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        p.setPen(QColor(40, 40, 50))
        if n:
            p.setFont(font(HANDWRITTEN, 96, bold=True))
            p.drawText(QRectF(0, 40, 300, 140), Qt.AlignmentFlag.AlignCenter, str(n))
            p.setPen(QColor(192, 57, 43))
            p.setFont(font(HANDWRITTEN, 52, bold=True))
            p.drawText(QRectF(0, 170, 300, 100), Qt.AlignmentFlag.AlignCenter, "waiting!")
        else:
            p.setFont(font(HANDWRITTEN, 60, bold=True))
            p.drawText(QRectF(10, 40, 280, 220), Qt.AlignmentFlag.AlignCenter |
                       Qt.TextFlag.TextWordWrap, "all clear!")
        p.restore()

        cards = self.cards()
        if "card" in pic.on and cards:
            src = cards[0]
            on("card")
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
            p.setPen(QColor(216, 50, 42))
            name = src.label.upper()
            fit(p, PRINTED, name, QRectF(0, 0, 176, 60), 50)
            p.drawText(QRectF(20, 118, 200, 100), Qt.AlignmentFlag.AlignCenter, name)
            size = re.search(r"([\d.]+ [KMGT]?B)", src.detail or "")
            if size:
                p.setPen(QColor(30, 64, 132))
                p.setFont(font(PRINTED, 34))
                p.drawText(QRectF(20, 210, 200, 70), Qt.AlignmentFlag.AlignCenter,
                           size.group(1).replace(".0 ", " ").replace(" ", ""))
            p.restore()
            on("tag")
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
            p.setPen(QColor(40, 30, 20))
            c = self.counts.get(src.ident)
            text = "pull me!" if c is None else ("%d new!" % c[1] if c[1] else "all in!")
            fit(p, HANDWRITTEN, text, QRectF(0, 0, 270, 100), 64, bold=True)
            p.drawText(QRectF(62, 10, 290, 140), Qt.AlignmentFlag.AlignCenter, text)
            p.restore()

    # -- the mouse -------------------------------------------------------------------------

    def _items(self, pic, x, y):
        if pic == "board":
            return self.boardroom.hit(x, y)
        return None

    def _live(self, pic, spot):
        if pic == "board":
            return self.boardroom.live(spot)
        if pic == "garage":
            if spot == "card":
                return bool(self.cards())
            if spot == "blink":
                return bool(self.cameras())
            if spot == "door":
                return self.waiting() > 0 and not self.busy()
            if spot == "car":
                return not self.busy()
            return True
        if spot == "start":
            return self.busy() or self.waiting() > 0
        return spot != "counter"

    def _tip(self, pic, spot):
        n = self.waiting()
        if pic == "board":
            return self.boardroom.tip(spot)
        if pic == "console" and self.room == "board":
            tip = {"key1": "View: see the picked shots big",
                   "key2": "Rotate: turn the picked shots a quarter to the right",
                   "key3": "Name: give the picked shots a title",
                   "key4": "Place: say where the picked shots were taken",
                   "key5": "Undo: take back the last change",
                   "knob-left": "Previous page", "knob-right": "Next page"}.get(spot)
            if tip:
                return tip
        if pic == "garage":
            if spot == "card":
                src = self.cards()[0]
                c = self.counts.get(src.ident)
                if c is None:
                    return "Pull the pictures from %s" % src.label
                if not c[1]:
                    return "%s: everything on it is already in the archive" % src.label
                return "Pull %s from %s" % (plural(c[1], "new picture"), src.label)
            if spot == "blink":
                return "Pull from %s" % self.cameras()[0].label
            return {"door": "Darkroom: put %s in the library" % plural(n, "shot"),
                    "board": "Photo Board: choose dates for the shots waiting",
                    "crate": "Originals: open the archive folder",
                    "car": "Honk: look for cameras again",
                    "lamp": "The light: switch it %s" % ("off" if self.lamp_on else "on"),
                    "headlights": "Headlights: %s" % ("off" if self.beams else "on")
                    }.get(spot, "")
        return {"key1": "Check card: read every file, to see the card is sound",
                "key2": "Eject: make the card safe to pull out",
                "key3": "Erase card: empty it for next time, once all of it is archived",
                "key4": "Sync: how the library is getting to the phone",
                "key5": "Library: open the library folder",
                "knob-left": "Sound: %s" % ("on" if self.settings.sounds else "off"),
                "knob-right": "Activity log",
                "screen": "Activity log",
                "badge": "DigiCarlo",
                "start": "Stop after this file" if self.busy() else
                         "Put %s in the library" % plural(n, "shot")}.get(spot, "")

    def _clicked(self, pic, spot):
        if pic == "board":
            self.boardroom.clicked(spot)
            return
        if pic == "console" and self.room == "board" and spot.startswith("knob"):
            self.boardroom.turn_page(-1 if spot == "knob-left" else 1)
            return
        if pic == "garage":
            {"card": lambda: self.pull_from(self.cards()),
             "blink": lambda: self.pull_from(self.cameras()),
             "door": self.develop,
             "board": lambda: self.go("board"),
             "crate": lambda: self._open(self.settings.archive),
             "car": self.honk,
             "lamp": self.flip_lamp,
             "headlights": self.flip_headlights}[spot]()
            return
        if spot.startswith("key"):
            self.push_key(int(spot[3:]))
        elif spot == "start":
            if self.busy():
                self.stop_job()
            else:
                self.develop()
        elif spot == "knob-left":
            self.sound_action.setChecked(not self.settings.sounds)
            self._toggle_sounds(not self.settings.sounds)
        elif spot in ("knob-right", "screen"):
            self.show_log()
        elif spot == "badge":
            self.credits()

    def _double_clicked(self, pic, spot):
        if pic == "board":
            self.boardroom.double_clicked(spot)

    def _context(self, pic, spot, where):
        if pic == "board":
            self.boardroom.context_menu(spot, where)

    def _wheeled(self, pic, step):
        if pic == "board":
            self.boardroom.turn_page(step)

    # -- walking between rooms ---------------------------------------------------------

    def go(self, room):
        if room == self.room:
            return
        self.room = room
        self.key, self.board_key, self.lit_screen = 0, 0, []
        self.stage.set_picture(0, self.boardroom.pic if room == "board" else self.garage_pic)
        self.set_title("DigiCarlo - Photo Board" if room == "board" else "DigiCarlo - The Garage")
        if room == "board":
            self.boardroom.relayout()
        self.show_state()

    def boardroom_do(self, name, *args):
        """A Shots menu command: done at the board."""
        self.go("board")
        getattr(self.boardroom, name)(*args)

    def bring_back(self):
        self.go("board")
        self.boardroom.selected.clear()
        self.boardroom.wastebasket()

    @staticmethod
    def today_now():
        return datetime.datetime.now().replace(second=0, microsecond=0)

    # -- startup and scanning --------------------------------------------------------------

    def startup(self):
        if not os.path.exists(self.settings.path):
            self.choose_folders(first_run=True)
        self.replan()
        self.rescan()

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
        if self.signature is not None and sig != self.signature and not self.busy():
            self.later(1500, self.rescan)
        self.signature = sig

    # -- for fun ---------------------------------------------------------------------

    def flip_lamp(self):
        self.lamp_on = not self.lamp_on
        if self.settings.sounds:
            toon.play("click")
        self.say("Lights on." if self.lamp_on else "Lights out.",
                 "" if self.lamp_on else "The darkroom is always this dark.")
        self.show_state()

    def flip_headlights(self):
        self.beams = not self.beams
        if self.settings.sounds:
            toon.play("click")
        self.show_state()

    def credits(self):
        if self.settings.sounds:
            toon.play("jingle")
        self.say("DigiCarlo %s." % __version__,
                 "Built in a garage in 1995, or near enough.",
                 "Keep your clocks wrong.")

    def honk(self):
        if self.settings.sounds:
            toon.play("honk")
        self.rescan()

    def rescan(self):
        if (self.scan_job is not None and self.scan_job.isRunning()) or self.busy():
            return
        self.signature = self._device_signature()
        arc_root = self.settings.archive

        def work(job, log):
            found = sources.find_sources(log)
            arc = archive.Archive(arc_root)
            counts = {}
            for src in found:
                try:
                    c = sources.count_new(src, arc)
                except OSError:
                    c = None
                if c is not None:
                    counts[src.ident] = c
            return found, counts
        job = Job(work, self)
        job.ok.connect(self._scanned)
        job.failed.connect(lambda msg: self._log("error", msg))
        self.scan_job = job
        job.start()

    def _scanned(self, result):
        self.found, self.counts = result
        self.show_state()

    def replan(self):
        self.arc.reload()
        log = GuiLog(self._log)
        try:
            with self.arc.locked():
                sources.ensure_metadata(self.arc, log)
        except archive.ArchiveBusy:
            pass
        batches = develop.plan_batches(self.arc, log)
        # Forget decisions about shots developed or left out since; keep any
        # about shots this archive does not know (another archive's).
        waiting = {s.key for b in batches for s in b.shots}
        self.board.prune(waiting | {k for k in self.board.keys() if k not in self.arc.files})
        self.plan = timeplan.build(batches, self.board.overrides,
                                   max_gap_days=self.settings.max_gap_days,
                                   spacing=self.settings.session_spacing)
        self.boardroom.relayout()
        self.show_state()

    # -- jobs ----------------------------------------------------------------------------

    def _log(self, level, text):
        self.lines.append("%-5s %s" % (level.upper(), text))

    def run(self, fn, done, caption):
        if self.busy():
            self.say("Busy: %s." % self.caption.rstrip("."))
            return False
        job = Job(fn, self)
        job.line.connect(self._log)
        job.step.connect(self._step)
        job.ok.connect(done)
        job.failed.connect(self._failed)
        job.finished.connect(self._finished)
        self.job = job
        self.last_ok = False
        self.caption = caption
        self.progress = (0, 0, "")
        job.start()
        self.show_state()
        return True

    def stop_job(self):
        if self.busy():
            self.job.cancel.set()
            self.caption = "Stopping after this file"

    def _step(self, done, total, caption):
        self.progress = (done, total, caption)
        self.stage.update()

    def _failed(self, msg):
        self._log("error", msg)
        self.say(msg)
        win95.message(self, "DigiCarlo", msg, "error")

    def _finished(self):
        self.progress = None
        self.replan()
        self.rescan()
        if self.last_ok and self.settings.sounds:
            toon.play("beepbeep")
        if self.trust_next is not None:
            self.later(0, self._ask_trust)

    def _ask_trust(self):
        """After a pull from a camera whose clock can be right: which of its
        sessions to date by it."""
        bid, camera = self.trust_next
        self.trust_next = None
        sessions = [s for s in self.plan.sessions if s.batch.id == bid]
        if not sessions:
            return
        dlg = TrustDialog(self, camera, sessions)
        ok = dlg.exec() == QDialog.DialogCode.Accepted
        if not dlg.again.isChecked():
            keep = [c for c in self.settings.trust_clock_cameras
                    if not config.Settings.asks_about_clock_static(c, camera)]
            self.settings.set("dates", "trust_clock_cameras", ", ".join(keep))
            self.settings.save()
        keys = dlg.trusted() if ok else set()
        if keys:
            self.board.set_dates(keys, "camera")
            self.replan()
            self.say("%s: dated by the camera's clock." % plural(len(keys), "shot"))

    # -- pulling and developing ---------------------------------------------------------------

    def pull_from(self, candidates):
        if len(candidates) == 1:
            self.pull(candidates[0])
            return
        menu = QMenu(self)
        for src in candidates:
            menu.addAction(src.describe(), lambda s=src: self.pull(s))
        menu.exec(self.cursor().pos())

    def pull(self, src):
        arc_root = self.settings.archive

        def work(job, log):
            arc = archive.Archive(arc_root)
            with arc.locked():
                return sources.pull(src, arc, log, progress=job.progress,
                                    cancel=job.cancel)
        self.key, self.lit_screen = 0, []
        self.run(work, lambda res: self._pulled(src, res), "Pulling from %s" % src.label)

    def pull_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Pull from a folder",
                                                os.path.expanduser("~"))
        if path:
            try:
                sources.check_folder(path, self.settings)
            except ValueError as exc:
                win95.message(self, "Pull from a folder", str(exc), "error")
                return
            self.pull(sources.folder_source(path))

    def _pulled(self, src, res):
        new, skipped, failed = len(res.new), len(res.skipped), len(res.failed)
        text = "%d new from %s%s." % (new, res.camera or src.label,
                                      ", %d already imported" % skipped if skipped else "")
        self.lines.append("OUT   " + text)
        self.last_ok = not failed
        if res.new and res.batch and self.settings.asks_about_clock(res.camera or ""):
            self.trust_next = (res.batch["id"], res.camera)
        if failed:
            names = "\n".join("  %s: %s" % f for f in res.failed[:12])
            more = "\n  ...and %d more" % (failed - 12) if failed > 12 else ""
            win95.message(self, "Some files could not be read",
                          "%s\n\n%d file%s could not be read from the camera:\n\n%s%s"
                          "\n\nThe rest are safe in the archive. A card that fails "
                          "like this may be wearing out." % (
                              text, failed, "" if failed == 1 else "s", names, more),
                          "error")

    def develop(self):
        if not self.plan or not self.plan.shots or self.busy():
            return
        n = self.waiting()
        first, last = min(self.plan.times.values()), max(self.plan.times.values())
        if not win95.message(self, "Put in library",
                             "Put %s in %s?\n\nThey will be dated %s. Clips become "
                             "MP4 with their video untouched. The originals stay in "
                             "the archive as they are." % (
                                 plural(n, "shot"), self.settings.library,
                                 timeplan.fmt_span(first, last)),
                             "question", ("Put in library", "Cancel")):
            return
        plan, settings = self.plan, self.settings
        decided = copy.deepcopy(self.board.edits)

        def work(job, log):
            arc = archive.Archive(settings.archive)
            with arc.locked():
                return develop.Developer(arc, settings, log).develop(
                    plan, progress=job.progress, cancel=job.cancel, edits=decided)
        self.key, self.lit_screen = 0, []
        self.run(work, self._developed, "Putting shots in the library")

    def _developed(self, res):
        made = sum(len(p) for _, p in res.made)
        text = "%d file%s now in %s." % (made, "" if made == 1 else "s",
                                         self._pretty(self.settings.library))
        self.lines.append("OUT   " + text)
        self.last_ok = not res.failed
        library = self.settings.library
        # Tell Syncthing now, so the phone does not wait for its next scan.
        threading.Thread(target=self._nudge_syncthing, args=(library,),
                         daemon=True).start()
        if res.failed:
            names = "\n".join("  %s: %s" % f for f in res.failed[:12])
            win95.message(self, "Some shots were not put in the library",
                          "%s\n\nThese failed and are still waiting:\n\n%s" % (text, names),
                          "error")

    def _nudge_syncthing(self, library):
        try:
            if syncthing.rescan(library):
                self.lines.append("INFO  asked Syncthing to rescan the library")
        except syncthing.SyncthingError as exc:
            self.lines.append("INFO  %s" % exc)

    def open_classic(self):
        from digicarlo import gui
        if self.classic is not None and not sip.isdeleted(self.classic) \
                and self.classic.isVisible():
            self.classic.raise_()
            return
        self.classic = gui.MainWindow(self.settings)
        self.classic.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.classic.destroyed.connect(lambda *_: self.later(0, self.replan))
        self.classic.show()

    # -- the radio keys --------------------------------------------------------------------------

    def push_key(self, k):
        if self.room == "board":
            # At the board the keys are pressed and spring back.
            if self.busy():
                self.say("Busy: %s." % self.caption.rstrip("."))
                return
            self.board_key = k
            self.show_state()
            self.stage.repaint()
            self.later(350, self._release_board_key)
            self.boardroom.key(k)
            return
        if self.key == k and not self.busy():
            self.key, self.lit_screen = 0, []          # push it again: it pops out
            self.show_state()
            return
        if self.busy():
            self.say("Busy: %s." % self.caption.rstrip("."))
            return
        self.key, self.lit_screen = k, []
        if self.settings.sounds:
            toon.play("beepbeep")
        getattr(self, "key_" + KEYS[k])()
        self.show_state()

    def _release_board_key(self):
        self.board_key = 0
        self.show_state()

    def _card(self):
        cards = self.cards()
        if not cards:
            self.say("No card in the reader.")
            return None
        return cards[0]

    def key_check(self):
        src = self._card()
        if src is None:
            return

        def work(job, log):
            return cardtools.check(src, log, progress=job.progress, cancel=job.cancel)

        def done(res):
            self.last_ok = not res.failed
            msgs = ["Checked %s, %s." % (plural(res.files, "file"), human(res.bytes))]
            if res.failed:
                msgs.append("%d would not read. Pull what you can, soon." % len(res.failed))
            else:
                msgs.append("All read cleanly.")
            if res.kernel:
                msgs.append("Kernel logged %s." % plural(len(res.kernel), "read error"))
            self.say(*msgs)
        self.run(work, done, "Checking %s" % src.label)

    def key_eject(self):
        src = self._card()
        if src is None:
            return
        self.run(lambda job, log: cardtools.eject(src, log),
                 lambda how: self.say("%s is safe to pull out." % src.label),
                 "Ejecting %s" % src.label)

    def key_erase(self):
        src = self._card()
        if src is None:
            return
        arc_root = self.settings.archive

        def work(job, log):
            arc = archive.Archive(arc_root)
            return cardtools.plan_erase(src, arc, log, progress=job.progress,
                                        cancel=job.cancel)
        self.run(work, lambda plan: self.later(0, lambda: self._erase(src, plan)),
                 "Checking %s against the archive" % src.label)

    def _erase(self, src, plan):
        if not plan.files and not plan.missing:
            self.say("%s has no pictures on it." % src.label)
            return
        if not plan.safe:
            why = []
            if plan.missing:
                why.append("%s not in the archive yet" % plural(len(plan.missing), "file"))
            if plan.damaged:
                why.append("%s whose archive copy no longer matches"
                           % plural(len(plan.damaged), "file"))
            if plan.unreadable:
                why.append("%s that would not read" % plural(len(plan.unreadable), "file"))
            self.say("Not erasing %s:" % src.label, "; ".join(why) + ".",
                     "Pull it first." if plan.missing else "")
            return
        if not win95.message(self, "Erase card",
                             "Erase %s (%s) from %s?\n\nEvery one is in the archive: "
                             "each was read off the card and compared, byte for byte, "
                             "with the archive's copy, read back just now." % (
                                 plural(len(plan.files), "picture and clip",
                                        "pictures and clips"),
                                 human(plan.bytes), src.label),
                             "warning", ("Erase", "Cancel")):
            self.say("Nothing erased.")
            return
        self.run(lambda job, log: cardtools.erase(plan, log, progress=job.progress,
                                                  cancel=job.cancel),
                 lambda res: self.say("Erased %s from %s." % (plural(res.erased, "file"),
                                                              src.label),
                                      "%s skipped." % plural(len(res.changed) + len(res.failed), "file")
                                      if res.changed or res.failed else
                                      "Ready for more pictures."),
                 "Erasing %s" % src.label)

    def key_sync(self):
        library = self.settings.library

        def work(job, log):
            st = syncthing.library_status(library)
            if st is not None:
                syncthing.rescan(library)
            return st

        def done(st):
            if st is None:
                self.say("Syncthing does not share the library folder.")
                return
            msgs = []
            for peer in st.peers[:2]:
                if peer.connected:
                    msgs.append("%s connected." % peer.name)
                elif peer.last_seen:
                    msgs.append("%s last seen %s." % (
                        peer.name, peer.last_seen.strftime("%b %d %H:%M")))
                else:
                    msgs.append("%s not connected." % peer.name)
            msgs.append("%s: %s." % (st.folder, plural(st.files, "file")))
            peer = st.peers[0] if st.peers else None
            if peer is not None and peer.completion is not None:
                if peer.need_items:
                    msgs.append("%d%% on the phone, %d to go." % (int(peer.completion),
                                                                peer.need_items))
                else:
                    msgs.append("100% on the phone.")
            self.say(*msgs)
        self.run(work, done, "Asking Syncthing")

    def key_library(self):
        library = self.settings.library
        self._open(library)

        def work(job, log):
            files = size = 0
            for dirpath, dirs, names in os.walk(library):
                for name in names:
                    try:
                        size += os.path.getsize(os.path.join(dirpath, name))
                        files += 1
                    except OSError:
                        pass
            probe = library
            while probe and not os.path.exists(probe):
                probe = os.path.dirname(probe)
            return files, size, shutil.disk_usage(probe or "/").free
        self.run(work, lambda r: self.say(
            "Library: %s." % self._pretty(library),
            "%s, %s." % (plural(r[0], "file"), human(r[1])),
            "%s free." % human(r[2])), "Looking in the library")

    # -- menus -------------------------------------------------------------------------------

    def _open(self, path):
        if os.path.exists(path):
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)

    def _toggle_sounds(self, on):
        self.settings.set("window", "sounds", "yes" if on else "no")
        self.settings.save()
        if not self.busy():
            self.key = 0
            self.say("Sound %s." % ("on" if on else "off"))
            self.show_state()

    def choose_folders(self, first_run=False):
        dlg = win95.FoldersDialog(self, self.settings, first_run)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            if first_run:
                self.settings.save()
            return
        vals = dlg.values()
        lib, arc = os.path.abspath(vals["library"]), os.path.abspath(vals["archive"])
        if lib == arc or lib.startswith(arc + os.sep) or arc.startswith(lib + os.sep):
            win95.message(self, "Folders", "The library and the archive have to be "
                          "separate folders, neither inside the other.", "error")
            return
        self.settings.set("folders", "library", vals["library"])
        self.settings.set("folders", "archive", vals["archive"])
        self.settings.save()
        self.arc = archive.Archive(self.settings.archive)
        self.replan()

    def show_log(self):
        win95.TextDialog(self, "Activity log",
                         "\n".join(self.lines) or "Nothing has happened yet.").exec()

    def check_updates(self):
        def done(result):
            version, info = result
            if version is None:
                win95.message(self, "Updates", "No releases have been published yet.")
            elif update.newer(version):
                win95.message(self, "Updates", "DigiCarlo %s is available (you have "
                              "%s).\n\nTo install it, run:\n\n    digicarlo update "
                              "--install" % (version, __version__))
            else:
                win95.message(self, "Updates", "DigiCarlo %s is the latest." % __version__)
        self.run(lambda job, log: update.latest(), done, "Checking for updates")

    def about(self):
        dlg = win95.Dialog("About DigiCarlo", self)
        row = QHBoxLayout()
        row.setSpacing(16)
        icon = QLabel()
        pm = toon.icon_pixmap(128)
        pm.setDevicePixelRatio(2.0)
        icon.setPixmap(pm)
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        row.addWidget(icon)
        text = QLabel(
            "<b>DigiCarlo %s</b><br><br>Gets the pictures off old digital cameras, "
            "dated when they came off the camera instead of by its wrong clock, "
            "with the camera's gaps between shots kept.<br><br>The garage is "
            "pre-rendered in POV-Ray, the way a 1995 CD-ROM game was.<br><br>"
            "The SiPix Blink II is driven by Blinky %s.<br><br>"
            "Licensed under the GNU LGPL, version 2.1." % (__version__, blinky.__version__),
            dlg)
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
    app.setPalette(win95.palette())
    app.setFont(win95.ui_font(9))
    themed = QIcon.fromTheme("digicarlo")
    app.setWindowIcon(themed if not themed.isNull() else toon.app_icon())
    win = GarageWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
