"""The digicarlo command.

    digicarlo import             pull from every camera and card found, show
                                 the dates they will get, and on a yes put
                                 them in the library
    digicarlo sources            what is plugged in
    digicarlo pull               copy new files into the archive only
    digicarlo plan               the dates waiting shots would get
    digicarlo develop            put waiting shots in the library
    digicarlo skip / unskip      leave shots out, or bring them back
    digicarlo remember DIR       treat what is in DIR as already imported
    digicarlo redeye PHOTO...    take the flash red out of eyes, into copies
    digicarlo doctor             check the tools and folders DigiCarlo needs
    digicarlo config             show or change settings
    digicarlo update             fetch a newer release

Dates: --date takes a selector and a time, and may be given more than once.

    --date "2026-09-12 19:00"          everything starts then
    --date S2="2026-09-12 19:00"       session 2 starts then
    --date S2-S4="yesterday 18:00"     sessions 2 to 4, one after another
    --date 12-30="2026-09-12 19:00"    shots 12 to 30
    --date S3=camera                   keep the camera's own dates

Session and shot numbers are the ones 'digicarlo plan' prints.
"""

import argparse
import datetime
import os
import shutil
import subprocess
import sys

from . import __version__, archive, blinky, config, develop, media, sources
from . import timeplan, update

EPILOG = __doc__.split("Dates:", 1)[1].strip()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def make_log(args):
    return blinky.Log(verbose=getattr(args, "verbose", False),
                      quiet=getattr(args, "quiet", False))


def settings_for(args):
    s = config.Settings(getattr(args, "config", None) or config.CONFIG_PATH)
    if getattr(args, "library", None):
        s.set("folders", "library", args.library)
    if getattr(args, "archive", None):
        s.set("folders", "archive", args.archive)
    return s


def parse_overrides(texts, now=None):
    return [timeplan.parse_override(t, now) for t in texts or []]


def build_plan(arc, settings, overrides, log):
    sources.ensure_metadata(arc, log)
    batches = develop.plan_batches(arc, log)
    plan = timeplan.build(batches, overrides,
                          max_gap_days=settings.max_gap_days,
                          spacing=settings.session_spacing)
    for ov in overrides:
        top = {"sessions": len(plan.sessions), "shots": len(plan.shots)} \
            .get(ov.scope)
        if top is not None and ov.last > top:
            raise timeplan.PlanError(
                "%s: there %s only %d %s waiting" %
                (ov.text, "is" if top == 1 else "are", top,
                 "session" + ("" if top == 1 else "s") if ov.scope == "sessions"
                 else "shot" + ("" if top == 1 else "s")))
    return plan


def describe_plan(plan, arc, per_shot=False):
    lines = []
    n_shots = len(plan.shots)
    if not n_shots:
        return ["Nothing is waiting to go into the library."]
    lines.append("%d shot%s waiting, from %d pull%s."
                 % (n_shots, "" if n_shots == 1 else "s", len(plan.batches),
                    "" if len(plan.batches) == 1 else "s"))
    for bn, batch in enumerate(plan.batches, 1):
        brec = arc.batches.get(batch.id, {})
        lines.append("")
        lines.append("Pull %d: %s, taken off %s"
                     % (bn, batch.label, timeplan.fmt(batch.anchor)))
        lines.append("        archived in %s" % arc.abspath(brec.get("dir", "")))
        for sess in [s for s in plan.sessions if s.batch is batch]:
            a, b = sess.shots[0].number, sess.shots[-1].number
            span = "shot %d" % a if a == b else "shots %d-%d" % (a, b)
            c0, c1 = sess.camera_range()
            lines.append("  S%-3d %-14s camera  %s" % (
                sess.number, span, timeplan.fmt_span(c0, c1)))
            groups = [g for g in plan.groups if g.session is sess]
            for g in groups:
                ga, gb = g.shots[0].number, g.shots[-1].number
                rule = g.rule.describe() if g.rule else "automatic"
                prefix = " " * 20 if len(groups) == 1 else \
                    "       %-13s" % ("%d-%d" % (ga, gb) if ga != gb else ga)
                lines.append("%s dated  %s   [%s]" % (
                    prefix, timeplan.fmt_span(g.start, g.end), rule))
            if per_shot:
                for shot in sess.shots:
                    lines.append("        %4d  %-18s %s  ->  %s" % (
                        shot.number, shot.label,
                        timeplan.fmt(shot.camera_time),
                        timeplan.fmt(plan.times[shot.key])))
    return lines


