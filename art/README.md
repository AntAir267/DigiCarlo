# Artwork

The next window is pre-rendered the way a 1995 CD-ROM game was: the garage,
the Photo Board and the console along the bottom are POV-Ray scenes, and the
program only draws the live parts on top (the Windows 95 frame, the green
screen's text, pinned photos, hover glows, dialogs).

```bash
art/render.sh          # everything, full quality: about a minute on 24 threads
art/render.sh quick    # no radiosity or soft shadows, for checking layout
```

It needs `povray` (3.7), `python3-pil` and `rsvg-convert` (`librsvg2-bin`).
The textures go to `tex/` and the pictures to `out/`; both are rebuilt every
run and neither is committed.

| File | What it is |
| --- | --- |
| `garage.pov` | The garage: Pick-Up Bench, darkroom door, Photo Board on the wall, the Metropolitan. `Card=1` puts the Polaroid's card in the reader instead of the Kodak's |
| `board.pov` | Walking up to the Photo Board, empty, with the dating tools on its ledge |
| `console.pov` | The console: message screen, push-button radio, shot counter, START. `Mode` 0 is the garage's, 1 the board's; `Lit` is the radio key pushed in (0 for none) |
| `clockicon.pov` | The alarm clock on the trust-the-camera's-clock dialog |
| `textures.py` | The pictures painted onto things: snapshots, calendar, sticky note, card labels and tags |
| `dial.py` | The radio's dial faces, one per key pushed in, so the lit station matches the key |
| `board_content.py` | What the program would pin on the board, for the mockup |
| `compose.py` | A mockup of the whole window: `garage`, `board` or `trust` |

The fonts are read from where they are on the machine that made these:
Cooper Black, Franklin Gothic Heavy and Demi Condensed, and Script MT Bold
from `~/.local/share/fonts`, Gloria Hallelujah likewise, and Nunito Black from
`fonts-nunito`; the mockups also ask fontconfig for Microsoft Sans Serif and
OCR A Extended. The Microsoft fonts may not be passed on, so they are not in
the repo -- only what is rendered with them will ship.

Still to do before the window can use these: renders at 2x (2544 x 1080 for a
scene) for scaled screens, and a picture for every state the program swaps in
-- each radio key in and out, the counter's digits, START lit and unlit, and a
highlight for everything that can be clicked.
