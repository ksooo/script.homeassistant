"""The dashboard window.

Only the window's own thread touches a control. The Home Assistant session
runs in the background and leaves notes instead; :meth:`Dashboard.pump` picks
them up. Rebuilding a container from the session thread pulled the selection
out from under whoever was navigating.

The row list is one column wide. That is what lets a device heading own its
row: a Kodi container gives every item the same cell, so a second column
would need blank filler items - and a focused blank item shows nothing at all.
"""

import os
import threading
import time

import xbmc
import xbmcgui

from . import actions as ha_actions
from . import (cameras, direct, formatting, icons, kodi, mediadialog, model,
               ptzdialog, sections, sliderdialog)
from .ha import auth as ha_auth
from .ha import client as ha_client

MEDIA_XML = "script.homeassistant-media.xml"
SLIDER_XML = "script.homeassistant-slider.xml"
PTZ_XML = "script.homeassistant-ptz.xml"
SHORTCUT_XML = "script.homeassistant-shortcut.xml"

# How long the rows are given to fade out before the next section is put in
# their place. The skin's fade is the same length.
_SWITCH_FADE = 0.12

# How long the wait for a live picture is shown before the dialog gives up
# and leaves the player to it.
_LIVE_PATIENCE = 30.0

_WEBRTC_INPUTSTREAM = "inputstream.webrtc"

# How long a favourite waits for Home Assistant before it gives up, rather
# than leave Kodi's busy spinner up.
_SHORTCUT_PATIENCE = 30.0

# How fast a camera is panned and tilted from the remote, out of Reolink's 64.
# Home Assistant's own suggestion for the service; a button alone moves at
# the camera's own speed, which is far too much for a single press.
_PTZ_SPEED = 10

# Home Assistant renews the token for brand images every thirty minutes and
# honours the one before as well; fetched this often, the one in hand always
# works, as its own frontend keeps it.
_BRANDS_RENEWAL = 25 * 60

ROW_LIST = 50
CATEGORY_LIST = 51
ROW_BAR = 60
CATEGORY_BAR = 61
LABEL_TITLE = 100
LABEL_STATUS = 101
LABEL_STATUS_MESSAGE = 104
LABEL_EMPTY = 105

ACTION_MOVE_UP = 3
ACTION_PAGE_UP = 5
ACTION_SHOW_INFO = 11
ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92
ACTION_CONTEXT_MENU = 117


class _LivePlayer(xbmc.Player):
    """Where the live picture comes from, and how far it has got."""

    def __init__(self, name, ways):
        super().__init__()
        self.name = name
        # The ways still to try, the one being tried taken off the front.
        self.ways = list(ways)
        self.source = None
        self.failure = ""
        # What the viewer has to do before this camera can play.
        self.notice = ""
        self.started = False
        self.via_hls = False
        self.playing = False
        self.ended = False

    @property
    def settled(self):
        return self.playing or self.ended

    def start(self):
        url, item = self.source
        self.started = True
        self.play(url, item)

    def fall_back(self):
        """Forget the stream that would not play, to try the next way."""
        self.source = None
        self.started = self.playing = self.ended = False

    def onAVStarted(self):
        self.playing = True

    def onPlayBackError(self):
        self.ended = True

    def onPlayBackStopped(self):
        self.ended = True

    def onPlayBackEnded(self):
        self.ended = True


def _waiting_dialog(name):
    dialog = xbmcgui.DialogProgress()
    dialog.create(name, kodi.tr("live_fetching"))
    # Nothing says how far along the stream is, so no bar to fill.
    dialog.update(-1)
    return dialog


