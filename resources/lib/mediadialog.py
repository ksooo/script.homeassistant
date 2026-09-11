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
IMAGE_COVER = 110
LABEL_BLANK = 112
LABEL_HINT = 113
LABEL_TITLE = 104
LABEL_SUBTITLE = 105
LABEL_ELAPSED = 108
LABEL_DURATION = 109
SLIDER_SEEK = 111
# Five slots, filled left to right with whatever the player offers.
BUTTONS = (120, 121, 122, 123, 124)
BUTTON_ICONS = (130, 131, 132, 133, 134)
# Repeat and shuffle sit at the ends of the transport line, where Home
# Assistant's own row puts them: [repeat, previous] ... [next, shuffle].
BUTTON_REPEAT = 125
IMAGE_REPEAT = 135
BUTTON_SHUFFLE = 126
IMAGE_SHUFFLE = 136
# The device row under the transport, where Home Assistant keeps it too: the
# media tree, the input to switch to, power. Not the transport - these act on
# the box, not on what it is playing.
DEVICE_BUTTONS = (160, 162, 164, 166, 168, 170)
DEVICE_ICONS = (161, 163, 165, 167, 169, 171)
IMAGE_BADGE = 172
LABEL_BADGE = 173

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

# Kodi reports no release, so a slider counts as settled once it has stood
# still this long. Seeking on every keypress would set the player going a
# dozen times across one drag.
_SEEK_SETTLE = 0.5
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
          "stop": "stop", "next": "skip-next", "play_pause": "play-pause",
          "power_standby": "power-standby",
          "power_on": "power-on", "power_off": "power-off",
          "source": "login-variant", "browse": "play-box-multiple",
          "group": "speaker-multiple", "sound": "music-note-eighth"}

# The remote's own transport keys, which a web page cannot have. The play
# key takes whichever of the two the player is offering.
# What each control is called at the foot of the dialog. The power buttons are
# named by the service they carry, because one icon serves both directions.
_HINTS = {SLIDER_SEEK: "action_position", SLIDER_VOLUME: "action_volume",
          BUTTON_MUTE: "action_mute", BUTTON_DOWN: "action_volume_down",
          BUTTON_UP: "action_volume_up"}
_BUTTON_HINTS = {"previous": "action_previous", "play": "action_play",
                 "pause": "action_pause", "stop": "action_stop",
                 "next": "action_next", "play_pause": "action_play_pause",
                 "browse": "action_browse", "group": "action_group",
                 "source": "action_source", "sound": "action_sound_mode",
                 "shuffle": "action_shuffle", "repeat": "action_repeat"}
