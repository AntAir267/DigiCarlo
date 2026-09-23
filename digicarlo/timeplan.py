"""Sessions, and the date each shot will be given.

A camera with a wrong clock is still a good stopwatch. Between two battery
pulls its clock runs steadily, so the gap between two shots is right even when
both dates are years out. DigiCarlo keeps those gaps and replaces only where
the run sits in time.

A *session* is a run of shots over which the camera's clock ran unbroken. A
new one starts wherever the clock goes backwards (a reset: the Kodaks jump
back to 2007-01-01 12:00, the C315 to 2005-01-01) or leaps forward further than
anyone leaves a camera in a drawer (the clock being set).

By default, each pull's last shot is dated when it came off the camera, and
earlier sessions are stacked back from there, a minute apart, because how
long really passed between sessions is exactly what a reset destroys. Any run
of shots can instead be given a start time -- or keep the camera's own dates,
for the rare camera whose clock is right. Overridden shots never move the ones
around them.
"""

import datetime
import re

DAY = 86400.0

# A clock going backwards by less than this is jitter -- a clip's start time
# against the photo before it -- not a reset.
BACKSTEP_TOLERANCE = 120.0


class Shot:
    def __init__(self, key, batch, camera_time, label=""):
        self.key = key
        self.batch = batch
        self.camera_time = camera_time
        self.label = label
        self.number = 0            # 1-based, across the whole plan
        self.session = None


class Session:
    def __init__(self, batch, shots):
        self.batch = batch
        self.shots = shots
        self.number = 0            # S1, S2 ... across the whole plan
        self.offsets = session_offsets([s.camera_time for s in shots])

    @property
    def span(self):
        return self.offsets[-1] if self.offsets else 0.0

    def camera_range(self):
        known = [s.camera_time for s in self.shots if s.camera_time]
        return (min(known), max(known)) if known else (None, None)


class Batch:
    """One pull from one camera: its shots in shooting order, and when they
    came off the camera."""

    def __init__(self, ident, anchor, shots, label=""):
        self.id = ident
        self.anchor = anchor
        self.shots = shots
        self.label = label


class Override:
    """A selector ('all', sessions a-b, shots a-b, or a set of shots picked
    in the window) and what to do with it: start at a datetime, or keep the
    camera's dates."""

    def __init__(self, scope, first, last, when, text="", keys=None):
        self.scope = scope          # "all" | "sessions" | "shots" | "keys"
        self.first = first
        self.last = last
        self.when = when            # datetime, or "camera"
        self.text = text
        self.keys = set(keys or ())

    def describe(self):
        if self.scope == "keys":
            n = len(self.keys)
            what = "%d shot%s" % (n, "" if n == 1 else "s")
            if self.when == "camera":
                return "%s: camera's own dates" % what
            return "%s: from %s" % (what, fmt(self.when))
        what = {"all": "everything",
                "sessions": "S%d" % self.first if self.first == self.last
                else "S%d-S%d" % (self.first, self.last),
                "shots": "shot %d" % self.first if self.first == self.last
                else "shots %d-%d" % (self.first, self.last)}[self.scope]
        if self.when == "camera":
            return "%s: camera's own dates" % what
        return "%s: from %s" % (what, fmt(self.when))


class Group:
    """A run of shots that share a session and a rule; what the window and
    'digicarlo plan' show."""

    def __init__(self, session, rule, shots, times):
        self.session = session
        self.rule = rule            # None (automatic) or an Override
        self.shots = shots
        self.times = times

    @property
    def start(self):
        return self.times[0]

    @property
    def end(self):
        return self.times[-1]


class Plan:
    def __init__(self, batches, sessions, shots, times, rules, groups):
        self.batches = batches
        self.sessions = sessions
        self.shots = shots
        self.times = times          # shot key -> datetime
        self.rules = rules          # shot key -> Override or None
        self.groups = groups


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def split(shots, max_gap_days=30.0):
    """Cut a pull's shots, in shooting order, where the clock broke."""
    max_gap = max_gap_days * DAY
    runs, cur, prev = [], [], None
    for shot in shots:
        t = shot.camera_time
        if cur and t is not None and prev is not None:
            step = (t - prev).total_seconds()
            if step < -BACKSTEP_TOLERANCE or step > max_gap:
                runs.append(cur)
                cur = []
        cur.append(shot)
        if t is not None:
            prev = t
    if cur:
        runs.append(cur)
    return runs


