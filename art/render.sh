#!/bin/sh
# Render every picture the window uses, at twice its logical size, and turn
# them into the program's assets in ../digicarlo/scenes/ (see assets.py).
#
#     art/render.sh           full quality: about an hour on 24 threads
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
quick="+A0.1 Declare=Rad=0 Declare=Area=0"

python3 textures.py
python3 dial.py

# pov SCENE OUTPUT WIDTH HEIGHT [POV-Ray options...]
# (Shell functions share their variables, so each function's are its own.)
pov() {
    p_scene=$1 p_out=$2 p_w=$3 p_h=$4
    shift 4
    if ! povray -D +I"$p_scene" +O"out/$p_out" +W"$p_w" +H"$p_h" +WT"$(nproc)" "$@" \
            >"out/${p_out%.png}.log" 2>&1; then
        tail -20 "out/${p_out%.png}.log"
        exit 1
    fi
    echo "rendered out/$p_out"
}

# Each scene's bounced light is worked out once, with nothing switched on
# that glows, and every variant reuses it: then a variant differs from the
# background only where something changed.
# reuse NAME: the options for rendering from NAME's saved bounced light
reuse() {
    [ "$1" = none ] && return
    [ -s "out/$1.rad" ] || { echo "no saved bounced light: out/$1.rad" >&2; exit 1; }
    echo "Declare=Reuse=1 Radiosity_File_Name=out/$1.rad Radiosity_From_File=on"
}
radpass() {
    r_scene=$1 r_name=$2 r_w=$3 r_h=$4
    shift 4
    if [ "$full" = "+A0.1 +AM2 +R3" ]; then
        rm -f "out/$r_name.rad"
        pov "$r_scene" "$r_name-radpass.png" "$r_w" "$r_h" +A0.3 "$@" \
            Radiosity_File_Name="out/$r_name.rad" Radiosity_To_File=on >&2
        [ -s "out/$r_name.rad" ] || { echo "no bounced light saved for $r_name" >&2; exit 1; }
        echo "$r_name"
    else
        echo none
    fi
}
# outlines SCENE NAME W H COUNT [options]: a flat quick render, and one more
# leaving out each clickable thing in turn
outlines() {
    o_scene=$1 o_name=$2 o_w=$3 o_h=$4 o_count=$5
    shift 5
    pov "$o_scene" "$o_name-q.png" "$o_w" "$o_h" $quick "$@"
    o_n=1
    while [ $o_n -le "$o_count" ]; do
        pov "$o_scene" "$o_name-q-hide$o_n.png" "$o_w" "$o_h" $quick "$@" Declare=Hide=$o_n
        o_n=$((o_n + 1))
    done
}

S="2544 1080"       # a scene
C="2544 460"        # the console

# the garage: empty, then with each thing that comes and goes; then the
# same in the dark, with the light over the car switched off; and the car's
# headlights, in the light and in the dark
rad=$(radpass garage.pov garage $S Declare=Card=1 Declare=Blink=1 Declare=Safe=0)
use=$(reuse $rad)
pov garage.pov garage.png           $S $full $use Declare=Card=0 Declare=Blink=0 Declare=Safe=0
pov garage.pov garage-card.png      $S $full $use Declare=Card=1 Declare=Blink=0 Declare=Safe=0
pov garage.pov garage-blink.png     $S $full $use Declare=Card=0 Declare=Blink=1 Declare=Safe=0
pov garage.pov garage-safelight.png $S $full $use Declare=Card=0 Declare=Blink=0 Declare=Safe=1
pov garage.pov garage-beams.png     $S $full $use Declare=Card=0 Declare=Blink=0 Declare=Safe=0 Declare=Beams=1
rad=$(radpass garage.pov garage-dark $S Declare=Lamp=0 Declare=Card=1 Declare=Blink=1 Declare=Safe=0)
use=$(reuse $rad)
dark="Declare=Lamp=0"
pov garage.pov garage-dark.png           $S $full $use $dark Declare=Card=0 Declare=Blink=0 Declare=Safe=0
pov garage.pov garage-dark-card.png      $S $full $use $dark Declare=Card=1 Declare=Blink=0 Declare=Safe=0
pov garage.pov garage-dark-blink.png     $S $full $use $dark Declare=Card=0 Declare=Blink=1 Declare=Safe=0
pov garage.pov garage-dark-safelight.png $S $full $use $dark Declare=Card=0 Declare=Blink=0 Declare=Safe=1
pov garage.pov garage-dark-beams.png     $S $full $use $dark Declare=Card=0 Declare=Blink=0 Declare=Safe=0 Declare=Beams=1
outlines garage.pov garage $S 8

# the Photo Board, and its wastebasket with left-out prints in it
rad=$(radpass board.pov board $S Declare=Trash=1)
use=$(reuse $rad)
pov board.pov board.png       $S $full $use Declare=Trash=0
pov board.pov board-trash.png $S $full $use Declare=Trash=1
outlines board.pov board $S 6 Declare=Trash=1

# the console: every key, START's two lamps and each counter digit in the
# garage; then the board's dial, and every key again with it
rad=$(radpass console.pov console $C Declare=Mode=0)
use=$(reuse $rad)
pov console.pov console.png $C $full $use Declare=Mode=0
for k in 1 2 3 4 5; do
    pov console.pov console-key$k.png $C $full $use Declare=Mode=0 Declare=Lit=$k
done
pov console.pov console-start.png $C $full $use Declare=Mode=0 Declare=Go=1
pov console.pov console-stop.png  $C $full $use Declare=Mode=0 Declare=Go=2
for d in 1 2 3 4 5 6 7 8 9; do
    pov console.pov console-digit$d.png $C $full $use Declare=Mode=0 Declare=Digit=$d
done
pov console.pov console-board.png $C $full $use Declare=Mode=1
for k in 1 2 3 4 5; do
    pov console.pov console-board-key$k.png $C $full $use Declare=Mode=1 Declare=Lit=$k
done
outlines console.pov console $C 11 Declare=Mode=0

# the map pins, and the alarm clock for the trust-the-camera's-clock dialog
for c in 1 2 3 4 5; do
    pov pin.pov pin$c.png 48 48 $full +UA Declare=Colour=$c
done
pov clockicon.pov clock-icon.png 128 128 $full +UA

python3 assets.py $([ "$1" = check ] && echo check)
