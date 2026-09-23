"""Background work for the windows: a job on a worker thread, reporting
through Qt signals, and the shared logger rerouted into the window."""

import threading

from PyQt6.QtCore import QThread, pyqtSignal

from digicarlo import archive, blinky


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
