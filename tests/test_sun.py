#!/usr/bin/env python3
"""Day and night: the sun's height, sunsets and sunrises, and where the
computer is.

    python3 tests/test_sun.py

The sunsets are checked against the published ones for the solstices; the
places come from small stand-in copies of the tz database's tables.
"""

import datetime
import os
import shutil
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from digicarlo import sun  # noqa: E402

PHOENIX = (33.4484, -112.0740)
CHICAGO = (41.8781, -87.6298)
TROMSO = (69.6496, 18.9560)
MST = ZoneInfo("America/Phoenix")
CENTRAL = ZoneInfo("America/Chicago")


class SunTests(unittest.TestCase):
    def assertNear(self, when, h, m, minutes=3):
        self.assertLessEqual(abs((when.hour * 60 + when.minute) - (h * 60 + m)), minutes,
                             "%s is not about %d:%02d" % (when, h, m))

    def test_noon_and_midnight(self):
        noon = datetime.datetime(2026, 6, 21, 12, 30, tzinfo=MST)
        self.assertGreater(sun.elevation(noon, *PHOENIX), 75)
        self.assertFalse(sun.is_night(noon, *PHOENIX))
        midnight = datetime.datetime(2026, 6, 22, 0, 30, tzinfo=MST)
        self.assertLess(sun.elevation(midnight, *PHOENIX), -30)
        self.assertTrue(sun.is_night(midnight, *PHOENIX))

    def test_phoenix_winter_solstice(self):
        # published: sunset 5:24 pm, sunrise 7:29 am the next day
        noon = datetime.datetime(2026, 12, 21, 12, 0, tzinfo=MST)
        sunset = sun.next_change(noon, *PHOENIX).astimezone(MST)
        self.assertNear(sunset, 17, 24)
        sunrise = sun.next_change(sunset + datetime.timedelta(minutes=1), *PHOENIX).astimezone(MST)
        self.assertEqual(sunrise.date(), datetime.date(2026, 12, 22))
        self.assertNear(sunrise, 7, 29)
        self.assertTrue(sun.is_night(sunset + datetime.timedelta(minutes=2), *PHOENIX))
        self.assertFalse(sun.is_night(sunset - datetime.timedelta(minutes=2), *PHOENIX))

    def test_chicago_summer_solstice(self):
        # published: sunset 8:29 pm (daylight time), sunrise 5:15 am
        noon = datetime.datetime(2026, 6, 21, 12, 0, tzinfo=CENTRAL)
        sunset = sun.next_change(noon, *CHICAGO).astimezone(CENTRAL)
        self.assertNear(sunset, 20, 29)
        sunrise = sun.next_change(sunset + datetime.timedelta(minutes=1), *CHICAGO).astimezone(CENTRAL)
        self.assertNear(sunrise, 5, 15)

    def test_a_naive_time_is_local(self):
        when = datetime.datetime(2026, 3, 1, 9, 0)
        self.assertAlmostEqual(sun.elevation(when, *PHOENIX),
                               sun.elevation(when.astimezone(), *PHOENIX), places=6)

    def test_polar_night_and_midnight_sun(self):
        oslo = ZoneInfo("Europe/Oslo")
        noon = datetime.datetime(2026, 12, 21, 12, 0, tzinfo=oslo)
        self.assertTrue(sun.is_night(noon, *TROMSO))
        self.assertIsNone(sun.next_change(noon, *TROMSO))
        midnight = datetime.datetime(2026, 6, 21, 0, 30, tzinfo=oslo)
        self.assertFalse(sun.is_night(midnight, *TROMSO))
        self.assertIsNone(sun.next_change(midnight, *TROMSO))


class WhereTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="digicarlo-sun-")
        self.zoneinfo = os.path.join(self.tmp, "zoneinfo")
        os.makedirs(os.path.join(self.zoneinfo, "America"))
        with open(os.path.join(self.zoneinfo, "zone1970.tab"), "w") as fh:
            fh.write("# comment\n"
                     "US\t+415100-0873900\tAmerica/Chicago\tCentral (most areas)\n"
                     "US,CA\t+332654-1120424\tAmerica/Phoenix\tMST - AZ (most areas)\n")
        with open(os.path.join(self.zoneinfo, "zone.tab"), "w") as fh:
            fh.write("NO\t+5955+01045\tEurope/Oslo\n")
        open(os.path.join(self.zoneinfo, "America", "Phoenix"), "w").close()
        self.etc = os.path.join(self.tmp, "etc")
        os.makedirs(self.etc)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_parse_places(self):
        lat, lon = sun.parse_iso6709("+332654-1120424")
        self.assertAlmostEqual(lat, 33.4483, places=3)
        self.assertAlmostEqual(lon, -112.0733, places=3)
        self.assertEqual(sun.parse_iso6709("+5955+01045"), (59 + 55 / 60, 10 + 45 / 60))
        with self.assertRaises(ValueError):
            sun.parse_iso6709("nowhere")

    def test_zone_from_localtime_link(self):
        os.symlink(os.path.join(self.zoneinfo, "America", "Phoenix"),
                   os.path.join(self.etc, "localtime"))
        self.assertEqual(sun.zone_name({}, self.etc), "America/Phoenix")
        lat, lon = sun.where("", {}, self.etc, self.zoneinfo)
        self.assertAlmostEqual(lat, 33.448, places=2)
        self.assertAlmostEqual(lon, -112.073, places=2)

    def test_zone_from_tz_and_etc_timezone(self):
        self.assertEqual(sun.zone_name({"TZ": ":America/Chicago"}, self.etc), "America/Chicago")
        with open(os.path.join(self.etc, "timezone"), "w") as fh:
            fh.write("Europe/Oslo\n")
        self.assertEqual(sun.zone_name({}, self.etc), "Europe/Oslo")
        self.assertAlmostEqual(sun.where("", {}, self.etc, self.zoneinfo)[0], 59.917, places=2)

    def test_the_setting_wins(self):
        os.symlink(os.path.join(self.zoneinfo, "America", "Phoenix"),
                   os.path.join(self.etc, "localtime"))
        self.assertEqual(sun.where("41.88, -87.63", {}, self.etc, self.zoneinfo), (41.88, -87.63))
        # nonsense in the setting falls back to the time zone
        self.assertAlmostEqual(sun.where("up north", {}, self.etc, self.zoneinfo)[0], 33.448, places=2)

    def test_no_zone_uses_the_clock_offset(self):
        now = datetime.datetime(2026, 7, 1, 12, 0, tzinfo=CENTRAL)     # daylight time
        lat, lon = sun.where("", {}, self.etc, self.zoneinfo, now=now)
        self.assertEqual((lat, lon), (40.0, -90.0))                    # standard time's -6 h


if __name__ == "__main__":
    unittest.main(verbosity=2)
