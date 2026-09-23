#!/usr/bin/env python3
"""The garage window and what its radio keys do.

    QT_QPA_PLATFORM=offscreen python3 tests/test_garage.py

The card tools run on folders standing in for cards, Syncthing is a small
local web server answering as Syncthing would, and the window is built
offscreen from the shipped scene assets.
"""

import datetime
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from digicarlo import archive, blinky, cardtools, config, sources, syncthing  # noqa: E402
from test_digicarlo import make_jpeg                                           # noqa: E402

D = datetime.datetime
QUIET = blinky.Log(quiet=True)

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


def make_card(root, n, start=1):
    card = os.path.join(root, "DCIM", "100KC613")
    base = D(2007, 1, 1, 12, 0, 9)
    for i in range(start, start + n):
        make_jpeg(os.path.join(card, "100_%04d.JPG" % i),
                  base + datetime.timedelta(seconds=30 * i), colour=(i * 20 % 255, 90, 120))
    return card


class CardToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="digicarlo-cards-")
        self.root = os.path.join(self.tmp, "card")
        make_card(self.root, 4)
        self.arc = archive.Archive(os.path.join(self.tmp, "arc"))
        self.src = sources.folder_source(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def pull(self):
        with self.arc.locked():
            sources.pull(self.src, self.arc, QUIET, now=D(2026, 9, 23, 14, 0, 0))
        self.arc.reload()

    def test_count_new(self):
        self.assertEqual(sources.count_new(self.src, self.arc), (4, 4))
        self.pull()
        make_card(self.root, 2, start=5)
        self.assertEqual(sources.count_new(self.src, self.arc), (6, 2))

    def test_check_reads_everything(self):
        res = cardtools.check(self.src, QUIET)
        self.assertEqual(res.files, 4)
        self.assertEqual(res.failed, [])
        self.assertEqual(res.bytes, sum(os.path.getsize(os.path.join(dp, f))
                                        for dp, _, fs in os.walk(self.root) for f in fs))

    def test_erase_refuses_until_everything_is_archived(self):
        plan = cardtools.plan_erase(self.src, self.arc, QUIET)
        self.assertFalse(plan.safe)
        self.assertEqual(len(plan.missing), 4)
        with self.assertRaises(RuntimeError):
            cardtools.erase(plan, QUIET)
        self.assertEqual(len(sources.list_media(self.root)), 4)

        self.pull()
        make_card(self.root, 1, start=5)             # one more, not pulled
        plan = cardtools.plan_erase(self.src, self.arc, QUIET)
        self.assertFalse(plan.safe)
        self.assertEqual(plan.missing, [os.path.join("DCIM", "100KC613", "100_0005.JPG")])
        self.assertEqual(len(sources.list_media(self.root)), 5)

    def test_erase_when_all_is_archived(self):
        self.pull()
        plan = cardtools.plan_erase(self.src, self.arc, QUIET)
        self.assertTrue(plan.safe)
        res = cardtools.erase(plan, QUIET)
        self.assertEqual(res.erased, 4)
        self.assertEqual(sources.list_media(self.root), [])
        # the archive keeps every one
        self.assertEqual(len(self.arc.files), 4)
        for rec in self.arc.files.values():
            self.assertTrue(os.path.exists(self.arc.abspath(rec["path"])))

    def test_erase_refuses_a_damaged_archive_copy(self):
        self.pull()
        rec = next(iter(self.arc.files.values()))
        with open(self.arc.abspath(rec["path"]), "r+b") as fh:
            fh.seek(200)
            fh.write(b"\x00\x01\x02")
        plan = cardtools.plan_erase(self.src, self.arc, QUIET)
        self.assertFalse(plan.safe)
        self.assertEqual(len(plan.damaged), 1)

    def test_erase_skips_a_file_changed_since_the_check(self):
        self.pull()
        plan = cardtools.plan_erase(self.src, self.arc, QUIET)
        rel, path = plan.files[0][0], plan.files[0][1]
        with open(path, "ab") as fh:
            fh.write(b"more")
        res = cardtools.erase(plan, QUIET)
        self.assertEqual(res.changed, [rel])
        self.assertEqual(res.erased, 3)
        self.assertTrue(os.path.exists(path))


# ---------------------------------------------------------------------------
# Syncthing
# ---------------------------------------------------------------------------

ME, PIXEL = "MEMEMEM-AAAAAAA", "PIXELPX-BBBBBBB"


class FakeSyncthing(http.server.BaseHTTPRequestHandler):
    calls = []

    def log_message(self, *a):
        pass

    def _reply(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _route(self, method):
        url = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(url.query))
        FakeSyncthing.calls.append((method, url.path, q))
        if self.headers.get("X-API-Key") != "sekrit":
            return self._reply({"error": "forbidden"}, 403)
        answers = {
            "/rest/system/status": {"myID": ME},
            "/rest/db/status": {"state": "idle", "localFiles": 604,
                                "localBytes": 2100000000, "errors": 0, "pullErrors": 0},
            "/rest/system/connections": {"connections": {PIXEL: {"connected": True}}},
            "/rest/stats/device": {PIXEL: {"lastSeen": "2026-09-23T18:42:00Z"}},
            "/rest/db/completion": {"completion": 97.5, "needItems": 12, "needBytes": 9000000},
            "/rest/db/scan": {},
        }
        if url.path not in answers:
            return self._reply({"error": "no"}, 404)
        return self._reply(answers[url.path])

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")


class SyncthingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="digicarlo-st-")
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeSyncthing)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        port = self.server.server_address[1]
        self.library = os.path.join(self.tmp, "Pixel Backup")
        self.cfg = os.path.join(self.tmp, "config.xml")
        with open(self.cfg, "w") as fh:
            fh.write('''<configuration version="37">
  <folder id="pixel-backup" label="Pixel Backup" path="%s" type="sendreceive">
    <device id="%s"></device><device id="%s"></device>
  </folder>
  <folder id="other" label="Other" path="%s/elsewhere"><device id="%s"></device></folder>
  <device id="%s" name="Penguin-360"></device>
  <device id="%s" name="Pixel"></device>
  <gui enabled="true" tls="false"><address>0.0.0.0:%d</address><apikey>sekrit</apikey></gui>
</configuration>''' % (self.library, ME, PIXEL, self.tmp, ME, ME, PIXEL, port))
        FakeSyncthing.calls = []

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_config(self):
        c = syncthing.Config(self.cfg)
        self.assertTrue(c.url.startswith("http://127.0.0.1:"))
        self.assertEqual(c.folder_for(os.path.join(self.library, "sub"))["id"], "pixel-backup")
        self.assertIsNone(c.folder_for("/nowhere"))
        self.assertIs(syncthing.find_config([os.path.join(self.tmp, "none.xml")]), None)

    def test_status(self):
        st = syncthing.library_status(self.library, config=syncthing.Config(self.cfg))
        self.assertEqual(st.folder, "Pixel Backup")
        self.assertEqual(st.files, 604)
        self.assertEqual(len(st.peers), 1)
        pixel = st.peers[0]
        self.assertEqual(pixel.name, "Pixel")
        self.assertTrue(pixel.connected)
        self.assertEqual(pixel.need_items, 12)
        self.assertAlmostEqual(pixel.completion, 97.5)
        self.assertIsNotNone(pixel.last_seen)
        self.assertIn(("GET", "/rest/db/completion", {"folder": "pixel-backup", "device": PIXEL}),
                      FakeSyncthing.calls)

    def test_rescan(self):
        cfg = syncthing.Config(self.cfg)
        self.assertTrue(syncthing.rescan(self.library, config=cfg))
        self.assertIn(("POST", "/rest/db/scan", {"folder": "pixel-backup"}), FakeSyncthing.calls)
        self.assertFalse(syncthing.rescan("/somewhere/else", config=cfg))

    def test_not_running(self):
        cfg = syncthing.Config(self.cfg)
        cfg.url = "http://127.0.0.1:1"              # nothing listens there
        with self.assertRaises(syncthing.SyncthingError):
            syncthing.library_status(self.library, config=cfg)

    def test_wrong_key(self):
        cfg = syncthing.Config(self.cfg)
        cfg.key = "wrong"
        with self.assertRaises(syncthing.SyncthingError):
            syncthing.library_status(self.library, config=cfg)


# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------

@unittest.skipUnless(HAVE_QT, "PyQt6 is not installed")
class GarageWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from digicarlo import garage, win95
        cls.garage = garage
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.app.setStyle("Windows")
        cls.app.setPalette(win95.palette())

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="digicarlo-garage-")
        self.card = os.path.join(self.tmp, "card")
        make_card(self.card, 3)
        self.settings = config.Settings(os.path.join(self.tmp, "digicarlo.conf"))
        self.settings.set("folders", "library", os.path.join(self.tmp, "lib"))
        self.settings.set("folders", "archive", os.path.join(self.tmp, "arc"))
        self.settings.set("window", "sounds", "no")
        self.settings.save()
        arc = archive.Archive(self.settings.archive)
        with arc.locked():
            sources.pull(sources.folder_source(self.card), arc, QUIET,
                         now=D(2026, 9, 23, 14, 5, 0))
        self.win = self.garage.GarageWindow(self.settings)
        self.win.poll.stop()
        self.win.resize(1280, 840)
        self.app.processEvents()
        self.win.replan()

    def tearDown(self):
        for job in (self.win.scan_job, self.win.job):
            if job is not None:
                job.wait(20000)
        self.win.deleteLater()
        self.app.processEvents()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def plug_in(self):
        src = sources.Source("volume", "/dev/sdz1", "KODAK", path=self.card,
                             device="/dev/sdz1", detail="SD card, 512.0 MB")
        self.win._scanned(([src], {src.ident: (5, 2)}))
        return src

    def point_of(self, pic, spot):
        """A widget position over `spot` in `pic`."""
        m = pic.map
        n = pic.names[spot]
        for y in range(0, m.height(), 3):
            for x in range(0, m.width(), 3):
                if m.pixelColor(x, y).red() == n:
                    t = self.win.stage.picture_transform(pic)
                    return t.map(QPointF(x * 2 + 1, y * 2 + 1))
        self.fail("no %s in the map" % spot)

    def test_counter_and_start_follow_the_waiting_shots(self):
        self.assertEqual(self.win.waiting(), 3)
        on = self.win.console.on
        self.assertIn("start", on)
        self.assertEqual([k for k in on if k.startswith("drum")],
                         ["drum0-0", "drum1-0", "drum2-0", "drum3-3"])
        self.assertIn("safelight", self.win.room.on)

    def test_card_appears_with_its_count(self):
        self.assertNotIn("card", self.win.room.on)
        self.assertFalse(self.win._live("garage", "card"))
        self.plug_in()
        self.assertIn("card", self.win.room.on)
        hit = self.win.stage.spot_under(self.point_of(self.win.room, "card"))
        self.assertEqual(hit[1], "card")
        self.assertIn("2 new pictures", self.win._tip("garage", "card"))
        self.assertIn("KODAK", " ".join(self.win.screen_lines()))

    def test_hotspots_are_where_the_things_are(self):
        for pic, spots in ((self.win.room, ("door", "board", "crate", "car")),
                           (self.win.console, ("key1", "key5", "start", "screen"))):
            for spot in spots:
                hit = self.win.stage.spot_under(self.point_of(pic, spot))
                self.assertIsNotNone(hit, spot)
                self.assertEqual(hit[1], spot)

    def test_pictures_compose(self):
        self.plug_in()
        img = self.win.room.composed()
        self.assertEqual((img.width(), img.height()), (2544, 1080))
        img = self.win.console.composed()
        self.assertEqual((img.width(), img.height()), (2544, 460))
        self.assertFalse(self.win.grab().isNull())

    def test_a_key_stays_in_and_pops_out(self):
        self.win.push_key(1)                     # CHECK CARD, with no card
        self.assertEqual(self.win.key, 1)
        self.assertIn("key1", self.win.console.on)
        self.assertIn("NO CARD", " ".join(self.win.screen_lines()))
        self.win.push_key(1)
        self.assertEqual(self.win.key, 0)
        self.assertNotIn("key1", self.win.console.on)

    def test_check_card_key(self):
        # a card the desktop mounted: no device to read the kernel's log for
        src = sources.Source("volume", "card", "KODAK", path=self.card, mounted=True)
        self.win._scanned(([src], {}))
        self.win.push_key(1)
        self.win.job.wait(20000)
        self.app.processEvents()
        self.assertIn("CHECKED 3 FILES", " ".join(self.win.screen_lines()))
        self.assertIn("ALL READ CLEANLY", " ".join(self.win.screen_lines()))

    def test_screen_wraps_to_its_width(self):
        lines = self.garage.screen("Kodak card in the reader: 32 new.", "118 shots waiting.")
        self.assertTrue(all(len(line) <= self.garage.SCREEN_COLUMNS for line in lines))
        self.assertTrue(lines[0].startswith("> "))
        self.assertTrue(lines[1].startswith("  "))


if __name__ == "__main__":
    unittest.main(verbosity=2)
