# Assemble the mockup: a Windows 95 window holding the pre-rendered garage
# and console, with the parts the program would draw live on top.
import sys
MODE = sys.argv[1] if len(sys.argv) > 1 else 'garage'
W, H = 1280, 840
VX, VY = 4, 44           # viewport origin
CY = VY + 540            # console top
SANS = 'font-family="Microsoft Sans Serif"'
MONO = 'font-family="&apos;OCR A Extended&apos;"'
out = []
def a(s): out.append(s)
def bevel(x, y, w, h, raised=True):
    tl, br, itl, ibr = ("#DFDFDF", "#000000", "#FFFFFF", "#808080") if raised else ("#808080", "#FFFFFF", "#000000", "#DFDFDF")
    a(f'<path d="M{x} {y+h-1} V{y} H{x+w-1}" stroke="{tl}" fill="none"/>')
    a(f'<path d="M{x} {y+h-0.5} H{x+w-0.5} V{y}" stroke="{br}" fill="none"/>')
    a(f'<path d="M{x+1} {y+h-2} V{y+1} H{x+w-2}" stroke="{itl}" fill="none"/>')
    a(f'<path d="M{x+1} {y+h-1.5} H{x+w-1.5} V{y+1}" stroke="{ibr}" fill="none"/>')
a(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}" shape-rendering="crispEdges">')
a('''<defs>
  <filter id="glow" x="-10%" y="-30%" width="120%" height="160%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <filter id="hot" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="5"/></filter>
  <pattern id="scan" width="4" height="3" patternUnits="userSpaceOnUse"><rect width="4" height="1" fill="#000" fill-opacity="0.35"/></pattern>
  <clipPath id="crt"><rect x="52" y="{CYS}" width="354" height="142" rx="6"/></clipPath>
</defs>'''.replace("{CYS}", str(CY + 42)))
# window frame
a(f'<rect width="{W}" height="{H}" fill="#C0C0C0"/>')
bevel(0, 0, W, H)
# title bar: Windows 95, navy
a(f'<rect x="4" y="4" width="{W-8}" height="18" fill="#000080"/>')
a('<rect x="7" y="6" width="14" height="14" rx="2" fill="#2EA3B9" stroke="#FFFFFF" stroke-width="1"/><circle cx="14" cy="13" r="4" fill="#FFFFFF"/><circle cx="14" cy="13" r="2" fill="#10304A"/>')
a(f'<text x="26" y="17" {SANS} font-weight="bold" font-size="12" fill="#FFFFFF">DigiCarlo - {"Photo Board" if MODE == "board" else "The Garage"}</text>')
for i, g in enumerate(("min", "max", "close")):
    x = W - 8 - 16 * (3 - i) - (2 if g == "close" else 0) + (0 if g != "close" else 2)
    x = [W - 58, W - 42, W - 22][i]
    a(f'<rect x="{x}" y="6" width="16" height="14" fill="#C0C0C0"/>')
    bevel(x, 6, 16, 14)
    if g == "min":
        a(f'<rect x="{x+4}" y="15" width="6" height="2" fill="#000"/>')
    elif g == "max":
        a(f'<rect x="{x+3.5}" y="8.5" width="9" height="8" fill="none" stroke="#000"/><rect x="{x+3}" y="8" width="10" height="2" fill="#000"/>')
    else:
        a(f'<path d="M{x+4} {9} L{x+11} {16} M{x+11} {9} L{x+4} {16}" stroke="#000" stroke-width="1.6"/>')
# menu bar
for x, word in ((10, "File"), (44, "Garage"), (100, "Shots"), (148, "View"), (190, "Help")):
    a(f'<text x="{x}" y="38" {SANS} font-size="12" fill="#000">{word}</text>')
    a(f'<rect x="{x}" y="39.5" width="6.5" height="1" fill="#000"/>')
# sunken frame round the scene
bevel(VX - 2, VY - 2, 1276, 544 + 230 + 0, False)
a(f'<image x="{VX}" y="{VY}" width="1272" height="540" xlink:href="{ {"garage": "garage_w.png", "board": "board_filled.png", "trust": "garage_polaroid.png"}[MODE] }"/>')
a(f'<image x="{VX}" y="{CY}" width="1272" height="230" xlink:href="{ {"garage": "console_w.png", "board": "console_board.png", "trust": "console_trust.png"}[MODE] }"/>')

if MODE == "trust":
    pass