class _Dashboard:
    """The dashboard's workings, for a window and a dialog alike: Python
    makes the Kodi object from the first Kodi base a class has, so the two
    cannot be had by deriving one from the other."""

    def __init__(self, xml_file, resource_path, theme_skin, theme_res, *args, **kwargs):
        super().__init__()
        self._settings = kwargs["settings"]
        self._store = model.Store(log=kodi.log, language=kodi.LANGUAGE)
        self._store.cameras_with_own_url = set(direct.load(kodi.profile_directory()))
        self._auth = ha_auth.Authenticator(
            self._settings.url,
            token=self._settings.token,
            username=self._settings.username,
            password=self._settings.password,
            prompt=kodi.prompt_login_field,
            verify_ssl=self._settings.verify_ssl)
        self._session = ha_client.Session(
            self._settings.url, self._auth,
            on_ready=self._on_ready, on_lost=self._on_lost,
            verify_ssl=self._settings.verify_ssl, log=kodi.log)
        self._options = sections.Options(
            favourites=self._settings.favourites,
            summaries=self._settings.summaries,
            areas=self._settings.areas,
            hide_empty_areas=self._settings.hide_empty_areas)

        self._sections = []
        self._category_labels = []
        self._section_index = 0
        self._section_key = ""
        self._row_positions = {}
        self._rows_key = ""
        self._pending_section = None
        self._switch_due = 0.0
        self._wanted_focus = 0
        self._brands_token = ""
        self._brands_due = 0.0
        self._icons = _shipped_icons()
        self._snapshots = cameras.Snapshots(
            self._settings.url, kodi.temp_directory(),
            verify_ssl=self._settings.verify_ssl, log=kodi.log)
        self._camera_worker = None
        self._camera_due = 0.0
        self._overlay = None
        self._live = None
        self._ptz = None
        self._window_id = 0
        self._landed = False
        self._started = False

        # Notes left by the session thread, taken by pump().
        self._notes = threading.Lock()
        self._rebuild_wanted = False
        self._changed_entities = set()
        self._status_text = None
        self._message_text = None
        self._camera_stills = {}

        self.closed = False

    # -- window callbacks ------------------------------------------------

    def onInit(self):
        # A script window learns its own id only at runtime, and by the time
        # this arrives the window manager has put it on the history.
        self._window_id = xbmcgui.getCurrentWindowId()
        if self._started:
            return
        self._started = True
        # Set here rather than in the XML: $LOCALIZE in an addon window looks
        # up Kodi's own strings, not the addon's, and comes back empty.
        self._set_label(LABEL_TITLE, kodi.tr("dashboard_title"))
        self._set_label(LABEL_STATUS, kodi.tr("connecting"))
        self._set_label(LABEL_STATUS_MESSAGE, kodi.tr("loading"))
        self._session.start()

    def onClick(self, control_id):
        if control_id == CATEGORY_LIST:
            self._show_section(self._position_of(CATEGORY_LIST))
            # A list on its way back cannot take the focus; pump() hands it
            # over once the rows are there.
            if self._pending_section is None:
                self._set_focus(ROW_LIST)
            else:
                self._wanted_focus = ROW_LIST
        elif control_id == ROW_LIST:
            entity_id = self._focused_entity()
            if not entity_id:
                return
            action = ha_actions.default_action(self._store, entity_id)
            if action is not None:
                self._execute(entity_id, action)

    def onFocus(self, control_id):
        if control_id in (CATEGORY_LIST, ROW_LIST):
            self._scroll_into_view(control_id)

    def onAction(self, action):
        action_id = action.getId()
        if action_id in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
            self.close()
        elif action_id == ACTION_CONTEXT_MENU:
            self._show_menu()
        elif action_id == ACTION_SHOW_INFO:
            # Only where a row is being stood on: the info action is about
            # the thing in focus, and in the section list that is not an
            # entity.
            if self._focused_control() == ROW_LIST:
                entity_id = self._focused_entity()
                if entity_id:
                    self._show_details(entity_id)
        else:
            if self._focused_control() == ROW_LIST:
                self._step_over_headings(
                    -1 if action_id in (ACTION_MOVE_UP, ACTION_PAGE_UP) else 1)
            self._follow_section()

    def _step_over_headings(self, step):
        """Carry the selection past a device heading.

        A heading is a caption, not something to act on, but Kodi containers
        focus every item they hold. The search keeps the direction of travel
        and wraps around the end, the way the container itself would: the
        first row of an area section is a heading, so the user never stands on
        row zero and Kodi's own wrap never gets a chance to fire.
        """
        try:
            rows = self.getControl(ROW_LIST)
            position = rows.getSelectedPosition()
            count = rows.size()
        except RuntimeError:
            return
        if count <= 0 or _is_entity_row(rows, position):
            return

        for offset in range(1, count + 1):
            index = (position + step * offset) % count
            if _is_entity_row(rows, index):
                self._select(rows, index)
                return

    def close(self):
        # Kodi goes back a window for every close, closed or not.
        if not self.closed:
            self.closed = True
            super().close()

    def shutdown(self):
        self.closed = True
        if self._overlay is not None:
            self._overlay.close()
            self._overlay = None
        if self._live is not None:
            if self._live[0] is not None:
                self._live[0].close()
            self._live = None
        if self._ptz is not None:
            self._ptz[0].finish()
            self._ptz = None
        self._store.cancel_pending_reload()
        self._session.stop()
        self._snapshots.clean_up()
        # Both of these were handed a bound method of this window, which is
        # to say they hold the window - and they outlive it, so it would be
        # left behind at the end of the script. Nothing is going to call
        # back now that the session thread is gone.
        self._store.on_states_changed = None
        self._store.on_structure_changed = None
        self._session.forget()

    # -- the one place that changes controls -----------------------------

    def pump(self):
        """Apply what the session thread left behind. Window thread only."""
        with self._notes:
            rebuild = self._rebuild_wanted
            changed = self._changed_entities
            status, message = self._status_text, self._message_text
            stills = self._camera_stills
            self._rebuild_wanted = False
            self._changed_entities = set()
            self._status_text = self._message_text = None
            self._camera_stills = {}

        if status is not None:
            self._set_label(LABEL_STATUS, status)
        if message is not None:
            self._set_label(LABEL_STATUS_MESSAGE, message)
        if rebuild:
            self._rebuild()
        elif changed:
            self._refresh_rows(changed)
        if stills:
            self._show_stills(stills)
        if self._pending_section is not None and time.time() >= self._switch_due:
            section, self._pending_section = self._pending_section, None
            self._fill_rows(section)
            self.clearProperty("switching")
            if self._wanted_focus:
                self._set_focus(self._wanted_focus)
                self._wanted_focus = 0
        self._take_camera_stills()
        self._renew_brands_token()
        self._tick_overlay()
        self._tick_live()
        self._tick_ptz()

    def _tick_live(self):
        """Start the player once a source is found, and take the waiting
        dialog down once the picture is up, or will not be.

        The dialog only comes up for HLS, which takes many seconds to start -
        the other ways are too quick to need one. Cancelling it stops the
        player too, which may still be buffering. A way that was found but
        would not play gives way to the next.
        """
        if self._live is None:
            return
        dialog, player, due, entity_id = self._live
        if dialog is None and player.via_hls:
            dialog = self._live[0] = _waiting_dialog(player.name)
        client = self._session.client
        if dialog is not None and dialog.iscanceled():
            if player.started:
                player.stop()
        elif player.failure:
            kodi.notify(player.failure, error=True)
        elif player.notice:
            xbmcgui.Dialog().ok(player.name, player.notice)
        elif not player.started:
            if player.source is None and time.time() < due:
                return
            if player.source is not None:
                player.start()
                return
        elif player.ended and not player.playing and player.ways and client:
            player.fall_back()
            threading.Thread(target=self._find_live_source,
                             args=(client, entity_id, player),
                             name="ha-live", daemon=True).start()
            return
        elif not player.settled and time.time() < due:
            return
        if dialog is not None:
            dialog.close()
        self._live = None
        if player.playing and not player.ended:
            self._open_ptz(entity_id, player)

    def _open_ptz(self, entity_id, player):
        """Lay the steering over the live picture, where the camera can be steered.

        Where it cannot, nothing is laid over it and Kodi's player keeps
        every key of its own.
        """
        buttons = ha_actions.ptz_buttons(self._store, entity_id)
        if buttons is None:
            return

        def press(button):
            return self._send("button", "press", button, None)

        def move(button):
            return self._send("reolink", "ptz_move", button, {"speed": _PTZ_SPEED})

        dialog = ptzdialog.PtzDialog(
            PTZ_XML, kodi.ADDON_PATH, "Default", "1080i", buttons=buttons,
            press=press,
            move=move if ha_actions.ptz_takes_speed(self._store, buttons) else press,
            end=player.stop)
        dialog.show()
        self._ptz = (dialog, player)

    def _tick_ptz(self):
        if self._ptz is None:
            return
        dialog, player = self._ptz
        if dialog.closed:
            self._ptz = None
        elif player.ended:
            # Stopped some other way - the stop key, or the stream giving out.
            dialog.finish()
            self._ptz = None
        else:
            dialog.tick()

    def _tick_overlay(self):
        """Let a shown dialog redraw or send. Window thread, like everything here.

        The dialogs are shown rather than run modally, so nothing else would
        drive them: without this they draw once and then stand still.
        """
        if self._overlay is None:
            return
        if self._overlay.closed:
            self._overlay = None
        elif not self._in_front():
            # Playing on Kodi itself brings up the fullscreen video, which
            # displaces this window - but not a dialog of ours, which would
            # be left sitting over a picture it has nothing to do with.
            self._overlay.close()
            self._overlay = None
        else:
            self._overlay.tick()

    def _in_front(self):
        """Whether this window is still the one Kodi has up.

        Kodi does not count a dialog as the active window, so the media
        dialog being open does not make this false. Playback taking the
        screen does.
        """
        if not self._window_id:
            return True
        return xbmcgui.getCurrentWindowId() == self._window_id

    # -- session callbacks, background thread ----------------------------

    def _on_ready(self, client):
        try:
            self._store.load(client)
            self._store.subscribe(client)
        except Exception as error:
            self._note(status=kodi.tr("disconnected"), message=str(error))
            raise

        self._fetch_brands_token(client)
        self._store.on_states_changed = self._on_states_changed
        self._store.on_structure_changed = self._on_structure_changed
        self._note(rebuild=True, message="",
                   status="%s  -  %s" % (kodi.tr("connected"), client.version))

    def _on_lost(self, error):
        self._store.on_states_changed = None
        self._store.on_structure_changed = None
        self._note(status=kodi.tr("reconnecting"))

    def _on_states_changed(self, entity_ids):
        self._note(entities=entity_ids)

    def _on_structure_changed(self):
        self._note(rebuild=True)

    def _note(self, rebuild=False, entities=(), status=None, message=None,
              stills=None):
        with self._notes:
            self._rebuild_wanted = self._rebuild_wanted or rebuild
            self._changed_entities.update(entities)
            if status is not None:
                self._status_text = status
            if message is not None:
                self._message_text = message
            if stills:
                self._camera_stills.update(stills)

    # -- brand images ----------------------------------------------------

    def _renew_brands_token(self):
        client = self._session.client
        if client is None or time.time() < self._brands_due:
            return
        self._brands_due = time.time() + _BRANDS_RENEWAL
        threading.Thread(target=self._fetch_brands_token, args=(client,),
                         name="ha-brands", daemon=True).start()

    def _fetch_brands_token(self, client):
        """Off the window thread: the session's on connecting, its own after."""
        self._brands_due = time.time() + _BRANDS_RENEWAL
        try:
            self._brands_token = client.command("brands/access_token")["token"]
        except (ha_client.HomeAssistantError, KeyError, TypeError) as error:
            kodi.log("brands token unavailable: %s" % error, 2)

    # -- camera stills ---------------------------------------------------

    def _take_camera_stills(self):
        """Fetch a new still for the cameras on screen, off the window thread."""
        interval = self._settings.camera_refresh
        if not interval:
            return
        if self._camera_worker is not None and self._camera_worker.is_alive():
            return
        now = time.time()
        if now < self._camera_due:
            return
        self._camera_due = now + interval

        # Only what the user is looking at; eight cameras at once would be a
        # lot of traffic for pictures nobody sees.
        pictures = {}
        for entity_id in self._row_positions:
            if not entity_id.startswith("camera."):
                continue
            state = self._store.states.get(entity_id)
            picture = state.attributes.get("entity_picture") if state else None
            if picture:
                pictures[entity_id] = picture
        if not pictures:
            return

        self._camera_worker = threading.Thread(
            target=self._fetch_stills, args=(pictures,), name="ha-cameras")
        self._camera_worker.daemon = True
        self._camera_worker.start()

    def _fetch_stills(self, pictures):
        for entity_id, picture in pictures.items():
            if self.closed:
                return
            path = self._snapshots.fetch(entity_id, picture)
            if path:
                self._note(stills={entity_id: path})

    def _show_stills(self, stills):
        try:
            rows = self.getControl(ROW_LIST)
        except RuntimeError:
            return
        for entity_id, path in stills.items():
            position = self._row_positions.get(entity_id)
            if position is None:
                continue
            try:
                rows.getListItem(position).setArt({"thumb": path})
            except (RuntimeError, ValueError):
                continue

    # -- building --------------------------------------------------------

    def _rebuild(self):
        self._sections = sections.build(self._store, self._options, kodi.tr)
        try:
            categories = self.getControl(CATEGORY_LIST)
        except RuntimeError:
            return

        index = 0
        for position, section in enumerate(self._sections):
            if section.key == self._section_key:
                index = position
                break

        # Refilling a container drops it back to the top, so the list jumps
        # even though the selection is restored right after. Leave it alone
        # while the tiles themselves are unchanged.
        labels = [(section.key, section.title, section.subtitle)
                  for section in self._sections]
        if labels != self._category_labels:
            self._category_labels = labels
            categories.reset()
            items = [xbmcgui.ListItem(label=section.title,
                                      label2=section.subtitle, offscreen=True)
                     for section in self._sections]
            if items:
                categories.addItems(items)
                self._select(categories, index)

        self._show_section(index)
        if (self._sections and self._overlay is None
                and self._focused_control() not in (CATEGORY_LIST, ROW_LIST,
                                                    CATEGORY_BAR, ROW_BAR)):
            self._set_focus(self._landing())
            self._landed = True

    def _landing(self):
        """Where the focus goes when nothing holds it.

        The first time that is the favourites themselves rather than the list
        of sections: they are what the dashboard is opened for, and they are
        already the section it opens on, so standing beside them would only
        cost a press.
        """
        if (not self._landed and self._row_positions
                and self._sections[self._section_index].kind == sections.FAVOURITES):
            return ROW_LIST
        return CATEGORY_LIST

    def _follow_section(self):
        """Show the section the list is on, without waiting for OK.

        Kodi runs the container's own navigation before this callback, so the
        position read here is the one the user just moved to.
        """
        if self._focused_control() != CATEGORY_LIST:
            return
        position = self._position_of(CATEGORY_LIST)
        if position != self._section_index:
            self._show_section(position)

    def _show_section(self, index):
        if not self._sections:
            self._set_label(LABEL_TITLE, kodi.tr("dashboard_title"))
            self._set_label(LABEL_EMPTY, kodi.tr("empty_section"))
            return

        index = max(0, min(index, len(self._sections) - 1))
        section = self._sections[index]
        self._section_index = index
        self._section_key = section.key

        # The trail Estuary puts in the same corner. A room carries its floor
        # as the subtitle, which is a step of its own on the way there.
        crumbs = [kodi.tr("dashboard_title")]
        if section.subtitle:
            crumbs.append(section.subtitle)
        crumbs.append(section.title)
        self._set_label(LABEL_TITLE, " / ".join(crumbs))
        if not self._rows_key or section.key == self._rows_key:
            self._fill_rows(section)
        else:
            # Kodi has no trigger for a list being refilled, and forcing a
            # control hidden draws no animation either - only a skin visible
            # condition turning over does. So this one is turned over, and
            # the rows are put back once the fade behind it has had its time.
            self.setProperty("switching", "1")
            self._pending_section = section
            self._switch_due = time.time() + _SWITCH_FADE

    def _fill_rows(self, section):
        try:
            rows = self.getControl(ROW_LIST)
        except RuntimeError:
            return

        # Where the user was standing, but only within the same section. A
        # rebuild in the background - a registry change, a reload - should not
        # move them, and a dialog they had open should outlive its own row;
        # stepping to another section should start at the top, even where that
        # section holds the very entity they were standing on, as a room and a
        # summary both do.
        standing = self._focused_entity() if section.key == self._rows_key else ""
        self._rows_key = section.key
        rows.reset()
        self._row_positions = {}
        items = []
        for group in section.groups:
            if group.title:
                items.append(self._make_header(group.title))
            for entity_id in group.entity_ids:
                self._row_positions[entity_id] = len(items)
                items.append(self._make_row(entity_id, section))

        if items:
            rows.addItems(items)
            # A refilled container keeps its old scroll offset, which would
            # leave the first row off screen. Land on the first entity rather
            # than row zero, which in an area section is a device heading.
            first = min(self._row_positions.values()) if self._row_positions else 0
            self._select(rows, self._row_positions.get(standing, first))
        self._set_label(LABEL_EMPTY, "" if items else kodi.tr("empty_section"))

    def _make_header(self, title):
        item = xbmcgui.ListItem(label=title, offscreen=True)
        item.setProperty("kind", "header")
        return item

    def _make_row(self, entity_id, section):
        # Under a device heading the device is already named; everywhere else
        # the row carries the composed name, the way Home Assistant shows it.
        name = (self._store.name_of(entity_id) if section.kind == sections.AREA
                else self._store.display_name_of(entity_id))
        item = xbmcgui.ListItem(label=name, offscreen=True)
        item.setProperty("kind", "entity")
        item.setProperty("entity_id", entity_id)
        if entity_id.startswith("camera."):
            item.setProperty("camera", "yes")
        # Rows that do something are drawn as buttons, the read-only ones flat.
        item.setProperty("action",
                         "yes" if ha_actions.default_action(self._store, entity_id)
                         else "no")
        item.setProperty("secondary", self._detail_text(section, entity_id))

        state = self._store.states.get(entity_id)
        # A camera's own picture URL carries a rotating token, so Kodi would
        # cache a fresh copy of it every time. Its still comes from a file.
        picture = (state.attributes.get("entity_picture")
                   if state and not entity_id.startswith("camera.") else None)
        if picture:
            item.setArt({"thumb": kodi.image_url(self._settings.url, picture,
                                                 self._brands_token)})
        self._apply_state(item, entity_id)
        return item

    def _detail_text(self, section, entity_id):
        """The third line names what the rest of the row does not.

        A room section is headed by device and a summary by room, and in a
        summary the row itself already carries the device. Favourites have no
        headings at all, so they name the room.
        """
        if section.kind == sections.FAVOURITES:
            return formatting.room_text(self._store, entity_id)
        return ""

    def _apply_state(self, item, entity_id):
        item.setLabel2(formatting.state_text(self._store, entity_id, kodi.tr))
        tint = formatting.colour(self._store, entity_id)
        item.setProperty("colour", tint)
        # The same hue behind the icon, at a tenth of the opacity.
        item.setProperty("halo", "1A%s" % tint[2:])
        icon = icons.icon_for(self._store, entity_id)
        item.setProperty("icon", "icons/%s.png" % icon if icon in self._icons else "")

    def _refresh_rows(self, entity_ids):
        try:
            rows = self.getControl(ROW_LIST)
        except RuntimeError:
            return
        for entity_id in entity_ids:
            position = self._row_positions.get(entity_id)
            if position is None:
                continue
            try:
                item = rows.getListItem(position)
            except (RuntimeError, ValueError):
                continue
            self._apply_state(item, entity_id)

    # -- acting ----------------------------------------------------------

    def _focused_entity(self):
        try:
            rows = self.getControl(ROW_LIST)
            position = rows.getSelectedPosition()
            # An empty list answers -1, and asking it for that item throws.
            # Kodi logs the throw as an error of its own before it reaches
            # the except below, so the list has to be asked first.
            if position < 0:
                return ""
            item = rows.getListItem(position)
        except (RuntimeError, ValueError):
            return ""
        return item.getProperty("entity_id")

    def _show_menu(self):
        if self._focused_control() != ROW_LIST:
            return

        entity_id = self._focused_entity()
        if not entity_id:
            return
        menu = ha_actions.menu_actions(self._store, entity_id)
        url = kodi.favourite_url(entity_id)
        favourite = kodi.is_favourite(url)
        # Only what OK does something with: a favourite opens that.
        offered = favourite or ha_actions.default_action(self._store, entity_id) is not None
        choice = xbmcgui.Dialog().contextmenu(
            [kodi.tr(action.label_key) for action in menu]
            + ([kodi.tr("favourite_remove" if favourite else "favourite_add")]
               if offered else []))
        if offered and choice == len(menu):
            kodi.toggle_favourite(url, self._store.name_with_device(entity_id),
                                  self._favourite_icon(entity_id))
        elif choice >= 0:
            self._execute(entity_id, menu[choice])

    def _favourite_icon(self, entity_id):
        """The entity's icon in favourite size, else the addon's."""
        path = os.path.join(kodi.LARGE_ICON_DIR,
                            icons.icon_for(self._store, entity_id) + ".png")
        return path if os.path.isfile(path) else kodi.ADDON_ICON

    def _execute(self, entity_id, action):
        if action.kind == ha_actions.DETAILS:
            self._show_details(entity_id)
            return

        if action.kind == ha_actions.COMMANDS:
            self._ask_command(entity_id)
            return

        if action.kind == ha_actions.MEDIA:
            self._open_media(entity_id)
            return

        if action.kind == ha_actions.LIVE:
            self._play_live(entity_id)
            return

        if action.kind == ha_actions.SLIDER:
            self._open_slider(entity_id, action)
            return

        if self._session.client is None:
            kodi.notify(kodi.tr("disconnected"), error=True)
            return

        if not self._may_act(entity_id, action.service):
            return

        data = self._collect_input(entity_id, action)
        if data is None:
            return
        self._send(action.domain, action.service, entity_id, data)

    def _ask_command(self, entity_id):
        """Offer what the entity says it can do, then carry it out."""
        state = self._store.states.get(entity_id)
        if state is None:
            return
        commands = ha_actions.commands_for(self._store, state)
        if not commands:
            return
        choice = xbmcgui.Dialog().select(
            kodi.tr("action_commands"),
            [kodi.tr(command.label_key) for command in commands])
        if choice >= 0:
            self._execute(entity_id, commands[choice])

    def _collect_input(self, entity_id, action):
        """Returns the service data, or None when the user cancels."""
        state = self._store.states.get(entity_id)
        attributes = state.attributes if state else {}
        dialog = xbmcgui.Dialog()

        if action.kind == ha_actions.SERVICE:
            return ha_actions.service_data(action, state)

        if action.kind == ha_actions.NUMBER:
            field = _NUMBER_FIELDS.get(action.service)
            if field:
                key, current = field[0], attributes.get(field[1], 0)
            else:
                key, current = "value", state.state if state else "0"
            value = dialog.numeric(0, kodi.tr(action.label_key), str(_as_int(current)))
            return None if value in (None, "") else {key: float(value)}

        if action.kind == ha_actions.TEMPERATURE:
            current = attributes.get("temperature", attributes.get("current_temperature", 20))
            value = dialog.numeric(0, kodi.tr("action_set_temperature"),
                                   str(_as_int(current)))
            return None if value in (None, "") else {"temperature": float(value)}

        if action.kind == ha_actions.PICK:
            labels, values = _choices(self._store, entity_id, action,
                                      attributes)
            if not values:
                return None
            choice = dialog.select(kodi.tr(action.label_key), labels)
            return None if choice < 0 else {action.data["as"]: values[choice]}

        if action.kind == ha_actions.AREAS:
            rooms = self._clean_areas(entity_id)
            if not rooms:
                return None
            chosen = xbmcgui.Dialog().multiselect(
                kodi.tr(action.label_key), [name for name, _ in rooms])
            if not chosen:
                return None
            return {action.data["as"]: [rooms[index][1] for index in chosen]}

        if action.kind == ha_actions.ALARM:
            return self._alarm_code(action, attributes, dialog)

        return {}


    def _alarm_code(self, action, attributes, dialog):
        """The panel's code, where the panel asks for one.

        Disarming needs it whenever a format is given; arming only when the
        panel says so. Home Assistant's own dialog draws the same distinction.
        """
        code_format = attributes.get("code_format")
        arming = action.service != "alarm_disarm"
        if not code_format or (arming
                               and not attributes.get("code_arm_required", True)):
            return {}
        heading = kodi.tr("action_code")
        if code_format == "number":
            code = dialog.numeric(0, heading, "", True)
        else:
            code = dialog.input(heading, type=xbmcgui.INPUT_ALPHANUM,
                                option=xbmcgui.ALPHANUM_HIDE_INPUT)
        return {"code": code} if code else None

    def _clean_areas(self, entity_id):
        """The rooms this vacuum has mapped, in registry order.

        Kodi hands back what was ticked in list order, not in the order it was
        ticked, so the rooms are cleaned in the order they are listed here.
        """
        mapped = ha_actions.cleanable_areas(self._store.entities.get(entity_id))
        return [(heading, area_id)
                for heading, area_id in sections.room_headings(self._store)
                if area_id in mapped]

    def _open_media(self, entity_id):
        self._overlay = mediadialog.MediaDialog(
            MEDIA_XML, kodi.ADDON_PATH, "Default", "1080i",
            store=self._store, entity_id=entity_id,
            art_url=lambda picture: kodi.image_url(
                self._settings.url, picture, self._brands_token),
            call=self._call_service,
            browse=self._browse_media)
        self._overlay.show()

    def _may_act(self, entity_id, service):
        """Ask first where the settings say to, and take no for an answer."""
        asking = ha_actions.confirmation(self._store, entity_id, service,
                                         self._settings)
        if asking is None:
            return True
        title, text = asking
        return xbmcgui.Dialog().yesno(
            kodi.tr(title),
            kodi.tr(text) % self._store.display_name_of(entity_id))

    def _play_live(self, entity_id):
        """Hand the camera's live picture to Kodi's own player.

        The ways are tried in turn: the camera's own stream URL where it
        answers, a second or two behind over RTSP; Home Assistant's WebRTC
        through Kodi's WebRTC inputstream; Home Assistant's HLS, many seconds
        behind, from an address that carries a token of its own.
        """
        client = self._session.client
        if client is None:
            kodi.notify(kodi.tr("disconnected"), error=True)
            return
        player = _LivePlayer(self._store.display_name_of(entity_id),
                             ha_actions.live_ways(self._store, entity_id))
        threading.Thread(target=self._find_live_source,
                         args=(client, entity_id, player),
                         name="ha-live", daemon=True).start()
        self._live = [None, player, time.time() + _LIVE_PATIENCE, entity_id]

    def _find_live_source(self, client, entity_id, player):
        """Off the window thread: the first of the ways left that is there."""
        while player.ways:
            way = player.ways.pop(0)
            if way == ha_actions.LIVE_OWN_URL:
                source = self._own_url_source(entity_id, player)
            elif way == ha_actions.LIVE_WEBRTC:
                source = self._webrtc_source(entity_id, player)
            else:
                source = self._hls_source(client, entity_id, player)
            if source is not None:
                player.source = source
                return
            if player.failure or player.notice:
                return
        player.failure = kodi.tr("live_unavailable")

    def _own_url_source(self, entity_id, player):
        url = direct.load(kodi.profile_directory()).get(entity_id)
        if not url or not direct.reachable(url):
            return None
        item = xbmcgui.ListItem(player.name)
        item.setContentLookup(False)
        # Over TCP: a home network may drop the UDP RTSP would use first.
        item.setProperty("rtsp_transport", "tcp")
        return url, item

    def _webrtc_source(self, entity_id, player):
        """Home Assistant's WebRTC, which the inputstream negotiates itself.

        Without the inputstream nothing is played, and the notice says what is
        missing: WebRTC is the best way there is, and a camera that offers it
        is not left to a worse one. The inputstream signs in to Home Assistant
        once, as the session is set up, so the short-lived token of a sign-in
        with user name and password will do.
        """
        if not xbmc.getCondVisibility("System.HasAddon(%s)" % _WEBRTC_INPUTSTREAM):
            player.notice = kodi.tr("webrtc_install")
            return None
        if not xbmc.getCondVisibility("System.AddonIsEnabled(%s)" % _WEBRTC_INPUTSTREAM):
            player.notice = kodi.tr("webrtc_enable")
            return None
        try:
            token = self._auth.access_token()
        except Exception as error:
            kodi.log("no token for WebRTC: %s" % error, xbmc.LOGWARNING)
            return None
        item = xbmcgui.ListItem(player.name)
        item.setContentLookup(False)
        item.setProperty("inputstream", _WEBRTC_INPUTSTREAM)
        item.setProperty(_WEBRTC_INPUTSTREAM + ".signaling", "homeassistant")
        item.setProperty(_WEBRTC_INPUTSTREAM + ".entity_id", entity_id)
        item.setProperty(_WEBRTC_INPUTSTREAM + ".bearer_token", token)
        return self._settings.url, item

    def _hls_source(self, client, entity_id, player):
        """Home Assistant's HLS stream, once it runs."""
        player.via_hls = True
        try:
            path = client.command("camera/stream", entity_id=entity_id)["url"]
        except ha_client.HomeAssistantError as error:
            player.failure = kodi.tr("error_service") % error
            return None
        url = self._settings.url.rstrip("/") + path
        # Played even where the stream did not answer the addon: Kodi has its
        # own way of saying why it cannot play.
        cameras.stream_ready(url, self._settings.verify_ssl)
        item = xbmcgui.ListItem(player.name)
        item.setMimeType("application/vnd.apple.mpegurl")
        item.setContentLookup(False)
        return url, item

    def _open_slider(self, entity_id, action):
        self._overlay = sliderdialog.SliderDialog(
            SLIDER_XML, kodi.ADDON_PATH, "Default", "1080i",
            name=self._store.display_name_of(entity_id), action=action,
            start=ha_actions.slider_start(self._store.states.get(entity_id), action),
            send=lambda data: self._send(action.domain, action.service,
                                         entity_id, data))
        self._overlay.show()

    def _call_service(self, entity_id, service, data=None):
        if self._may_act(entity_id, service):
            self._send("media_player", service, entity_id, data)

    def _send(self, domain, service, entity_id, data):
        """Carry a service out; True once Home Assistant reports it done."""
        client = self._session.client
        if client is None:
            kodi.notify(kodi.tr("disconnected"), error=True)
            return False
        try:
            client.call_service(domain, service, data=data,
                                target={"entity_id": entity_id})
        except ha_client.HomeAssistantError as error:
            kodi.notify(kodi.tr("error_service") % error, error=True)
            return False
        return True

    def _browse_media(self, entity_id, content_type=None, content_id=None):
        """One level of a player's media tree, or None if it cannot be had.

        The root is asked for by leaving both out, as Home Assistant's own
        frontend does.
        """
        client = self._session.client
        if client is None:
            kodi.notify(kodi.tr("disconnected"), error=True)
            return None
        payload = {"entity_id": entity_id}
        if content_id is not None:
            payload["media_content_type"] = content_type
            payload["media_content_id"] = content_id
        try:
            return client.command("media_player/browse_media", **payload)
        except ha_client.HomeAssistantError as error:
            kodi.notify(kodi.tr("error_service") % error, error=True)
            return None

    def _show_details(self, entity_id):
        state = self._store.states.get(entity_id)
        if state is None:
            return
        lines = ["%s: %s" % (entity_id, state.state), ""]
        for key in sorted(state.attributes):
            lines.append("%s: %s" % (key, state.attributes[key]))
        xbmcgui.Dialog().textviewer("%s - %s" % (kodi.tr("details_title"),
                                                 self._store.name_of(entity_id)),
                                    "\n".join(lines))

    # -- control helpers -------------------------------------------------

    def _focused_control(self):
        try:
            return self.getFocusId()
        except RuntimeError:
            return 0

    def _position_of(self, control_id):
        try:
            return self.getControl(control_id).getSelectedPosition()
        except RuntimeError:
            return 0

    def _scroll_into_view(self, control_id):
        """Make a container show its selected item.

        Kodi keeps the scroll offset when focus arrives, so the selected item
        can sit outside the visible page. Selecting it again scrolls it in;
        an item already on screen stays put.
        """
        try:
            control = self.getControl(control_id)
        except RuntimeError:
            return
        self._select(control, control.getSelectedPosition())

    @staticmethod
    def _select(control, position):
        try:
            control.selectItem(position)
        except (RuntimeError, ValueError, TypeError):
            pass

    def _set_focus(self, control_id):
        try:
            self.setFocusId(control_id)
        except RuntimeError:
            pass

    def _set_label(self, control_id, text):
        try:
            self.getControl(control_id).setLabel(text)
        except RuntimeError:
            pass



