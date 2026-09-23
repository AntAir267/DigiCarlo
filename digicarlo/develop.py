"""Making the library copies: re-dated, and in a form a phone will take.

Everything starts from the archive copy, which is never touched. For each shot:

  JPEG and other stills   copied; EXIF DateTimeOriginal, CreateDate and
                          ModifyDate set, with the UTC offset alongside
  MOV, AVI, MTS           remuxed into MP4. The video stream is copied bit
                          for bit -- checked afterwards by hashing it in
                          both files -- and only audio MP4 cannot carry,
                          such as the 8-bit PCM these cameras record, is
                          converted (to AAC). QuickTime dates are set.
  MP4 and friends         copied, QuickTime dates set
  camera raw (ARW, ...)   left in the archive when the camera also wrote a
                          JPEG of the same shot; otherwise treated as a still
  SiPix Blink II          decoded by Blinky, written as JPEG (or PNG), dated

Every file's modification time is set to its new date too, since that is
what some phone galleries fall back on.
"""

import datetime
import json
import os
import shutil
import subprocess
import tempfile

from . import blinky, media

WORK = ".work"


class DevelopError(RuntimeError):
    pass


class Result:
    def __init__(self):
        self.made = []          # (sha, [paths])
        self.archive_only = []  # (sha, why)
        self.failed = []        # (name, reason)


