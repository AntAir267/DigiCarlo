"""DigiCarlo - get the pictures off old digital cameras, with dates that are right.

Every camera DigiCarlo is meant for has a clock that is wrong: reset to
2007-01-01 by a battery swap, or unable to count as far as the current year.
So the date a photo ends up with comes from when it was taken off the camera,
not from the camera, while the gaps between shots -- which the camera's clock
does get right between resets -- are kept.

Modules:
    sources   find memory cards, USB cameras and the SiPix Blink II
    archive   the untouched originals and the manifest that remembers them
    media     what a file is, and what the camera's clock said about it
    timeplan  sessions, and the dates each shot will be given
    develop   re-dated, remuxed copies into the library folder
    cli       the digicarlo command
    gui       the digicarlo-gui window
    cartoon   how the window is drawn: paint, type, scenery, the horn
    blinky    the SiPix Blink II driver, taken from Blinky (see BLINKY_SOURCE)
"""

__version__ = "1.3.0"
APP_NAME = "DigiCarlo"