class Dashboard(_Dashboard, xbmcgui.WindowXML):
    pass


class Shortcut(_Dashboard, xbmcgui.WindowXMLDialog):
    """What a Kodi favourite of an entity opens: that entity's OK action, as
    if pressed on the dashboard, with no dashboard to be seen.

    A dialog lies over the window the favourite was chosen in rather than
    taking its place, so that window is what stays in view and what Kodi
    comes back to. Its skin file has nothing in it.
    """

    def __init__(self, xml_file, resource_path, theme_skin, theme_res, *args, **kwargs):
        super().__init__(xml_file, resource_path, theme_skin, theme_res, *args, **kwargs)
        self._entity_id = kwargs["entity_id"]
        self._acted = False
        self._busy = False
        self._due = time.time() + _SHORTCUT_PATIENCE

    def onInit(self):
        if not self._started:
            self._busy = True
            xbmc.executebuiltin("ActivateWindow(busydialognocancel)")
        super().onInit()

    def pump(self):
        super().pump()
        if not self._acted:
            if self._store.states:
                self._act()
            elif time.time() >= self._due:
                kodi.notify(kodi.tr("disconnected"), error=True)
                self.close()
        elif self._overlay is None and self._live is None and self._ptz is None:
            self.close()

    def close(self):
        self._end_busy()
        super().close()

    def _act(self):
        self._acted = True
        self._end_busy()
        if self._entity_id not in self._store.states:
            return
        action = ha_actions.default_action(self._store, self._entity_id)
        if action is not None:
            self._execute(self._entity_id, action)

    def _end_busy(self):
        if self._busy:
            self._busy = False
            xbmc.executebuiltin("Dialog.Close(busydialognocancel)")

    def _rebuild(self):
        pass

    def _refresh_rows(self, entity_ids):
        pass

    def _set_label(self, control_id, text):
        pass