def session_offsets(times):
    """Seconds from a session's first shot, strictly increasing.

    Shots the camera gave no time (the SiPix has no clock at all) sit a
    second after the one before. Shots stamped in the same second, or a
    little out of order, are nudged a second apart, so the order they were
    shot in survives into any photo library that sorts by date.
    """
    if not times:
        return []
    known = [t for t in times if t is not None]
    if not known:
        return [float(i) for i in range(len(times))]
    base = known[0]
    out = [None if t is None else (t - base).total_seconds() for t in times]
    first = next(i for i, v in enumerate(out) if v is not None)
    for i in range(first - 1, -1, -1):
        out[i] = out[i + 1] - 1.0
    for i in range(first + 1, len(out)):
        if out[i] is None:
            out[i] = out[i - 1] + 1.0
    for i in range(1, len(out)):
        if out[i] < out[i - 1] + 1.0:
            out[i] = out[i - 1] + 1.0
    shift = out[0]
    return [v - shift for v in out]


def build(batches, overrides=(), max_gap_days=30.0, spacing=60.0):
    """Number shots and sessions, and work out every shot's date."""
    shots, sessions = [], []
    for batch in batches:
        for run in split(batch.shots, max_gap_days):
            sessions.append(Session(batch, run))
    for n, sess in enumerate(sessions, 1):
        sess.number = n
        for shot in sess.shots:
            shot.session = sess
            shots.append(shot)
    for n, shot in enumerate(shots, 1):
        shot.number = n

    times = _automatic(batches, sessions, spacing)
    rules = {s.key: None for s in shots}
    for ov in overrides:
        for shot in _covered(ov, shots, sessions):
            rules[shot.key] = ov
    for ov in overrides:
        mine = [s for s in shots if rules[s.key] is ov]
        times.update(_overridden(ov, mine, spacing))

    groups = []
    for sess in sessions:
        run = []
        for shot in sess.shots:
            if run and rules[run[-1].key] is not rules[shot.key]:
                groups.append(Group(sess, rules[run[0].key], run,
                                    [times[s.key] for s in run]))
                run = []
            run.append(shot)
        if run:
            groups.append(Group(sess, rules[run[0].key], run,
                                [times[s.key] for s in run]))
    return Plan(batches, sessions, shots, times, rules, groups)


def _automatic(batches, sessions, spacing):
    """Each pull's last shot at the moment it came off the camera, sessions
    stacked back from there `spacing` seconds apart."""
    times = {}
    for batch in batches:
        mine = [s for s in sessions if s.batch is batch]
        end = batch.anchor
        for sess in reversed(mine):
            start = end - datetime.timedelta(seconds=sess.span)
            for shot, off in zip(sess.shots, sess.offsets):
                times[shot.key] = _whole(start + datetime.timedelta(seconds=off))
            end = start - datetime.timedelta(seconds=spacing)
    return times


def _covered(ov, shots, sessions):
    if ov.scope == "all":
        return list(shots)
    if ov.scope == "sessions":
        return [s for s in shots if ov.first <= s.session.number <= ov.last]
    if ov.scope == "keys":
        return [s for s in shots if s.key in ov.keys]
    return [s for s in shots if ov.first <= s.number <= ov.last]


def _overridden(ov, shots, spacing):
    """Times for the shots an override governs: runs within one session keep
    their camera gaps; successive runs follow one another."""
    times = {}
    if ov.when == "camera":
        last = None
        for shot in shots:
            t = shot.camera_time
            if t is None:
                t = (last + datetime.timedelta(seconds=1)) if last else None
            times[shot.key] = t
            last = t or last
        # A clockless shot before any dated one borrows the next date.
        pending = [s for s in shots if times[s.key] is None]
        if pending:
            nxt = next((times[s.key] for s in shots if times[s.key]), None)
            for n, shot in enumerate(reversed(pending), 1):
                times[shot.key] = (nxt or datetime.datetime.now().replace(
                    microsecond=0)) - datetime.timedelta(seconds=n)
        return times
    runs = []
    for shot in shots:
        if runs and runs[-1][-1].session is shot.session \
                and runs[-1][-1].number == shot.number - 1:
            runs[-1].append(shot)
        else:
            runs.append([shot])
    start = ov.when
    for run in runs:
        offs = session_offsets([s.camera_time for s in run])
        for shot, off in zip(run, offs):
            times[shot.key] = _whole(start + datetime.timedelta(seconds=off))
        start = times[run[-1].key] + datetime.timedelta(seconds=spacing)
    return times


