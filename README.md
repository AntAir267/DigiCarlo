# DigiCarlo

[![tests](https://github.com/AntAir267/DigiCarlo/actions/workflows/tests.yml/badge.svg)](https://github.com/AntAir267/DigiCarlo/actions/workflows/tests.yml)

<img src="docs/icon.png" width="96" align="right" alt="DigiCarlo icon">

Gets the pictures off old digital cameras, with dates that are right.

Every camera DigiCarlo is meant for has a clock that is wrong. A Kodak
EasyShare resets to 2007-01-01 12:00 whenever its batteries come out; a C315
goes back to 2005, a Polaroid PDC1300 to 2000; several cannot be set to 2026
at all. Put their pictures in a photo library and they land years in the
past.

So DigiCarlo dates pictures by **when they came off the camera**, and keeps
the one thing such a clock still gets right: the gaps between shots. Any run
of shots can be given a date of its own instead.

![DigiCarlo](docs/screenshot.png)

## Install

```bash
./packaging/build-deb.sh
sudo apt install ./packaging/digicarlo_1.3.0-1_all.deb
```

That brings in what it needs — `exiftool` to write dates, `ffmpeg` to remux
clips, `udisks2` to mount cards — and recommends PyQt6 for the window,
`python3-usb` for the SiPix Blink II and `gphoto2` for PTP cameras. It adds a
udev rule so the Blink II works without root, a menu entry, a KDE device
notifier action ("Import pictures with DigiCarlo"), man pages and bash
completion.

Later releases can be fetched with `digicarlo update --install`, which checks
the download against the release's published `SHA256SUMS` before handing it
to apt.

To run from the source tree instead: `./digicarlo-dev` for the command,
`./digicarlo-dev gui` for the window, `./digicarlo-dev classic` for the old one.

## Where things go

DigiCarlo keeps two folders, set with **File > Folders** or `digicarlo config`:

- **The archive** (`~/Pictures/DigiCarlo Archive`): the camera's files byte
  for byte, one folder per pull, under their card paths. Each copy is read
  back and compared before it counts. Nothing here is ever changed, and
  everything in the library can be rebuilt from it.
- **The library** (`~/Pictures/DigiCarlo` by default — a synced folder such as
  a phone backup is what it is for): re-dated copies, flat, under the
  camera's own file names.

Keep the archive out of anything that syncs, or every photo arrives twice.

`manifest.jsonl` in the archive records what arrived, what the camera's clock
said, and what was made of it. It is append-only JSON lines: a crash costs at
most the line being written.

A file already archived is recognised by content (its size and a hash of its
first and last 64 KiB), so it is not pulled twice even after renaming. To keep
a library filled before DigiCarlo from getting second copies:

```bash
digicarlo remember ~/"Pixel Backup"
```

## Dates

A **session** is a run of shots over which the camera's clock ran unbroken.
A new one starts where the clock goes backwards — a battery swap resetting it
— or leaps forward more than 30 days, which is the clock being set rather than
the camera sitting in a drawer. Shooting order comes from the DCF file
numbers, which a reset cannot disturb.

By default a pull's **last shot is dated when it came off the camera**. The
rest of its session keeps the camera's gaps back from there. Earlier sessions
are stacked before it a minute apart, because how long really passed between
two sessions is exactly what a reset destroys. Shots stamped in the same
second are nudged a second apart so their order survives into a library that
sorts by date.

Any group of shots can instead:

- **start at a date you give** — the rest follow with the camera's gaps, and
  successive sessions follow each other;
- **keep the camera's own date**, for the rare camera whose clock is right;
- go back to **automatic**.

Overriding some shots never moves the ones around them. In the window, pick
shots on the Photo Board (click a session's card to take all of it) and use
the date stamp, the alarm clock or the eraser. On the command line:

```bash
digicarlo plan                                   # sessions, and the dates they get
digicarlo import --date S2="2026-09-12 19:00"    # session 2 starts then
digicarlo import --date 12-30="yesterday 18:00"  # shots 12 to 30
digicarlo import --date "2026-09-12"             # everything, from noon that day
digicarlo import --date S3=camera                # keep the camera's dates
```

Stills get EXIF `DateTimeOriginal`, `CreateDate` and `ModifyDate` with the UTC
offset alongside; clips get QuickTime creation dates (UTC, as the format
specifies) and `Keys:CreationDate` in local time; every file's modification
time is set too, since some galleries fall back on it.

Where the camera's clock comes from: EXIF for stills, the QuickTime or AVI
header for clips, and otherwise the file's time on the card. FAT stores that
without a time zone and Linux presents it as UTC, so DigiCarlo compares it
with the EXIF times on the same card and corrects for any difference.

## Clips

MOV, AVI and MTS clips become MP4. The **video stream is copied bit for bit**,
never re-encoded, and checked afterwards by hashing it in both files. Only
audio MP4 cannot carry is converted: the Kodaks record 8-bit PCM, which has
no MP4 codec tag, so it becomes AAC at 128 kbit/s — comfortably more than an
11 kHz 8-bit source holds.

The video in those Kodak clips is Motion JPEG, which ffmpeg tags `mp4v` in an
MP4. Anything that looks at the bitstream plays it, which is ffmpeg, VLC and
phones. A player that trusts the tag alone would not. The original MOV is
always in the archive.

## Red eye

`digicarlo redeye PHOTO... --out DIR` takes the flash red out of eyes, writing
corrected copies (JPEG quality 95, EXIF kept) and never touching the originals.

Faces are found by [YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet)
(MIT licence, 230 KB, shipped beside the code), run layer by layer in plain
numpy so that DigiCarlo needs no OpenCV: Ubuntu's OpenCV package pulls in
several hundred megabytes, for a network of 53 small convolutions. Around each
eye it looks for a flash-red pupil -- deep red, compact, roundish, surrounded
by something that is not red -- and replaces the red with a dark neutral from
the pupil's own green and blue, so its shape and catchlight stay.

On 138 flash photos from a Kodak EasyShare C613 and C315 it matches OpenCV's
own face detector and a reference implementation byte for byte: 34 eyes in 21
photos, with no fixes on fabric, lamps or skin. It takes about 0.8 s a photo.
It misses some pinker red eyes; the Photo Board's red-eye pen lets you fix
those by hand.

## Cameras

| Kind | How it is found | How it is read |
| --- | --- | --- |
| Memory card, or a camera in USB-drive mode | `lsblk`; mounted read-only through udisks if the desktop has not mounted it | Copied from `DCIM` (and Sony/Panasonic video folders), skipping `.Trashes` |
| PTP camera | `gphoto2 --auto-detect` | `gphoto2 --get-all-files`, keeping what is new |
| SiPix StyleCam Blink II | USB `0c77:1011` | Blinky's driver: raw bytes to disk first, whole-image retries, 4 KB prefix reads to spot photos already archived |
| Any folder | `--from DIR`, or **Folder...** | As a card |

A card that is failing gives up files one at a time. DigiCarlo reports each
one it cannot read and carries on with the rest; nothing that failed is
recorded, so the next pull tries it again.

Camera raw files (ARW, CR2, NEF, ...) stay in the archive when the camera also
wrote a JPEG of the same shot, and go to the library otherwise.

### The SiPix Blink II

The Blink II is driven by [Blinky](https://github.com/AntAir267/blinky),
included here as `digicarlo/blinky.py` — an unmodified copy, with its commit
recorded in `digicarlo/BLINKY_SOURCE`. DigiCarlo uses it as a library; it
does not need the Blinky package installed and does not conflict with it.
Stills are decoded to 640x480 and saved as JPEG so they can carry EXIF dates
(`digicarlo config set still_format png` for lossless PNG instead), clips as
MP4, and names continue Blinky's `imageNNNN` numbering. The camera has no
clock, so its shots are a second apart in the order it lists them.
`digicarlo doctor` runs Blinky's link checks when the camera is attached.

## The window

`digicarlo-gui` is a Windows 95 program looking into a garage, pre-rendered
in POV-Ray the way a 1995 CD-ROM game was, with a console of Nash
Metropolitan hardware along the bottom in its factory Caribbean Blue.
Everything in the room that can be clicked glows under the mouse and does one
thing:

| In the garage | What it does |
| --- | --- |
| The card in the reader | Pulls its pictures into the archive. Its tag says how many are new |
| The camera on the bench | Pulls from the SiPix Blink II, or a PTP camera |
| The Photo Board | Walks over to it, to date the shots waiting |
| The darkroom door | Puts the waiting shots in the library, as START does. Its safelight is on while any are waiting |
| The crate of originals | Opens the archive folder |
| The car | Honks, and looks for cameras again |
| The calendar | Today: the date a pull's newest shot gets |

### The Photo Board

Every shot waiting is pinned up as a print showing the time it will get,
each session led by an index card with what the camera's clock said and the
dates its shots will get. Click a print to pick it (Shift for a run, Ctrl
for one more), or a card for its whole session; right-click for everything
below. The tools on the ledge work on the picked shots:

| On the ledge | What it does |
| --- | --- |
| Date stamp | Starts them at a date you give; the rest follow with the camera's gaps |
| Alarm clock | Keeps the camera's own dates |
| Eraser | Back to automatic |
| Wastebasket | Leaves them out of the library (they stay in the archive). With nothing picked, brings back the ones left out |
| Red-eye pen | Takes the flash red out of their eyes. Each photo is shown with the fixes it would make: click one to drop it, or click a red eye it missed to add it |
| GARAGE sign | Back to the garage |

A quarter turn, a name and a place go into the library copies as they are
made -- for a JPEG the turn is the EXIF orientation, so nothing is
recompressed -- and the archive copy never changes. What is decided is kept
in `~/.config/digicarlo/board.json` until the shots are developed, so closing
the window loses nothing. Places are saved under `[places]` in the settings.

After a pull from a camera whose clock can be right -- the Polaroid i1237 and
Konica KD-400Z, or whatever `trust_clock_cameras` lists -- a dialog asks,
session by session, which to date by the camera. Sessions that look like a
reset clock (before 2010, or the stroke of New Year) come unticked.

### The console

A green screen says what is going on (click it for the activity log), a drum
counter shows how many shots are waiting, and START puts them in the library
(STOP while a job runs). The radio's keys do what has no place in the room:

| In the garage | What it does |
| --- | --- |
| CHECK CARD | Reads every file on the card to its last byte, and looks in the kernel's log for read errors |
| EJECT | Unmounts the card and powers off the reader, so it can be pulled out |
| ERASE CARD | Empties the card for next time -- only when every file on it has a copy in the archive, compared byte for byte, and otherwise nothing |
| SYNC | Asks Syncthing whether the phone is connected and how much of the library it has |
| LIBRARY | Opens the library folder |

| At the board | What it does |
| --- | --- |
| VIEW | The picked shots big, one at a time |
| ROTATE | A quarter turn to the right |
| NAME | A title, such as "Grandma's birthday", written as the title and description Google Photos shows |
| PLACE | Where they were taken: GPS coordinates from a saved place, or a new one pasted from a map |
| UNDO | Takes back the last change, one at a time |

In the garage the left knob turns sounds on and off and the right opens the
activity log; at the board they turn the pages, as do the mouse wheel and
Page Up and Page Down. After putting shots in the library DigiCarlo asks
Syncthing to rescan the folder, so they go to the phone straight away.

The green screen is set in Glass TTY VT220 and the handwriting in Comic Neue
(`fonts-glasstty` and `fonts-comic-neue`, which the .deb recommends). The
frame is drawn by the program, so moving and resizing are handed to the
compositor (`startSystemMove`, `startSystemResize`) -- the only way a window
may move itself on Wayland. How the pictures are made is in
[art/](art/README.md).

`digicarlo-gui --classic`, or **View > Classic window**, opens the cartoon
dashboard of 1.1 and 1.2 instead.

## Commands

| Command | What it does |
| --- | --- |
| `digicarlo import` | Pull from everything plugged in, show the dates, and on a yes develop |
| `digicarlo sources` | List cameras and cards |
| `digicarlo pull` | Copy new files into the archive only |
| `digicarlo plan` | Show the sessions and the dates they would get |
| `digicarlo develop` | Put waiting shots in the library |
| `digicarlo skip 3-5` / `unskip` | Leave shots out, or bring them back |
| `digicarlo remember DIR` | Treat what is in DIR as already imported |
| `digicarlo redeye PHOTO... --out DIR` | Take the flash red out of eyes, into copies |
| `digicarlo doctor` | Check tools, folders, and what is plugged in |
| `digicarlo config [set KEY VALUE]` | Show or change settings |
| `digicarlo update` | Fetch a newer release |

## Tests

```bash
python3 tests/test_digicarlo.py
python3 tests/test_redeye.py
QT_QPA_PLATFORM=offscreen python3 tests/test_gui.py
QT_QPA_PLATFORM=offscreen python3 tests/test_garage.py
QT_QPA_PLATFORM=offscreen python3 tests/test_board.py
```

No camera is needed: cards are folders, the Blink II is Blinky's simulated
camera, clips are made with ffmpeg, and Syncthing is a small local server
answering as it would. Tests that write dates need exiftool and are skipped,
with a reason, without it.

## Licence

LGPL-2.1-or-later, as Blinky is, since Blinky's protocol work follows
libgphoto2's.
