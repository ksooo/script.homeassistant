"""Steering a Reolink camera from the remote while its live picture plays.

Reolink only. Home Assistant has no pan and tilt of its own, so the addon
uses the buttons the Reolink integration puts on a camera's device. The
steering cross appears where the camera comes from that integration and its
device carries the left, right, up, down and stop buttons, all enabled -
Reolink creates them only for cameras that pan and tilt. OK goes to the
home position where the device has that button too, and the moves go at a
gentle speed where Reolink marks the buttons as taking one. Every other
camera plays in Kodi's player as it always did.

The dialog lies over Kodi's fullscreen video and takes the arrows, OK and
Back. Kodi still hands the player whatever the dialog leaves alone and the
player handles anywhere - pause, stop, the volume.

Reolink moves until it is told to stop, and Kodi never says that a key was
let go. So a press is a short step: the move, and a stop a moment after the
last press - which a held key, repeating, keeps putting off.

The picture comes seconds late, so the arrow lights up for the move it
stands for - the whole cross for the way home - and turns red for a moment
where the camera would not take it -
Home Assistant answers only once the camera has, so a refusal is known at
once, long before the picture could tell.
"""

import time

import xbmcgui

from . import formatting

# How long a move runs after the last press of its key.
_STEP = 0.3
# How long a refused move stays red, and new presses of it wait.
_REFUSED = 1.5
# How long the cross stays lit once the camera has taken the way home.
_HOME_LIT = 1.0

_MOVING = "FF41BDF5"
_FAILED = formatting.RED

ACTION_MOVE_LEFT = 1
ACTION_MOVE_RIGHT = 2
ACTION_MOVE_UP = 3
ACTION_MOVE_DOWN = 4
ACTION_SELECT_ITEM = 7
ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92

_MOVES = {ACTION_MOVE_LEFT: "left", ACTION_MOVE_RIGHT: "right",
          ACTION_MOVE_UP: "up", ACTION_MOVE_DOWN: "down"}


class PtzDialog(xbmcgui.WindowXMLDialog):
    def __init__(self, xml_file, resource_path, theme_skin, theme_res, **kwargs):
        super().__init__()
        self._buttons = kwargs["buttons"]
        self._press = kwargs["press"]
        self._move = kwargs["move"]
        self._end = kwargs["end"]
        self._moving = None
        self._stop_due = 0.0
        self._refused_until = 0.0
        self._lit_until = 0.0
        self.closed = False

    def onAction(self, action):
        code = action.getId()
        if code in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
            self.finish()
            self._end()
            return
        move = _MOVES.get(code)
        if move is not None:
            if time.time() < self._refused_until:
                return
            # A held key repeats; the camera is told once and kept going.
            if move != self._moving:
                self._moving = move
                self._lit_until = 0.0
                self._light(move, _MOVING)
                if not self._move(self._buttons[move]):
                    self._moving = None
                    self._light(move, _FAILED)
                    self._refused_until = time.time() + _REFUSED
                    return
            self._stop_due = time.time() + _STEP
        elif code == ACTION_SELECT_ITEM and "home" in self._buttons:
            # Going home is a move of its own; a stop still due would cut it short.
            self._moving = None
            self._light("home", _MOVING)
            if self._press(self._buttons["home"]):
                self._lit_until = time.time() + _HOME_LIT
            else:
                self._light("home", _FAILED)
                self._refused_until = time.time() + _REFUSED

    def tick(self):
        now = time.time()
        if self._moving is not None and now >= self._stop_due:
            self._stop()
        elif self._refused_until and now >= self._refused_until:
            self._refused_until = 0.0
            self.clearProperty("ptz_move")
        elif self._lit_until and now >= self._lit_until:
            self._lit_until = 0.0
            self.clearProperty("ptz_move")

    def finish(self):
        if self._moving is not None:
            self._stop()
        self.closed = True
        self.close()

    def _stop(self):
        self._moving = None
        self.clearProperty("ptz_move")
        self._press(self._buttons["stop"])

    def _light(self, move, colour):
        self.setProperty("ptz_colour", colour)
        self.setProperty("ptz_move", move)