def pick_sources(args, log, settings):
    found = []
    for path in getattr(args, "from_dirs", None) or []:
        if not os.path.isdir(os.path.expanduser(path)):
            raise SystemExit("error: %s is not a folder" % path)
        try:
            sources.check_folder(path, settings)
        except ValueError as exc:
            raise SystemExit("error: %s" % exc)
        found.append(sources.folder_source(path))
    if found and not args.sources:
        return found
    detected = sources.find_sources(log)
    if not args.sources:
        return found + detected
    for want in args.sources:
        match = None
        if want.isdigit() and 1 <= int(want) <= len(detected):
            match = detected[int(want) - 1]
        else:
            for src in detected:
                if want.lower() in (src.label.lower(), src.ident.lower(),
                                    (src.device or "").lower(),
                                    (src.path or "").lower()) \
                        or want.lower() in src.label.lower():
                    match = src
                    break
        if match is None:
            raise SystemExit("error: no camera or card matches %r; "
                             "'digicarlo sources' lists them" % want)
        found.append(match)
    return found


def confirm(question, assume_yes=False):
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print("%s\n(not a terminal; pass --yes to go ahead)" % question)
        return False
    try:
        return input("%s [y/N] " % question).strip().lower() in ("y", "yes")
    except EOFError:
        return False


class Progress:
    """A single self-rewriting status line on a terminal; nothing otherwise."""

    def __init__(self, enabled=True):
        self.enabled = enabled and sys.stderr.isatty()
        self.width = 0

    def __call__(self, done, total, caption):
        if not self.enabled:
            return
        pct = int(100 * done / total) if total else 100
        text = "  [%3d%%] %s" % (pct, caption)
        cols = shutil.get_terminal_size((80, 20)).columns - 1
        text = text[:cols]
        sys.stderr.write("\r" + text.ljust(self.width))
        sys.stderr.flush()
        self.width = len(text)

    def done(self):
        if self.enabled and self.width:
            sys.stderr.write("\r" + " " * self.width + "\r")
            sys.stderr.flush()
            self.width = 0


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_sources(args, log, settings):
    found = sources.find_sources(log)
    if not found:
        log.out("No cameras or memory cards found.")
        log.out("A card reader's card, a camera in USB drive mode, a PTP "
                "camera and the SiPix Blink II are all looked for.")
        return 1
    for n, src in enumerate(found, 1):
        where = src.path or src.ident
        log.out("%2d. %-28s %-10s %s" % (n, src.label, src.kind, where))
        if src.detail:
            log.out("    %s" % src.detail)
    return 0


def do_pull(args, log, settings, arc):
    picked = pick_sources(args, log, settings)
    if not picked:
        log.out("No cameras or memory cards found. Plug one in, or name a "
                "folder with --from.")
        return None
    results = []
    for src in picked:
        log.out("Pulling from %s" % src.describe())
        prog = Progress(not args.quiet)
        try:
            res = sources.pull(src, arc, log, progress=prog)
        except (RuntimeError, blinky.CameraError, OSError) as exc:
            prog.done()
            log.error("%s: %s" % (src.label, exc))
            results.append(None)
            continue
        prog.done()
        results.append(res)
        where = arc.abspath(res.batch["dir"]) if res.batch else None
        log.out("  %d new, %d already imported, %d failed%s"
                % (len(res.new), len(res.skipped), len(res.failed),
                   " -> %s" % where if where else ""))
        for name, why in res.failed:
            log.out("  could not read %s: %s" % (name, why))
    return results


def cmd_pull(args, log, settings):
    arc = archive.Archive(settings.archive)
    with arc.locked():
        results = do_pull(args, log, settings, arc)
    if results is None:
        return 1
    log.out("")
    log.out("Run 'digicarlo plan' to see the dates they will get.")
    return 1 if any(r is None or r.failed for r in results) else 0


