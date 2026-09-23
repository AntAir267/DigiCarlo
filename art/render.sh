#!/bin/sh
# Rebuild every picture in out/ from the scenes: the textures, the POV-Ray
# renders, the filled Photo Board and the three window mockups.
#
#     art/render.sh           full quality (about a minute on 24 threads)
#     art/render.sh quick     no radiosity or soft shadows, for checking layout
#
# Needs povray (3.7), python3 with Pillow, and rsvg-convert (librsvg2-bin).
set -e
cd "$(dirname "$0")"
mkdir -p tex out

if [ "$1" = quick ]; then
    quality="+A0.3 Declare=Rad=0 Declare=Area=0"
else
    quality="+A0.1 +AM2 +R3"
fi

python3 textures.py
python3 dial.py

# pov SCENE OUTPUT WIDTH HEIGHT [POV-Ray options...]
pov() {
    scene=$1 name=$2 w=$3 h=$4
    shift 4
    if ! povray -D +I"$scene" +O"out/$name" +W"$w" +H"$h" $quality +WT"$(nproc)" "$@" \
            >"out/${name%.png}.log" 2>&1; then
        tail -20 "out/${name%.png}.log"
        exit 1
    fi
    echo "rendered out/$name"
}

pov garage.pov    garage_w.png        1272 540
pov garage.pov    garage_polaroid.png 1272 540 Declare=Card=1
pov board.pov     board_w.png         1272 540
pov console.pov   console_w.png       1272 230 Declare=Mode=0 Declare=Lit=4
pov console.pov   console_board.png   1272 230 Declare=Mode=1 Declare=Lit=1
pov console.pov   console_trust.png   1272 230 Declare=Mode=0 Declare=Lit=0
pov clockicon.pov clock_icon.png       128 128 +UA

python3 board_content.py
for m in garage board trust; do
    python3 compose.py $m
    rsvg-convert out/mockup_$m.svg -o out/mockup_$m.png
    echo "composed out/mockup_$m.png"
done