def offset_text(when):
    """'-07:00' for a naive local datetime, allowing for daylight saving."""
    off = when.astimezone().utcoffset()
    mins = int(off.total_seconds() // 60)
    sign = "+" if mins >= 0 else "-"
    mins = abs(mins)
    return "%s%02d:%02d" % (sign, mins // 60, mins % 60)


def exif_stamp(when):
    return when.strftime("%Y:%m:%d %H:%M:%S")


# ---------------------------------------------------------------------------
# exiftool, kept running for the whole job
# ---------------------------------------------------------------------------

class ExifTool:
    """One exiftool process for many files: -stay_open saves its start-up
    cost (a Perl interpreter) on every photo."""

    def __init__(self):
        tool = media.exiftool_path()
        if not tool:
            raise DevelopError(
                "exiftool is needed to write dates into photos.\n"
                "  Fix: sudo apt install libimage-exiftool-perl")
        self.proc = subprocess.Popen(
            # -m lets through the minor format quibbles old cameras'
            # files are full of; real errors still fail the file.
            [tool, "-stay_open", "True", "-@", "-", "-common_args",
             "-charset", "filename=utf8", "-overwrite_original", "-m"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8")
        self.n = 0

    def run(self, args, path):
        self.n += 1
        tag = "{ready%d}" % self.n
        body = "\n".join(list(args) + [path, "-execute%d" % self.n]) + "\n"
        self.proc.stdin.write(body)
        self.proc.stdin.flush()
        lines = []
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise DevelopError("exiftool exited unexpectedly")
            if line.strip() == tag:
                break
            lines.append(line.rstrip())
        text = "\n".join(lines)
        if "1 image files updated" not in text:
            raise DevelopError("exiftool could not write %s: %s"
                               % (os.path.basename(path), text.strip()))
        return text

    def close(self):
        try:
            self.proc.stdin.write("-stay_open\nFalse\n")
            self.proc.stdin.flush()
            self.proc.wait(timeout=20)
        except Exception:
            self.proc.kill()


def still_date_args(when, make=None, model=None):
    stamp, off = exif_stamp(when), offset_text(when)
    args = ["-AllDates=" + stamp, "-OffsetTime=" + off,
            "-OffsetTimeOriginal=" + off, "-OffsetTimeDigitized=" + off]
    if make:
        args.append("-Make=" + make)
    if model:
        args.append("-Model=" + model)
    return args


def video_date_args(when):
    # QuickTime dates are UTC by specification; -api QuickTimeUTC makes
    # exiftool convert from the local time given. Keys:CreationDate carries
    # the local time and its offset, which is what phones display.
    stamp = exif_stamp(when) + offset_text(when)
    args = ["-api", "QuickTimeUTC=1"]
    for tag in ("CreateDate", "ModifyDate", "TrackCreateDate",
                "TrackModifyDate", "MediaCreateDate", "MediaModifyDate"):
        args.append("-QuickTime:%s=%s" % (tag, stamp))
    args.append("-Keys:CreationDate=" + stamp)
    return args


# ---------------------------------------------------------------------------
# ffmpeg
# ---------------------------------------------------------------------------

# Audio codecs an MP4 may hold as they are.
MP4_AUDIO = {"aac", "mp3", "ac3", "eac3", "alac", "opus", "flac"}


def probe(path):
    try:
        res = subprocess.run(["ffprobe", "-v", "error", "-show_streams",
                              "-show_format", "-of", "json", path],
                             capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        raise DevelopError("ffmpeg is needed to remux video.\n"
                           "  Fix: sudo apt install ffmpeg")
    try:
        return json.loads(res.stdout or "{}")
    except ValueError:
        return {}


def video_digest(path, decode=False):
    """MD5 of a file's first video stream: of its packets as stored, or with
    decode=True of the decoded frames."""
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-map", "0:v:0"]
    if not decode:
        cmd += ["-c", "copy"]
    cmd += ["-f", "md5", "-"]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    out = res.stdout.strip()
    return out if out.startswith("MD5=") else None


def remux(src, dst, bitrate="128k", log=None):
    """src -> MP4 at dst with the video stream copied untouched.

    Returns a short description of what was done to the audio. Raises
    DevelopError if the result's video does not match the source's.
    """
    info = probe(src)
    streams = info.get("streams") or []
    video = [s for s in streams if s.get("codec_type") == "video"]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    if not video:
        raise DevelopError("no video stream in %s" % os.path.basename(src))
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", src,
           "-map", "0:v:0"]
    note = "no audio"
    if audio:
        cmd += ["-map", "0:a:0"]
    cmd += ["-c:v", "copy"]
    if audio:
        codec = audio[0].get("codec_name", "?")
        if codec in MP4_AUDIO:
            cmd += ["-c:a", "copy"]
            note = "audio copied (%s)" % codec
        else:
            cmd += ["-c:a", "aac", "-b:a", bitrate]
            note = "audio %s -> AAC %s" % (codec, bitrate)
    # MJPEG has no MP4 sample entry of its own; ffmpeg tags it mp4v, which
    # ffmpeg, VLC and phones decode by looking at the bitstream.
    cmd += ["-movflags", "+faststart", "-f", "mp4", dst]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if res.returncode != 0 or not os.path.exists(dst):
        raise DevelopError("ffmpeg could not remux %s: %s"
                           % (os.path.basename(src),
                              (res.stderr or "").strip()[-400:]))
    same = video_digest(src) == video_digest(dst)
    if not same and video[0].get("codec_name") in ("h264", "hevc"):
        # A transport stream stores H.264 as Annex B and MP4 as length-
        # prefixed NALs, so the packets differ even when nothing was lost.
        # Compare the pictures instead.
        same = video_digest(src, decode=True) == video_digest(dst, decode=True)
    if not same:
        raise DevelopError("the remuxed video of %s does not match the "
                           "original" % os.path.basename(src))
    return note


# ---------------------------------------------------------------------------
# Placing files in the library
# ---------------------------------------------------------------------------

def free_name(folder, name):
    """name, or 'name (2).ext' and so on if taken."""
    path = os.path.join(folder, name)
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(name)
    n = 2
    while os.path.exists(os.path.join(folder, "%s (%d)%s" % (stem, n, ext))):
        n += 1
    return os.path.join(folder, "%s (%d)%s" % (stem, n, ext))


def place(work_path, folder, name, when):
    """Move a finished file into the library in one step, so a sync tool
    watching the folder never sees half a file."""
    os.makedirs(folder, exist_ok=True)
    epoch = when.timestamp()
    os.utime(work_path, (epoch, epoch))
    dst = free_name(folder, name)
    try:
        os.rename(work_path, dst)
    except OSError:
        # Different filesystems: copy to a hidden name, then rename.
        tmp = os.path.join(folder, ".%s.digicarlo-part" % os.path.basename(dst))
        shutil.copyfile(work_path, tmp)
        with open(tmp, "rb+") as fh:
            os.fsync(fh.fileno())
        os.utime(tmp, (epoch, epoch))
        os.rename(tmp, dst)
        os.unlink(work_path)
    return dst


# ---------------------------------------------------------------------------
# The job
# ---------------------------------------------------------------------------

class Developer:
    def __init__(self, arc, settings, log, library=None):
        self.arc = arc
        self.settings = settings
        self.log = log
        self.library = os.path.expanduser(library or settings.library)
        self.exif = None
        self.sipix_counter = None

    def develop(self, plan, progress=None, cancel=None):
        result = Result()
        shots = [s for s in plan.shots if s.key in self.arc.files
                 and s.key not in self.arc.developed]
        if not shots:
            return result
        if os.path.abspath(self.library) == os.path.abspath(self.arc.root):
            raise DevelopError("the library and the archive must be "
                               "different folders")
        work = os.path.join(self.arc.root, WORK)
        os.makedirs(work, exist_ok=True)
        self.exif = ExifTool()
        try:
            for n, shot in enumerate(shots, 1):
                if cancel is not None and cancel.is_set():
                    self.log.warn("stopped; %d shot(s) left for next time"
                                  % (len(shots) - n + 1))
                    break
                rec = self.arc.files[shot.key]
                name = os.path.basename(rec["path"])
                if progress:
                    progress(n - 1, len(shots), "Developing %s" % name)
                when = plan.times[shot.key]
                rule = plan.rules.get(shot.key)
                tmpdir = tempfile.mkdtemp(dir=work)
                try:
                    outputs, why = self._one(rec, when, tmpdir, plan)
                except (DevelopError, blinky.CameraError, OSError) as exc:
                    self.log.error("%s: %s" % (name, exc))
                    result.failed.append((name, str(exc)))
                    continue
                finally:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                self.arc.mark_developed(shot.key, outputs, when,
                                        rule.describe() if rule else "auto")
                if outputs:
                    result.made.append((shot.key, outputs))
                    for path in outputs:
                        self.log.info("  %s -> %s  %s"
                                      % (name, os.path.basename(path),
                                         when.strftime("%Y-%m-%d %H:%M:%S")))
                else:
                    result.archive_only.append((shot.key, why))
                    self.log.info("  %s: %s" % (name, why))
            if progress:
                progress(len(shots), len(shots), "Done")
        finally:
            self.exif.close()
            self.exif = None
        return result

    # -- per kind --------------------------------------------------------------

    def _one(self, rec, when, tmp, plan):
        src = self.arc.abspath(rec["path"])
        kind = rec.get("kind")
        name = os.path.basename(src)
        ext = os.path.splitext(name)[1].lower()
        if kind == "raw" and self._has_jpeg_twin(rec):
            return [], "raw kept in the archive only; its JPEG goes to the library"
        if kind in ("still", "raw"):
            work = os.path.join(tmp, name)
            shutil.copyfile(src, work)
            if ext in media.EXIF_WRITABLE:
                self.exif.run(still_date_args(when), work)
            return [place(work, self.library, name, when)], None
        if kind == "video":
            stem = os.path.splitext(name)[0]
            if ext in media.REMUX_EXTS:
                work = os.path.join(tmp, stem + ".mp4")
                try:
                    note = remux(src, work, self.settings.aac_bitrate, self.log)
                    self.log.debug("%s: remuxed, %s" % (name, note))
                    self.exif.run(video_date_args(when), work)
                    return [place(work, self.library, stem + ".mp4", when)], None
                except DevelopError as exc:
                    self.log.warn("%s; putting the original in the library "
                                  "instead" % exc)
            work = os.path.join(tmp, name)
            shutil.copyfile(src, work)
            if ext in media.EXIF_WRITABLE:
                self.exif.run(video_date_args(when), work)
            return [place(work, self.library, name, when)], None
        if kind in (media.SIPIX_STILL, media.SIPIX_CLIP):
            return self._sipix(rec, src, when, tmp), None
        return [], "not a picture or clip"

    def _has_jpeg_twin(self, rec):
        stem = os.path.splitext(rec["path"])[0].lower()
        for other in self.arc.files.values():
            if other["batch"] == rec["batch"] and other.get("kind") == "still" \
                    and os.path.splitext(other["path"])[0].lower() == stem:
                return True
        return False

    def _sipix_name(self, ext):
        # Blinky's convention: carry on numbering from the highest imageNNNN
        # already in the folder, because the camera restarts at zero after
        # every erase and its own index is no identity.
        if self.sipix_counter is None:
            self.sipix_counter = blinky.next_free_index(self.library)
        name = "image%04d%s" % (self.sipix_counter, ext)
        self.sipix_counter += 1
        return name

    def _sipix(self, rec, src, when, tmp):
        with open(src, "rb") as fh:
            data = fh.read()
        log = self.log
        is_clip = rec.get("kind") == media.SIPIX_CLIP
        if is_clip and not blinky.movie_extension(data)[1] \
                and len(blinky.split_clip_frames(data)) == 1:
            is_clip = False     # one frame is a photograph (as in Blinky)
        if is_clip:
            if blinky.movie_extension(data)[1]:
                avi = os.path.join(tmp, "clip.avi")
                with open(avi, "wb") as fh:
                    fh.write(data)
            else:
                w, h, frames, partial = blinky.decode_clip(data, log)
                avi = os.path.join(tmp, "clip.avi")
                blinky.write_mjpeg_avi(avi, frames, w, h)
            name = self._sipix_name(".mp4")
            work = os.path.join(tmp, name)
            remux(avi, work, self.settings.aac_bitrate, log)
            self.exif.run(video_date_args(when), work)
            return [place(work, self.library, name, when)]
        width, height, raster, partial = blinky.decode_still(data, log)
        if partial:
            log.warn("%s is damaged in the camera; the picture holds the rows "
                     "that decoded" % rec.get("orig"))
        if self.settings.sipix_format == "png":
            name = self._sipix_name(".png")
            work = os.path.join(tmp, name)
            blinky.write_png(work, width, height, raster)
        else:
            name = self._sipix_name(".jpg")
            work = os.path.join(tmp, name)
            blinky.write_jpeg(work, width, height, raster,
                              self.settings.jpeg_quality)
        self.exif.run(still_date_args(when, "SiPix", "StyleCam Blink II"), work)
        return [place(work, self.library, name, when)]


def plan_batches(arc, log):
    """Turn the archive's pending files into timeplan batches."""
    from . import timeplan
    from .archive import from_iso
    batches = []
    for brec, recs in arc.pending():
        anchor = from_iso(brec.get("pulled_at")) or datetime.datetime.now() \
            .replace(microsecond=0)
        shots = [timeplan.Shot(r["sha256"], brec.get("id"),
                               from_iso(r.get("camera_time")),
                               os.path.basename(r["path"])) for r in recs]
        label = brec.get("camera") or brec.get("source_label") or "camera"
        batches.append(timeplan.Batch(brec.get("id"), anchor, shots, label))
    return batches
