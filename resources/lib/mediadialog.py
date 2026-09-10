"""The dialog a media player opens.

Shown rather than run modally, for the reason the dashboard is: doModal()
would block the thread that opened it, and the progress has to be carried
forward while the dialog stands. Kodi hands it the input all the same -
WindowXMLDialog reports itself as modal, and the window manager offers an
action to the topmost modal dialog before the active window sees it.
"""

import xbmcgui

from . import formatting, kodi, media

LABEL_ROOM = 100
LABEL_NAME = 101
IMAGE_ART = 102
IMAGE_ICON = 103
LABEL_TITLE = 104
LABEL_SUBTITLE = 105
IMAGE_TRACK = 106
IMAGE_FILL = 107
LABEL_ELAPSED = 108
LABEL_DURATION = 109
# Five slots, filled left to right with whatever the player offers.
BUTTONS = (120, 121, 122, 123, 124)
BUTTON_ICONS = (130, 131, 132, 133, 134)
# Two slots at the top right, filled from the right edge inwards.
POWER_BUTTONS = (140, 142)
POWER_ICONS = (141, 143)
POWER_RIGHT = 898
POWER_TOP = 66
POWER_STEP = 68

TRACK_WIDTH = 560
BUTTON_SIZE = 56
BUTTON_GAP = 24
BUTTON_TOP = 584
ICON_INSET = 16
CENTRE = 640

ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92
ACTION_PAUSE = 12
ACTION_STOP = 13
ACTION_NEXT_ITEM = 14
ACTION_PREV_ITEM = 15
ACTION_PLAYER_PLAYPAUSE = 229

_ICONS = {"previous": "skip-previous", "pause": "pause", "play": "play",
          "stop": "stop", "next": "skip-next", "power": "power",
          "power_on": "power-on", "power_off": "power-off"}

# The remote's own transport keys, which a web page cannot have. The play
# key takes whichever of the two the player is offering.
_KEYS = {ACTION_PLAYER_PLAYPAUSE: ("pause", "play"),
         ACTION_PAUSE: ("pause", "play"),
         ACTION_STOP: ("stop",),
         ACTION_NEXT_ITEM: ("next",),
         ACTION_PREV_ITEM: ("previous",)}