def cmd_plan(args, log, settings):
    arc = archive.Archive(settings.archive)
    plan = build_plan(arc, settings, parse_overrides(args.date), log)
    for line in describe_plan(plan, arc, per_shot=args.shots):
        log.out(line)
    return 0


def do_develop(args, log, settings, arc, overrides):
    plan = build_plan(arc, settings, overrides, log)
    for line in describe_plan(plan, arc, per_shot=getattr(args, "shots", False)):
        log.out(line)
    if not plan.shots:
        return 0
    log.out("")
    if not confirm("Put %d file%s in %s with these dates?"
                   % (len(plan.shots), "" if len(plan.shots) == 1 else "s",
                      settings.library), args.yes):
        log.out("Nothing changed. The shots stay in the archive; change "
                "dates with --date, or leave some out with 'digicarlo skip'.")
        return 0
    dev = develop.Developer(arc, settings, log)
    prog = Progress(not args.quiet)
    try:
        res = dev.develop(plan, progress=prog)
    finally:
        prog.done()
    log.out("")
    made = sum(len(p) for _, p in res.made)
    log.out("%d file%s in %s%s%s." % (
        made, "" if made == 1 else "s", settings.library,
        ", %d kept in the archive only" % len(res.archive_only)
        if res.archive_only else "",
        ", %d failed" % len(res.failed) if res.failed else ""))
    for name, why in res.failed:
        log.out("  failed: %s -- %s" % (name, why))
    return 1 if res.failed else 0


def cmd_develop(args, log, settings):
    arc = archive.Archive(settings.archive)
    overrides = parse_overrides(args.date)
    with arc.locked():
        return do_develop(args, log, settings, arc, overrides)


def cmd_import(args, log, settings):
    arc = archive.Archive(settings.archive)
    overrides = parse_overrides(args.date)
    with arc.locked():
        results = do_pull(args, log, settings, arc)
        if results is None and not arc.pending():
            return 1
        log.out("")
        rc = do_develop(args, log, settings, arc, overrides)
    if results and any(r is None or r.failed for r in results):
        return 1
    return rc


def _shot_selection(text, plan):
    """'3-5', 'S2', '7' -> the shots they name."""
    ov = timeplan.parse_override(text + "=now")
    if ov.scope == "sessions":
        return [s for s in plan.shots if ov.first <= s.session.number <= ov.last]
    return [s for s in plan.shots if ov.first <= s.number <= ov.last]


def cmd_skip(args, log, settings):
    arc = archive.Archive(settings.archive)
    with arc.locked():
        if args.command == "unskip":
            if not arc.skipped:
                log.out("Nothing has been left out.")
                return 0
            names = {os.path.basename(arc.files[s]["path"]): s
                     for s in arc.skipped if s in arc.files}
            wanted = args.which or sorted(names)
            for name in wanted:
                if name not in names:
                    log.error("%s was not left out" % name)
                    continue
                arc.unskip(names[name])
                log.out("  brought back %s" % name)
            return 0
        plan = build_plan(arc, settings, [], log)
        chosen = []
        for sel in args.which:
            chosen += _shot_selection(sel, plan)
        for shot in chosen:
            arc.skip(shot.key)
            log.out("  left out %d %s" % (shot.number, shot.label))
        log.out("%d shot(s) left out. They stay in the archive; "
                "'digicarlo unskip NAME' brings one back." % len(chosen))
    return 0


