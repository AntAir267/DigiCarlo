#!/usr/bin/env python3
"""DigiCarlo's tests. No camera needed: cards are folders, the SiPix is
Blinky's simulated camera, and clips are made with ffmpeg.

    python3 tests/test_digicarlo.py

Tests that write dates need exiftool, and video tests need ffmpeg; each is
skipped, with a reason, when its tool is missing.
"""

import datetime
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from digicarlo import archive, blinky, cli, config, develop, media  # noqa: E402
from digicarlo import sources, timeplan                            # noqa: E402

HAVE_EXIFTOOL = bool(shutil.which("exiftool"))
HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

D = datetime.datetime


def quiet_log():
    return blinky.Log(quiet=True)


def shot(key, t, batch="b"):
    return timeplan.Shot(key, batch, t, key)


def make_jpeg(path, when=None, model="KODAK EASYSHARE C315 DIGITAL CAMERA",
              make="EASTMAN KODAK COMPANY", colour=(200, 10, 10), mtime=None):
    from PIL import Image
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = Image.new("RGB", (64, 48), colour)
    exif = Image.Exif()
    if make:
        exif[0x010F] = make
    if model:
        exif[0x0110] = model
    if when:
        stamp = when.strftime("%Y:%m:%d %H:%M:%S")
        # IFD0 DateTime as well: older Pillow does not write a nested Exif
        # IFD that was only filled in through get_ifd().
        exif[0x0132] = stamp
        exif.get_ifd(0x8769)[0x9003] = stamp
    img.save(path, exif=exif)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def make_mov(path, when, seconds=1):
    """An MJPEG + 8-bit PCM QuickTime clip, like the Kodaks record."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
         "testsrc=size=160x120:rate=10", "-f", "lavfi", "-i",
         "sine=frequency=440:sample_rate=11025", "-t", str(seconds),
         "-c:v", "mjpeg", "-q:v", "5", "-c:a", "pcm_u8", "-ac", "1",
         "-metadata", "creation_time=" + when.strftime("%Y-%m-%dT%H:%M:%SZ"),
         path], check=True)
    return path


def exif_of(path):
    out = subprocess.run(["exiftool", "-j", "-DateTimeOriginal", "-CreateDate",
                          "-ModifyDate", "-OffsetTimeOriginal", "-Make",
                          "-Model", "-api", "QuickTimeUTC=1",
                          "-Keys:CreationDate", path],
                         capture_output=True, text=True).stdout
    return json.loads(out)[0]


class TempDirs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="digicarlo-test-")
        self.card = os.path.join(self.tmp, "card")
        self.lib = os.path.join(self.tmp, "Pixel Backup")
        self.arcdir = os.path.join(self.tmp, "Archive")
        cfg = os.path.join(self.tmp, "digicarlo.conf")
        self.settings = config.Settings(cfg)
        self.settings.set("folders", "library", self.lib)
        self.settings.set("folders", "archive", self.arcdir)
        self.log = quiet_log()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def pull_card(self, now=None):
        arc = archive.Archive(self.arcdir)
        src = sources.folder_source(self.card)
        with arc.locked():
            res = sources.pull(src, arc, self.log, now=now)
        return arc, res

    def plan(self, arc, overrides=()):
        return cli.build_plan(arc, self.settings, list(overrides), self.log)


# ---------------------------------------------------------------------------
# Sessions and dates
# ---------------------------------------------------------------------------

class SessionTests(unittest.TestCase):
    def test_backwards_clock_starts_a_session(self):
        t = D(2007, 1, 1, 12, 0, 9)
        shots = [shot("a", t), shot("b", t + datetime.timedelta(minutes=40)),
                 shot("c", t + datetime.timedelta(seconds=5)),    # reset
                 shot("d", t + datetime.timedelta(seconds=30))]
        runs = timeplan.split(shots)
        self.assertEqual([[s.key for s in r] for r in runs],
                         [["a", "b"], ["c", "d"]])

    def test_small_backstep_is_jitter(self):
        t = D(2007, 1, 1, 12, 0, 0)
        shots = [shot("clip", t + datetime.timedelta(seconds=60)),
                 shot("photo", t + datetime.timedelta(seconds=10))]
        self.assertEqual(len(timeplan.split(shots)), 1)

    def test_huge_forward_leap_is_the_clock_being_set(self):
        t = D(2007, 1, 1, 12, 0, 0)
        shots = [shot("a", t), shot("b", D(2016, 5, 1, 9, 0, 0)),
                 shot("c", D(2016, 5, 3, 9, 0, 0))]
        runs = timeplan.split(shots, max_gap_days=30)
        self.assertEqual([len(r) for r in runs], [1, 2])

    def test_offsets_keep_gaps_and_order(self):
        t = D(2007, 1, 1, 12, 0, 0)
        offs = timeplan.session_offsets(
            [t, t + datetime.timedelta(seconds=90), None,
             t + datetime.timedelta(seconds=90),        # same second
             t + datetime.timedelta(seconds=600)])
        self.assertEqual(offs, [0, 90, 91, 92, 600])

    def test_offsets_without_any_clock(self):
        self.assertEqual(timeplan.session_offsets([None, None, None]),
                         [0, 1, 2])

    def test_leading_unknowns_count_back(self):
        t = D(2007, 1, 1, 12, 0, 0)
        self.assertEqual(timeplan.session_offsets([None, t, t.replace(second=5)]),
                         [0, 1, 6])


class PlanTests(unittest.TestCase):
    def setUp(self):
        base = D(2007, 1, 1, 12, 0, 9)
        m = lambda s: base + datetime.timedelta(seconds=s)    # noqa: E731
        self.anchor = D(2026, 9, 23, 14, 5, 0)
        self.batch = timeplan.Batch("b1", self.anchor, [
            shot("s1a", m(0)), shot("s1b", m(120)), shot("s1c", m(3000)),
            shot("s2a", m(10)), shot("s2b", m(70))], "Kodak")

    def build(self, *overrides, now=None):
        ovs = [timeplan.parse_override(o, now) for o in overrides]
        return timeplan.build([self.batch], ovs, spacing=60)

    def test_last_shot_gets_the_pull_time_and_gaps_are_kept(self):
        plan = self.build()
        t = plan.times
        self.assertEqual(len(plan.sessions), 2)
        self.assertEqual(t["s2b"], self.anchor)
        self.assertEqual((t["s2b"] - t["s2a"]).total_seconds(), 60)
        self.assertEqual((t["s1c"] - t["s1a"]).total_seconds(), 3000)
        # sessions stacked a minute apart
        self.assertEqual((t["s2a"] - t["s1c"]).total_seconds(), 60)
        self.assertEqual([s.number for s in plan.shots], [1, 2, 3, 4, 5])

    def test_session_override_starts_there_and_leaves_others(self):
        auto = self.build().times
        plan = self.build("S2=2026-09-12 19:00")
        self.assertEqual(plan.times["s2a"], D(2026, 9, 12, 19, 0, 0))
        self.assertEqual(plan.times["s2b"], D(2026, 9, 12, 19, 1, 0))
        for k in ("s1a", "s1b", "s1c"):
            self.assertEqual(plan.times[k], auto[k])

    def test_everything_override_chains_forward(self):
        plan = self.build("2026-09-12 19:00")
        t = plan.times
        self.assertEqual(t["s1a"], D(2026, 9, 12, 19, 0, 0))
        self.assertEqual((t["s1c"] - t["s1a"]).total_seconds(), 3000)
        self.assertEqual((t["s2a"] - t["s1c"]).total_seconds(), 60)

    def test_shot_range_splits_a_session_without_moving_neighbours(self):
        auto = self.build().times
        plan = self.build("2-2=2026-01-02 10:00")
        self.assertEqual(plan.times["s1b"], D(2026, 1, 2, 10, 0, 0))
        self.assertEqual(plan.times["s1a"], auto["s1a"])
        self.assertEqual(plan.times["s1c"], auto["s1c"])
        groups = [g for g in plan.groups if g.session.number == 1]
        self.assertEqual([len(g.shots) for g in groups], [1, 1, 1])

    def test_camera_dates_kept(self):
        plan = self.build("S1=camera")
        self.assertEqual(plan.times["s1a"], D(2007, 1, 1, 12, 0, 9))

    def test_every_kind_of_override_describes_itself(self):
        for text in ("2026-09-12 19:00", "S2=camera", "S1-S2=now", "3=now",
                     "2-4=2026-01-01"):
            self.assertTrue(timeplan.parse_override(text).describe())
        keys = timeplan.Override("keys", None, None, "camera", keys={"a"})
        self.assertEqual(keys.describe(), "1 shot: camera's own dates")

    def test_later_override_wins(self):
        plan = self.build("2026-01-01 00:00", "S2=2026-02-01 00:00")
        self.assertEqual(plan.times["s1a"], D(2026, 1, 1))
        self.assertEqual(plan.times["s2a"], D(2026, 2, 1))

    def test_times_strictly_increase_through_plan(self):
        plan = self.build()
        ts = [plan.times[s.key] for s in plan.shots]
        self.assertEqual(ts, sorted(ts))
        self.assertEqual(len(set(ts)), len(ts))


class ParseTests(unittest.TestCase):
    NOW = D(2026, 9, 23, 14, 5, 7)

    def test_dates(self):
        p = lambda s: timeplan.parse_when(s, self.NOW)   # noqa: E731
        self.assertEqual(p("2026-09-12 19:00"), D(2026, 9, 12, 19, 0))
        self.assertEqual(p("2026-09-12"), D(2026, 9, 12, 12, 0))
        self.assertEqual(p("2026/9/12 7pm"), D(2026, 9, 12, 19, 0))
        self.assertEqual(p("yesterday 18:30"), D(2026, 9, 22, 18, 30))
        self.assertEqual(p("today"), D(2026, 9, 23, 12, 0))
        self.assertEqual(p("now"), self.NOW)
        self.assertEqual(p("camera"), "camera")
        with self.assertRaises(timeplan.PlanError):
            p("next thursday")

    def test_selectors(self):
        o = timeplan.parse_override("S2-S4=2026-09-12 19:00")
        self.assertEqual((o.scope, o.first, o.last), ("sessions", 2, 4))
        o = timeplan.parse_override("12-30=camera")
        self.assertEqual((o.scope, o.first, o.last, o.when),
                         ("shots", 12, 30, "camera"))
        o = timeplan.parse_override("2026-09-12 19:00")
        self.assertEqual(o.scope, "all")
        for bad in ("S4-S2=now", "0=now", "3-S4=now"):
            with self.assertRaises(timeplan.PlanError):
                timeplan.parse_override(bad)


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

class MediaTests(unittest.TestCase):
    def test_dcf(self):
        self.assertEqual(media.dcf_key("DCIM/101KC613/101_0063.MOV"), (101, 63))
        self.assertEqual(media.dcf_key("DCIM/100_PANA/P1000123.JPG"), (100, 123))
        self.assertIsNone(media.dcf_key("image0003.raw"))
        self.assertIsNone(media.dcf_key("Holiday/IMG_1.JPG"))

    def test_shooting_order_merges_by_time(self):
        t = D(2020, 1, 1, 10)
        items = [
            {"rel": "DCIM/100X/DSC_0002.JPG", "dcf": (100, 2),
             "camera_time": t.replace(minute=5)},
            {"rel": "DCIM/100X/DSC_0001.JPG", "dcf": (100, 1),
             "camera_time": t},
            {"rel": "PRIVATE/AVCHD/BDMV/STREAM/00001.MTS", "dcf": None,
             "camera_time": t.replace(minute=2)},
        ]
        order = [i["rel"].split("/")[-1] for i in media.shooting_order(items)]
        self.assertEqual(order, ["DSC_0001.JPG", "00001.MTS", "DSC_0002.JPG"])

    def test_pretty_camera(self):
        self.assertEqual(media.pretty_camera(
            "EASTMAN KODAK COMPANY", "KODAK EASYSHARE C613 ZOOM DIGITAL CAMERA"),
            "Kodak EasyShare C613 Zoom")
        self.assertEqual(media.pretty_camera(
            "Konica Corporation", "Konica Digital Camera KD-400Z"),
            "Konica KD-400Z")
        self.assertEqual(media.pretty_camera("Polaroid", "i1237"),
                         "Polaroid i1237")

    def test_calibrate_uses_exif_to_read_file_times(self):
        # File times presented as UTC wall clock, a few seconds after EXIF.
        exif = D(2007, 1, 1, 12, 0, 9)
        epoch = (exif + datetime.timedelta(seconds=5)).replace(
            tzinfo=datetime.timezone.utc).timestamp()
        items = [
            {"camera_time": exif, "time_source": "exif", "mtime": epoch},
            {"camera_time": None, "time_source": None, "mtime": epoch + 60,
             "kind": "still"},
            {"camera_time": None, "time_source": None, "mtime": epoch + 120,
             "kind": "video", "duration": 30.0},
        ]
        self.assertEqual(media.calibrate(items), 0.0)
        self.assertEqual(items[1]["camera_time"], D(2007, 1, 1, 12, 1, 14))
        self.assertEqual(items[2]["camera_time"], D(2007, 1, 1, 12, 1, 44))

    def test_calibrate_detects_a_zone_shift(self):
        exif = D(2007, 1, 1, 12, 0, 0)
        # Presented seven hours off, as a local-time mount in MST would be.
        epoch = (exif + datetime.timedelta(hours=7, seconds=4)).replace(
            tzinfo=datetime.timezone.utc).timestamp()
        items = [{"camera_time": exif, "time_source": "exif", "mtime": epoch},
                 {"camera_time": None, "mtime": epoch + 30, "kind": "still"}]
        self.assertEqual(media.calibrate(items), 7 * 3600.0)
        self.assertEqual(items[1]["camera_time"], D(2007, 1, 1, 12, 0, 34))

    def test_quick_fingerprint_sees_the_middle_only_through_size(self):
        tmp = tempfile.mkdtemp()
        try:
            a = os.path.join(tmp, "a")
            b = os.path.join(tmp, "b")
            with open(a, "wb") as fh:
                fh.write(os.urandom(300000))
            shutil.copy(a, b)
            self.assertEqual(media.quick_fingerprint(a),
                             media.quick_fingerprint(b))
            with open(b, "ab") as fh:
                fh.write(b"x")
            self.assertNotEqual(media.quick_fingerprint(a),
                                media.quick_fingerprint(b))
        finally:
            shutil.rmtree(tmp)


class ArchiveTests(TempDirs):
    def test_manifest_survives_a_torn_line(self):
        arc = archive.Archive(self.arcdir)
        b = arc.new_batch("folder", "card", D(2026, 1, 1))
        arc.add_file({"sha256": "aa", "qfp": "q1:1:x", "batch": b["id"],
                      "path": "p", "kind": "still"})
        with open(arc.path, "a") as fh:
            fh.write('{"type": "file", "sha256": "bb", "qf')   # crash mid-write
        again = archive.Archive(self.arcdir)
        self.assertIn("aa", again.files)
        self.assertNotIn("bb", again.files)
        self.assertTrue(again.has("q1:1:x"))

    def test_skip_and_unskip(self):
        arc = archive.Archive(self.arcdir)
        b = arc.new_batch("folder", "card", D(2026, 1, 1))
        arc.add_file({"sha256": "aa", "qfp": "q", "batch": b["id"],
                      "path": "x/a.jpg", "kind": "still"})
        arc.skip("aa")
        self.assertEqual(archive.Archive(self.arcdir).pending(), [])
        arc.unskip("aa")
        self.assertEqual(len(archive.Archive(self.arcdir).pending()), 1)

    def test_one_writer_at_a_time(self):
        a1 = archive.Archive(self.arcdir)
        a2 = archive.Archive(self.arcdir)
        with a1.locked():
            with self.assertRaises(archive.ArchiveBusy):
                with a2.locked():
                    pass


class PullTests(TempDirs):
    def make_card(self):
        base = D(2005, 1, 1, 12, 0, 9)
        m = lambda s: base + datetime.timedelta(seconds=s)   # noqa: E731
        d = os.path.join(self.card, "DCIM", "100KC315")
        make_jpeg(os.path.join(d, "100_3166.JPG"), m(0), colour=(1, 2, 3))
        make_jpeg(os.path.join(d, "100_3167.JPG"), m(600), colour=(4, 5, 6))
        # the battery came out: the clock is back at noon
        make_jpeg(os.path.join(d, "100_3168.JPG"), m(3), colour=(7, 8, 9))
        make_jpeg(os.path.join(d, "100_3169.JPG"), m(20), colour=(9, 8, 7))
        os.makedirs(os.path.join(self.card, ".Trashes", "501"))
        make_jpeg(os.path.join(self.card, ".Trashes", "501", "old.JPG"), m(0))
        with open(os.path.join(d, "100_3166.THM"), "wb") as fh:
            fh.write(b"thumb")

    def test_pull_copies_new_files_only(self):
        self.make_card()
        now = D(2026, 9, 23, 14, 5, 0)
        arc, res = self.pull_card(now)
        self.assertEqual(len(res.new), 4)             # not .Trashes, not THM
        self.assertEqual(res.camera, "Kodak EasyShare C315")
        for rec in res.new:
            src = os.path.join(self.card, rec["orig"])
            self.assertEqual(sources.sha256_file(arc.abspath(rec["path"])),
                             sources.sha256_file(src))
        arc2, res2 = self.pull_card(now)
        self.assertEqual((len(res2.new), len(res2.skipped)), (0, 4))
        self.assertIsNone(res2.batch)

    def test_plan_from_a_pulled_card(self):
        self.make_card()
        now = D(2026, 9, 23, 14, 5, 0)
        arc, res = self.pull_card(now)
        plan = self.plan(arc)
        self.assertEqual(len(plan.sessions), 2)
        last = plan.shots[-1]
        self.assertEqual(last.label, "100_3169.JPG")
        self.assertEqual(plan.times[last.key], now)
        first = plan.shots[0]
        self.assertEqual(plan.times[first.key],
                         now - datetime.timedelta(seconds=17 + 60 + 600))

    def test_remember_marks_a_library_as_already_imported(self):
        self.make_card()
        os.makedirs(self.lib)
        shutil.copy2(os.path.join(self.card, "DCIM", "100KC315", "100_3166.JPG"),
                     self.lib)
        arc = archive.Archive(self.arcdir)
        with arc.locked():
            added, seen = sources.remember(arc, self.lib, self.log)
        self.assertEqual((added, seen), (1, 1))
        arc, res = self.pull_card()
        self.assertEqual((len(res.new), len(res.skipped)), (3, 1))

    def test_refuses_to_pull_from_the_library_or_archive(self):
        for bad in (self.lib, self.arcdir, os.path.join(self.lib, "sub"),
                    self.tmp):
            with self.assertRaises(ValueError):
                sources.check_folder(bad, self.settings)
        sources.check_folder(self.card, self.settings)

    def test_unreadable_file_is_reported_and_the_rest_come(self):
        self.make_card()
        bad = os.path.join(self.card, "DCIM", "100KC315", "100_3167.JPG")
        real_copy = sources.copy_verified

        def failing(src, dst):
            if src == bad:
                raise OSError(5, "Input/output error")
            return real_copy(src, dst)
        sources.copy_verified = failing
        try:
            arc, res = self.pull_card()
        finally:
            sources.copy_verified = real_copy
        self.assertEqual(len(res.new), 3)
        self.assertEqual(len(res.failed), 1)
        # the failed one is not remembered, so the next pull tries again
        arc, res = self.pull_card()
        self.assertEqual(len(res.new), 1)


# ---------------------------------------------------------------------------
# Developing
# ---------------------------------------------------------------------------

@unittest.skipUnless(HAVE_EXIFTOOL, "exiftool is not installed")
class DevelopTests(TempDirs):
    def develop(self, arc, overrides=()):
        plan = self.plan(arc, overrides)
        with arc.locked():
            res = develop.Developer(arc, self.settings, self.log).develop(plan)
        return plan, res

    def test_still_is_redated_and_archive_untouched(self):
        d = os.path.join(self.card, "DCIM", "100KC315")
        make_jpeg(os.path.join(d, "100_0001.JPG"), D(2005, 1, 1, 12, 0, 9))
        now = D(2026, 9, 23, 14, 5, 0)
        arc, res = self.pull_card(now)
        before = sources.sha256_file(arc.abspath(res.new[0]["path"]))
        plan, dres = self.develop(arc)
        self.assertFalse(dres.failed)
        out = os.path.join(self.lib, "100_0001.JPG")
        info = exif_of(out)
        self.assertEqual(info["DateTimeOriginal"], "2026:09:23 14:05:00")
        self.assertEqual(info["CreateDate"], "2026:09:23 14:05:00")
        self.assertEqual(info["OffsetTimeOriginal"], develop.offset_text(now))
        self.assertEqual(os.path.getmtime(out), now.timestamp())
        self.assertEqual(sources.sha256_file(arc.abspath(res.new[0]["path"])),
                         before)
        # developed once only
        self.assertEqual(archive.Archive(self.arcdir).pending(), [])

    def test_name_clash_in_library_gets_a_number(self):
        d = os.path.join(self.card, "DCIM", "100KC315")
        make_jpeg(os.path.join(d, "100_0001.JPG"), D(2005, 1, 1, 12, 0, 9))
        os.makedirs(self.lib)
        with open(os.path.join(self.lib, "100_0001.JPG"), "wb") as fh:
            fh.write(b"someone else's photo")
        arc, _ = self.pull_card()
        self.develop(arc)
        self.assertTrue(os.path.exists(os.path.join(self.lib,
                                                    "100_0001 (2).JPG")))
        with open(os.path.join(self.lib, "100_0001.JPG"), "rb") as fh:
            self.assertEqual(fh.read(), b"someone else's photo")

    @unittest.skipUnless(HAVE_FFMPEG, "ffmpeg is not installed")
    def test_mov_is_remuxed_with_identical_video(self):
        d = os.path.join(self.card, "DCIM", "100KC613")
        src = make_mov(os.path.join(d, "100_0969.MOV"), D(2007, 1, 1, 12, 5, 0))
        now = D(2026, 9, 23, 14, 5, 0)
        arc, res = self.pull_card(now)
        plan, dres = self.develop(arc)
        self.assertFalse(dres.failed, dres.failed)
        out = os.path.join(self.lib, "100_0969.mp4")
        self.assertTrue(os.path.exists(out))
        self.assertEqual(develop.video_digest(src), develop.video_digest(out))
        streams = develop.probe(out)["streams"]
        self.assertEqual([s["codec_name"] for s in streams], ["mjpeg", "aac"])
        info = exif_of(out)
        # QuickTimeUTC reads the UTC stored value back as local time
        self.assertTrue(info["CreateDate"].startswith("2026:09:23 14:05:00"),
                        info)

    def test_override_reaches_the_file(self):
        d = os.path.join(self.card, "DCIM", "100KC315")
        make_jpeg(os.path.join(d, "100_0001.JPG"), D(2005, 1, 1, 12, 0, 9))
        make_jpeg(os.path.join(d, "100_0002.JPG"), D(2005, 1, 1, 12, 1, 9),
                  colour=(0, 0, 0))
        arc, _ = self.pull_card()
        self.develop(arc, [timeplan.parse_override("2026-09-12 19:00")])
        self.assertEqual(exif_of(os.path.join(self.lib, "100_0002.JPG"))
                         ["DateTimeOriginal"], "2026:09:12 19:01:00")

    def test_raw_with_a_jpeg_twin_stays_in_the_archive(self):
        d = os.path.join(self.card, "DCIM", "100MSDCF")
        make_jpeg(os.path.join(d, "DSC00001.JPG"), D(2012, 1, 1, 9, 0, 0))
        with open(os.path.join(d, "DSC00001.ARW"), "wb") as fh:
            fh.write(b"II*\x00" + os.urandom(1000))
        arc, res = self.pull_card()
        plan, dres = self.develop(arc)
        self.assertEqual(len(dres.archive_only), 1)
        self.assertFalse(os.path.exists(os.path.join(self.lib, "DSC00001.ARW")))


@unittest.skipUnless(HAVE_EXIFTOOL, "exiftool is not installed")
class SipixTests(TempDirs):
    def test_blink_ii_pull_and_develop(self):
        from simcam import make_cam, make_jpeg as sim_jpeg
        blobs = [(sim_jpeg(seed=3), False), (sim_jpeg(seed=9), False)]
        cam, sim = make_cam(blobs)
        real = blinky.Blink2
        blinky.Blink2 = lambda log, *a, **kw: cam
        cam.open = lambda handshake=True: cam
        try:
            arc = archive.Archive(self.arcdir)
            src = sources.Source("sipix", "sipix", "SiPix Blink II")
            now = D(2026, 9, 23, 14, 5, 0)
            with arc.locked():
                res = sources.pull(src, arc, self.log, now=now)
            self.assertEqual(len(res.new), 2)
            with arc.locked():
                res2 = sources.pull(src, arc, self.log, now=now)
            self.assertEqual((len(res2.new), len(res2.skipped)), (0, 2))
        finally:
            blinky.Blink2 = real
        plan = cli.build_plan(arc, self.settings, [], self.log)
        with arc.locked():
            develop.Developer(arc, self.settings, self.log).develop(plan)
        out = os.path.join(self.lib, "image0001.jpg")
        self.assertTrue(os.path.exists(out))
        info = exif_of(out)
        self.assertEqual(info["DateTimeOriginal"], "2026:09:23 14:05:00")
        self.assertEqual(info["Model"], "StyleCam Blink II")
        from PIL import Image
        with Image.open(out) as img:
            self.assertEqual(img.size, (640, 480))


# ---------------------------------------------------------------------------
# Command line and gphoto2 parsing
# ---------------------------------------------------------------------------

class ParsingTests(unittest.TestCase):
    def test_autodetect(self):
        text = """Model                          Port
