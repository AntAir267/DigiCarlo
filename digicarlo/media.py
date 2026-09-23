"""What a file is, what order it was shot in, and what the camera's clock said.

The camera's clock is wrong in absolute terms -- that is the premise of the
whole program -- but it is right about the gaps between shots until its
battery is pulled. So this module reads it faithfully and leaves judging it to
timeplan.
"""

import datetime
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess

STILL_EXTS = {".jpg", ".jpeg", ".jpe", ".png", ".tif", ".tiff", ".bmp",
              ".gif", ".heic", ".heif", ".webp"}
RAW_EXTS = {".arw", ".srf", ".sr2", ".cr2", ".cr3", ".crw", ".nef", ".nrw",
            ".orf", ".raf", ".rw2", ".dng", ".pef", ".srw", ".kdc", ".dcr",
            ".mrw", ".x3f", ".3fr", ".erf", ".mef", ".mos", ".rwl", ".iiq"}
VIDEO_EXTS = {".mov", ".avi", ".mp4", ".m4v", ".3gp", ".3g2", ".mts",
              ".m2ts", ".mpg", ".mpeg", ".wmv", ".asf", ".mkv"}

# Containers the library gets as MP4 instead. The video stream is copied
# bit for bit; only audio MP4 cannot carry (the 8-bit PCM old cameras record)
# is converted. See develop.remux.
REMUX_EXTS = {".mov", ".avi", ".mts", ".m2ts"}

# What exiftool can write dates into. Anything else gets its file time set
# and nothing more.
EXIF_WRITABLE = {".jpg", ".jpeg", ".jpe", ".png", ".tif", ".tiff", ".heic",
                 ".heif", ".webp", ".mp4", ".m4v", ".mov", ".3gp", ".3g2"} | RAW_EXTS

# Where cameras keep things. DCIM is the standard; the others are where Sony
# and Panasonic put video.
MEDIA_ROOTS = ("DCIM", "PRIVATE/AVCHD/BDMV/STREAM", "PRIVATE/M4ROOT/CLIP",
               "MP_ROOT", "AVCHD/BDMV/STREAM")

QFP_CHUNK = 64 * 1024

# SiPix Blink II raw transfers: the camera's own bytes, decoded by blinky.
SIPIX_STILL = "sipix-still"
SIPIX_CLIP = "sipix-clip"


def kind_of(name):
    ext = os.path.splitext(name)[1].lower()
    if ext in STILL_EXTS:
        return "still"
    if ext in RAW_EXTS:
        return "raw"
    if ext in VIDEO_EXTS:
        return "video"
    return None


def quick_fingerprint(path, size=None):
    """Size plus a hash of the first and last 64 KiB.

    Enough to recognise a file already archived without reading all of it
    off a slow card, and two different photos agreeing on 128 KiB of JPEG
    data and their exact length does not happen.
    """
    if size is None:
        size = os.path.getsize(path)
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read(QFP_CHUNK))
        if size > 2 * QFP_CHUNK:
            fh.seek(size - QFP_CHUNK)
            h.update(fh.read(QFP_CHUNK))
        elif size > QFP_CHUNK:
            h.update(fh.read())
    return "q1:%d:%s" % (size, h.hexdigest()[:40])


def sipix_fingerprint(size, prefix):
    """The key blinky's own duplicate detection uses: size and prefix hash."""
    return "sipix:%d:%s" % (size, hashlib.sha256(prefix).hexdigest())


_DIR_RE = re.compile(r"^(\d{3})[0-9A-Za-z_]{5}$")
_NUM_RE = re.compile(r"(\d{4})$")


def dcf_key(rel):
    """(folder number, file number) for a DCF path such as
    DCIM/101KC613/101_0063.MOV, else None.

    DCF numbering is the camera's shooting order, stills and clips alike,
    and it is the one thing on the card that a clock reset cannot disturb.
    """
    parts = rel.replace("\\", "/").split("/")
    if len(parts) < 2:
        return None
    d = _DIR_RE.match(parts[-2])
    stem = os.path.splitext(parts[-1])[0]
    n = _NUM_RE.search(stem)
    if not d or not n:
        return None
    folder = int(d.group(1))
    if not 100 <= folder <= 999:
        return None
    return folder, int(n.group(1))


