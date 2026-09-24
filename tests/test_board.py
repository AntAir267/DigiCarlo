#!/usr/bin/env python3
"""The Photo Board's decisions, and what develop does with them.

    python3 tests/test_board.py

Develop tests need exiftool (and ffmpeg for clips) and skip without them.
"""

import datetime
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from digicarlo import develop, edits, sources, timeplan          # noqa: E402
from test_digicarlo import (HAVE_EXIFTOOL, HAVE_FFMPEG, TempDirs,  # noqa: E402
                            make_jpeg, make_mov)

D = datetime.datetime


def tags(path, *names):
    out = subprocess.run(["exiftool", "-j", "-n"] + ["-" + n for n in names] + [path],
                         capture_output=True, text=True).stdout
    return json.loads(out)[0]


class BoardStateTests(TempDirs):
    def board(self):
        return edits.Board(os.path.join(self.tmp, "board.json"))

    def test_dates_replace_each_other(self):
        b = self.board()
        b.set_dates({"a", "b", "c"}, D(2026, 9, 12, 19, 0))
        b.set_dates({"b"}, "camera")
        self.assertEqual(b.rule_for("a"), D(2026, 9, 12, 19, 0))
        self.assertEqual(b.rule_for("b"), "camera")
        b.set_dates({"a", "b", "c"}, "auto")
        self.assertEqual(b.overrides, [])

    def test_everything_is_kept_across_a_restart(self):
        b = self.board()
        b.set_dates({"a"}, D(2026, 9, 12, 19, 0))
        b.rotate({"a", "b"})
        b.rotate({"b"}, 2)
        b.set_title({"a"}, "  Grandma's birthday ")
        b.set_place({"b"}, ("Home", 44.1, -121.3))
        b.set_redeye({"a": [(10, 20, 30, 30)]})
        again = self.board()
        self.assertEqual(again.rule_for("a"), D(2026, 9, 12, 19, 0))
        self.assertEqual(again.edits["a"].rotate, 1)
        self.assertEqual(again.edits["b"].rotate, 3)
        self.assertEqual(again.edits["a"].title, "Grandma's birthday")
        self.assertEqual(again.edits["b"].place, ("Home", 44.1, -121.3))
        self.assertEqual(again.edits["a"].redeye, [(10, 20, 30, 30)])

    def test_undo_steps_back_one_change_at_a_time(self):
        b = self.board()
        b.set_title({"a"}, "one")
        b.rotate({"a"})
        b.set_dates({"a"}, "camera")
        self.assertEqual(b.undo(), "camera's dates")
        self.assertIsNone(b.rule_for("a"))
        self.assertEqual(b.undo(), "rotate")
        self.assertEqual(b.edits["a"].rotate, 0)
        self.assertEqual(b.edits["a"].title, "one")
        self.assertEqual(b.undo(), "name")
        self.assertIsNone(b.undo())
        self.assertEqual(self.board().edits.get("a", edits.Edit()).title, "")

    def test_prune_forgets_what_is_not_waiting(self):
        b = self.board()
        b.set_dates({"a", "b"}, "camera")
        b.set_title({"a", "b"}, "x")
        b.prune({"b"})
        self.assertEqual(b.overrides[0].keys, {"b"})
        self.assertEqual(set(self.board().edits), {"b"})

    def test_a_damaged_file_is_a_fresh_board(self):
        with open(os.path.join(self.tmp, "board.json"), "w") as fh:
            fh.write("{not json")
        self.assertEqual(self.board().edits, {})

    def test_the_plan_takes_the_boards_dates(self):
        d = os.path.join(self.card, "DCIM", "100KC315")
        for n in range(3):
            make_jpeg(os.path.join(d, "100_%04d.JPG" % (n + 1)),
                      D(2005, 1, 1, 12, 0, 9) + datetime.timedelta(minutes=n))
        arc, res = self.pull_card(D(2026, 9, 23, 14, 5, 0))
        b = self.board()
        keys = [r["sha256"] for r in res.new]
        b.set_dates({keys[0]}, D(2026, 9, 12, 19, 0, 0))
        plan = timeplan.build(develop.plan_batches(arc, self.log), b.overrides)
        self.assertEqual(plan.times[keys[0]], D(2026, 9, 12, 19, 0, 0))


