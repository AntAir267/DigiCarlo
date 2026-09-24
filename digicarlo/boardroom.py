"""The Photo Board, as the window uses it: picking shots, and what the tools
on the ledge and the radio's keys do to them.

    click a print          pick it (Shift: a run of them, Ctrl: one more)
    click a session card   pick the whole session
    double-click a print   see it big
    date stamp             start the picked shots at a date you give
    alarm clock            keep the camera's own dates
    eraser                 back to automatic: dated when they came off
    wastebasket            leave them out (with nothing picked: bring back
                           the ones left out)
    red-eye pen            take the flash red out of their eyes
    GARAGE sign            back to the garage
    radio keys             VIEW, ROTATE, NAME, PLACE, UNDO
    knobs, wheel, PgUp/Dn  turn the pages

Every decision goes into the window's edits.Board, which keeps it until the
shots are developed; nothing touches the archive except leaving shots out,
which the archive records.
"""

import os

from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtGui import QColor, QPen, QPolygonF
from PyQt6.QtWidgets import QApplication, QDialog, QMenu

from digicarlo import archive, photoboard, timeplan
from digicarlo.dialogs import (DateDialog, NameDialog, PlaceDialog, RedEyeDialog,
                               Viewer, describe_numbers)
from digicarlo.jobs import ThumbLoader, load_picture
from digicarlo.stage import PRINTED, Picture, font
from digicarlo import win95

BOARD_KEYS = {1: "view", 2: "rotate", 3: "name", 4: "place", 5: "undo"}
JPEG = (".jpg", ".jpeg", ".jpe")