_SERVICE_HINTS = {"turn_on": "action_turn_on", "turn_off": "action_turn_off"}

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
        self._art_url = kwargs["art_url"]
        self._call = kwargs["call"]
        self._fetch = kwargs["browse"]
        self.closed = False
        self._drawn = None
        self._slots = {}
        self._pending_volume = None
        self._pending_seek = None
        self._volume_due = 0.0

    # -- Kodi callbacks --------------------------------------------------

    def onInit(self):
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
        focused = self._focused()
        if focused == SLIDER_VOLUME:
            self._pending_volume = self._level(SLIDER_VOLUME)
            return
        if focused == SLIDER_SEEK:
            self._pending_seek = (self._level(SLIDER_SEEK), time.time())
            return
        for name in _KEYS.get(code, ()):
            if self._command(name):
                return

    def onFocus(self, control_id):
        self._hint(control_id)

    def onClick(self, control_id):
        state = self._store.states.get(self._entity_id)
        if state is None:
            return
        name, service = self._slots.get(control_id, ("", None))
        if name == "browse":
            self._browse()
        elif name == "group":
            self._choose_group()
        elif name == "source":
            self._choose_source(state)
        elif name == "sound":
            self._choose_sound_mode(state)
        elif name in ("shuffle", "repeat"):
            self._set_playback(name, state)
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
        self._flush_seek()
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
        if state.state == "unavailable":
            self._blank()
            self._drawn = self._picture(state)
            return

        self._show(LABEL_BLANK, False)
        self._set(LABEL_TITLE, media.title(state)
                  or formatting.state_text(self._store, self._entity_id, kodi.tr))
        self._set(LABEL_SUBTITLE, media.subtitle(state))

        picture = state.attributes.get("entity_picture")
        if picture:
            # Not cached: the picture's URL carries a token that turns over
            # with every medium, and Kodi caches by URL.
            self._image(IMAGE_ART, self._art_url(picture), cache=False)
        self._show(IMAGE_ART, bool(picture))
        # Home Assistant fills an empty cover with its own box and a note,
        # rather than with the player's icon.
        self._show(IMAGE_COVER, not picture)
        self._show(IMAGE_ICON, not picture)

        self._slots = {}
        seek = self._progress(state)
        repeat, shuffle = self._extras(state)
        transport = repeat + self._buttons(state) + shuffle
        volume, device = self._volume(state), self._device(state)
        self._badge(state)
        rows = [seek, transport, volume, device]
        self._wire(rows)
        # The transport first, then volume, then the device row, then seeking.
        visible = [control for row in rows for control in row]
        wanted = transport or volume or device or seek
        if wanted and self._focused() not in visible:
            self._focus(wanted[0])
        self._hint(self._focused())

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

    def _hint(self, control_id):
        """Name the focused control at the foot of the dialog.

        Kodi names the setting under the cursor in its own dialogs, and this
        window is a wall of icons that say nothing on their own.
        """
        name, service = self._slots.get(control_id, ("", None))
        key = (_SERVICE_HINTS.get(service) or _BUTTON_HINTS.get(name)
               or _HINTS.get(control_id, ""))
        self._set(LABEL_HINT, kodi.tr(key) if key else "")

    def _progress(self, state):
        """The position slider and the two times beside it.

        Shown wherever the medium has a length - a live stream has none and
        gets nothing - and movable only where the player can seek. One that
        cannot still shows how far along it is, as Home Assistant's disabled
        slider does.
        """
        total = media.duration(state)
        for control_id in (SLIDER_SEEK, LABEL_ELAPSED, LABEL_DURATION):
            self._show(control_id, bool(total))
        if not total:
            return []
        self._set(LABEL_ELAPSED, media.clock(media.elapsed(state)))
        self._set(LABEL_DURATION, media.clock(total))
        seekable = media.can_seek(state)
        self._enable(SLIDER_SEEK, seekable)
        # Not while it has the focus: setting it under a moving thumb would
        # fight whoever is moving it.
        if self._focused() != SLIDER_SEEK:
            self._percent(SLIDER_SEEK, (media.fraction(state) or 0.0) * 100)
        return [SLIDER_SEEK] if seekable else []

    def _flush_seek(self):
        """Send where the position slider was left, once it has settled."""
        if self._pending_seek is None:
            return
        share, when = self._pending_seek
        if time.time() - when < _SEEK_SETTLE:
            return
        self._pending_seek = None
        state = self._store.states.get(self._entity_id)
        target = media.seek_target(state, share) if state is not None else None
        if target is not None:
            self._call(self._entity_id, "media_seek", {"seek_position": target})

    def _blank(self):
        """What Home Assistant shows for a player it cannot reach.

        Its dialog stops at the cover box with the state written in it, so
        everything else goes - including the two buttons that ask only for a
        feature bit and would otherwise sit there on a player that is gone.
        """
        for control_id in (IMAGE_ART, IMAGE_ICON, LABEL_TITLE, LABEL_SUBTITLE,
                           SLIDER_SEEK, LABEL_ELAPSED, LABEL_DURATION,
                           IMAGE_BADGE, LABEL_BADGE, SLIDER_VOLUME, BUTTON_MUTE,
                           IMAGE_MUTE, BUTTON_DOWN, IMAGE_DOWN, BUTTON_UP,
                           IMAGE_UP, BUTTON_REPEAT, IMAGE_REPEAT, BUTTON_SHUFFLE,
                           IMAGE_SHUFFLE, LABEL_HINT):
            self._show(control_id, False)
        for control_id in BUTTONS + BUTTON_ICONS + DEVICE_BUTTONS + DEVICE_ICONS:
            self._show(control_id, False)
        self._slots = {}
        self._show(IMAGE_COVER, True)
        self._show(LABEL_BLANK, True)
        self._set(LABEL_BLANK,
                  formatting.state_text(self._store, self._entity_id, kodi.tr))

    def _badge(self, state):
        """The number on the group button once players have joined it.

        The button lands in whichever slot the row had left over, so the badge
        is moved onto it rather than given a place of its own.
        """
        button = next((control for control, (name, _) in self._slots.items()
                       if name == "group"), None)
        count = len(media.group_members(state))
        shown = button is not None and count > 1
        self._show(IMAGE_BADGE, shown)
        self._show(LABEL_BADGE, shown)
        if not shown:
            return
        try:
            left = self.getControl(button).getX()
        except RuntimeError:
            return
        self._place(IMAGE_BADGE, left + 36)
        self._place(LABEL_BADGE, left + 36)
        self._set(LABEL_BADGE, str(count))

    def _extras(self, state):
        """The two playback settings, at the ends of the transport line."""
        return (self._extra(BUTTON_REPEAT, IMAGE_REPEAT, "repeat",
                            media.repeat(state)),
                self._extra(BUTTON_SHUFFLE, IMAGE_SHUFFLE, "shuffle",
                            media.shuffle(state)))

    def _extra(self, button, image, name, setting):
        """Draw one setting where the skin put it, or hide it.

        Its icon comes from the setting rather than from the icon table: it
        says how the player stands, so it changes with the player.
        """
        self._show(button, setting is not None)
        self._show(image, setting is not None)
        if setting is None:
            return []
        self._image(image, "icons/%s.png" % setting[0])
        self._slots[button] = (name, None)
        return [button]

    def _set_playback(self, name, state):
        """Move a playback setting on: shuffle over, repeat round."""
        setting = media.shuffle(state) if name == "shuffle" else media.repeat(state)
        if setting is not None:
            self._call(self._entity_id, "%s_set" % name, {name: setting[1]})

    def _device(self, state):
        """The box itself: its media tree, its group, its input, its sound
        field, its power - Home Assistant's order for that row.

        The group button is the one departure: it is left out where there is
        nothing to group with, rather than opening on an empty list.
        """
        drawn = [("browse", None)] if media.can_browse(state) else []
        if media.can_group(state):
            drawn.append(("group", None))
        if media.can_select_source(state):
            drawn.append(("source", None))
        if media.sound_modes(state):
            drawn.append(("sound", None))
        drawn += media.power(state)
        return self._row(DEVICE_BUTTONS, DEVICE_ICONS,
                         drawn[:len(DEVICE_BUTTONS)])

    def _picture(self, state):
        """Everything that decides what is on screen, to redraw only on change."""
        _, level, _ = media.volume(state)
        return (state.state, state.attributes.get("media_title"),
                media.clock(media.elapsed(state)), media.duration(state),
                round(level * 100) if level is not None else None,
                state.attributes.get("is_volume_muted"),
                state.attributes.get("shuffle"), state.attributes.get("repeat"),
                len(state.attributes.get("group_members") or []))

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

    def _level(self, control_id):
        try:
            percent = self.getControl(control_id).getPercent()
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

    def _choose_sound_mode(self, state):
        """Which sound field to put the player into, the current one marked."""
        names = media.sound_modes(state)
        if not names:
            return
        labels = formatting.option_texts(self._store, self._entity_id,
                                         "sound_mode", names)
        current = str(state.attributes.get("sound_mode") or "")
        choice = xbmcgui.Dialog().select(
            kodi.tr("action_sound_mode"), labels,
            preselect=names.index(current) if current in names else -1)
        if choice >= 0:
            self._call(self._entity_id, "select_sound_mode",
                       {"sound_mode": names[choice]})

    def _choose_group(self):
        """Who plays along with this player, ticked as it stands.

        What comes back is a membership, and Home Assistant takes changes
        rather than memberships, so group_plan works out the calls: the joiners
        arrive together, each leaver leaves on its own.
        """
        choices = media.group_choices(self._store, self._entity_id)
        if not choices:
            return
        picked = xbmcgui.Dialog().multiselect(
            kodi.tr("action_group"), [name for _, name, _ in choices],
            preselect=[index for index, choice in enumerate(choices) if choice[2]])
        if picked is None:
            return
        # The player's own row is fixed - it is always in its own group - so it
        # takes no part in the joining and the leaving.
        current = [entity for entity, _, joined in choices
                   if joined and entity != self._entity_id]
        wanted = [choices[index][0] for index in picked
                  if choices[index][0] != self._entity_id]
        added, removed = media.group_plan(current, wanted)
        if added:
            self._call(self._entity_id, "join", {"group_members": added})
        for entity_id in removed:
            self._call(entity_id, "unjoin")

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

    def _enable(self, control_id, enabled):
        try:
            self.getControl(control_id).setEnabled(enabled)
        except RuntimeError:
            pass


def _inset(size):
    """Where an icon sits in a button of that size: in the middle of it."""
    return (size - ICON_SIZE) // 2
