"""Where pictures come from, and getting them into the archive.

Three kinds of camera are handled:

  volume  a memory card in a reader, or a camera that shows up as a USB
          drive. Found with lsblk; mounted read-only through udisks if the
          desktop has not already mounted it.
  ptp     a camera that speaks PTP over USB (most EasyShare-era cameras
          when plugged in directly). Driven through the gphoto2 command.
  sipix   the SiPix StyleCam Blink II, which speaks neither and is driven by
          Blinky's own driver.

plus any folder named on the command line, treated like a card.

Pulling copies whatever the archive does not already hold into a new batch
folder, checking every file against what was read. Nothing on the camera is
changed.
"""

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile

from . import archive as archive_mod
from . import blinky, media

FS_TYPES = {"vfat", "exfat", "ntfs", "ntfs3", "hfsplus", "hfs", "msdos",
            "fat", "fat12", "fat16", "fat32", "udf", "iso9660"}
COPY_CHUNK = 1024 * 1024


class Source:
    def __init__(self, kind, ident, label, path=None, device=None,
                 mounted=True, detail=""):
        self.kind = kind            # volume | folder | ptp | sipix
        self.ident = ident          # device, folder, port, or "sipix"
        self.label = label
        self.path = path            # mount point or folder
        self.device = device
        self.mounted = mounted
        self.detail = detail
        self.we_mounted = False

    def __repr__(self):
        return "<Source %s %s>" % (self.kind, self.ident)

    def describe(self):
        text = self.label
        if self.detail:
            text += " (%s)" % self.detail
        return text


class PullResult:
    def __init__(self):
        self.batch = None
        self.new = []               # file records
        self.skipped = []           # (name, where it already is)
        self.failed = []            # (name, reason)
        self.camera = None


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def find_sources(log, include_ptp=True, include_sipix=True):
    found = list(find_volumes(log))
    if include_ptp:
        found += find_ptp(log)
    if include_sipix:
        found += find_sipix(log)
    return found


def _lsblk():
    try:
        res = subprocess.run(
            ["lsblk", "-J", "-b", "-o",
             "NAME,PATH,RM,HOTPLUG,TRAN,FSTYPE,LABEL,MOUNTPOINTS,SIZE,TYPE,"
             "MODEL,VENDOR"],
            capture_output=True, text=True, timeout=15)
        return json.loads(res.stdout or "{}").get("blockdevices", [])
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []


def _walk_blk(nodes, parent=None):
    for node in nodes:
        yield node, parent
        yield from _walk_blk(node.get("children") or [], node)


def _human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1000 or unit == "TB":
            return ("%.0f %s" if unit in ("B", "KB") else "%.1f %s") % (n, unit)
        n /= 1000.0


def has_media(path):
    if not path or not os.path.isdir(path):
        return False
    return any(os.path.isdir(os.path.join(path, r)) for r in media.MEDIA_ROOTS)


def find_volumes(log):
    """Removable filesystems. Mounted ones count only if they look like a
    camera's; unmounted ones are offered, since a card the desktop did not
    mount is exactly the one people need help with."""
    out, seen = [], set()
    for node, parent in _walk_blk(_lsblk()):
        fstype = (node.get("fstype") or "").lower()
        if fstype not in FS_TYPES:
            continue
        top = parent or node
        removable = any(str(x.get(k)).lower() in ("1", "true")
                        for x in (node, top) for k in ("rm", "hotplug")) \
            or (top.get("tran") or "") in ("usb", "mmc") \
            or (node.get("name") or "").startswith("mmcblk")
        if not removable:
            continue
        mounts = [m for m in (node.get("mountpoints") or []) if m]
        mount = mounts[0] if mounts else None
        if mount and not has_media(mount):
            log.debug("%s is mounted at %s but has no DCIM; not a camera card"
                      % (node.get("path"), mount))
            continue
        label = node.get("label") or " ".join(
            x for x in ((top.get("vendor") or "").strip(),
                        (top.get("model") or "").strip()) if x) or node["name"]
        kind = "SD card" if (top.get("tran") == "mmc"
                             or node["name"].startswith("mmcblk")) \
            else "USB drive"
        detail = "%s, %s" % (kind, _human(int(node.get("size") or 0)))
        if not mount:
            detail += ", not mounted"
        out.append(Source("volume", node["path"], label, path=mount,
                          device=node["path"], mounted=bool(mount),
                          detail=detail))
        seen.add(mount)
    # Anything the desktop mounted that lsblk did not describe (fuse, odd
    # readers): look where udisks puts things.
    user = os.environ.get("USER") or ""
    for base in ("/run/media/%s" % user, "/media/%s" % user):
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        for name in names:
            path = os.path.join(base, name)
            if path in seen or not has_media(path):
                continue
            out.append(Source("volume", path, name, path=path,
                              detail="mounted drive"))
    return out