def natural_key(text):
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", text)]


def parse_camera_date(value):
    """'2007:01:01 12:00:09' (with or without a zone suffix) -> naive
    datetime, or None for the zeroes and garbage cameras write when unset."""
    if not value or not isinstance(value, str):
        return None
    m = re.match(r"(\d{4})[:\-](\d{2})[:\-](\d{2})[ T](\d{2}):(\d{2}):(\d{2})",
                 value.strip())
    if not m:
        return None
    try:
        dt = datetime.datetime(*(int(g) for g in m.groups()))
    except ValueError:
        return None
    if dt.year < 1980:
        return None
    return dt


def utc_wall(epoch):
    """A file time as the wall clock it was written from.

    FAT and exFAT store the camera's local time with no zone, and the kernel
    presents it as if it were UTC -- checked against EXIF on a Kodak C613
    card, where file times read as UTC match the shot times to within the
    few seconds a write takes. calibrate() corrects this if a system differs.
    """
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc) \
        .replace(tzinfo=None)


def exiftool_path():
    return shutil.which("exiftool")


def read_metadata(paths, log=None):
    """{path: {camera_time, time_source, duration, make, model}} for each path.

    One exiftool run covers every file, which matters on a card of a few
    thousand. Without exiftool, JPEG EXIF is read with Pillow and everything
    else falls back to its file time.
    """
    out = {p: {"camera_time": None, "time_source": None, "duration": None,
               "make": None, "model": None} for p in paths}
    if not paths:
        return out
    tool = exiftool_path()
    if tool:
        records = _exiftool_json(tool, paths, log)
        for rec in records:
            src = rec.get("SourceFile")
            if src not in out:
                continue
            info = out[src]
            # A clip's embedded date is when recording started; a still's is
            # when the shutter fired. Only the second pairs usefully with a
            # file time in calibrate(), so keep them apart.
            source = "video" if kind_of(src) == "video" else "exif"
            for tag in ("DateTimeOriginal", "CreationDate", "CreateDate",
                        "ModifyDate"):
                dt = parse_camera_date(rec.get(tag))
                if dt:
                    info["camera_time"], info["time_source"] = dt, source
                    break
            dur = rec.get("Duration")
            if isinstance(dur, (int, float)):
                info["duration"] = float(dur)
            info["make"] = _clean(rec.get("Make"))
            info["model"] = _clean(rec.get("Model"))
    else:
        if log:
            log.warn("exiftool is not installed; reading JPEG dates with "
                     "Pillow only (sudo apt install libimage-exiftool-perl)")
        for p in paths:
            if kind_of(p) == "still":
                out[p].update(_pillow_metadata(p))
    return out


def _clean(value):
    if value is None:
        return None
    value = str(value).strip().strip("\x00").strip()
    return value or None


def _exiftool_json(tool, paths, log=None):
    records = []
    # Chunk the argument list: exiftool reads a file list from stdin with
    # -@ -, which keeps odd filenames intact and avoids ARG_MAX.
    for i in range(0, len(paths), 500):
        chunk = paths[i:i + 500]
        cmd = [tool, "-j", "-n", "-fast", "-charset", "filename=utf8",
               "-DateTimeOriginal", "-CreationDate", "-CreateDate",
               "-ModifyDate", "-Duration",
               "-Make", "-Model", "-@", "-"]
        try:
            res = subprocess.run(cmd, input="\n".join(chunk) + "\n",
                                 capture_output=True, text=True, timeout=600)
        except (OSError, subprocess.TimeoutExpired) as exc:
            if log:
                log.warn("exiftool failed: %s" % exc)
            continue
        try:
            records.extend(json.loads(res.stdout or "[]"))
        except ValueError:
            if log:
                log.warn("exiftool returned unreadable output: %s"
                         % (res.stderr.strip()[:200]))
    return records


def _pillow_metadata(path):
    info = {}
    try:
        from PIL import Image
        with Image.open(path) as img:
            exif = img.getexif()
            sub = exif.get_ifd(0x8769)
            dt = parse_camera_date(sub.get(0x9003)) or \
                parse_camera_date(exif.get(0x0132))
            if dt:
                info["camera_time"], info["time_source"] = dt, "exif"
            info["make"] = _clean(exif.get(0x010F))
            info["model"] = _clean(exif.get(0x0110))
    except Exception:
        pass
    return info


