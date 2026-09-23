#!/usr/bin/env python3
"""The window builds, lists what is waiting, dates shots, and draws.

    QT_QPA_PLATFORM=offscreen python3 tests/test_gui.py

Skipped when PyQt6 is not installed.
"""

import datetime
import os
import shutil
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

try:
    from PyQt6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

from digicarlo import archive, config, sources, blinky   # noqa: E402
from test_digicarlo import make_jpeg                      # noqa: E402

D = datetime.datetime


@unittest.skipUnless(HAVE_QT, "PyQt6 is not installed")
class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from digicarlo import gui
        cls.gui = gui
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Windows")
        cls.app.setPalette(gui.win95_palette())
        cls.app.setFont(gui.ui_font(8))

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="digicarlo-gui-")
        card = os.path.join(self.tmp, "card", "DCIM", "100KC613")
        base = D(2007, 1, 1, 12, 0, 9)
        for n, off in enumerate((0, 30, 900, 5, 25), 1):     # reset after 3
            make_jpeg(os.path.join(card, "100_%04d.JPG" % n),
                      base + datetime.timedelta(seconds=off),
                      colour=(n * 40, 90, 200 - n * 30))
        cfg = os.path.join(self.tmp, "digicarlo.conf")
        self.settings = config.Settings(cfg)
        self.settings.set("folders", "library", os.path.join(self.tmp, "lib"))
        self.settings.set("folders", "archive", os.path.join(self.tmp, "arc"))
        self.settings.save()
        arc = archive.Archive(self.settings.archive)
        with arc.locked():
            sources.pull(sources.folder_source(os.path.join(self.tmp, "card")),
                         arc, blinky.Log(quiet=True),
                         now=D(2026, 9, 23, 14, 5, 0))
        self.win = self.gui.MainWindow(self.settings)
        self.win.poll.stop()
        self.win.replan()

    def tearDown(self):
        self.win.loader.stop()
        self.win.loader.wait(2000)
        self.win.deleteLater()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def items(self, kind):
        gui = self.gui
        return [self.win.list.item(i) for i in range(self.win.list.count())
                if self.win.list.item(i).data(gui.KIND_ROLE) == kind]

    def test_lists_sessions_and_shots(self):
        self.assertEqual(len(self.items("batch")), 1)
        self.assertEqual(len(self.items("session")), 2)
        self.assertEqual(len(self.items("shot")), 5)
        self.assertTrue(self.win.dash.go.isEnabled())

    def test_setting_a_date_for_selected_shots(self):
        gui = self.gui
        shots = [s for s in self.win.plan.shots if s.number in (4, 5)]
        self.win.apply_rule(D(2026, 9, 12, 19, 0), shots)
        times = self.win.plan.times
        self.assertEqual(times[shots[0].key], D(2026, 9, 12, 19, 0))
        self.assertEqual(times[shots[1].key], D(2026, 9, 12, 19, 0, 20))
        pinned = [it.data(gui.DATA_ROLE)["pinned"] for it in self.items("shot")]
        self.assertEqual(pinned, [None, None, None, "set", "set"])
        self.win.apply_rule("auto", shots)
        self.assertEqual(self.win.plan.times[shots[1].key],
                         D(2026, 9, 23, 14, 5, 0))

    def test_clicking_a_session_heading_selects_it(self):
        heading = self.items("session")[1]
        self.win.list._clicked(heading)
        self.assertEqual(len(self.win.list.selected_keys()), 2)

    def test_everything_draws(self):
        self.win.resize(900, 650)
        self.win.show()
        self.app.processEvents()
        self.assertFalse(self.win.grab().isNull())
        dlg = self.gui.DateDialog(self.win, self.win.plan.shots[:2],
                                  self.win.plan)
        self.assertFalse(dlg.grab().isNull())
        self.assertEqual(dlg.choice(), self.win.plan.times[
            self.win.plan.shots[0].key])
        g = self.gui.Speedometer()
        g.value = 0.5
        g.set_odometer(123456)
        self.assertFalse(g.grab().isNull())
        for size in (16, 32, 256):
            self.assertEqual(self.gui.icon_pixmap(size).width(), size)

    def test_describe_numbers(self):
        self.assertEqual(self.gui.describe_numbers([3, 1, 2, 7, 9, 8]),
                         "shots 1-3, 7-9")
        self.assertEqual(self.gui.describe_numbers([4]), "shot 4")


if __name__ == "__main__":
    unittest.main(verbosity=2)