@unittest.skipUnless(HAVE_EXIFTOOL, "exiftool is not installed")
class DevelopEditTests(TempDirs):
    def run_develop(self, arc, board):
        plan = timeplan.build(develop.plan_batches(arc, self.log), board.overrides)
        with arc.locked():
            res = develop.Developer(arc, self.settings, self.log).develop(plan, edits=board.edits)
        self.assertFalse(res.failed, res.failed)
        return res

    def test_turn_title_and_place_go_into_the_library_copy(self):
        d = os.path.join(self.card, "DCIM", "100KC315")
        make_jpeg(os.path.join(d, "100_0001.JPG"), D(2005, 1, 1, 12, 0, 9))
        make_jpeg(os.path.join(d, "100_0002.JPG"), D(2005, 1, 1, 12, 1, 9))
        arc, res = self.pull_card(D(2026, 9, 23, 14, 5, 0))
        first, second = (r["sha256"] for r in sorted(res.new, key=lambda r: r["path"]))
        original = sources.sha256_file(arc.abspath(res.new[0]["path"]))
        b = edits.Board(None)
        b.rotate({first})
        b.rotate({second}, 3)
        b.set_title({first}, "Grandma's birthday")
        b.set_place({first}, ("Grandma's", 45.5231, -122.6765))
        self.run_develop(arc, b)
        one = tags(os.path.join(self.lib, "100_0001.JPG"), "Orientation", "XMP-dc:Title",
                   "ImageDescription", "GPSLatitude", "GPSLongitude", "DateTimeOriginal")
        self.assertEqual(one["Orientation"], 6)
        self.assertEqual(one["Title"], "Grandma's birthday")
        self.assertEqual(one["ImageDescription"], "Grandma's birthday")
        self.assertAlmostEqual(one["GPSLatitude"], 45.5231, places=4)
        self.assertAlmostEqual(one["GPSLongitude"], -122.6765, places=4)
        two = tags(os.path.join(self.lib, "100_0002.JPG"), "Orientation", "GPSLatitude")
        self.assertEqual(two["Orientation"], 8)
        self.assertNotIn("GPSLatitude", two)
        # the archive copy never changes
        self.assertEqual(sources.sha256_file(arc.abspath(res.new[0]["path"])), original)

    def test_red_eye_is_fixed_in_the_copy_only(self):
        try:
            import numpy as np
            from PIL import Image
            from test_redeye import eye_patch
        except ImportError:
            self.skipTest("numpy is not installed")
        d = os.path.join(self.card, "DCIM", "100KC613")
        path = make_jpeg(os.path.join(d, "100_0001.JPG"), D(2007, 1, 1, 12, 0, 9))
        img = np.zeros((300, 400, 3), np.uint8)
        img[:] = (206, 152, 128)
        img[110:150, 140:180] = eye_patch()
        with Image.open(path) as im:
            exif = im.info.get("exif")
        Image.fromarray(img).save(path, quality=98, exif=exif)
        arc, res = self.pull_card(D(2026, 9, 23, 14, 5, 0))
        key = res.new[0]["sha256"]
        b = edits.Board(None)
        from digicarlo import redeye
        b.set_redeye({key: [redeye.box_at((400, 300), 160, 130)]})
        self.run_develop(arc, b)
        out = os.path.join(self.lib, "100_0001.JPG")
        r, g, bl = (int(v) for v in np.asarray(Image.open(out))[131, 160])
        self.assertLess(r, 100)
        r0 = int(np.asarray(Image.open(arc.abspath(res.new[0]["path"])))[131, 160][0])
        self.assertGreater(r0, 150)
        self.assertEqual(tags(out, "DateTimeOriginal")["DateTimeOriginal"], "2026:09:23 14:05:00")

    def test_a_png_is_turned_in_its_pixels(self):
        from PIL import Image
        d = os.path.join(self.card, "DCIM", "100SIPIX")
        os.makedirs(d)
        Image.new("RGB", (60, 40), (10, 200, 30)).save(os.path.join(d, "shot.png"))
        arc, res = self.pull_card(D(2026, 9, 23, 14, 5, 0))
        b = edits.Board(None)
        b.rotate({res.new[0]["sha256"]})
        self.run_develop(arc, b)
        with Image.open(os.path.join(self.lib, "shot.png")) as im:
            self.assertEqual(im.size, (40, 60))

    @unittest.skipUnless(HAVE_FFMPEG, "ffmpeg is not installed")
    def test_a_clip_turns_and_is_named(self):
        make_mov(os.path.join(self.card, "DCIM", "100KC315", "100_0003.MOV"),
                 D(2007, 1, 1, 12, 0, 9))
        arc, res = self.pull_card(D(2026, 9, 23, 14, 5, 0))
        key = res.new[0]["sha256"]
        b = edits.Board(None)
        b.rotate({key})
        b.set_title({key}, "Beach")
        b.set_place({key}, ("Beach", -33.8688, 151.2093))
        self.run_develop(arc, b)
        t = tags(os.path.join(self.lib, "100_0003.mp4"), "Rotation", "Title", "GPSCoordinates")
        self.assertEqual(t["Rotation"], 90)
        self.assertEqual(t["Title"], "Beach")
        self.assertIn("-33.8688", str(t["GPSCoordinates"]))


