"""The dialog a media player opens.

Shown rather than run modally, for the reason the dashboard is: doModal()
would block the thread that opened it, and the progress has to be carried
forward while the dialog stands. Kodi hands it the input all the same -
WindowXMLDialog reports itself as modal, and the window manager offers an
action to the topmost modal dialog before the active window sees it.
"""

import time

import xbmcgui

from . import actions as ha_actions
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
POWER_STEP = 68

# The volume row: a slider where the player takes a level, two step buttons
# where it does not, and muting either way.
SLIDER_VOLUME = 150
BUTTON_MUTE = 151
IMAGE_MUTE = 152
BUTTON_DOWN = 153
IMAGE_DOWN = 154
BUTTON_UP = 155
IMAGE_UP = 156
VOLUME_SIZE = 44
VOLUME_GAP = 12
VOLUME_INSET = 10
SLIDER_WIDTH = 300

# Home Assistant is told at most this often while the slider moves.
_VOLUME_INTERVAL = 0.25

_MUTE = ha_actions.Action("action_mute", ha_actions.SERVICE, "media_player",
                          "volume_mute", {"flip": "is_volume_muted"})

_VOLUME_BUTTONS = ((BUTTON_MUTE, IMAGE_MUTE, "volume-high"),
                   (BUTTON_DOWN, IMAGE_DOWN, "volume-minus"),
                   (BUTTON_UP, IMAGE_UP, "volume-plus"))

# What Home Assistant draws on the speaker once the player is muted.
_MUTED_ICON = "volume-off"

TRACK_WIDTH = 560
BUTTON_SIZE = 56
BUTTON_GAP = 24
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
        self._pending_volume = None
        self._volume_due = 0.0

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
        # Kodi never tells a script that a slider moved: it sends a click
        # that the Python wrapper refuses. So the value is read back here,
        # after Kodi has already acted on the key.
        if self._focused() == SLIDER_VOLUME:
            self._pending_volume = self._level()
            return
        for name in _KEYS.get(code, ()):
            if self._command(name):
                return

    def onClick(self, control_id):
        service = self._slots.get(control_id)
        if service:
            self._call(self._entity_id, service)
            return
        state = self._store.states.get(self._entity_id)
        if state is None:
            return
        if control_id == BUTTON_MUTE:
            self._call(self._entity_id, "volume_mute",
                       ha_actions.service_data(_MUTE, state))
        elif control_id == BUTTON_DOWN:
            self._call(self._entity_id, "volume_down")
        elif control_id == BUTTON_UP:
            self._call(self._entity_id, "volume_up")

    # -- driven by the dashboard's own loop ------------------------------

    def tick(self):
        self._flush_volume()
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
        # Elapsed on its own says nothing: without a duration there is
        # nothing for it to be elapsed against, and Home Assistant shows no
        # progress at all for a live stream.
        for control_id in (IMAGE_TRACK, IMAGE_FILL, LABEL_ELAPSED, LABEL_DURATION):
            self._show(control_id, share is not None)
        self._set(LABEL_ELAPSED, media.clock(media.elapsed(state)))
        self._set(LABEL_DURATION, media.clock(media.duration(state)))
        if share is not None:
            self._width(IMAGE_FILL, max(2, int(TRACK_WIDTH * share)))

        rows = [self._power(state), self._buttons(state), self._volume(state)]
        self._wire(rows)
        # The transport row first, else the volume row, else power.
        visible = [control for row in rows for control in row]
        wanted = rows[1] or rows[2] or rows[0]
        if wanted and self._focused() not in visible:
            self._focus(wanted[0])

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
            self._place(button, x)
            self._place(image, x + ICON_INSET)

        return [button for button, _ in zip(BUTTONS, drawn)]

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
            self._place(button, x)
            self._place(image, x + ICON_INSET)

        return [button for button, _ in zip(POWER_BUTTONS, drawn)]

    def _picture(self, state):
        """Everything that decides what is on screen, to redraw only on change."""
        _, level, _ = media.volume(state)
        return (state.state, state.attributes.get("media_title"),
                media.clock(media.elapsed(state)), media.duration(state),
                round(level * 100) if level is not None else None,
                state.attributes.get("is_volume_muted"))

    def _flush_volume(self):
        """Send what the slider was left at, a few times a second at most."""
        if self._pending_volume is None:
            return
        now = time.time()
        if now < self._volume_due:
            return
        self._volume_due = now + _VOLUME_INTERVAL
        level, self._pending_volume = self._pending_volume, None
        self._call(self._entity_id, "volume_set", {"volume_level": level})

    def _volume(self, state):
        mute, level, steps = media.volume(state)
        shown = ([BUTTON_MUTE] if mute else []) + (
            [BUTTON_DOWN, BUTTON_UP] if steps else [])
        span = len(shown) * VOLUME_SIZE + max(0, len(shown) - 1) * VOLUME_GAP
        if level is not None:
            span += (VOLUME_GAP if shown else 0) + SLIDER_WIDTH
        left = CENTRE - span // 2

        for button, image, icon in _VOLUME_BUTTONS:
            filled = button in shown
            self._show(button, filled)
            self._show(image, filled)
            if not filled:
                continue
            if button == BUTTON_MUTE and media.muted(state):
                icon = _MUTED_ICON
            self._image(image, "icons/%s.png" % icon)
            self._place(button, left)
            self._place(image, left + VOLUME_INSET)
            left += VOLUME_SIZE + VOLUME_GAP

        self._show(SLIDER_VOLUME, level is not None)
        if level is None:
            return shown
        self._place(SLIDER_VOLUME, left)
        # Not while it has the focus: setting it under a moving thumb would
        # fight whoever is moving it.
        if self._focused() != SLIDER_VOLUME:
            self._percent(SLIDER_VOLUME, level * 100)
        return shown + [SLIDER_VOLUME]

    def _level(self):
        try:
            percent = self.getControl(SLIDER_VOLUME).getPercent()
        except RuntimeError:
            return None
        return max(0.0, min(1.0, percent / 100.0))

    def _percent(self, control_id, value):
        try:
            self.getControl(control_id).setPercent(value)
        except RuntimeError:
            pass

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

    def _wire(self, rows):
        """Give the visible controls their neighbours, top row first.

        Kodi's own navigation cannot do this: how many buttons a row holds
        depends on the player, and a hidden control can only hand a move on
        to one fixed successor. Python knows what is on screen, so it says -
        the same division of labour as with the positions.
        """
        rows = [row for row in rows if row]
        for index, row in enumerate(rows):
            above = rows[(index - 1) % len(rows)]
            below = rows[(index + 1) % len(rows)]
            for position, control_id in enumerate(row):
                self._navigate(control_id, above[0], below[0],
                               row[(position - 1) % len(row)],
                               row[(position + 1) % len(row)])

    def _navigate(self, control_id, up, down, left, right):
        try:
            self.getControl(control_id).setNavigation(
                self.getControl(up), self.getControl(down),
                self.getControl(left), self.getControl(right))
        except RuntimeError:
            pass

    def _place(self, control_id, x):
        """Move a control sideways, leaving the y the layout gave it.

        The window XML owns the vertical geometry and this packs a row
        horizontally. Reading the y back is what keeps the two from drifting:
        they did once, and the transport row came to rest on the volume row.
        """
        try:
            control = self.getControl(control_id)
            control.setPosition(x, control.getY())
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