elif MODE == "garage":
    # the KODAK card, hovered: it glows, the hand points, a tooltip explains
    a(f'<g shape-rendering="auto"><ellipse cx="{VX+208}" cy="{VY+300}" rx="48" ry="34" fill="#FFE27A" opacity="0.55" filter="url(#hot)"/>')
    a(f'<image x="{VX}" y="{VY}" width="1272" height="540" xlink:href="garage_w.png" clip-path="url(#cardclip)"/>')
    a(f'<clipPath id="cardclip"><path d="M{VX+188} {VY+272} h32 v28 h28 v22 h-78 v-22 h18 z"/></clipPath></g>')
    hx, hy = VX + 222, VY + 292
    a('<g shape-rendering="auto">')
    a(f'<path d="M{hx} {hy} l0 -14 a3 3 0 0 1 6 0 v10 l0 -3 a3 3 0 0 1 6 0 v4 l0 -2 a3 3 0 0 1 6 0 v4 l0 -1 a3 3 0 0 1 6 0 v11 c0 7 -4 12 -10 12 h-6 c-5 0 -8 -3 -10 -7 l-6 -9 a3 3 0 0 1 5 -3 z" fill="#FFFFFF" stroke="#000" stroke-width="1.4" stroke-linejoin="round"/>')
    a('</g>')
    tx, ty = hx + 18, hy + 30
    a(f'<rect x="{tx}" y="{ty}" width="222" height="19" fill="#FFFFE1" stroke="#000"/>')
    a(f'<text x="{tx+5}" y="{ty+14}" {SANS} font-size="12" fill="#000">Pull 32 new pictures from KODAK</text>')

else:
    hx, hy = VX + 292, VY + 392
    a('<g shape-rendering="auto">')
    a(f'<ellipse cx="{VX+272}" cy="{VY+405}" rx="62" ry="58" fill="#FFE27A" opacity="0.35" filter="url(#hot)"/>')
    a(f'<image x="{VX}" y="{VY}" width="1272" height="540" xlink:href="board_filled.png" clip-path="url(#stampclip)"/>')
    a(f'<clipPath id="stampclip"><rect x="{VX+224}" y="{VY+352}" width="100" height="106"/></clipPath>')
    a(f'<path d="M{hx} {hy} l0 -14 a3 3 0 0 1 6 0 v10 l0 -3 a3 3 0 0 1 6 0 v4 l0 -2 a3 3 0 0 1 6 0 v4 l0 -1 a3 3 0 0 1 6 0 v11 c0 7 -4 12 -10 12 h-6 c-5 0 -8 -3 -10 -7 l-6 -9 a3 3 0 0 1 5 -3 z" fill="#FFFFFF" stroke="#000" stroke-width="1.4" stroke-linejoin="round"/>')
    a('</g>')
    tx, ty = hx + 18, hy + 30
    a(f'<rect x="{tx}" y="{ty}" width="206" height="19" fill="#FFFFE1" stroke="#000"/>')
    a(f'<text x="{tx+5}" y="{ty+14}" {SANS} font-size="12" fill="#000">Stamp shots 9-12 with a date</text>')

# the message screen, drawn live: phosphor green, scanlines
lines = {"garage": ["> SYNC: PIXEL CONNECTED 11:42.",
                    "  PIXEL BACKUP: 604 FILES,",
                    "  100% ON THE PHONE.",
                    "> NOTHING LEFT TO SEND._"],
         "board": ["> SHOTS 9-12 PICKED.",
                   "  CAMERA SAID JAN 1, 2007.",
                   "> SET DATE, OR STAMP THEM",
                   "  WITH THE DATE STAMP._"],
         "trust": ["> POLAROID CARD IN THE READER:",
                   "  21 NEW PICTURES.",
                   "> ITS CLOCK MIGHT BE RIGHT.",
                   "  TRUST IT?_"]}[MODE]
a('<g clip-path="url(#crt)" shape-rendering="auto">')
a(f'<g filter="url(#glow)">')
for i, line in enumerate(lines):
    a(f'<text x="70" y="{CY + 76 + i*28}" {MONO} font-size="16" fill="#86FF9C" xml:space="preserve">{line}</text>')
a('</g>')
a(f'<rect x="52" y="{CY + 42}" width="354" height="142" fill="url(#scan)"/>')
a('</g>')