def check_folder(path, settings):
    """Refuse to pull from the library or the archive, or anything holding
    them: that would bring every picture in a second time."""
    path = os.path.abspath(os.path.expanduser(path))
    for name, other in (("library", settings.library),
                        ("archive", settings.archive)):
        other = os.path.abspath(os.path.expanduser(other))
        if path == other or path.startswith(other + os.sep) \
                or other.startswith(path + os.sep):
            raise ValueError(
                "%s %s the %s folder; pulling from it would import "
                "everything twice. To mark what is there as already "
                "imported, use 'digicarlo remember'."
                % (path, "is" if path == other else "is inside, or holds,",
                   name))


def folder_source(path):
    path = os.path.abspath(os.path.expanduser(path))
    return Source("folder", path, os.path.basename(path.rstrip("/")) or path,
                  path=path, detail="folder")


def ensure_mounted(source, log):
    """Mount a card read-only through udisks (no root needed for removable
    media). Read-only because a card worth rescuing is often a card that is
    failing, and nothing here has any reason to write to it."""
    if source.kind != "volume" or source.mounted:
        return source.path
    try:
        res = subprocess.run(["udisksctl", "mount", "-b", source.device,
                              "-o", "ro", "--no-user-interaction"],
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("could not run udisksctl to mount %s: %s"
                           % (source.device, exc))
    m = re.search(r" at (.+?)\.?\s*$", res.stdout.strip())
    if res.returncode != 0 or not m:
        raise RuntimeError("could not mount %s: %s"
                           % (source.device, (res.stderr or res.stdout).strip()))
    source.path = m.group(1)
    source.mounted = True
    source.we_mounted = True
    log.info("mounted %s read-only at %s" % (source.device, source.path))
    return source.path


def release(source, log):
    """Unmount a card DigiCarlo mounted itself, so it can be pulled out."""
    if not source.we_mounted:
        return
    try:
        subprocess.run(["udisksctl", "unmount", "-b", source.device,
                        "--no-user-interaction"],
                       capture_output=True, text=True, timeout=60)
        source.mounted = False
        source.we_mounted = False
        log.info("unmounted %s; it is safe to remove" % source.device)
    except (OSError, subprocess.TimeoutExpired):
        pass


def find_ptp(log):
    if not shutil.which("gphoto2"):
        return []
    try:
        res = subprocess.run(["gphoto2", "--auto-detect"], capture_output=True,
                             text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [Source("ptp", port, model, detail="USB camera")
            for model, port in parse_autodetect(res.stdout)]


def parse_autodetect(text):
    """[(model, port)] from `gphoto2 --auto-detect`, leaving out cameras
    handled some other way: mounted drives (disk:) and the SiPix."""
    out = []
    for line in text.splitlines():
        m = re.match(r"^(.*?)\s{2,}((?:usb|ptpip|serial):\S*)\s*$", line)
        if not m:
            continue
        model, port = m.group(1).strip(), m.group(2)
        if "sipix" in model.lower():
            continue
        out.append((model, port))
    return out


def find_sipix(log):
    try:
        usb = blinky._import_usb()
    except Exception:
        return []
    try:
        dev = usb.core.find(idVendor=blinky.VENDOR_ID,
                            idProduct=blinky.PRODUCT_ID)
    except Exception as exc:
        log.debug("USB scan for the SiPix failed: %s" % exc)
        return []
    if dev is None:
        return []
    return [Source("sipix", "sipix", "SiPix Blink II", detail="USB camera")]


# ---------------------------------------------------------------------------
# Pulling
# ---------------------------------------------------------------------------

def list_media(root, exclude=()):
    """[(rel, abs, size, mtime)] for every picture and clip under a card's
    media folders (or anywhere under a plain folder), skipping hidden and
    system directories -- including a Mac's .Trashes, whose contents the
    owner already deleted."""
    roots = [r for r in media.MEDIA_ROOTS
             if os.path.isdir(os.path.join(root, r))] or [""]
    exclude = [os.path.abspath(e) for e in exclude if e]
    out = []
    for sub in roots:
        top = os.path.join(root, sub)
        for dirpath, dirs, files in os.walk(top):
            dirs[:] = sorted(d for d in dirs if not d.startswith(".")
                             and d not in ("System Volume Information",
                                           "$RECYCLE.BIN", "lost+found")
                             and not any(os.path.abspath(
                                 os.path.join(dirpath, d)) == e
                                 for e in exclude))
            for name in files:
                if name.startswith(".") or not media.kind_of(name):
                    continue
                path = os.path.join(dirpath, name)
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                out.append((os.path.relpath(path, root), path, st.st_size,
                            st.st_mtime))
    return out


def copy_verified(src, dst):
    """Copy a file, fsync it, read it back, and compare. Returns sha256.

    The comparison is against what was read from the source, which is all
    that can be known: a failing card can hand back wrong bytes without an
    error, and no copy can detect that. What it does rule out is the copy
    itself going wrong.
    """
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".part"
    h = hashlib.sha256()
    try:
        with open(src, "rb") as fin, open(tmp, "wb") as fout:
            while True:
                chunk = fin.read(COPY_CHUNK)
                if not chunk:
                    break
                h.update(chunk)
                fout.write(chunk)
            fout.flush()
            os.fsync(fout.fileno())
        digest = h.hexdigest()
        if sha256_file(tmp) != digest:
            raise OSError("the copy of %s did not read back the same"
                          % os.path.basename(src))
        st = os.stat(src)
        os.utime(tmp, (st.st_atime, st.st_mtime))
        os.replace(tmp, dst)
        return digest
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(COPY_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _progress(cb, done, total, caption):
    if cb:
        cb(done, total, caption)


def _cancelled(cancel):
    return cancel is not None and cancel.is_set()


def pull(source, arc, log, progress=None, cancel=None, now=None):
    """Copy everything new on `source` into a fresh batch in the archive."""
    now = (now or datetime.datetime.now()).replace(microsecond=0)
    if source.kind in ("volume", "folder"):
        path = ensure_mounted(source, log)
        try:
            return pull_tree(arc, path, source, log, progress, cancel, now)
        finally:
            release(source, log)
    if source.kind == "ptp":
        return pull_ptp(arc, source, log, progress, cancel, now)
    if source.kind == "sipix":
        return pull_sipix(arc, source, log, progress, cancel, now)
    raise ValueError("unknown source kind %r" % source.kind)


def pull_tree(arc, root, source, log, progress=None, cancel=None, now=None,
              moving=False, orig_prefix=""):
    """Pull every new media file under `root`. With moving=True the files
    are already local (a gphoto2 download) and are moved, not copied."""
    result = PullResult()
    root = os.path.abspath(root)
    guard = [arc.root]
    files = list_media(root, exclude=guard)
    if not files:
        log.info("no pictures or clips found under %s" % root)
        return result
    total = len(files)
    log.info("%d picture(s) and clip(s) on %s" % (total, source.describe()))
    fresh = []
    for n, (rel, path, size, mtime) in enumerate(files, 1):
        if _cancelled(cancel):
            break
        _progress(progress, n - 1, total * 2, "Checking %s" % rel)
        try:
            qfp = media.quick_fingerprint(path, size)
        except OSError as exc:
            log.error("%s: cannot be read: %s" % (rel, exc))
            result.failed.append((rel, str(exc)))
            continue
        if arc.has(qfp):
            result.skipped.append((rel, arc.where(qfp)))
            log.debug("%s: already have it (%s)" % (rel, arc.where(qfp)))
            continue
        fresh.append((rel, path, size, mtime, qfp))

    if fresh and not _cancelled(cancel):
        result.batch = arc.new_batch(source.kind, source.label, now)
        bdir = arc.abspath(result.batch["dir"])
        for n, (rel, path, size, mtime, qfp) in enumerate(fresh, 1):
            if _cancelled(cancel):
                log.warn("stopped; %d file(s) not pulled" % (len(fresh) - n + 1))
                break
            _progress(progress, total + int(total * (n - 1) / len(fresh)),
                      total * 2, "Copying %s" % rel)
            dst = os.path.join(bdir, rel)
            try:
                if moving:
                    sha = sha256_file(path)
                    if sha in arc.files:
                        os.unlink(path)
                        result.skipped.append((rel, arc.abspath(
                            arc.files[sha]["path"])))
                        continue
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.move(path, dst)
                else:
                    sha = copy_verified(path, dst)
            except OSError as exc:
                # A card with bad sectors fails file by file; take what reads.
                log.error("%s: could not be copied: %s" % (rel, exc))
                result.failed.append((rel, str(exc)))
                continue
            if sha in arc.files:
                # Same bytes arrived under a different fingerprint before;
                # keep the first copy, not two.
                os.unlink(dst)
                result.skipped.append((rel, arc.abspath(arc.files[sha]["path"])))
                continue
            rec = arc.add_file({
                "sha256": sha, "qfp": qfp, "size": size,
                "batch": result.batch["id"],
                "orig": orig_prefix + rel.replace(os.sep, "/"),
                "path": os.path.relpath(dst, arc.root),
                "kind": media.kind_of(rel), "mtime": mtime,
                "dcf": media.dcf_key(rel)})
            result.new.append(rec)
            log.info("  %s" % rel)
        _prune_empty(bdir)
        if result.new:
            result.camera = read_batch_metadata(arc, result.batch, log)
    _progress(progress, total * 2, total * 2, "Done")
    return result


def _prune_empty(top):
    for dirpath, dirs, files in os.walk(top, topdown=False):
        if dirpath != top and not os.listdir(dirpath):
            try:
                os.rmdir(dirpath)
            except OSError:
                pass


def read_batch_metadata(arc, batch, log):
    """Read the camera's dates for a batch's files from the archive copies,
    fill gaps from file times, and record it all. Returns the camera name."""
    recs = [r for r in arc.files.values() if r["batch"] == batch["id"]
            and r.get("kind") in ("still", "raw", "video")]
    if not recs:
        return batch.get("camera")
    paths = [arc.abspath(r["path"]) for r in recs]
    meta = media.read_metadata(paths, log)
    items = []
    for r, p in zip(recs, paths):
        m = meta[p]
        items.append(dict(r, **m))
    offset = media.calibrate(items)
    if offset:
        log.debug("file times on this card run %+d s from the camera's "
                  "EXIF clock" % offset)
    for it in items:
        arc.add_file(dict(
            {k: v for k, v in it.items() if k != "type"},
            camera_time=archive_mod.iso(it.get("camera_time")),
            meta=True))
    camera = media.camera_label(items) or batch.get("source_label")
    arc.set_batch_camera(batch, camera)
    return camera


def ensure_metadata(arc, log):
    """Batches pulled by an interrupted run may lack dates; read them now."""
    todo = {r["batch"] for r in arc.files.values()
            if not r.get("meta") and r.get("kind") in ("still", "raw", "video")}
    for bid in todo:
        batch = arc.batches.get(bid)
        if batch:
            read_batch_metadata(arc, batch, log)


# -- PTP ----------------------------------------------------------------------

def _usb_node(port):
    m = re.match(r"usb:(\d+),(\d+)$", port)
    if not m:
        return None
    return "/dev/bus/usb/%03d/%03d" % (int(m.group(1)), int(m.group(2)))


def pull_ptp(arc, source, log, progress=None, cancel=None, now=None):
    """Download everything with gphoto2 into a scratch folder inside the
    archive, then keep what is new.

    gphoto2 cannot read part of a file, so there is no cheap way to ask
    whether a photo is new before fetching it; cameras of this age hold a
    few hundred at most, so fetching all and discarding the known ones is
    both simple and quick enough.
    """
    os.makedirs(arc.root, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".ptp-", dir=arc.root)
    try:
        node = _usb_node(source.ident)
        if node:
            holders, _ = blinky.processes_holding(node)
            for pid, name, _cmd in holders:
                log.warn("%s (pid %d) has the camera open" % (name, pid))
                if "gvfs" in name:
                    subprocess.run(["gio", "mount", "-u", "gphoto2://*"],
                                   capture_output=True, timeout=20)
        total = count_ptp_files(source.ident, log)
        cmd = ["gphoto2", "--port", source.ident, "--get-all-files",
               "--filename", os.path.join(staging, "%F", "%f.%C")]
        log.info("downloading from %s with gphoto2" % source.label)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        done = 0
        output = []
        for line in proc.stdout:
            output.append(line.rstrip())
            if line.startswith("Saving file as"):
                done += 1
                _progress(progress, done, max(total, done) * 2,
                          line.strip()[len("Saving file as "):])
            if _cancelled(cancel):
                proc.terminate()
                break
        proc.wait()
        if proc.returncode not in (0, None) and not _cancelled(cancel):
            tail = "\n".join(output[-6:])
            if "Could not claim the USB device" in tail:
                raise RuntimeError(
                    "another program has the camera open. Close any photo "
                    "importer or file manager window showing it, then try "
                    "again.\n" + tail)
            if done == 0:
                raise RuntimeError("gphoto2 could not read the camera:\n"
                                   + tail)
            log.warn("gphoto2 stopped early:\n" + tail)
        result = pull_tree(arc, staging, source, log, progress, cancel, now,
                           moving=True, orig_prefix="/")
        return result
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def count_ptp_files(port, log):
    try:
        res = subprocess.run(["gphoto2", "--port", port, "--list-files"],
                             capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return 0
    return len(parse_list_files(res.stdout))


def parse_list_files(text):
    """[(folder, name)] from `gphoto2 --list-files`."""
    out, folder = [], None
    for line in text.splitlines():
        m = re.match(r"^There (?:is|are) .* in folder '(.*)':?$", line.strip())
        if m:
            folder = m.group(1)
            continue
        m = re.match(r"^#\d+\s+(\S+)", line)
        if m and folder is not None:
            out.append((folder, m.group(1)))
    return out


# -- SiPix Blink II -----------------------------------------------------------

def pull_sipix(arc, source, log, progress=None, cancel=None, now=None):
    """Fetch the Blink II's photos with Blinky's driver: raw bytes to disk
    before anything interprets them, each image retried whole, and a photo
    already archived recognised by a 4 KB prefix read instead of a full
    transfer."""
    result = PullResult()
    sizes = {int(k.split(":")[1]) for k in list(arc.by_qfp) + list(arc.known)
             if k.startswith("sipix:")}
    cam = blinky.Blink2(log)
    try:
        cam.open()
        numpics = cam.get_numpics()
        if numpics == 0:
            log.info("the camera is empty")
            return result
        entries, _, _ = cam.get_directory(numpics)
        total = len(entries)
        for n, entry in enumerate(entries, 1):
            if _cancelled(cancel):
                break
            _progress(progress, n - 1, total, "Reading %s" % entry.basename)
            fp = None
            if entry.data_bytes in sizes:
                try:
                    fp = media.sipix_fingerprint(entry.data_bytes,
                                                 cam.read_prefix(entry))
                except blinky.CameraError as exc:
                    log.warn("could not fingerprint %s (%s); fetching it"
                             % (entry.basename, exc))
                if fp and arc.has(fp):
                    result.skipped.append((entry.basename, arc.where(fp)))
                    continue
            try:
                data = cam.read_image_with_retries(entry)
            except (blinky.PermissionDenied, blinky.NotPresent,
                    blinky.DeviceStalled) as exc:
                result.failed.append((entry.basename, str(exc)))
                log.error("%s; the camera is no longer usable" % exc)
                break
            except blinky.CameraError as exc:
                result.failed.append((entry.basename, str(exc)))
                log.error("%s: %s" % (entry.basename, exc))
                continue
            fp = media.sipix_fingerprint(len(data),
                                         data[:blinky.FINGERPRINT_BYTES])
            if arc.has(fp):
                result.skipped.append((entry.basename, arc.where(fp)))
                continue
            if result.batch is None:
                result.batch = arc.new_batch("sipix", source.label, now)
            bdir = arc.abspath(result.batch["dir"])
            os.makedirs(bdir, exist_ok=True)
            dst = os.path.join(bdir, "image%04d.raw" % entry.index)
            blinky.write_file_atomically(dst, data)
            sha = hashlib.sha256(data).hexdigest()
            if sha in arc.files:
                os.unlink(dst)
                result.skipped.append((entry.basename,
                                       arc.abspath(arc.files[sha]["path"])))
                continue
            kind = media.SIPIX_CLIP if entry.is_movie else media.SIPIX_STILL
            rec = arc.add_file({
                "sha256": sha, "sipix": fp, "size": len(data),
                "batch": result.batch["id"], "orig": entry.basename,
                "path": os.path.relpath(dst, arc.root), "kind": kind,
                "mtime": None, "dcf": None, "camera_time": None,
                "meta": True, "index": entry.index,
                "make": "SiPix", "model": "StyleCam Blink II"})
            result.new.append(rec)
            log.info("  %s (%d bytes)" % (entry.basename, len(data)))
        if result.batch:
            arc.set_batch_camera(result.batch, "SiPix Blink II")
            result.camera = "SiPix Blink II"
    finally:
        cam.close()
    _progress(progress, 1, 1, "Done")
    return result


# -- Remembering what is already in a library -----------------------------------

def remember(arc, folder, log, progress=None):
    """Record every picture already in `folder` so a pull never brings in a
    second copy of it. For libraries filled before DigiCarlo existed."""
    folder = os.path.abspath(os.path.expanduser(folder))
    added = 0
    items = []
    for dirpath, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            if name.startswith("."):
                continue
            if media.kind_of(name) or name.lower().endswith(".raw"):
                items.append(os.path.join(dirpath, name))
    for n, path in enumerate(sorted(items), 1):
        _progress(progress, n, len(items), os.path.basename(path))
        try:
            size = os.path.getsize(path)
            if path.lower().endswith(".raw"):
                with open(path, "rb") as fh:
                    fp = media.sipix_fingerprint(
                        size, fh.read(blinky.FINGERPRINT_BYTES))
            else:
                fp = media.quick_fingerprint(path, size)
        except OSError as exc:
            log.warn("%s: %s" % (path, exc))
            continue
        if not arc.has(fp):
            arc.mark_known(fp, path)
            added += 1
    return added, len(items)
