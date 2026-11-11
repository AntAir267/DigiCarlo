"""Whether the sun is up: the garage window shows night from sunset to sunrise.

Sunset and sunrise are when the sun's top edge meets the horizon, as the
almanacs have it: its middle 0.833 degrees below, for the air bending its
light and its own size. Where it is worked out for comes from the
`location` setting if there is one, otherwise from the computer's time zone:
the tz database gives every zone the place it is named for (America/Phoenix
is Phoenix), and that is near enough for a sunset to within minutes. With
no named zone at all, the clock's offset from UTC stands in for a longitude.

The sun's position is NOAA's (the Astronomical Algorithms one their solar
calculator uses), good to a minute or so for centuries either side of now.
"""

import datetime
import math
import os

HORIZON = -0.833          # degrees: the sun's middle at sunrise and sunset
ZONEINFO = "/usr/share/zoneinfo"


def elevation(when, lat, lon):
    """The sun's height above the horizon, in degrees, at `when` (an aware
    datetime, or a naive one in local time) seen from lat, lon (degrees,
    north and east positive)."""
    if when.tzinfo is None:
        when = when.astimezone()
    utc = when.astimezone(datetime.timezone.utc)
    jd = utc.timestamp() / 86400.0 + 2440587.5
    t = (jd - 2451545.0) / 36525.0                      # Julian centuries since J2000
    L0 = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360
    M = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    Mr = math.radians(M)
    centre = (math.sin(Mr) * (1.914602 - t * (0.004817 + 0.000014 * t))
              + math.sin(2 * Mr) * (0.019993 - 0.000101 * t)
              + math.sin(3 * Mr) * 0.000289)
    omega = math.radians(125.04 - 1934.136 * t)
    apparent = math.radians(L0 + centre - 0.00569 - 0.00478 * math.sin(omega))
    obliquity = (23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60
                 + 0.00256 * math.cos(omega))
    ob = math.radians(obliquity)
    decl = math.asin(math.sin(ob) * math.sin(apparent))
    y = math.tan(ob / 2) ** 2
    L0r = math.radians(L0)
    eq_time = 4 * math.degrees(y * math.sin(2 * L0r) - 2 * e * math.sin(Mr)
                               + 4 * e * y * math.sin(Mr) * math.cos(2 * L0r)
                               - 0.5 * y * y * math.sin(4 * L0r)
                               - 1.25 * e * e * math.sin(2 * Mr))   # minutes
    minutes = utc.hour * 60 + utc.minute + (utc.second + utc.microsecond / 1e6) / 60
    solar = (minutes + eq_time + 4 * lon) % 1440        # true solar time, minutes
    hour_angle = math.radians(solar / 4 - 180)
    la = math.radians(lat)
    cos_zenith = (math.sin(la) * math.sin(decl)
                  + math.cos(la) * math.cos(decl) * math.cos(hour_angle))
    return 90 - math.degrees(math.acos(max(-1.0, min(1.0, cos_zenith))))


def is_night(when, lat, lon):
    """Whether it is between sunset and sunrise at `when`."""
    return elevation(when, lat, lon) < HORIZON


def next_change(when, lat, lon, within=datetime.timedelta(days=2)):
    """The next sunrise or sunset after `when` (to the second), or None if
    the sun neither rises nor sets that soon (a polar day or night)."""
    if when.tzinfo is None:
        when = when.astimezone()
    night = is_night(when, lat, lon)
    step = datetime.timedelta(minutes=10)
    a, end = when, when + within
    while a < end:
        b = a + step
        if is_night(b, lat, lon) != night:
            while b - a > datetime.timedelta(seconds=1):
                mid = a + (b - a) / 2
                if is_night(mid, lat, lon) == night:
                    a = mid
                else:
                    b = mid
            return b.replace(microsecond=0)
        a = b
    return None


# -- where -----------------------------------------------------------------------

def parse_iso6709(text):
    """'+332654-1120424' (as zone1970.tab writes a place) -> (33.448, -112.073)."""
    i = max(text.rfind("+"), text.rfind("-"))
    if i <= 0:
        raise ValueError("not a place: %r" % text)

    def angle(part, degree_digits):
        sign = -1 if part[0] == "-" else 1
        digits = part[1:]
        if not digits.isdigit():
            raise ValueError("not a place: %r" % text)
        d = int(digits[:degree_digits])
        m = int(digits[degree_digits:degree_digits + 2] or 0)
        s = int(digits[degree_digits + 2:degree_digits + 4] or 0)
        return sign * (d + m / 60 + s / 3600)
    return angle(text[:i], 2), angle(text[i:], 3)


def zone_places(zoneinfo=ZONEINFO):
    """{zone name: (lat, lon)} from the tz database's zone tables."""
    places = {}
    for table in ("zone.tab", "zone1970.tab"):       # the second wins
        try:
            with open(os.path.join(zoneinfo, table), encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("#"):
                        continue
                    cols = line.rstrip("\n").split("\t")
                    if len(cols) >= 3:
                        try:
                            places[cols[2]] = parse_iso6709(cols[1])
                        except ValueError:
                            pass
        except OSError:
            pass
    return places


def zone_name(environ=None, etc="/etc"):
    """The computer's time zone, as a tz database name, or None."""
    environ = os.environ if environ is None else environ
    tz = (environ.get("TZ") or "").lstrip(":")
    if "/" in tz and not tz.startswith("/"):
        return tz
    if tz.startswith("/") and "zoneinfo/" in tz:
        return tz.split("zoneinfo/", 1)[1]
    try:
        target = os.path.realpath(os.path.join(etc, "localtime"))
        if "zoneinfo/" in target:
            return target.split("zoneinfo/", 1)[1]
    except OSError:
        pass
    try:
        with open(os.path.join(etc, "timezone"), encoding="utf-8") as fh:
            name = fh.read().strip()
            return name or None
    except OSError:
        return None


def where(setting="", environ=None, etc="/etc", zoneinfo=ZONEINFO, now=None):
    """(lat, lon) to work sunsets out for: the `location` setting
    ("latitude, longitude"), else the place the time zone is named for,
    else 40 degrees north at the longitude the clock's offset from UTC
    implies."""
    if setting and setting.strip():
        try:
            lat, lon = (float(v) for v in setting.split(","))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
        except ValueError:
            pass
    name = zone_name(environ, etc)
    if name:
        place = zone_places(zoneinfo).get(name)
        if place:
            return place
    now = now or datetime.datetime.now().astimezone()
    offset = now.utcoffset() - (now.dst() or datetime.timedelta(0))
    return 40.0, max(-180.0, min(180.0, offset.total_seconds() / 240.0))
