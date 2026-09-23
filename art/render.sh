#!/bin/sh
# Render every picture the window uses, at twice its logical size, and turn
# them into the program's assets in ../digicarlo/scenes/ (see assets.py).
#
#     art/render.sh           full quality: about a quarter of an hour on 24 threads
#     art/render.sh quick     no bounced light or soft shadows, for checking layout
#     art/render.sh check     full quality, plus out/check-*.png showing the
#                             hotspots and the surfaces the program paints on
#
# Needs povray (3.7) and python3 with Pillow and numpy.
set -e
cd "$(dirname "$0")"
mkdir -p tex out

full="+A0.1 +AM2 +R3"
if [ "$1" = quick ]; then
    full="+A0.3 Declare=Rad=0 Declare=Area=0"
fi

python3 textures.py
python3 dial.py

# pov SCENE OUTPUT WIDTH HEIGHT [POV-Ray options...]
pov() {
    scene=$1 name=$2 w=$3 h=$4
    shift 4
    if ! povray -D +I"$scene" +O"out/$name" +W"$w" +H"$h" +WT"$(nproc)" "$@" \
            >"out/${name%.png}.log" 2>&1; then
        tail -20 "out/${name%.png}.log"
        exit 1
    fi
    echo "rendered out/$name"
}

# Each scene's bounced light is worked out once, with nothing switched on
# that glows, and every variant reuses it: then a variant differs from the
# background only where something changed.
# reuse NAME: the options for rendering from NAME's saved bounced light
reuse() {
    [ "$1" = none ] && return
    echo "Declare=Reuse=1 Radiosity_File_Name=out/$1.rad Radiosity_From_File=on"
}
radpass() {
    scene=$1 name=$2 w=$3 h=$4
    shift 4
    if [ "$full" = "+A0.1 +AM2 +R3" ]; then
        pov "$scene" "$name-radpass.png" "$w" "$h" +A0.3 "$@" \
            Radiosity_File_Name="out/$name.rad" Radiosity_To_File=on >&2
        echo "$name"
    else
        echo none
    fi
}

# the garage: empty, then with each thing that comes and goes
G="2544 1080"
rad=$(radpass garage.pov garage $G Declare=Card=1 Declare=Blink=1 Declare=Safe=0)
pov garage.pov garage.png           $G $full $(reuse $rad) Declare=Card=0 Declare=Blink=0 Declare=Safe=0
pov garage.pov garage-card.png      $G $full $(reuse $rad) Declare=Card=1 Declare=Blink=0 Declare=Safe=0
pov garage.pov garage-blink.png     $G $full $(reuse $rad) Declare=Card=0 Declare=Blink=1 Declare=Safe=0
pov garage.pov garage-safelight.png $G $full $(reuse $rad) Declare=Card=0 Declare=Blink=0 Declare=Safe=1
# outlines of the clickable things: flat, quick renders leaving each out
quick="+A0.1 Declare=Rad=0 Declare=Area=0"
pov garage.pov garage-q.png $G $quick
for n in 1 2 3 4 5 6; do
    pov garage.pov garage-q-hide$n.png $G $quick Declare=Hide=$n
done

# the garage's console: every key, START's two lamps, and each counter digit
C="2544 460"
rad=$(radpass console.pov console-garage $C Declare=Mode=0)
pov console.pov console-garage.png $C $full $(reuse $rad) Declare=Mode=0
for k in 1 2 3 4 5; do
    pov console.pov console-garage-key$k.png $C $full $(reuse $rad) Declare=Mode=0 Declare=Lit=$k
done
pov console.pov console-garage-start.png $C $full $(reuse $rad) Declare=Mode=0 Declare=Go=1
pov console.pov console-garage-stop.png  $C $full $(reuse $rad) Declare=Mode=0 Declare=Go=2
for d in 1 2 3 4 5 6 7 8 9; do
    pov console.pov console-garage-digit$d.png $C $full $(reuse $rad) Declare=Mode=0 Declare=Digit=$d
done
pov console.pov console-garage-q.png $C $quick Declare=Mode=0
for n in 1 2 3 4 5 6 7 8 9 10; do
    pov console.pov console-garage-q-hide$n.png $C $quick Declare=Mode=0 Declare=Hide=$n
done

python3 assets.py $([ "$1" = check ] && echo check)
