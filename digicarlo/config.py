"""Settings: where things go, and how dates are spread.

Stored as an INI file at $XDG_CONFIG_HOME/digicarlo/digicarlo.conf. Command
line options override it; the window writes to it when a folder is changed.
"""

import configparser
import os

from . import blinky

CONFIG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
    "digicarlo")
CONFIG_PATH = os.path.join(CONFIG_DIR, "digicarlo.conf")

# pictures_dir honours XDG and localised folder names; Blinky already has it.
PICTURES = blinky._pictures_dir()

DEFAULTS = {
    "folders": {
        # Re-dated, remuxed copies: the folder that gets synced or browsed.
        "library": os.path.join(PICTURES, "DigiCarlo"),
        # The camera's exact bytes, one folder per pull. Never synced, never
        # modified, and the thing everything in the library can be rebuilt
        # from.
        "archive": os.path.join(PICTURES, "DigiCarlo Archive"),
    },
    "dates": {
        # A jump forward bigger than this between two consecutive shots is
        # taken to be the clock being set, not the camera sitting in a drawer.
        "max_gap_days": "30",
        # Sessions whose real spacing is unknown are placed this far apart.
        "session_spacing_seconds": "60",
        # Cameras whose clock can be set right but sometimes resets: every
        # pull from one asks, session by session, whether to trust it.
        # Matched against the camera's model, ignoring case and hyphens.
        "trust_clock_cameras": "i1237, KD-400Z",
    },
    "sipix": {
        # jpeg carries EXIF dates that every photo service reads; png is
        # lossless but its date support is patchy.
        "still_format": "jpeg",
        "jpeg_quality": "95",
    },
    "window": {
        # The horn honks, and a job that finishes beeps twice.
        "sounds": "yes",
    },
    "video": {
        # Audio that MP4 cannot hold (8-bit PCM and the like) becomes AAC at
        # this rate; the video stream is always copied untouched.
        "aac_bitrate": "128k",
    },
}


class Settings:
    def __init__(self, path=CONFIG_PATH):
        self.path = path
        self.cp = configparser.ConfigParser(interpolation=None)
        self.cp.read_dict(DEFAULTS)
        self.cp.read(path)

    def _get(self, section, key):
        return self.cp.get(section, key)

    @property
    def library(self):
        return os.path.expanduser(self._get("folders", "library"))

    @property
    def archive(self):
        return os.path.expanduser(self._get("folders", "archive"))

    @property
    def max_gap_days(self):
        return self.cp.getfloat("dates", "max_gap_days")

    @property
    def session_spacing(self):
        return self.cp.getfloat("dates", "session_spacing_seconds")

    @property
    def sipix_format(self):
        fmt = self._get("sipix", "still_format").strip().lower()
        return fmt if fmt in ("jpeg", "png") else "jpeg"

    @property
    def jpeg_quality(self):
        return self.cp.getint("sipix", "jpeg_quality")

    @property
    def trust_clock_cameras(self):
        return [c.strip() for c in self._get("dates", "trust_clock_cameras").split(",")
                if c.strip()]

    def asks_about_clock(self, camera):
        """Whether pulls from `camera` should ask about trusting its clock."""
        return any(self.asks_about_clock_static(c, camera)
                   for c in self.trust_clock_cameras)

    @staticmethod
    def asks_about_clock_static(pattern, camera):
        """Whether `camera` is the model `pattern` names (ignoring case,
        spaces and hyphens)."""
        def norm(t):
            return "".join(ch for ch in (t or "").lower() if ch.isalnum())
        return bool(norm(pattern)) and norm(pattern) in norm(camera)

    def places(self):
        """Saved places, [(name, latitude, longitude)], as [places] holds
        them: one per line, "name | latitude, longitude"."""
        out = []
        if not self.cp.has_section("places"):
            return out
        for key, value in self.cp.items("places"):
            name, _, where = value.rpartition("|")
            try:
                lat, lon = (float(v) for v in where.split(","))
            except ValueError:
                continue
            if name.strip():
                out.append((name.strip(), lat, lon))
        return out

    def add_place(self, name, lat, lon):
        """Save a place (replacing one of the same name)."""
        name = name.replace("|", "/").strip()
        kept = [p for p in self.places() if p[0].lower() != name.lower()]
        kept.append((name, float(lat), float(lon)))
        self.cp.remove_section("places")
        self.cp.add_section("places")
        for n, (pname, plat, plon) in enumerate(kept, 1):
            self.cp.set("places", "place%d" % n, "%s | %.6f, %.6f" % (pname, plat, plon))

    @property
    def sounds(self):
        return self.cp.getboolean("window", "sounds", fallback=True)

    @property
    def aac_bitrate(self):
        return self._get("video", "aac_bitrate").strip()

    def set(self, section, key, value):
        if not self.cp.has_section(section):
            self.cp.add_section(section)
        self.cp.set(section, key, str(value))

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        # Only write what differs from the defaults, so a later release can
        # change a default without every existing config pinning the old one.
        out = configparser.ConfigParser(interpolation=None)
        for section in self.cp.sections():
            for key, value in self.cp.items(section):
                if DEFAULTS.get(section, {}).get(key) != value:
                    if not out.has_section(section):
                        out.add_section(section)
                    out.set(section, key, value)
        tmp = self.path + ".part"
        with open(tmp, "w") as fh:
            fh.write("# DigiCarlo settings. Anything not listed uses the "
                     "built-in default.\n")
            out.write(fh)
        os.replace(tmp, self.path)