----------------------------------------------------------
Kodak EasyShare C613           usb:001,012
SiPix Blink 2                  usb:003,009
Mass Storage Camera            disk:/run/media/me/KODAK
"""
        self.assertEqual(sources.parse_autodetect(text),
                         [("Kodak EasyShare C613", "usb:001,012")])

    def test_list_files(self):
        text = """There is no file in folder '/'.
There is no file in folder '/store_00010001'.
There are 2 files in folder '/store_00010001/DCIM/100KC613':
#1     100_0001.JPG               rd  1532 KB 2848x2134 image/jpeg 1167652809
#2     100_0002.MOV               rd 17264 KB image/quicktime 1167652900
"""
        self.assertEqual(sources.parse_list_files(text), [
            ("/store_00010001/DCIM/100KC613", "100_0001.JPG"),
            ("/store_00010001/DCIM/100KC613", "100_0002.MOV")])


@unittest.skipUnless(HAVE_EXIFTOOL, "exiftool is not installed")
class CliTests(TempDirs):
    def run_cli(self, *argv):
        buf = io.StringIO()
        real = sys.stdout
        sys.stdout = buf
        try:
            rc = cli.main(list(argv) + ["--library", self.lib,
                                        "--archive", self.arcdir, "-q"])
        finally:
            sys.stdout = real
        return rc, buf.getvalue()

    def test_import_from_folder(self):
        d = os.path.join(self.card, "DCIM", "100KC315")
        make_jpeg(os.path.join(d, "100_0001.JPG"), D(2005, 1, 1, 12, 0, 9))
        make_jpeg(os.path.join(d, "100_0002.JPG"), D(2005, 1, 1, 12, 0, 30),
                  colour=(0, 9, 9))
        rc, out = self.run_cli("import", "--from", self.card, "--yes",
                               "--date", "S1=2026-09-12 19:00")
        self.assertEqual(rc, 0, out)
        self.assertIn("2 files in", out)
        self.assertEqual(exif_of(os.path.join(self.lib, "100_0002.JPG"))
                         ["DateTimeOriginal"], "2026:09:12 19:00:21")
        rc, out = self.run_cli("plan")
        self.assertIn("Nothing is waiting", out)

    def test_plan_rejects_a_session_that_is_not_there(self):
        d = os.path.join(self.card, "DCIM", "100KC315")
        make_jpeg(os.path.join(d, "100_0001.JPG"), D(2005, 1, 1, 12, 0, 9))
        self.run_cli("pull", "--from", self.card)
        rc, out = self.run_cli("plan", "--date", "S5=now")
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