def cmd_redeye(args, log, settings):
    try:
        from . import redeye
    except ImportError as exc:
        log.error("red-eye removal needs numpy (%s)" % exc)
        log.out("  Fix: sudo apt install python3-numpy")
        return 1
    from PIL import Image
    out_dir = os.path.abspath(os.path.expanduser(args.out))
    os.makedirs(out_dir, exist_ok=True)
    eyes = photos = 0
    for path in args.photos:
        name = os.path.basename(path)
        try:
            with Image.open(path) as im:
                im.load()
                exif = im.info.get("exif")
                fmt = "PNG" if name.lower().endswith(".png") else "JPEG"
                fixed_img, fixed, faces = redeye.remove_red_eye(im)
        except OSError as exc:
            log.error("%s: %s" % (name, exc))
            continue
        if not fixed:
            log.out("%s: %d face%s, no red eye" % (name, len(faces), "" if len(faces) == 1 else "s"))
            continue
        # Never over the original: a new name in the output folder.
        dst = develop.free_name(out_dir, name)
        extra = {"exif": exif} if exif else {}
        if fmt == "JPEG":
            extra["quality"] = 95
        fixed_img.save(dst, fmt, **extra)
        eyes += len(fixed)
        photos += 1
        log.out("%s: %d eye%s fixed -> %s" % (name, len(fixed), "" if len(fixed) == 1 else "s", dst))
    log.out("%d eye%s fixed in %d photo%s." % (eyes, "" if eyes == 1 else "s", photos, "" if photos == 1 else "s"))
    return 0


def cmd_remember(args, log, settings):
    arc = archive.Archive(settings.archive)
    with arc.locked():
        total_added = 0
        for folder in args.folders:
            if not os.path.isdir(os.path.expanduser(folder)):
                log.error("%s is not a folder" % folder)
                return 1
            prog = Progress(not args.quiet)
            added, seen = sources.remember(arc, folder, log, progress=prog)
            prog.done()
            total_added += added
            log.out("%s: %d file(s) looked at, %d newly remembered"
                    % (folder, seen, added))
    log.out("A pull will now skip anything identical to those.")
    return 0


def check(name, ok, detail, fix=None):
    return (name, ok, detail, fix)


def cmd_doctor(args, log, settings):
    results = []
    tool = media.exiftool_path()
    results.append(check("exiftool", bool(tool), tool or "not installed",
                         "sudo apt install libimage-exiftool-perl"))
    ff = shutil.which("ffmpeg") and shutil.which("ffprobe")
    results.append(check("ffmpeg", bool(ff), shutil.which("ffmpeg")
                         or "not installed", "sudo apt install ffmpeg"))
    results.append(check("udisks (mounting cards)",
                         bool(shutil.which("udisksctl")),
                         shutil.which("udisksctl") or "not installed",
                         "sudo apt install udisks2"))
    gp = shutil.which("gphoto2")
    results.append(check("gphoto2 (USB cameras)", bool(gp),
                         gp or "not installed -- only needed for cameras "
                         "that are not USB drives", "sudo apt install gphoto2"))
    try:
        blinky._import_usb()
        usb_ok, usb_detail = True, "pyusb available"
    except Exception as exc:
        usb_ok, usb_detail = False, str(exc).splitlines()[0]
    results.append(check("pyusb (SiPix Blink II)", usb_ok, usb_detail,
                         "sudo apt install python3-usb"))
    extra = "/usr/lib/udev/rules.d/70-digicarlo-sipix.rules"
    rule = extra if os.path.exists(extra) else blinky.find_udev_rule()[0]
    results.append(check("SiPix udev rule", bool(rule),
                         rule or "none; the Blink II will need root",
                         "install the DigiCarlo package, which adds one"))
    for label, path in (("library", settings.library),
                        ("archive", settings.archive)):
        probe = path
        while probe and not os.path.exists(probe):
            probe = os.path.dirname(probe)
        ok = bool(probe) and os.access(probe, os.W_OK)
        results.append(check("%s folder" % label, ok,
                             path + ("" if os.path.exists(path)
                                     else " (will be created)"),
                             "choose another with 'digicarlo config set "
                             "%s DIR'" % label))
    lib, arc_ = (os.path.abspath(settings.library),
                 os.path.abspath(settings.archive))
    apart = lib != arc_ and not lib.startswith(arc_ + os.sep) \
        and not arc_.startswith(lib + os.sep)
    results.append(check("library and archive kept apart", apart,
                         "yes" if apart else "one is inside the other",
                         "the archive must not be synced; keep it outside "
                         "the library"))
    bad = 0
    for name, ok, detail, fix in results:
        log.out("[%s] %-32s %s" % ("PASS" if ok else "FAIL", name, detail))
        if not ok:
            bad += 1
            if fix:
                log.out("       fix: %s" % fix)
    found = sources.find_sources(log)
    log.out("")
    if found:
        log.out("Plugged in:")
        for src in found:
            log.out("  %s -- %s" % (src.label, src.detail or src.kind))
    else:
        log.out("No cameras or cards plugged in.")
    if any(s.kind == "sipix" for s in found) or args.sipix:
        log.out("")
        log.out("SiPix Blink II link checks (from Blinky):")
        checks, cam = blinky.run_checks(log)
        if cam is not None:
            cam.close()
        for c in checks:
            log.out(c.render())
            bad += 0 if c.ok or c.status == "SKIP" else 1
    return 1 if bad else 0