class MediaDialog(xbmcgui.WindowXMLDialog):
    def __init__(self, xml_file, resource_path, theme_skin, theme_res, **kwargs):
        super().__init__()
        self._store = kwargs["store"]
        self._entity_id = kwargs["entity_id"]
        self._icon = kwargs["icon"]
        self._art_url = kwargs["art_url"]
        self._call = kwargs["call"]
        self.closed = False
        self._drawn = None
        self._slots = {}
        self._drawn_buttons = False

    # -- Kodi callbacks --------------------------------------------------

    def onInit(self):
        if self._icon:
            self._image(IMAGE_ICON, self._icon)
        self._draw()

    def onAction(self, action):
        code = action.getId()
        if code in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
            # onAction is overridden, so the base class no longer closes.
            self.closed = True
            self.close()
            return
        for name in _KEYS.get(code, ()):
            if self._command(name):
                return

    def onClick(self, control_id):
        service = self._slots.get(control_id)
        if service:
            self._call(self._entity_id, service)

    # -- driven by the dashboard's own loop ------------------------------

    def tick(self):
        state = self._store.states.get(self._entity_id)
        if state is not None and self._picture(state) != self._drawn:
            self._draw(state)

    # -- drawing ---------------------------------------------------------

    def _draw(self, state=None):
        state = state or self._store.states.get(self._entity_id)
        if state is None:
            return
        area_id = self._store.area_of(self._entity_id)
        self._set(LABEL_ROOM, (self._store.areas.get(area_id) or {}).get("name", ""))
        self._set(LABEL_NAME, self._store.display_name_of(self._entity_id))
        self._set(LABEL_TITLE, state.attributes.get("media_title")
                  or formatting.state_text(self._store, self._entity_id, kodi.tr))
        self._set(LABEL_SUBTITLE, media.subtitle(state))

        picture = state.attributes.get("entity_picture")
        if picture:
            # Not cached: the picture's URL carries a token that turns over
            # with every medium, and Kodi caches by URL.
            self._image(IMAGE_ART, self._art_url(picture), cache=False)
        self._show(IMAGE_ART, bool(picture))
        self._show(IMAGE_ICON, not picture and bool(self._icon))

        share = media.fraction(state)
        for control_id in (IMAGE_TRACK, IMAGE_FILL):
            self._show(control_id, share is not None)
        self._set(LABEL_ELAPSED, media.clock(media.elapsed(state)))
        self._set(LABEL_DURATION, media.clock(media.duration(state)))
        if share is not None:
            self._width(IMAGE_FILL, max(2, int(TRACK_WIDTH * share)))

        self._buttons(state)
        self._power(state)

        self._drawn = self._picture(state)

    def _buttons(self, state):
        """Only what the player can do, centred on whatever is left.

        Hidden rather than disabled: a disabled button is not told apart from
        a working one in this skin, and a row where half of it does nothing
        invites pressing it.
        """
        drawn = media.controls(state)[:len(BUTTONS)]
        self._slots = {}
        span = len(drawn) * BUTTON_SIZE + max(0, len(drawn) - 1) * BUTTON_GAP
        left = CENTRE - span // 2
        for slot, (button, image) in enumerate(zip(BUTTONS, BUTTON_ICONS)):
            filled = slot < len(drawn)
            self._show(button, filled)
            self._show(image, filled)
            if not filled:
                continue
            name, service = drawn[slot]
            self._slots[button] = service
            self._image(image, "icons/%s.png" % _ICONS[name])
            x = left + slot * (BUTTON_SIZE + BUTTON_GAP)
            self._move(button, x, BUTTON_TOP)
            self._move(image, x + ICON_INSET, BUTTON_TOP + ICON_INSET)

        self._drawn_buttons = bool(drawn)

    def _power(self, state):
        drawn = media.power(state)[:len(POWER_BUTTONS)]
        for slot, (button, image) in enumerate(zip(POWER_BUTTONS, POWER_ICONS)):
            filled = slot < len(drawn)
            self._show(button, filled)
            self._show(image, filled)
            if not filled:
                continue
            name, service = drawn[slot]
            self._slots[button] = service
            self._image(image, "icons/%s.png" % _ICONS[name])
            # Right-aligned, so a single button keeps the corner.
            x = POWER_RIGHT - (len(drawn) - 1 - slot) * POWER_STEP
            self._move(button, x, POWER_TOP)
            self._move(image, x + ICON_INSET, POWER_TOP + ICON_INSET)

        # Whatever is left focusable: the transport row first, else power.
        if self._focused() not in self._slots:
            if self._drawn_buttons:
                self._focus(BUTTONS[0])
            elif drawn:
                self._focus(POWER_BUTTONS[0])

    def _picture(self, state):
        """Everything that decides what is on screen, to redraw only on change."""
        return (state.state, state.attributes.get("media_title"),
                media.clock(media.elapsed(state)), media.duration(state))

    def _command(self, name):
        state = self._store.states.get(self._entity_id)
        if state is None:
            return False
        for offered, service in media.controls(state):
            if offered == name:
                self._call(self._entity_id, service)
                return True
        return False

    # Every control access is guarded: Kodi frees them when the dialog goes.
    def _set(self, control_id, text):
        try:
            self.getControl(control_id).setLabel(text)
        except RuntimeError:
            pass

    def _image(self, control_id, path, cache=True):
        try:
            self.getControl(control_id).setImage(path, cache)
        except RuntimeError:
            pass

    def _show(self, control_id, visible):
        try:
            self.getControl(control_id).setVisible(visible)
        except RuntimeError:
            pass

    def _move(self, control_id, x, y):
        try:
            self.getControl(control_id).setPosition(x, y)
        except RuntimeError:
            pass

    def _focused(self):
        try:
            return self.getFocusId()
        except RuntimeError:
            return 0

    def _focus(self, control_id):
        try:
            self.setFocusId(control_id)
        except RuntimeError:
            pass

    def _width(self, control_id, width):
        try:
            self.getControl(control_id).setWidth(width)
        except RuntimeError:
            pass
