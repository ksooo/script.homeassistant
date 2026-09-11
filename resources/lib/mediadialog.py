"""The dialog a media player opens.

Shown rather than run modally, for the reason the dashboard is: doModal()
would block the thread that opened it, and the progress has to be carried
forward while the dialog stands. Kodi hands it the input all the same -
WindowXMLDialog reports itself as modal, and the window manager offers an
action to the topmost modal dialog before the active window sees it.
"""

import os
import time

import xbmcgui

from . import actions as ha_actions
from . import browse, formatting, kodi, media

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
# The device row under the transport, where Home Assistant keeps it too: the
# media tree, the input to switch to, power. Not the transport - these act on
# the box, not on what it is playing.
DEVICE_BUTTONS = (140, 142, 144, 146)
DEVICE_ICONS = (141, 143, 145, 147)

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
ICON_SIZE = 24
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
          "power_on": "power-on", "power_off": "power-off",
          "source": "login-variant", "browse": "play-box-multiple"}

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
        self._fetch = kwargs["browse"]
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
        state = self._store.states.get(self._entity_id)
        if state is None:
            return
        name, service = self._slots.get(control_id, ("", None))
        if name == "browse":
            self._browse()
        elif name == "source":
            self._choose_source(state)
        elif service:
            self._call(self._entity_id, service)
        elif control_id == BUTTON_MUTE:
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

        # Cleared here rather than in a row: each row adds to it, and the one
        # that cleared it used to throw away what the row before had filled in.
        self._slots = {}
        rows = [self._buttons(state), self._volume(state), self._device(state)]
        self._wire(rows)
        # The transport row first, else the volume row, else the device row.
        visible = [control for row in rows for control in row]
        wanted = rows[0] or rows[1] or rows[2]
        if wanted and self._focused() not in visible:
            self._focus(wanted[0])

        self._drawn = self._picture(state)

    def _row(self, buttons, images, drawn, size=BUTTON_SIZE, gap=BUTTON_GAP):
        """Fill a row's slots left to right, centred, and hide the rest.

        Hidden rather than disabled: a disabled button is not told apart from
        a working one in this skin, and a row where half of it does nothing
        invites pressing it.
        """
        span = len(drawn) * size + max(0, len(drawn) - 1) * gap
        left = CENTRE - span // 2
        for slot, (button, image) in enumerate(zip(buttons, images)):
            filled = slot < len(drawn)
            self._show(button, filled)
            self._show(image, filled)
            if not filled:
                continue
            name, service = drawn[slot]
            self._slots[button] = (name, service)
            self._image(image, "icons/%s.png" % _ICONS[name])
            x = left + slot * (size + gap)
            self._place(button, x)
            self._place(image, x + _inset(size))
        return list(buttons[:len(drawn)])

    def _buttons(self, state):
        """The transport: what the player says it can do with the medium."""
        return self._row(BUTTONS, BUTTON_ICONS,
                         media.controls(state)[:len(BUTTONS)])

    def _device(self, state):
        """The box itself: its media tree, its input, its power."""
        drawn = [("browse", None)] if media.can_browse(state) else []
        if media.sources(state):
            drawn.append(("source", "select_source"))
        drawn += media.power(state)
        return self._row(DEVICE_BUTTONS, DEVICE_ICONS,
                         drawn[:len(DEVICE_BUTTONS)])

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
            self._place(image, left + _inset(VOLUME_SIZE))
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

    def _choose_source(self, state):
        names = media.sources(state)
        if not names:
            return
        choice = xbmcgui.Dialog().select(kodi.tr("action_source"), names)
        if choice >= 0:
            self._call(self._entity_id, "select_source", {"source": names[choice]})

    def _browse(self):
        """Walk the player's media tree, one select dialog per level.

        Cancelling steps back out of the level, not out of the tree, which is
        what Home Assistant's own back arrow does. The way back is this list
        because a level's reply cannot be trusted about itself.
        """
        trail = [(None, None, "")]
        while trail:
            content_type, content_id, title = trail[-1]
            node = self._fetch(self._entity_id, content_type, content_id)
            if node is None:
                return
            listing = browse.rows(node, kodi.tr("action_play"))
            if not listing:
                kodi.notify(kodi.tr("browse_empty"))
                trail.pop()
                continue
            choice = xbmcgui.Dialog().select(
                title or str(node.get("title") or ""),
                [self._item(row) for row in listing], useDetails=True)
            if choice < 0:
                trail.pop()
                continue
            row = listing[choice]
            if row.expand:
                trail.append((row.content_type, row.content_id, row.title))
            else:
                self._call(self._entity_id, "play_media",
                           {"media_content_type": row.content_type,
                            "media_content_id": row.content_id})
                return

    def _item(self, row):
        """A line for the select dialog, with whatever picture there is.

        Home Assistant's thumbnails are absolute for a station's own logo and
        relative for an integration's brand, which image_url tells apart. A
        line that brings none falls back to a shipped icon, and that needs its
        full path: the select dialog is a dialog of Kodi's, not this skin.
        """
        item = xbmcgui.ListItem(row.title)
        picture = self._art_url(row.thumbnail) if row.thumbnail else os.path.join(
            kodi.ICON_DIR, "folder.png" if row.expand else "play.png")
        item.setArt({"thumb": picture, "icon": picture})
        return item

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


def _inset(size):
    """Where an icon sits in a button of that size: in the middle of it."""
    return (size - ICON_SIZE) // 2