def _is_entity_row(rows, position):
    try:
        return rows.getListItem(position).getProperty("kind") == "entity"
    except (RuntimeError, ValueError):
        return False


def _shipped_icons():
    """Icon names available as PNG; anything else falls back to the circle."""
    try:
        return {name[:-4] for name in os.listdir(kodi.ICON_DIR)
                if name.endswith(".png")}
    except OSError:
        return set()


# The service field a number goes into, and the attribute holding what it is
# now. Anything not named here sets a value and reads the state.
_NUMBER_FIELDS = {
    "set_cover_position": ("position", "current_position"),
    "set_cover_tilt_position": ("tilt_position", "current_tilt_position"),
    "set_valve_position": ("position", "current_position"),
    "set_percentage": ("percentage", "percentage"),
    "set_humidity": ("humidity", "humidity"),
}


def _choices(store, entity_id, action, attributes):
    """What to offer, and the value behind each line.

    Fixed steps travel with the action and carry their own label; everything
    else the entity lists itself, and Home Assistant words those values - the
    action already says which attribute they belong to.
    """
    steps = action.data.get("choices")
    if steps is not None:
        say = kodi.tr if action.data.get("translate") else (lambda label: label)
        return [say(label) for label, _ in steps], [value for _, value in steps]
    named = attributes.get(action.data["from"]) or []
    return (formatting.option_texts(store, entity_id, action.data["as"], named),
            named)


def _as_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0
