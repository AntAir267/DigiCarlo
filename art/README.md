# Artwork

The garage window is pre-rendered the way a 1995 CD-ROM game was: the garage,
the Photo Board and the console along the bottom are POV-Ray scenes, rendered
at twice the window's logical size so they stay sharp on a scaled screen. The
program only paints what changes on top: the green screen's text, today's
date on the calendar and the date stamp, the card's name and how many pictures
on it are new, and the shots pinned to the board.

```bash
art/render.sh          # everything, full quality: about half an hour on 24 threads
art/render.sh quick    # no bounced light or soft shadows, for checking layout
art/render.sh check    # full quality, plus out/check-*.png to look over
```

It needs `povray` (3.7) and `python3` with Pillow and numpy. The renders go to
`out/` and the textures to `tex/`, neither committed; what the program ships
goes to `../digicarlo/scenes/`, which is.

## How the pieces fit

The program swaps things in and out of the pictures -- a card in the reader,
the SiPix on the bench, the safelight on, prints in the wastebasket, a radio
key pushed in, the board's stations on the dial, START lit, each digit of the
counter. Each is a full render of the scene in that state,
and `assets.py` keeps only what differs from the background, feathered at the
edge. For that to leave no seam, every render of a scene has to light it
exactly alike, so:

- soft shadows use no `jitter`, which would scatter them differently each
  run;
- the bounced light (radiosity) is worked out once per scene, saved, and
  reused by every render of it (`Reuse=1` and POV-Ray's
  `Radiosity_From_File`). Renders then agree to within a few shades.

The clickable things are found the same way: a quick flat render of the scene,
and one more for each thing with that thing left out (`Hide=n`, which makes it
invisible to the camera but not to reflections or shadows). What changes is
exactly the thing's visible outline. From the outlines come the map of what is
under each pixel and the glow shown while the mouse is on it.

The surfaces the program paints on are found by `camera.py`, which projects
their corners through the scene's own camera.

| File | What it is |
| --- | --- |
| `garage.pov` | The garage: Pick-Up Bench, darkroom door, Photo Board, the Metropolitan. `Card`, `Blink`, `Safe` switch the card, the SiPix and the safelight |
| `board.pov` | Walking up to the Photo Board, empty. On its ledge: the date stamp, the alarm clock (the camera's date), the eraser (automatic), the wastebasket (`Trash` fills it), the red-eye pen, and the sign back to the garage |
| `console.pov` | The console. `Mode` 0 is the garage's, 1 the board's; `Lit` is the radio key pushed in, `Go` START's lamp (2 for STOP), `Digit` what the counter shows |
| `clockicon.pov` | The alarm clock for the trust-the-camera's-clock dialog |
| `pin.pov` | A map pin, in five colours, for pinning shots to the board |
| `textures.py` | The pictures on things: snapshots, the blank calendar, card, tag and sticky note the program writes on |
| `dial.py` | The radio's dial faces, one for each key pushed in |
| `camera.py` | Where a point in a scene lands in its picture |
| `assets.py` | Cuts the pieces, outlines and glows, and writes `scenes.json` |

The fonts are read from where they are on the machine that made these:
Cooper Black, Franklin Gothic Heavy and Demi Condensed, and Script MT Bold
from `~/.local/share/fonts`, Gloria Hallelujah likewise, and Nunito Black from
`fonts-nunito`. The Microsoft fonts may not be passed on, so they are not in
the repo -- only what is rendered with them ships. What the program paints
live uses free fonts: Nunito, Comic Neue and Glass TTY VT220.
