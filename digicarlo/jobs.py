"""Background work for the windows: a job on a worker thread, reporting
through Qt signals; the shared logger rerouted into the window; and the
thumbnail maker."""

import queue
import subprocess
import threading

from PyQt6.QtCore import QSize, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QImageReader

from digicarlo import archive, blinky, media

THUMB_W, THUMB_H = 100, 75          # logical; made at twice this


class GuiLog(blinky.Log):
    """The shared logger, rerouted into the window."""

    def __init__(self, sink):
        super().__init__(verbose=False, quiet=True)
        self.sink = sink

    def _emit(self, msg, stream=None):
        self.sink("info", str(msg))

    def out(self, msg=""):
        self._record("OUT", msg)
        if str(msg).strip():
            self.sink("out", str(msg))

    def warn(self, msg):
        self._record("WARN", msg)
        self.sink("warn", str(msg))

    def error(self, msg):
        self._record("ERROR", msg)
        self.sink("error", str(msg))


class Job(QThread):
    line = pyqtSignal(str, str)
    step = pyqtSignal(int, int, str)
    ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn
        self.cancel = threading.Event()

    def progress(self, done, total, caption):
        self.step.emit(int(done), int(total), str(caption))

    def run(self):
        log = GuiLog(self.line.emit)
        try:
            self.ok.emit(self.fn(self, log))
        except Exception as exc:                      # never take the UI down
            self.failed.emit(str(exc) if isinstance(
                exc, (RuntimeError, OSError, blinky.CameraError,
                      archive.ArchiveBusy)) else
                "%s: %s" % (type(exc).__name__, exc))


class ThumbLoader(QThread):
    """Makes thumbnails from the archive copies, newest request first."""

    loaded = pyqtSignal(str, QImage)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.q = queue.LifoQueue()
        self.stopping = False

    def request(self, key, path, kind):
        self.q.put((key, path, kind))

    def stop(self):
        self.stopping = True
        self.q.put(None)

    def run(self):
        while not self.stopping:
            job = self.q.get()
            if job is None:
                continue
            key, path, kind = job
            try:
                img = self.make(path, kind)
            except Exception:
                img = QImage()
            self.loaded.emit(key, img)

    @staticmethod
    def make(path, kind):
        return load_picture(path, kind, QSize(THUMB_W * 2, THUMB_H * 2))


def load_picture(path, kind, box=None):
    """A picture of an archived shot, as a QImage: fitted to cover `box`
    (a QSize) if given, else at full size. A clip gives its first frame; a
    raw, its preview; a SiPix file, Blinky's decoding."""
    if kind in ("still", "raw"):
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        size = reader.size()
        if box is not None and size.isValid():
            reader.setScaledSize(size.scaled(
                box, Qt.AspectRatioMode.KeepAspectRatioByExpanding))
        img = reader.read()
        if not img.isNull():
            return img
        if kind == "raw":
            # Most raws carry a JPEG preview; exiftool can lift it out.
            res = subprocess.run(["exiftool", "-b", "-PreviewImage", path],
                                 capture_output=True, timeout=30)
            if res.stdout:
                img = QImage.fromData(res.stdout)
                return img if box is None else \
                    img.scaled(box, Qt.AspectRatioMode.KeepAspectRatio)
        return QImage()
    if kind == "video":
        scale = ["-vf", "scale=%d:-2" % box.width()] if box is not None else []
        res = subprocess.run(
            ["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-frames:v", "1"]
            + scale + ["-f", "image2pipe", "-c:v", "png", "-"],
            capture_output=True, timeout=30)
        return QImage.fromData(res.stdout) if res.stdout else QImage()
    if kind in (media.SIPIX_STILL, media.SIPIX_CLIP):
        with open(path, "rb") as fh:
            data = fh.read()
        if kind == media.SIPIX_CLIP:
            frames = blinky.split_clip_frames(data)
            if not frames:
                return QImage()
            data = frames[0]
        w, h, raster, _ = blinky.decode_still(data, blinky.Log(quiet=True))
        img = QImage(raster, w, h, w * 3, QImage.Format.Format_RGB888).copy()
        return img if box is None else img.scaled(
            box, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
    return QImage()