def calibrate(items):
    """Fill in camera_time from file times for items the camera left no
    date inside, corrected by how file times relate to EXIF on this card.

    items are dicts with camera_time, time_source, mtime, duration, kind.
    Returns the offset applied, in seconds.
    """
    diffs = []
    for it in items:
        if it.get("time_source") == "exif" and it.get("mtime") is not None:
            diffs.append((utc_wall(it["mtime"]) - it["camera_time"])
                         .total_seconds())
    offset = 0.0
    if diffs:
        # The median shrugs off the odd file the user touched; rounding to a
        # quarter hour keeps a zone difference and drops the write delay.
        offset = round(statistics.median(diffs) / 900.0) * 900.0
    for it in items:
        if it.get("camera_time") is None and it.get("mtime") is not None:
            t = utc_wall(it["mtime"]) - datetime.timedelta(seconds=offset)
            if it.get("kind") == "video" and it.get("duration"):
                # A clip's file time is when recording stopped.
                t -= datetime.timedelta(seconds=it["duration"])
            it["camera_time"] = t.replace(microsecond=0)
            it["time_source"] = "file"
    return offset


def shooting_order(items):
    """Sort items (dicts with rel, dcf, camera_time) into the order they
    were shot.

    DCF numbers decide where they exist. Files outside the DCF scheme (AVCHD
    clips, a folder of loose files) are slotted in by their camera time.
    """
    dcf = sorted((i for i in items if i.get("dcf")),
                 key=lambda i: (tuple(i["dcf"]), natural_key(i["rel"])))
    rest = sorted((i for i in items if not i.get("dcf")),
                  key=lambda i: (i.get("camera_time") is None,
                                 i.get("camera_time") or datetime.datetime.min,
                                 natural_key(i["rel"])))
    if not dcf:
        return rest
    if not rest:
        return dcf
    out = list(dcf)
    for it in rest:
        t = it.get("camera_time")
        if t is None:
            out.append(it)
            continue
        pos = 0
        for n, other in enumerate(out):
            ot = other.get("camera_time")
            if ot is not None and ot <= t:
                pos = n + 1
        out.insert(pos, it)
    return out


def camera_label(items):
    """The camera these came from, by majority of the EXIF models."""
    counts = {}
    for it in items:
        model = it.get("model")
        if model:
            make = it.get("make") or ""
            label = pretty_camera(make, model)
            counts[label] = counts.get(label, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]


def pretty_camera(make, model):
    """'EASTMAN KODAK COMPANY', 'KODAK EASYSHARE C613 ZOOM DIGITAL CAMERA'
    -> 'Kodak EasyShare C613 Zoom'."""
    make = (make or "").strip()
    model = (model or "").strip()
    short_make = {
        "EASTMAN KODAK COMPANY": "Kodak", "KODAK": "Kodak",
        "NIKON CORPORATION": "Nikon", "OLYMPUS IMAGING CORP.": "Olympus",
        "OLYMPUS OPTICAL CO.,LTD": "Olympus", "Konica Corporation": "Konica",
        "Minolta Co., Ltd.": "Minolta", "SONY": "Sony", "Canon": "Canon",
        "FUJIFILM": "Fujifilm", "Panasonic": "Panasonic",
        "SAMSUNG TECHWIN": "Samsung", "Polaroid": "Polaroid",
        "CASIO COMPUTER CO.,LTD.": "Casio", "PENTAX Corporation": "Pentax",
    }.get(make, make.title() if make.isupper() else make)
    for noise in (" DIGITAL CAMERA", " Digital Camera", " DIGITAL STILL CAMERA"):
        model = model.replace(noise, "")
    words = model.split()
    if words and short_make and words[0].lower() == short_make.lower():
        words = words[1:]
    if words and short_make and \
            " ".join(words).lower().startswith(short_make.lower() + " "):
        words = words[1:]

    def tidy(w):
        if w.upper() == "EASYSHARE":
            return "EasyShare"
        if w.isupper() and w.isalpha() and len(w) > 3:
            return w.title()
        return w
    model = " ".join(tidy(w) for w in words)
    return ("%s %s" % (short_make, model)).strip() or None
