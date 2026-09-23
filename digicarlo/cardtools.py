"""What the radio's card keys do: check a card, eject it, erase it.

Checking reads every file on the card to its last byte, which is what finds a
card that is failing before its pictures are trusted to it, and looks in the
kernel's log for the read errors a failing card leaves there.

Erasing empties a camera's card for next time, and only ever deletes a file
whose every byte is in the archive: each file on the card is hashed in full,
the archive copy with that hash is read back and hashed again, and if any
file on the card has no such copy, nothing is deleted at all. It is the rule
Blinky keeps before erasing the SiPix.
"""

import os
import re
import subprocess
import time

from . import sources

CHUNK = 1024 * 1024


class CheckResult:
    def __init__(self):
        self.files = 0
        self.bytes = 0
        self.failed = []                # (rel, reason)
        self.kernel = None              # lines, or None if the log was unreadable


class ErasePlan:
    def __init__(self, root):
        self.root = root
        self.files = []                 # (rel, path, size, mtime, sha256)
        self.bytes = 0
        self.missing = []               # rel: no copy in the archive
        self.damaged = []               # (rel, archive path): the copy no longer matches
        self.unreadable = []            # (rel, reason)

    @property
    def safe(self):
        return bool(self.files) and not (self.missing or self.damaged or self.unreadable)


class EraseResult:
    def __init__(self):
        self.erased = 0
        self.bytes = 0
        self.failed = []                # (rel, reason)
        self.changed = []               # rel: different from when it was checked


def _progress(cb, done, total, caption):
    if cb:
        cb(done, total, caption)


def _cancelled(cancel):
    return cancel is not None and cancel.is_set()


def _walk(root):
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in ("System Volume Information",
                                                      "$RECYCLE.BIN", "lost+found"))
        for name in sorted(files):
            yield os.path.join(dirpath, name)


def read_through(path):
    """Read a file to its end; returns its size."""
    n = 0
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                return n
            n += len(chunk)