class BoardRoom:
    def __init__(self, win):
        self.win = win
        self.pic = Picture("board")
        self.pic.painter = self.paint
        self.pages = [[]]
        self.page = 0
        self.selected = set()
        self.anchor = None
        self.stamp_date = None          # the last date stamped
        self.thumbs = {}
        self.asked = set()
        self.loader = ThumbLoader(win)
        self.loader.loaded.connect(self._thumb_loaded)
        self.loader.start()
        self._redraw = QTimer(win)
        self._redraw.setSingleShot(True)
        self._redraw.setInterval(120)
        self._redraw.timeout.connect(lambda: (self.pic.invalidate(), win.stage.update()))
        cork, rect = self.pic.surface("cork")
        self.cork = cork
        self.uncork, _ = cork.inverted()

    def stop(self):
        self.loader.stop()
        self.loader.wait(2000)

    # -- what is on the board ----------------------------------------------------

    @property
    def plan(self):
        return self.win.plan

    def relayout(self):
        self.pages = photoboard.layout(self.plan)
        self.page = max(0, min(self.page, len(self.pages) - 1))
        waiting = {s.key for s in self.plan.shots} if self.plan else set()
        self.selected &= waiting
        self.pic.set_pieces(["trash"] if self.win.arc.skipped else [])
        self.pic.invalidate()
        self._want_thumbs()

    def items(self):
        return self.pages[self.page] if self.pages else []

    def item(self, name):
        for it in self.items():
            if it.name == name:
                return it
        return None

    def picked(self):
        return [s for s in self.plan.shots if s.key in self.selected] if self.plan else []

    def turn_page(self, step):
        n = len(self.pages)
        if n > 1:
            self.page = (self.page + step) % n
            self.pic.invalidate()
            self._want_thumbs()
            self.win.stage.update()

    # -- thumbnails ------------------------------------------------------------------

    def _want_thumbs(self):
        want = [it for p in (self.page, self.page + 1) if p < len(self.pages)
                for it in self.pages[p] if it.kind == "shot"]
        for it in reversed(want):        # the loader takes the newest first
            key = it.shot.key
            if key in self.thumbs or key in self.asked:
                continue
            rec = self.win.arc.files.get(key)
            if rec:
                self.asked.add(key)
                self.loader.request(key, self.win.arc.abspath(rec["path"]), rec.get("kind"))

    def _thumb_loaded(self, key, img):
        self.thumbs[key] = img
        self._redraw.start()

    # -- drawing ---------------------------------------------------------------------

    class _Context:
        pass

    def paint(self, p, pic):
        ctx = self._Context()
        ctx.selected = self.selected
        ctx.edits = self.win.board.edits
        ctx.thumb = self.thumbs.get
        ctx.record = lambda key: self.win.arc.files.get(key, {})
        ctx.plan = self.plan
        ctx.many_batches = bool(self.plan) and len(self.plan.batches) > 1
        p.save()
        photoboard.paint_board(p, self.cork, self.items(), ctx, self.page, len(self.pages))
        p.restore()
        # the stamp's rubber shows the date it will stamp
        t, r = pic.surface("stamp")
        p.save()
        p.setTransform(t)
        p.setPen(QColor(255, 214, 60))
        p.setFont(font(PRINTED, 60))
        when = self.stamp_date or self.win.today_now()
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, when.strftime("%b %d").upper().replace(" 0", " "))
        p.restore()

    def paint_hover(self, p, stage):
        hot = stage.hot
        if self.win.room != "board" or hot is None or hot[0] is not self.pic:
            return
        it = self.item(hot[1])
        if it is None:
            return
        poly = photoboard.outline(it)
        to_widget = self.cork * stage.picture_transform(self.pic)
        p.setTransform(to_widget)
        pen = QPen(QColor(255, 226, 110, 200), 2.2)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolygon(QPolygonF(poly))

    # -- the mouse ---------------------------------------------------------------------

    def hit(self, x, y):
        pt = self.uncork.map(QPointF(x, y))
        name = photoboard.hit(self.items(), pt, len(self.pages))
        if name is None and 0 <= pt.x() <= 1272 and 0 <= pt.y() <= 436:
            return "cork"
        return name

    def live(self, spot):
        if spot in ("stamp", "clock", "eraser", "pen"):
            return bool(self.selected)
        if spot == "bin":
            return bool(self.selected) or bool(self.win.arc.skipped)
        return True

    def tip(self, spot):
        n = len(self.selected)
        what = "the picked shot" if n == 1 else "the %d picked shots" % n
        if spot.startswith("shot:"):
            key = spot[5:]
            shot = next((s for s in self.plan.shots if s.key == key), None)
            if shot is None:
                return ""
            rec = self.win.arc.files.get(key, {})
            lines = ["Shot %d: %s" % (shot.number, rec.get("orig", shot.label)),
                     "Camera's clock: %s" % timeplan.fmt(shot.camera_time),
                     "Will be dated: %s" % timeplan.fmt(self.plan.times[key])]
            e = self.win.board.edits.get(key)
            if e is not None:
                if e.title:
                    lines.append("Named: %s" % e.title)
                if e.place:
                    lines.append("Place: %s" % e.place[0])
                if e.redeye:
                    lines.append("Red eye: %d fixed" % len(e.redeye))
            return "\n".join(lines)
        if spot.startswith("card:"):
            it = self.item(spot)
            return "Session %d: click to pick all its shots" % it.session.number if it else ""
        return {"note:page": "Turn to the next page",
                "stamp": "Date stamp: start %s at a date you give" % what,
                "clock": "Alarm clock: keep the camera's own dates for %s" % what,
                "eraser": "Eraser: back to automatic dates for %s" % what,
                "bin": "Wastebasket: leave %s out of the library" % what if n else
                       "Wastebasket: bring back the shots left out",
                "pen": "Red-eye pen: take the flash red out of %s" % what,
                "garage": "Back to the garage"}.get(spot, "")

    def clicked(self, spot):
        mods = QApplication.keyboardModifiers()
        if spot.startswith("shot:"):
            self._pick(spot[5:], mods)
        elif spot.startswith("card:"):
            it = self.item(spot)
            if it is not None:
                keys = {s.key for s in it.session.shots}
                if mods & Qt.KeyboardModifier.ControlModifier:
                    self.selected ^= keys if keys <= self.selected else keys - self.selected
                else:
                    self.selected = set(keys)
        elif spot == "note:page":
            self.turn_page(1)
            return
        elif spot == "cork":
            self.selected.clear()
        else:
            {"stamp": self.stamp, "clock": self.clock, "eraser": self.eraser,
             "bin": self.wastebasket, "pen": self.pen,
             "garage": lambda: self.win.go("garage")}[spot]()
            return
        self.pic.invalidate()
        self.win.quiet_note()
        self.win.show_state()

    def _pick(self, key, mods):
        if mods & Qt.KeyboardModifier.ShiftModifier and self.anchor:
            order = [s.key for s in self.plan.shots]
            if self.anchor in order and key in order:
                a, b = sorted((order.index(self.anchor), order.index(key)))
                self.selected |= set(order[a:b + 1])
                return
        if mods & Qt.KeyboardModifier.ControlModifier:
            self.selected ^= {key}
        else:
            self.selected = {key}
        self.anchor = key

    def double_clicked(self, spot):
        if spot.startswith("shot:"):
            self.selected = {spot[5:]}
            self.pic.invalidate()
            self.win.show_state()
            self.view()

    def select_all(self):
        self.selected = {s.key for s in self.plan.shots} if self.plan else set()
        self.pic.invalidate()
        self.win.quiet_note()
        self.win.show_state()

    def clear(self):
        self.selected.clear()
        self.pic.invalidate()
        self.win.quiet_note()
        self.win.show_state()

    def context_menu(self, spot, where):
        if spot.startswith("shot:") and spot[5:] not in self.selected:
            self.selected = {spot[5:]}
            self.pic.invalidate()
            self.win.show_state()
        if not self.selected:
            return
        m = QMenu(self.win)
        m.addAction("View", self.view)
        m.addSeparator()
        m.addAction("Set a date...", self.stamp)
        m.addAction("Keep the camera's date", self.clock)
        m.addAction("Automatic date", self.eraser)
        m.addSeparator()
        m.addAction("Rotate right", lambda: self.rotate(1))
        m.addAction("Rotate left", lambda: self.rotate(3))
        m.addAction("Name...", self.name)
        m.addAction("Place...", self.place)
        m.addAction("Red eye...", self.pen)
        m.addSeparator()
        m.addAction("Leave out", self.wastebasket)
        m.exec(where)

    # -- the tools on the ledge ------------------------------------------------------------

    def _need_picks(self):
        if not self.selected:
            self.win.say("Pick some shots first:", "click a print, or a card for a whole session.")
            return None
        return self.picked()

    def _changed(self, text):
        self.win.replan()
        self.win.say(text)

    def stamp(self):
        shots = self._need_picks()
        if not shots:
            return
        dlg = DateDialog(self.win, shots, self.plan, self.stamp_date)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        when = dlg.choice()
        if not isinstance(when, str):
            self.stamp_date = when
        self.win.board.set_dates({s.key for s in shots}, when)
        self._changed("%s: %s." % (describe_numbers([s.number for s in shots]).capitalize(),
                                   {"camera": "camera's dates", "auto": "automatic dates"}
                                   .get(when, "") if isinstance(when, str)
                                   else "from " + timeplan.fmt(when)))

    def clock(self):
        shots = self._need_picks()
        if not shots:
            return
        if not any(s.camera_time for s in shots):
            self.win.say("These came from a camera that keeps no clock.")
            return
        self.win.board.set_dates({s.key for s in shots}, "camera")
        self._changed("%s keep the camera's dates." %
                      describe_numbers([s.number for s in shots]).capitalize())

    def eraser(self):
        shots = self._need_picks()
        if not shots:
            return
        self.win.board.set_dates({s.key for s in shots}, "auto")
        self._changed("%s back to automatic dates." %
                      describe_numbers([s.number for s in shots]).capitalize())

    def wastebasket(self):
        arc = self.win.arc
        if not self.selected:
            n = len(arc.skipped)
            if not n:
                return
            if not win95.message(self.win, "Bring back", "Bring back the %s left out?" %
                                 ("shot" if n == 1 else "%d shots" % n), "question",
                                 ("Bring back", "Cancel")):
                return
            try:
                with arc.locked():
                    for sha in list(arc.skipped):
                        arc.unskip(sha)
            except archive.ArchiveBusy as exc:
                win95.message(self.win, "DigiCarlo", str(exc), "error")
            self._changed("Brought back %s." % ("1 shot" if n == 1 else "%d shots" % n))
            return
        shots = self.picked()
        if not win95.message(self.win, "Leave out", "Leave %s out of the library?\n\n"
                             "They stay in the archive; click the wastebasket with "
                             "nothing picked to bring them back." %
                             describe_numbers([s.number for s in shots]), "question",
                             ("Leave out", "Cancel")):
            return
        try:
            with arc.locked():
                for s in shots:
                    arc.skip(s.key)
        except archive.ArchiveBusy as exc:
            win95.message(self.win, "DigiCarlo", str(exc), "error")
        self.selected.clear()
        self._changed("Left out %s." % describe_numbers([s.number for s in shots]))

    def pen(self):
        shots = self._need_picks()
        if not shots:
            return
        photos = []
        for s in shots:
            rec = self.win.arc.files.get(s.key, {})
            if os.path.splitext(rec.get("path", ""))[1].lower() in JPEG:
                photos.append((s, self.win.arc.abspath(rec["path"]), rec))
        if not photos:
            self.win.say("The red-eye pen works on JPEG photos.")
            return
        try:
            from digicarlo import redeye
        except ImportError:
            win95.message(self.win, "Red-eye pen", "The red-eye pen needs numpy.\n\n"
                          "    sudo apt install python3-numpy", "error")
            return
        board = self.win.board

        def work(job, log):
            out = []
            for n, (s, path, rec) in enumerate(photos):
                job.progress(n, len(photos), "Looking at %s" % os.path.basename(path))
                e = board.edits.get(s.key)
                if e is not None and e.redeye is not None:
                    boxes = list(e.redeye)
                else:
                    from PIL import Image
                    with Image.open(path) as im:
                        boxes = redeye.remove_red_eye(im)[1]
                out.append({"key": s.key, "path": path, "boxes": boxes,
                            "caption": "Shot %d" % s.number})
            return out

        def done(found):
            self.win.later(0, lambda: self._pen_dialog(found))
        self.win.run(work, done, "Looking for red eyes")

    def _pen_dialog(self, photos):
        dlg = RedEyeDialog(self.win, photos)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        fixes = dlg.fixes()
        self.win.board.set_redeye(fixes)
        n = sum(len(b or []) for b in fixes.values())
        self.pic.invalidate()
        self._changed("The pen will fix %d eye%s as the shots are developed." %
                      (n, "" if n == 1 else "s"))

    # -- the radio's keys at the board -----------------------------------------------------

    def key(self, k):
        getattr(self, BOARD_KEYS[k])()

    def view(self):
        shots = self.picked() or [it.shot for it in self.items() if it.kind == "shot"]
        if not shots:
            self.win.say("Nothing on the board to see.")
            return
        entries = []
        for s in shots:
            rec = self.win.arc.files.get(s.key, {})
            e = self.win.board.edits.get(s.key)
            entries.append(("Shot %d, %s" % (s.number, timeplan.fmt(self.plan.times[s.key])),
                            self.win.arc.abspath(rec.get("path", "")), rec.get("kind"),
                            e.rotate if e else 0))
        Viewer(self.win, entries, 0, load_picture).exec()

    def rotate(self, quarters=1):
        shots = self._need_picks()
        if not shots:
            return
        self.win.board.rotate({s.key for s in shots}, quarters)
        self.pic.invalidate()
        self._changed("Turned %s a quarter %s." % (
            describe_numbers([s.number for s in shots]), "right" if quarters == 1 else "left"))

    def name(self):
        shots = self._need_picks()
        if not shots:
            return
        titles = {(self.win.board.edits.get(s.key).title if self.win.board.edits.get(s.key)
                   else "") for s in shots}
        dlg = NameDialog(self.win, len(shots), titles.pop() if len(titles) == 1 else "")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.win.board.set_title({s.key for s in shots}, dlg.value())
        self.pic.invalidate()
        self._changed("Named %s \"%s\"." % (describe_numbers([s.number for s in shots]),
                                            dlg.value()) if dlg.value() else "Name taken off.")

    def place(self):
        shots = self._need_picks()
        if not shots:
            return
        places = {(self.win.board.edits.get(s.key).place if self.win.board.edits.get(s.key)
                   else None) for s in shots}
        dlg = PlaceDialog(self.win, self.win.settings, len(shots),
                          places.pop() if len(places) == 1 else None)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        where = dlg.value()
        self.win.board.set_place({s.key for s in shots}, where)
        self.pic.invalidate()
        self._changed("%s taken at %s." % (describe_numbers([s.number for s in shots])
                                           .capitalize(), where[0]) if where else "Place taken off.")

    def undo(self):
        what = self.win.board.undo()
        if what is None:
            self.win.say("Nothing to undo.")
            return
        self.pic.invalidate()
        self._changed("Undid: %s." % what)

    # -- the screen ---------------------------------------------------------------------

    def screen(self):
        from digicarlo.garage import plural
        if not self.plan or not self.plan.shots:
            return ["Nothing waiting.", "Pull a card in the garage."]
        shots = self.picked()
        if shots:
            cams = [s.camera_time for s in shots if s.camera_time]
            times = [self.plan.times[s.key] for s in shots]
            msgs = ["%s picked." % describe_numbers([s.number for s in shots]).capitalize()]
            if cams:
                msgs.append("Camera said %s." % photoboard.short_day(min(cams)))
            msgs.append("Dated %s." % photoboard.span_line(min(times), max(times),
                                                           self.win.today_now().year))
            return msgs
        n = len(self.plan.shots)
        pages = len(self.pages)
        msgs = ["%s waiting%s." % (plural(n, "shot"),
                                   ", page %d of %d" % (self.page + 1, pages) if pages > 1 else "")]
        msgs.append("Click a print to pick it, or a card for its session.")
        return msgs
