#!/usr/bin/env python3
"""Render the app icon to PNGs for /usr/share/icons/hicolor.

The drawing lives in one place, digicarlo.gui.paint_icon, so the icon in the
window's title bar and the icon on the desktop can never drift apart.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from PyQt6.QtWidgets import QApplication            # noqa: E402
from digicarlo import gui                           # noqa: E402

SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "icons")
    app = QApplication([])                          # noqa: F841
    for size in SIZES:
        d = os.path.join(out, "%dx%d" % (size, size))
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "digicarlo.png")
        if not gui.icon_pixmap(size).save(path, "PNG"):
            print("failed to write %s" % path, file=sys.stderr)
            return 1
        print("  %-9s %s" % ("%dx%d" % (size, size), path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
