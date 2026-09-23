#!/bin/sh
# Build digicarlo_<version>_all.deb from the source tree. No root needed.
set -e

here=$(cd "$(dirname "$0")" && pwd)
src=$(dirname "$here")
version=1.2.0
revision=1
pkg="digicarlo_${version}-${revision}_all"
build="$here/build/$pkg"

rm -rf "$here/build"
mkdir -p "$build/DEBIAN" \
         "$build/usr/bin" \
         "$build/usr/lib/python3/dist-packages/digicarlo" \
         "$build/usr/lib/udev/rules.d" \
         "$build/usr/share/man/man1" \
         "$build/usr/share/applications" \
         "$build/usr/share/solid/actions" \
         "$build/usr/share/bash-completion/completions" \
         "$build/usr/share/doc/digicarlo"

# The code ships as a Python package, with thin launchers in /usr/bin. Blinky
# travels inside it as digicarlo.blinky, so this package neither needs nor
# conflicts with the blinky package.
pkgdir="$build/usr/lib/python3/dist-packages/digicarlo"
for f in "$src"/digicarlo/*.py; do
    install -m 644 "$f" "$pkgdir/"
done
install -m 644 "$src/digicarlo/BLINKY_SOURCE" "$pkgdir/"
# The face finder red-eye removal runs on (YuNet, MIT licence).
install -m 644 "$src/digicarlo/face_detection_yunet_2023mar.onnx" "$pkgdir/"
install -m 644 "$src/digicarlo/YUNET_LICENSE" "$pkgdir/"
# The garage window's pre-rendered pictures (made by art/render.sh).
install -d "$pkgdir/scenes"
install -m 644 "$src"/digicarlo/scenes/* "$pkgdir/scenes/"

cat > "$build/usr/bin/digicarlo" <<'LAUNCH'
#!/usr/bin/python3
import sys
from digicarlo.cli import main
sys.exit(main())
LAUNCH

cat > "$build/usr/bin/digicarlo-gui" <<'LAUNCH'
#!/usr/bin/python3
import sys
try:
    from digicarlo.gui import main
except ImportError as exc:
    if "PyQt6" in str(exc):
        sys.exit("digicarlo-gui needs PyQt6.\n"
                 "  Fix: sudo apt install python3-pyqt6\n"
                 "The command line tool, digicarlo(1), does not need it.")
    raise
sys.exit(main())
LAUNCH
chmod 755 "$build/usr/bin/digicarlo" "$build/usr/bin/digicarlo-gui"

install -m 644 "$here/70-digicarlo-sipix.rules" "$build/usr/lib/udev/rules.d/"
install -m 644 "$here/digicarlo.desktop"        "$build/usr/share/applications/"
install -m 644 "$here/digicarlo-solid.desktop" \
               "$build/usr/share/solid/actions/digicarlo-import.desktop"

# Icons are rendered from gui.paint_icon, so the window's icon and the
# desktop's are one drawing. Regenerate if PyQt6 is here; otherwise use the
# checked-in copies.
if python3 -c "import PyQt6" 2>/dev/null; then
    python3 "$here/make-icons.py" "$here/icons" >/dev/null
fi
for dir in "$here"/icons/*/; do
    sz=$(basename "$dir")
    [ -f "$dir/digicarlo.png" ] || continue
    install -D -m 644 "$dir/digicarlo.png" \
        "$build/usr/share/icons/hicolor/$sz/apps/digicarlo.png"
done
install -m 644 "$here/digicarlo.bash-completion" \
               "$build/usr/share/bash-completion/completions/digicarlo"
install -m 644 "$here/copyright" "$build/usr/share/doc/digicarlo/"
gzip -9nc "$here/digicarlo.1"     > "$build/usr/share/man/man1/digicarlo.1.gz"
gzip -9nc "$here/digicarlo-gui.1" > "$build/usr/share/man/man1/digicarlo-gui.1.gz"
gzip -9nc "$here/changelog"       > "$build/usr/share/doc/digicarlo/changelog.Debian.gz"
gzip -9nc "$src/README.md"        > "$build/usr/share/doc/digicarlo/README.md.gz"
chmod 644 "$build"/usr/share/man/man1/*.gz "$build"/usr/share/doc/digicarlo/*.gz

install -m 755 "$here/postinst" "$build/DEBIAN/postinst"
install -m 755 "$here/postrm"   "$build/DEBIAN/postrm"

size=$(du -ks "$build" | cut -f1)
cat > "$build/DEBIAN/control" <<CONTROL
Package: digicarlo
Version: ${version}-${revision}
Section: graphics
Priority: optional
Architecture: all
Depends: python3 (>= 3.8), python3-pil, libimage-exiftool-perl, ffmpeg, udisks2
Recommends: python3-pyqt6, python3-usb, gphoto2, fonts-nunito, python3-numpy,
 fonts-glasstty, fonts-comic-neue
Installed-Size: ${size}
Maintainer: antair <antairdo@gmail.com>
Description: get the pictures off old digital cameras, with dates that are right
 DigiCarlo takes pictures and clips off memory cards, USB cameras and the
 SiPix StyleCam Blink II, and dates them by when they came off the camera
 instead of by the camera's clock -- which on cameras of this age has been
 reset to 2005 or 2007 by a battery swap, or cannot count as far as the
 current year. The gaps between shots, which such a clock still measures
 correctly, are kept; any run of shots can be given a date of its own.
 .
 The camera's files are archived byte for byte, checked against what was
 read, before anything else happens. The library gets re-dated copies: EXIF
 and QuickTime dates set, and MOV, AVI and MTS clips remuxed to MP4 with the
 video stream copied untouched and only audio MP4 cannot carry, such as 8-bit
 PCM, converted to AAC.
 .
 The window, digicarlo-gui, is a Windows 95 program dressed as a cartoon Nash
 Metropolitan, its controls on the dashboard the way Putt-Putt's were. It
 needs python3-pyqt6; the digicarlo command does not. The SiPix Blink II is
 driven by Blinky's driver, included, and needs python3-usb; a udev rule is
 installed so it works without root. USB cameras that speak PTP need gphoto2.
CONTROL

( cd "$build" && find . -type f ! -path './DEBIAN/*' -printf '%P\0' \
    | sort -z | xargs -0 md5sum > DEBIAN/md5sums )
chmod 644 "$build/DEBIAN/md5sums" "$build/DEBIAN/control"

dpkg-deb --root-owner-group --build "$build" "$here/${pkg}.deb" >/dev/null
echo "$here/${pkg}.deb"
