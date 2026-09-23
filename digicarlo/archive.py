"""The archive: every file exactly as the camera had it, and a manifest.

Each pull gets its own folder, named for when it happened and where it came
from, holding the camera's files byte for byte under their card paths. Nothing
here is ever modified; the library is built from it and can be rebuilt from it.

manifest.jsonl records what arrived, what the camera's clock said about it,
and what was made of it. It is append-only JSON lines -- a crash can cost at
most the line being written, and it can be read with any text editor.
"""

import contextlib
import datetime
import fcntl
import json
import os

from . import media

MANIFEST = "manifest.jsonl"


class ArchiveBusy(RuntimeError):
    pass


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else None


def from_iso(text):
    if not text:
        return None
    return datetime.datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S")


def safe_name(text):
    bad = '/\\:*?"<>|\x00'
    out = "".join("_" if c in bad else c for c in (text or "")).strip(" .")
    return out or "camera"


class Archive:
    def __init__(self, root):
        self.root = os.path.expanduser(root)
        self.path = os.path.join(self.root, MANIFEST)
        self.reload()

    # -- reading -------------------------------------------------------------

    def reload(self):
        self.batches = {}          # id -> record
        self.files = {}            # sha256 -> record
        self.by_qfp = {}           # quick fingerprint -> sha256
        self.developed = {}        # sha256 -> record
        self.skipped = set()       # sha256 the user left out
        self.known = {}            # fingerprint -> path already in a library
        try:
            fh = open(self.path, encoding="utf-8")
        except FileNotFoundError:
            return
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue            # a torn final line from a crash
                self._apply(rec)

    def _apply(self, rec):
        t = rec.get("type")
        if t == "batch":
            self.batches.setdefault(rec["id"], {}).update(rec)
        elif t == "file":
            self.files[rec["sha256"]] = rec
            for key in (rec.get("qfp"), rec.get("sipix")):
                if key:
                    self.by_qfp[key] = rec["sha256"]
        elif t == "developed":
            self.developed[rec["sha256"]] = rec
            self.skipped.discard(rec["sha256"])
        elif t == "skip":
            self.skipped.add(rec["sha256"])
        elif t == "unskip":
            self.skipped.discard(rec["sha256"])
        elif t == "known":
            self.known[rec["fp"]] = rec.get("path")

    def has(self, fingerprint):
        return fingerprint in self.by_qfp or fingerprint in self.known

    def where(self, fingerprint):
        """Where a file with this fingerprint already is, for messages."""
        sha = self.by_qfp.get(fingerprint)
        if sha:
            done = self.developed.get(sha)
            if done and done.get("outputs"):
                return done["outputs"][0]
            return self.abspath(self.files[sha]["path"])
        return self.known.get(fingerprint)

    def abspath(self, rel):
        return os.path.join(self.root, rel)

    def pending(self):
        """[(batch record, [file records in shooting order])] still to be
        developed, oldest pull first."""
        by_batch = {}
        for sha, rec in self.files.items():
            if sha in self.developed or sha in self.skipped:
                continue
            by_batch.setdefault(rec["batch"], []).append(rec)
        out = []
        for bid in sorted(by_batch, key=lambda b: self.batches.get(b, {})
                          .get("pulled_at", "")):
            recs = by_batch[bid]
            items = [dict(r, rel=r.get("orig") or r["path"],
                          camera_time=from_iso(r.get("camera_time")))
                     for r in recs]
            ordered = media.shooting_order(items)
            out.append((self.batches.get(bid, {"id": bid}),
                        [self.files[i["sha256"]] for i in ordered]))
        return out

    # -- writing -------------------------------------------------------------

    def _append(self, rec):
        os.makedirs(self.root, exist_ok=True)
        line = json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n"
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        self._apply(rec)

    @contextlib.contextmanager
    def locked(self):
        """One writer at a time: the window and the command line must not
        pull the same card into the same archive at once."""
        os.makedirs(self.root, exist_ok=True)
        fh = open(os.path.join(self.root, ".lock"), "w")
        try:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ArchiveBusy(
                    "another DigiCarlo is working in %s; wait for it to "
                    "finish" % self.root)
            self.reload()
            yield self
        finally:
            fh.close()

    def new_batch(self, source_kind, source_label, pulled_at):
        stamp = pulled_at.strftime("%Y-%m-%d %H.%M.%S")
        folder = "%s %s" % (stamp, safe_name(source_label))
        n = 2
        while os.path.exists(os.path.join(self.root, folder)):
            folder = "%s %s (%d)" % (stamp, safe_name(source_label), n)
            n += 1
        os.makedirs(os.path.join(self.root, folder))
        ident = folder
        self._append({"type": "batch", "id": ident, "dir": folder,
                      "pulled_at": iso(pulled_at), "source": source_kind,
                      "source_label": source_label})
        return self.batches[ident]

    def set_batch_camera(self, batch, camera):
        self._append({"type": "batch", "id": batch["id"], "camera": camera})

    def add_file(self, rec):
        rec = dict(rec, type="file")
        self._append(rec)
        return self.files[rec["sha256"]]

    def mark_developed(self, sha, outputs, planned, rule=None):
        self._append({"type": "developed", "sha256": sha,
                      "outputs": outputs, "date": iso(planned),
                      "rule": rule,
                      "at": iso(datetime.datetime.now())})

    def skip(self, sha):
        self._append({"type": "skip", "sha256": sha})

    def unskip(self, sha):
        self._append({"type": "unskip", "sha256": sha})

    def mark_known(self, fp, path):
        self._append({"type": "known", "fp": fp, "path": path})
