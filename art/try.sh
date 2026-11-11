#!/bin/sh
# Test renders, to look at a change before the full render (render.sh); they
# go in out/try/. Meant for the T7 (see README.md), like the full render.
#
#     art/try.sh [board] [garage] [night] [toy]   (board, garage and toy
#                                                  when none is named)
#
#   board    the Photo Board at full size, without bounced light (layout)
#   garage   the garage at half size with bounced light: by day and by night,
#            the light on and off (how the lighting reads)
#   night    just the two by night
#   desk     the desk lamp switched off, by day and by night with the light off
#   toy      the board's toy Metropolitan close up, as the board's camera sees it
set -e
cd "$(dirname "$0")"
mkdir -p tex out/try
python3 textures.py

try() {
    t_name=$1
    shift
    if ! povray -D +O"out/try/$t_name.png" +WT"$(nproc)" "$@" >"out/try/$t_name.log" 2>&1; then
        tail -20 "out/try/$t_name.log"
        exit 1
    fi
    echo "rendered out/try/$t_name.png in $(sed -n 's/.*Trace Time:.*(\(.*\) seconds).*/\1/p' "out/try/$t_name.log") s"
}

[ $# -eq 0 ] && set -- board garage toy
for what in "$@"; do
    case $what in
    board)
        try board +Iboard.pov +W2544 +H1080 +A0.3 Declare=Rad=0 Declare=Area=0 ;;
    garage)
        half="+Igarage.pov +W1272 +H540 +A0.3 Declare=Area=0 Declare=Card=0 Declare=Safe=0"
        try garage-day        $half
        try garage-dark       $half Declare=Lamp=0
        try garage-night      $half Declare=Night=1
        try garage-night-dark $half Declare=Night=1 Declare=Lamp=0 ;;
    night)
        half="+Igarage.pov +W1272 +H540 +A0.3 Declare=Area=0 Declare=Card=0 Declare=Safe=0"
        try garage-night      $half Declare=Night=1
        try garage-night-dark $half Declare=Night=1 Declare=Lamp=0 ;;
    desk)
        half="+Igarage.pov +W1272 +H540 +A0.3 Declare=Area=0 Declare=Card=1 Declare=Safe=0 Declare=Desk=0"
        try garage-desk-off            $half
        try garage-night-dark-desk-off $half Declare=Night=1 Declare=Lamp=0 ;;
    toy)
        try toy +Icar_test.pov +W1200 +H700 +A0.2 Declare=Toy=1 Declare=View=3 ;;
    *)
        echo "try.sh: no such test: $what" >&2
        exit 1 ;;
    esac
done