# ---------------------------------------------------------------------------
# the clock question, as a Windows 95 dialog
# ---------------------------------------------------------------------------
if MODE == "trust":
    DX, DY, DW, DH = 318, 150, 644, 356
    a(f'<rect x="{DX}" y="{DY}" width="{DW}" height="{DH}" fill="#C0C0C0"/>')
    bevel(DX, DY, DW, DH)
    a(f'<rect x="{DX+3}" y="{DY+3}" width="{DW-6}" height="18" fill="#000080"/>')
    a(f'<text x="{DX+8}" y="{DY+16}" {SANS} font-weight="bold" font-size="12" fill="#FFFFFF">POLAROID card - trust the camera\'s clock?</text>')
    bx = DX + DW - 21
    a(f'<rect x="{bx}" y="{DY+5}" width="16" height="14" fill="#C0C0C0"/>')
    bevel(bx, DY + 5, 16, 14)
    a(f'<path d="M{bx+4} {DY+8} L{bx+11} {DY+15} M{bx+11} {DY+8} L{bx+4} {DY+15}" stroke="#000" stroke-width="1.6"/>')
    a(f'<image x="{DX+14}" y="{DY+32}" width="64" height="64" xlink:href="clock_icon.png" shape-rendering="auto"/>')
    text = ["The Polaroid i1237's clock says these 21 pictures were taken between",
            "Sep 17 and Sep 22, 2026. Its clock can be set right, but it sometimes",
            "resets. Tick the sessions whose camera dates you trust:"]
    for i, t in enumerate(text):
        a(f'<text x="{DX+92}" y="{DY+46+i*17}" {SANS} font-size="12" fill="#000">{t}</text>')
    LX, LY, LW, LH = DX + 92, DY + 104, DW - 108, 94
    a(f'<rect x="{LX}" y="{LY}" width="{LW}" height="{LH}" fill="#FFFFFF"/>')
    bevel(LX, LY, LW, LH, False)
    rows = [(True, "Session 1", "8 shots", "Sep 17, 2026", "4:02 - 4:40 pm", "looks right"),
            (True, "Session 2", "9 shots", "Sep 21, 2026", "10:15 - 11:02 am", "looks right"),
            (False, "Session 3", "4 shots", "Jan 1, 2000", "12:00 - 12:03 am", "clock was reset")]
    for i, (on, name, n, day, span, note) in enumerate(rows):
        y = LY + 8 + i * 28
        a(f'<rect x="{LX+10}" y="{y+2}" width="13" height="13" fill="#FFFFFF"/>')
        bevel(LX + 10, y + 2, 13, 13, False)
        if on:
            a(f'<path d="M{LX+13} {y+8} l3 3 l6 -6" stroke="#000" stroke-width="2" fill="none"/>')
        for x, t in ((32, name), (110, n), (170, day), (270, span), (400, note)):
            col = "#A00000" if note.startswith("clock") and x == 400 else "#000"
            a(f'<text x="{LX+x}" y="{y+13}" {SANS} font-size="12" fill="{col}">{t}</text>')
        if i < 2:
            a(f'<path d="M{LX+6} {y+22.5} H{LX+LW-6}" stroke="#E4E4E4"/>')
    a(f'<text x="{DX+92}" y="{DY+220}" {SANS} font-size="12" fill="#000">Shots you leave unticked are dated from when they come off the camera.</text>')
    a(f'<rect x="{DX+92}" y="{DY+238}" width="13" height="13" fill="#FFFFFF"/>')
    bevel(DX + 92, DY + 238, 13, 13, False)
    a(f'<path d="M{DX+95} {DY+244} l3 3 l6 -6" stroke="#000" stroke-width="2" fill="none"/>')
    a(f'<text x="{DX+112}" y="{DY+249}" {SANS} font-size="12" fill="#000">Ask about this camera\'s clock every time</text>')
    for i, (label, default) in enumerate((("Trust ticked", True), ("Date all from now", False))):
        w = 128
        x = DX + DW - 16 - (2 - i) * (w + 10)
        y = DY + DH - 44
        if default:
            a(f'<rect x="{x-1}" y="{y-1}" width="{w+2}" height="{28}" fill="#000"/>')
        a(f'<rect x="{x}" y="{y}" width="{w}" height="26" fill="#C0C0C0"/>')
        bevel(x, y, w, 26)
        a(f'<text x="{x+w/2}" y="{y+17}" text-anchor="middle" {SANS} font-size="12" fill="#000">{label}</text>')
        if default:
            a(f'<rect x="{x+4.5}" y="{y+4.5}" width="{w-9}" height="17" fill="none" stroke="#000" stroke-dasharray="1 1"/>')

# status bar
SY = CY + 230 + 4
for x, w, text in ((4, 520, "Library: ~/Pixel Backup"), (527, 520, "Archive: ~/Pictures/DigiCarlo Archive"), (1050, 226, {"garage": "118 waiting", "board": "16 waiting, 4 picked", "trust": "Pulling from POLAROID..."}[MODE])):
    a(f'<rect x="{x}" y="{SY}" width="{w}" height="18" fill="#C0C0C0"/>')
    a(f'<path d="M{x} {SY+17.5} V{SY+0.5} H{x+w}" stroke="#808080" fill="none"/><path d="M{x+0.5} {SY+17.5} H{x+w-0.5} V{SY}" stroke="#FFFFFF" fill="none"/>')
    a(f'<text x="{x+5}" y="{SY+13}" {SANS} font-size="12" fill="#000">{text}</text>')
for i in range(3):
    o = 4 + i * 4
    a(f'<path d="M{W-5} {H-5-o} L{W-5-o} {H-5}" stroke="#FFFFFF"/><path d="M{W-5} {H-4-o} L{W-4-o} {H-5}" stroke="#808080"/>')
a('</svg>')
open(f"out/mockup_{MODE}.svg", "w").write("\n".join(out))