try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtWidgets import QApplication, QDialog
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PyQt6 is not installed")
class BoardWindowTests(TempDirs):
    @classmethod
    def setUpClass(cls):
        from digicarlo import boardroom, dialogs, garage, win95
        cls.garage, cls.dialogs, cls.win95, cls.boardroom = garage, dialogs, win95, boardroom
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.app.setStyle("Windows")
        cls.app.setPalette(win95.palette())

    def setUp(self):
        super().setUp()
        self.settings.set("window", "sounds", "no")
        self.settings.save()
        d = os.path.join(self.card, "DCIM", "100KC613")
        base = D(2007, 1, 1, 12, 0, 9)
        for n in range(25):                      # the clock resets after 12
            when = base + datetime.timedelta(seconds=40 * (n if n < 12 else n - 12))
            make_jpeg(os.path.join(d, "100_%04d.JPG" % (n + 1)), when,
                      colour=(10 * n % 250, 90, 200 - 5 * n))
        self.pull_card(D(2026, 9, 23, 14, 5, 0))
        self.win = self.garage.GarageWindow(self.settings)
        self.win.poll.stop()
        self.win.resize(1280, 840)
        self.app.processEvents()
        self.win.replan()
        self.win.go("board")
        self.br = self.win.boardroom
        self.keys = [s.key for s in self.win.plan.shots]
        self.patched = []

    def tearDown(self):
        for obj, name, old in reversed(self.patched):
            setattr(obj, name, old)
        for job in (self.win.scan_job, self.win.job):
            if job is not None:
                job.wait(30000)
        self.win.close()
        self.win.deleteLater()
        self.app.processEvents()
        super().tearDown()

    def patch(self, obj, name, value):
        self.patched.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def wait_job(self):
        if self.win.job is not None:
            self.win.job.wait(60000)
        for _ in range(5):
            self.app.processEvents()

    def test_the_board_lays_out_every_shot(self):
        self.assertEqual(len(self.win.plan.sessions), 2)
        self.assertEqual(len(self.br.pages), 2)          # 25 prints and 2 cards
        on = [it for page in self.br.pages for it in page if it.kind == "shot"]
        self.assertEqual(sorted(it.shot.key for it in on), sorted(self.keys))
        self.assertEqual(self.br.pages[0][0].kind, "card")
        self.assertEqual(self.win.windowTitle(), "DigiCarlo - Photo Board")
        self.assertIn("board-dial", self.win.console.on)

    def test_a_print_is_where_it_is_drawn(self):
        it = next(i for i in self.br.items() if i.kind == "shot")
        to_widget = self.br.cork * self.win.stage.picture_transform(self.br.pic)
        hit = self.win.stage.spot_under(to_widget.map(it.rect.center()))
        self.assertEqual(hit[1], it.name)

    def test_picking(self):
        self.br.clicked("shot:" + self.keys[2])
        self.assertEqual(self.br.selected, {self.keys[2]})
        self.br._pick(self.keys[5], Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(self.br.selected, set(self.keys[2:6]))
        self.br._pick(self.keys[3], Qt.KeyboardModifier.ControlModifier)
        self.assertNotIn(self.keys[3], self.br.selected)
        card = next(i for i in self.br.items() if i.kind == "card")
        self.br.clicked(card.name)
        self.assertEqual(self.br.selected, {s.key for s in card.session.shots})
        self.br.clicked("cork")
        self.assertEqual(self.br.selected, set())
        self.assertIn("NOTHING", " ".join(self.win.screen_lines()) + "NOTHING")

    def test_the_stamp_the_clock_and_the_eraser(self):
        picked = set(self.keys[:3])
        self.br.selected = set(picked)
        when = D(2026, 9, 12, 19, 0, 0)
        self.patch(self.dialogs.DateDialog, "exec", lambda dlg: QDialog.DialogCode.Accepted)
        self.patch(self.dialogs.DateDialog, "choice", lambda dlg: when)
        self.br.clicked("stamp")
        self.assertEqual(self.win.plan.times[self.keys[0]], when)
        self.assertEqual(self.br.stamp_date, when)
        self.br.clicked("clock")
        self.assertEqual(self.win.plan.times[self.keys[0]],
                         self.win.plan.shots[0].camera_time)
        self.br.clicked("eraser")
        self.assertIsNone(self.win.plan.rules.get(self.keys[0]))

    def test_keys_rotate_and_undo(self):
        self.br.selected = {self.keys[0], self.keys[1]}
        self.win.push_key(2)                      # ROTATE
        self.assertEqual(self.win.board.edits[self.keys[0]].rotate, 1)
        self.assertEqual(self.win.board_key, 2)
        self.assertIn("board-key2", self.win.console.on)
        self.win.push_key(5)                      # UNDO
        self.assertEqual(self.win.board.edits.get(self.keys[0], edits.Edit()).rotate, 0)
        self.assertIn("UNDID", " ".join(self.win.screen_lines()))

    def test_name_and_place(self):
        self.br.selected = {self.keys[4]}
        self.patch(self.dialogs.NameDialog, "exec", lambda dlg: QDialog.DialogCode.Accepted)
        self.patch(self.dialogs.NameDialog, "value", lambda dlg: "Beach day")
        self.win.push_key(3)
        self.assertEqual(self.win.board.edits[self.keys[4]].title, "Beach day")
        self.patch(self.dialogs.PlaceDialog, "exec", lambda dlg: QDialog.DialogCode.Accepted)
        self.patch(self.dialogs.PlaceDialog, "value", lambda dlg: ("Beach", 1.5, 2.5))
        self.win.push_key(4)
        self.assertEqual(self.win.board.edits[self.keys[4]].place, ("Beach", 1.5, 2.5))

    def test_leave_out_and_bring_back(self):
        self.patch(self.win95, "message", lambda *a, **k: True)
        self.br.selected = set(self.keys[:2])
        self.br.clicked("bin")
        self.assertEqual(len(self.win.plan.shots), 23)
        self.assertIn("trash", self.br.pic.on)
        self.br.clicked("bin")                   # nothing picked: bring them back
        self.assertEqual(len(self.win.plan.shots), 25)
        self.assertNotIn("trash", self.br.pic.on)

    def test_pages_turn(self):
        self.br.turn_page(1)
        self.assertEqual(self.br.page, 1)
        self.win._clicked("console", "knob-right")
        self.assertEqual(self.br.page, 0)
        self.br.clicked("note:page")
        self.assertEqual(self.br.page, 1)

    def test_the_sign_goes_back_to_the_garage(self):
        self.br.clicked("garage")
        self.assertEqual(self.win.room, "garage")
        self.assertIs(self.win.stage.pictures[0], self.win.garage_pic)

    def test_decisions_outlive_the_window(self):
        self.br.selected = {self.keys[0]}
        self.win.board.set_dates({self.keys[0]}, "camera")
        again = self.garage.GarageWindow(self.settings)
        again.poll.stop()
        self.app.processEvents()
        again.replan()
        self.assertEqual(again.plan.times[self.keys[0]], again.plan.shots[0].camera_time)
        if again.scan_job is not None:
            again.scan_job.wait(20000)
        again.close()
        again.deleteLater()

    @unittest.skipUnless(HAVE_EXIFTOOL, "exiftool is not installed")
    def test_develop_takes_what_the_board_decided(self):
        self.patch(self.win95, "message", lambda *a, **k: True)
        self.win.board.rotate({self.keys[0]})
        self.win.develop()
        self.wait_job()
        path = os.path.join(self.lib, "100_0001.JPG")
        self.assertEqual(tags(path, "Orientation")["Orientation"], 6)
        self.assertEqual(self.win.waiting(), 0)
        self.assertEqual(self.win.board.edits, {})

    def test_the_red_eye_pen(self):
        try:
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("numpy is not installed")
        self.br.selected = {self.keys[0]}
        box = (4, 4, 24, 24)
        self.patch(self.dialogs.RedEyeDialog, "exec", lambda dlg: QDialog.DialogCode.Accepted)
        self.patch(self.dialogs.RedEyeDialog, "fixes", lambda dlg: {self.keys[0]: [box]})
        self.br.clicked("pen")
        self.wait_job()
        self.assertEqual(self.win.board.edits[self.keys[0]].redeye, [box])

    def test_a_camera_whose_clock_can_be_right_is_asked_about(self):
        d = os.path.join(self.tmp, "polaroid", "DCIM", "100POLAR")
        make_jpeg(os.path.join(d, "IMG_0001.JPG"), D(2026, 6, 3, 14, 2, 0),
                  make="Polaroid", model="i1237")
        make_jpeg(os.path.join(d, "IMG_0002.JPG"), D(2026, 6, 3, 14, 40, 0),
                  make="Polaroid", model="i1237")
        make_jpeg(os.path.join(d, "IMG_0003.JPG"), D(2000, 1, 1, 0, 0, 5),
                  make="Polaroid", model="i1237")
        shown = []

        def fake_exec(dlg):
            shown.append([b.isChecked() for b, _ in dlg.boxes])
            return QDialog.DialogCode.Accepted
        self.patch(self.dialogs.TrustDialog, "exec", fake_exec)
        self.win.pull(sources.folder_source(os.path.join(self.tmp, "polaroid")))
        self.wait_job()
        for _ in range(10):
            self.app.processEvents()
        self.assertEqual(shown, [[True, False]])    # the June session, not the reset
        juneshots = [s for s in self.win.plan.shots if s.camera_time and
                     s.camera_time.year == 2026]
        self.assertEqual(len(juneshots), 2)
        for s in juneshots:
            self.assertEqual(self.win.plan.times[s.key], s.camera_time)


if __name__ == "__main__":
    unittest.main(verbosity=2)
