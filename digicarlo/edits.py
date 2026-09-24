"""What is decided on the Photo Board, kept until the shots are developed.

Two kinds of decision:

  dates     which shots start at a date given, keep the camera's own, or
            go back to automatic -- timeplan overrides over sets of shots
  edits     per shot: a quarter-turn rotation, a title, a place, and the
            red-eye fixes to make in the library copy

Both are saved after every change (to board.json beside the settings), so
closing the window loses nothing, and dropped once their shots are developed
or left out. Every change can be undone, one step at a time, back to when
the window opened.

Nothing here touches the archive: the archive copy of a shot never changes,
and all of this is applied to the library copy as it is made.
"""

import copy
import datetime
import json
import os

from . import timeplan

UNDO_STEPS = 50


class Edit:
    def __init__(self):
        self.rotate = 0             # quarter turns clockwise, 0-3
        self.title = ""
        self.place = None           # (name, latitude, longitude)
        self.redeye = None          # [(x, y, w, h)] in the archive copy's pixels

    def empty(self):
        return not (self.rotate or self.title or self.place or self.redeye)

    def to_json(self):
        out = {}
        if self.rotate:
            out["rotate"] = self.rotate
        if self.title:
            out["title"] = self.title
        if self.place:
            out["place"] = list(self.place)
        if self.redeye:
            out["redeye"] = [list(b) for b in self.redeye]
        return out

    @classmethod
    def from_json(cls, d):
        e = cls()
        e.rotate = int(d.get("rotate") or 0) % 4
        e.title = d.get("title") or ""
        p = d.get("place")
        e.place = (str(p[0]), float(p[1]), float(p[2])) if p else None
        r = d.get("redeye")
        e.redeye = [tuple(int(v) for v in b) for b in r] if r else None
        return e


def _when_json(when):
    return when if when == "camera" else when.isoformat()


def _when_from(text):
    return text if text == "camera" else datetime.datetime.fromisoformat(text)


class Board:
    def __init__(self, path=None):
        self.path = path
        self.overrides = []         # timeplan.Override, scope "keys"
        self.edits = {}             # sha -> Edit
        self.history = []           # (what, state) to undo to
        self.load()

    # -- keeping --------------------------------------------------------------

    def state(self):
        return {"dates": [{"keys": sorted(ov.keys), "when": _when_json(ov.when)}
                          for ov in self.overrides],
                "edits": {k: e.to_json() for k, e in self.edits.items() if not e.empty()}}

    def _restore(self, state):
        self.overrides = [timeplan.Override("keys", None, None, _when_from(d["when"]),
                                            keys=set(d["keys"]))
                          for d in state.get("dates", []) if d.get("keys")]
        self.edits = {k: Edit.from_json(v) for k, v in state.get("edits", {}).items()}

    def load(self):
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path) as fh:
                self._restore(json.load(fh))
        except (OSError, ValueError, KeyError, TypeError, IndexError):
            self.overrides, self.edits = [], {}

    def save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".part"
        with open(tmp, "w") as fh:
            json.dump(self.state(), fh, indent=1)
        os.replace(tmp, self.path)

    def keys(self):
        """Every shot something is decided about."""
        out = set(self.edits)
        for ov in self.overrides:
            out |= ov.keys
        return out

    def prune(self, waiting):
        """Forget decisions about shots no longer waiting."""
        waiting = set(waiting)
        for ov in self.overrides:
            ov.keys &= waiting
        self.overrides = [ov for ov in self.overrides if ov.keys]
        self.edits = {k: e for k, e in self.edits.items() if k in waiting and not e.empty()}
        self.save()

    # -- undo ------------------------------------------------------------------

    def _checkpoint(self, what):
        self.history.append((what, copy.deepcopy(self.state())))
        del self.history[:-UNDO_STEPS]

    def undo(self):
        """Go back one change; says what was undone, or None."""
        if not self.history:
            return None
        what, state = self.history.pop()
        self._restore(state)
        self.save()
        return what

    # -- changes ---------------------------------------------------------------

    def edit(self, key):
        e = self.edits.get(key)
        if e is None:
            e = self.edits[key] = Edit()
        return e

    def set_dates(self, keys, when):
        """when: a datetime for the first of them, "camera", or "auto"."""
        keys = set(keys)
        self._checkpoint({"auto": "automatic dates", "camera": "camera's dates"}
                         .get(when, "set a date") if isinstance(when, str) else "set a date")
        for ov in self.overrides:
            ov.keys -= keys
        self.overrides = [ov for ov in self.overrides if ov.keys]
        if when != "auto":
            self.overrides.append(timeplan.Override("keys", None, None, when, keys=keys))
        self.save()

    def rotate(self, keys, quarters=1):
        self._checkpoint("rotate")
        for k in keys:
            e = self.edit(k)
            e.rotate = (e.rotate + quarters) % 4
            # the fixes' boxes are in the unrotated picture, so they stay
        self.save()

    def set_title(self, keys, title):
        self._checkpoint("name")
        for k in keys:
            self.edit(k).title = title.strip()
        self.save()

    def set_place(self, keys, place):
        self._checkpoint("place")
        for k in keys:
            self.edit(k).place = tuple(place) if place else None
        self.save()

    def set_redeye(self, fixes):
        """fixes: {key: [(x, y, w, h)] or None}."""
        self._checkpoint("red eye")
        for k, boxes in fixes.items():
            self.edit(k).redeye = [tuple(b) for b in boxes] if boxes else None
        self.save()

    def rule_for(self, key):
        for ov in self.overrides:
            if key in ov.keys:
                return ov.when
        return None