def _whole(dt):
    return dt.replace(microsecond=0)


# ---------------------------------------------------------------------------
# Parsing what the user asked for
# ---------------------------------------------------------------------------

class PlanError(ValueError):
    pass


_SEL_RE = re.compile(r"^\s*(S?)(\d+)\s*(?:-\s*(S?)(\d+))?\s*$", re.I)


def parse_override(text, now=None):
    """'S2=2026-09-12 19:00', '12-30=yesterday 18:00', 'S3=camera', or a bare
    date for everything."""
    selector, value = None, text
    if "=" in text:
        left, right = text.split("=", 1)
        if _SEL_RE.match(left):
            selector, value = left, right
    when = parse_when(value, now)
    if selector is None:
        return Override("all", None, None, when, text)
    m = _SEL_RE.match(selector)
    s1, a, s2, b = m.groups()
    a = int(a)
    b = int(b) if b else a
    if s2 and not s1:
        raise PlanError("%r mixes a shot number with a session" % selector)
    if b < a:
        raise PlanError("%r runs backwards" % selector)
    if a < 1:
        raise PlanError("numbering starts at 1 in %r" % selector)
    return Override("sessions" if s1 else "shots", a, b, when, text)


def parse_when(text, now=None):
    """A date, a date and time, 'now', 'today 14:00', 'yesterday 18:30', or
    'camera'. A bare date means noon: the middle of whatever day it was."""
    now = (now or datetime.datetime.now()).replace(microsecond=0)
    t = text.strip().lower()
    if t in ("camera", "keep", "camera's"):
        return "camera"
    if t == "now":
        return now
    day = None
    for word, delta in (("today", 0), ("yesterday", 1)):
        if t == word or t.startswith(word + " "):
            day = (now - datetime.timedelta(days=delta)).date()
            t = t[len(word):].strip()
            break
    if day is not None:
        if not t:
            return datetime.datetime.combine(day, datetime.time(12, 0))
        clock = _parse_clock(t)
        if clock is None:
            raise PlanError("cannot read the time in %r" % text)
        return datetime.datetime.combine(day, clock)
    for fmt_ in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S",
                 "%Y-%m-%dT%H:%M", "%Y:%m:%d %H:%M:%S", "%Y/%m/%d %H:%M",
                 "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.datetime.strptime(text.strip(), fmt_)
        except ValueError:
            pass
    m = re.match(r"^(\d{4}[-/]\d{1,2}[-/]\d{1,2})\s+(.+)$", text.strip())
    if m:
        d = _parse_date(m.group(1))
        clock = _parse_clock(m.group(2))
        if d and clock:
            return datetime.datetime.combine(d, clock)
    d = _parse_date(text.strip())
    if d:
        return datetime.datetime.combine(d, datetime.time(12, 0))
    raise PlanError("cannot read %r as a date; try 2026-09-12 19:00, "
                    "'yesterday 18:00', 'now' or 'camera'" % text)


def _parse_date(text):
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", text)
    if not m:
        return None
    try:
        return datetime.date(*(int(g) for g in m.groups()))
    except ValueError:
        return None


def _parse_clock(text):
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?(?::(\d{2}))?\s*(am|pm)?$",
                 text.strip().lower())
    if not m:
        return None
    h, mi, s, ampm = m.groups()
    h, mi, s = int(h), int(mi or 0), int(s or 0)
    if ampm:
        if not 1 <= h <= 12:
            return None
        h = h % 12 + (12 if ampm == "pm" else 0)
    try:
        return datetime.time(h, mi, s)
    except ValueError:
        return None


def fmt(dt):
    if dt is None:
        return "?"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def fmt_span(a, b):
    if a is None:
        return "no clock"
    if b is None or a == b:
        return fmt(a)
    if a.date() == b.date():
        return "%s - %s" % (fmt(a), b.strftime("%H:%M:%S"))
    return "%s - %s" % (fmt(a), fmt(b))