def cmd_config(args, log, settings):
    if args.action == "set":
        key = args.key
        section = {"library": "folders", "archive": "folders",
                   "max_gap_days": "dates",
                   "session_spacing_seconds": "dates",
                   "still_format": "sipix", "jpeg_quality": "sipix",
                   "aac_bitrate": "video", "sounds": "window"}.get(key)
        if section is None:
            log.error("unknown setting %r" % key)
            return 1
        settings.set(section, key, args.value)
        settings.save()
        log.out("%s = %s  (saved to %s)" % (key, args.value, settings.path))
        return 0
    log.out("Settings file: %s%s" % (settings.path, "" if os.path.exists(
        settings.path) else " (not created yet; all defaults)"))
    log.out("  library                  %s" % settings.library)
    log.out("  archive                  %s" % settings.archive)
    log.out("  max_gap_days             %g" % settings.max_gap_days)
    log.out("  session_spacing_seconds  %g" % settings.session_spacing)
    log.out("  still_format (SiPix)     %s" % settings.sipix_format)
    log.out("  jpeg_quality (SiPix)     %d" % settings.jpeg_quality)
    log.out("  aac_bitrate              %s" % settings.aac_bitrate)
    log.out("  sounds (window)          %s" % ("yes" if settings.sounds else "no"))
    return 0