def kernel_errors(device, since):
    """Read errors the kernel logged for `device` since `since` (epoch
    seconds): lines, or None if the kernel's log cannot be read."""
    if not device:
        return []
    name = os.path.basename(device)
    disk = re.sub(r"p?\d+$", "", name) if re.search(r"\d$", name) else name
    try:
        res = subprocess.run(["journalctl", "-k", "-q", "-o", "cat",
                              "--since", "@%d" % int(since)],
                             capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if res.returncode != 0:
        return None
    bad = re.compile(r"I/O error|medium error|Buffer I/O|critical|timeout|reset",
                     re.IGNORECASE)
    return [line for line in res.stdout.splitlines()
            if (name in line or disk in line) and bad.search(line)]


def _root(source, log, writable=False):
    """Where the card's files are, mounting it if it is not."""
    if source.kind == "folder":
        return source.path, False
    if source.kind != "volume":
        raise RuntimeError("%s is a camera, not a card" % source.label)
    if source.mounted and source.path:
        if writable and os.statvfs(source.path).f_flag & os.ST_RDONLY:
            raise RuntimeError("%s is mounted read-only; eject it and put it "
                               "back in, then try again" % source.label)
        return source.path, False
    if not writable:
        return sources.ensure_mounted(source, log), True
    try:
        res = subprocess.run(["udisksctl", "mount", "-b", source.device,
                              "--no-user-interaction"],
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("could not run udisksctl: %s" % exc)
    m = re.search(r" at (.+?)\.?\s*$", res.stdout.strip())
    if res.returncode != 0 or not m:
        raise RuntimeError("could not mount %s: %s"
                           % (source.device, (res.stderr or res.stdout).strip()))
    source.path, source.mounted, source.we_mounted = m.group(1), True, True
    return source.path, True


# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------

def check(source, log, progress=None, cancel=None):
    root, mounted_here = _root(source, log)
    started = time.time()
    res = CheckResult()
    try:
        paths = list(_walk(root))
        total = len(paths)
        for n, path in enumerate(paths):
            if _cancelled(cancel):
                log.warn("stopped after %d of %d files" % (n, total))
                break
            rel = os.path.relpath(path, root)
            _progress(progress, n, total, "Reading %s" % rel)
            try:
                res.bytes += read_through(path)
                res.files += 1
            except OSError as exc:
                res.failed.append((rel, exc.strerror or str(exc)))
                log.error("%s: %s" % (rel, exc.strerror or exc))
        _progress(progress, total, total, "Done")
    finally:
        if mounted_here:
            sources.release(source, log)
    res.kernel = kernel_errors(source.device, started - 1)
    if res.kernel:
        for line in res.kernel[:20]:
            log.warn("kernel: %s" % line)
    log.out("Checked %d file(s), %d byte(s), on %s: %d would not read"
            % (res.files, res.bytes, source.label, len(res.failed)))
    return res


# ---------------------------------------------------------------------------
# Eject
# ---------------------------------------------------------------------------

def eject(source, log):
    """Unmount the card, and power off the reader where it can be, so it
    can be pulled out. Returns what happened, for the screen."""
    if source.kind != "volume" or not source.device:
        raise RuntimeError("%s is not a card that can be ejected" % source.label)
    if source.mounted:
        res = subprocess.run(["udisksctl", "unmount", "-b", source.device,
                              "--no-user-interaction"],
                             capture_output=True, text=True, timeout=60)
        if res.returncode != 0:
            raise RuntimeError("could not unmount %s: %s" % (
                source.label, (res.stderr or res.stdout).strip()))
        source.mounted = False
        source.we_mounted = False
    log.out("%s unmounted; it is safe to remove" % source.label)
    try:
        res = subprocess.run(["udisksctl", "power-off", "-b", source.device,
                              "--no-user-interaction"],
                             capture_output=True, text=True, timeout=60)
        if res.returncode == 0:
            log.info("powered off the reader")
            return "powered off"
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "unmounted"


# ---------------------------------------------------------------------------
# Erase
# ---------------------------------------------------------------------------

def plan_erase(source, arc, log, progress=None, cancel=None):
    """Hash every picture and clip on the card and find each in the archive,
    reading the archive copy back too. Nothing is deleted here."""
    root, _ = _root(source, log, writable=True)
    plan = ErasePlan(root)
    files = sources.list_media(root, exclude=[arc.root])
    total = len(files)
    for n, (rel, path, size, mtime) in enumerate(files):
        if _cancelled(cancel):
            raise RuntimeError("stopped before every file was checked; "
                               "nothing was erased")
        _progress(progress, n, total, "Checking %s" % rel)
        try:
            sha = sources.sha256_file(path)
        except OSError as exc:
            plan.unreadable.append((rel, exc.strerror or str(exc)))
            continue
        rec = arc.files.get(sha)
        if rec is None:
            plan.missing.append(rel)
            continue
        copy = arc.abspath(rec["path"])
        try:
            if sources.sha256_file(copy) != sha:
                plan.damaged.append((rel, copy))
                continue
        except OSError:
            plan.damaged.append((rel, copy))
            continue
        plan.files.append((rel, path, size, mtime, sha))
        plan.bytes += size
    _progress(progress, total, total, "Done")
    return plan


def erase(plan, log, progress=None, cancel=None):
    """Delete what `plan` found safe, if it found all of it safe."""
    if not plan.safe:
        raise RuntimeError("refusing to erase: not every file on the card "
                           "is in the archive")
    res = EraseResult()
    total = len(plan.files)
    for n, (rel, path, size, mtime, sha) in enumerate(plan.files):
        if _cancelled(cancel):
            log.warn("stopped; %d file(s) left on the card" % (total - n))
            break
        _progress(progress, n, total, "Erasing %s" % rel)
        try:
            st = os.stat(path)
            if st.st_size != size or int(st.st_mtime) != int(mtime):
                res.changed.append(rel)
                continue
            os.unlink(path)
            res.erased += 1
            res.bytes += size
        except OSError as exc:
            res.failed.append((rel, exc.strerror or str(exc)))
            log.error("%s: %s" % (rel, exc.strerror or exc))
    os.sync()
    _progress(progress, total, total, "Done")
    log.out("Erased %d file(s) from the card; every one is in the archive"
            % res.erased)
    return res