def cmd_update(args, log, settings):
    log.out("Installed: DigiCarlo %s" % __version__)
    try:
        version, info = update.latest()
    except update.UpdateError as exc:
        log.error(str(exc))
        log.out("  Releases are listed at %s" % update.RELEASES_PAGE)
        return 1
    if version is None:
        log.out("No releases have been published yet.")
        return 0
    log.out("Latest:    DigiCarlo %s" % version)
    if not update.newer(version):
        log.out("You are up to date.")
        return 0
    body = (info.get("body") or "").strip()
    if body:
        log.out("")
        log.out("What is new in %s:" % version)
        for line in body.splitlines()[:20]:
            log.out("  %s" % line)
    if args.check:
        log.out("")
        log.out("Run 'digicarlo update' to fetch it.")
        return 0
    try:
        path = update.download(info, args.out)
    except update.UpdateError as exc:
        log.error(str(exc))
        return 1
    log.out("Downloaded and verified %s" % path)
    if not args.install:
        log.out("To install it:  sudo apt install %s" % path)
        return 0
    rc = subprocess.call(["sudo", "apt", "install", "-y", path])
    if rc:
        log.error("apt exited %d; nothing was changed" % rc)
        return 1
    log.out("Installed DigiCarlo %s." % version)
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-v", "--verbose", action="store_true",
                        help="say more about what is happening")
    common.add_argument("-q", "--quiet", action="store_true",
                        help="only print results and errors")
    common.add_argument("--library", metavar="DIR",
                        help="where re-dated copies go (default from settings)")
    common.add_argument("--archive", metavar="DIR",
                        help="where untouched originals go (default from "
                             "settings)")
    common.add_argument("--config", metavar="FILE", help=argparse.SUPPRESS)

    dates = argparse.ArgumentParser(add_help=False)
    dates.add_argument("--date", action="append", metavar="[WHICH=]WHEN",
                       help="date shots differently; see below")
    dates.add_argument("--shots", action="store_true",
                       help="list every shot, not just sessions")

    which = argparse.ArgumentParser(add_help=False)
    which.add_argument("sources", nargs="*", metavar="SOURCE",
                       help="a number or name from 'digicarlo sources' "
                            "(default: everything plugged in)")
    which.add_argument("--from", dest="from_dirs", action="append",
                       metavar="DIR", help="pull from a folder instead of a "
                                           "camera, as if it were a card")

    p = argparse.ArgumentParser(
        prog="digicarlo",
        description="Get the pictures off old digital cameras, dated when "
                    "they came off the camera rather than by its wrong clock.",
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version",
                   version="DigiCarlo %s" % __version__)
    sub = p.add_subparsers(dest="command", metavar="COMMAND")
    fmt = argparse.RawDescriptionHelpFormatter

    s = sub.add_parser("import", parents=[common, dates, which],
                       help="pull, show the dates, and develop on a yes",
                       epilog=EPILOG, formatter_class=fmt)
    s.add_argument("-y", "--yes", action="store_true",
                   help="do not ask before writing to the library")
    s.set_defaults(func=cmd_import)

    s = sub.add_parser("sources", parents=[common],
                       help="list cameras and cards plugged in")
    s.set_defaults(func=cmd_sources)

    s = sub.add_parser("pull", parents=[common, which],
                       help="copy new files into the archive only")
    s.set_defaults(func=cmd_pull)

    s = sub.add_parser("plan", parents=[common, dates],
                       help="show the dates waiting shots would get",
                       epilog=EPILOG, formatter_class=fmt)
    s.set_defaults(func=cmd_plan)

    s = sub.add_parser("develop", parents=[common, dates],
                       help="put waiting shots in the library",
                       epilog=EPILOG, formatter_class=fmt)
    s.add_argument("-y", "--yes", action="store_true",
                   help="do not ask before writing to the library")
    s.set_defaults(func=cmd_develop)

    s = sub.add_parser("skip", parents=[common],
                       help="leave shots out of the library")
    s.add_argument("which", nargs="+", metavar="SHOTS",
                   help="shot numbers (7, 3-5) or sessions (S2)")
    s.set_defaults(func=cmd_skip)

    s = sub.add_parser("unskip", parents=[common],
                       help="bring left-out shots back")
    s.add_argument("which", nargs="*", metavar="NAME",
                   help="file names (default: all of them)")
    s.set_defaults(func=cmd_skip)

    s = sub.add_parser("redeye", parents=[common],
                       help="take the flash red out of eyes in photos")
    s.add_argument("photos", nargs="+", metavar="PHOTO")
    s.add_argument("--out", required=True, metavar="DIR",
                   help="where the corrected copies go; originals are never changed")
    s.set_defaults(func=cmd_redeye)

    s = sub.add_parser("remember", parents=[common],
                       help="treat what is in a folder as already imported")
    s.add_argument("folders", nargs="+", metavar="DIR")
    s.set_defaults(func=cmd_remember)

    s = sub.add_parser("doctor", parents=[common],
                       help="check the tools and folders DigiCarlo needs")
    s.add_argument("--sipix", action="store_true",
                   help="run the Blink II link checks even if it is not seen")
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("config", parents=[common], help="show or change settings")
    cs = s.add_subparsers(dest="action", metavar="ACTION")
    cs.add_parser("show", help="print the settings")
    sset = cs.add_parser("set", help="change a setting")
    sset.add_argument("key")
    sset.add_argument("value")
    s.set_defaults(func=cmd_config, action="show")

    s = sub.add_parser("update", parents=[common],
                       help="fetch a newer release from GitHub")
    s.add_argument("--check", action="store_true",
                   help="only say whether there is one")
    s.add_argument("--install", action="store_true",
                   help="install it with sudo apt")
    s.add_argument("--out", metavar="DIR", help="where to save the .deb")
    s.set_defaults(func=cmd_update)
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    log = make_log(args)
    settings = settings_for(args)
    try:
        return args.func(args, log, settings)
    except timeplan.PlanError as exc:
        log.error(str(exc))
        return 2
    except (archive.ArchiveBusy, develop.DevelopError) as exc:
        log.error(str(exc))
        return 1
    except KeyboardInterrupt:
        log.error("interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
