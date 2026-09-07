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

import xbmcgui

from . import actions as ha_actions
from . import cameras, formatting, icons, kodi, model, sections
from .ha import auth as ha_auth
from .ha import client as ha_client

ROW_LIST = 50
CATEGORY_LIST = 51
LABEL_TITLE = 100
LABEL_STATUS = 101
LABEL_SECTION = 102
LABEL_STATUS_MESSAGE = 104
LABEL_EMPTY = 105
LABEL_FOOTER = 103

ACTION_MOVE_UP = 3
ACTION_PAGE_UP = 5
ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92
ACTION_CONTEXT_MENU = 117


class Dashboard(xbmcgui.WindowXML):
    def __init__(self, xml_file, resource_path, theme_skin, theme_res, *args, **kwargs):
        super().__init__()
        self._settings = kwargs["settings"]
        self._store = model.Store(log=kodi.log)
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
        self._section_index = 0
        self._section_key = ""
        self._row_positions = {}
        self._image_token = ""
        self._icons = _shipped_icons()
        self._snapshots = cameras.Snapshots(
            self._settings.url, kodi.temp_directory(),
            verify_ssl=self._settings.verify_ssl, log=kodi.log)
        self._camera_worker = None
        self._camera_due = 0.0
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
        if self._started:
            return
        self._started = True
        # Set here rather than in the XML: $LOCALIZE in an addon window looks
        # up Kodi's own strings, not the addon's, and comes back empty.
        self._set_label(LABEL_TITLE, kodi.tr("dashboard_title"))
        self._set_label(LABEL_FOOTER, kodi.tr("hint_footer"))
        self._set_label(LABEL_STATUS, kodi.tr("connecting"))
        self._set_label(LABEL_STATUS_MESSAGE, kodi.tr("loading"))
        self._session.start()

    def onClick(self, control_id):
        if control_id == CATEGORY_LIST:
            self._show_section(self._position_of(CATEGORY_LIST))
            self._set_focus(ROW_LIST)
        elif control_id == ROW_LIST:
            entity_id = self._focused_entity()
            if not entity_id:
                return
            action = ha_actions.default_action(self._store, entity_id)
            if action is None:
                kodi.notify(kodi.tr("read_only"))
            else:
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
        self.closed = True
        super().close()

    def shutdown(self):
        self.closed = True
        self._store.cancel_pending_reload()
        self._session.stop()
        self._snapshots.clean_up()

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
        self._take_camera_stills()

    # -- session callbacks, background thread ----------------------------

    def _on_ready(self, client):
        try:
            self._store.load(client)
            self._store.subscribe(client)
        except Exception as error:
            self._note(status=kodi.tr("disconnected"), message=str(error))
            raise

        self._image_token = self._auth.access_token()
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

    # -- camera stills ---------------------------------------------------

    def _take_camera_stills(self):
        """Fetch a new still for the cameras on screen, off the window thread."""
        interval = self._settings.camera_refresh
        if not interval or not self._image_token:
            return
        if self._camera_worker is not None and self._camera_worker.is_alive():
            return
        now = time.time()
        if now < self._camera_due:
            return
        self._camera_due = now + interval

        # Only what the user is looking at; eight cameras at once would be a
        # lot of traffic for pictures nobody sees.
        entity_ids = [entity_id for entity_id in self._row_positions
                      if entity_id.startswith("camera.")]
        if not entity_ids:
            return

        self._camera_worker = threading.Thread(
            target=self._fetch_stills, args=(entity_ids, self._image_token),
            name="ha-cameras")
        self._camera_worker.daemon = True
        self._camera_worker.start()

    def _fetch_stills(self, entity_ids, token):
        for entity_id in entity_ids:
            if self.closed:
                return
            path = self._snapshots.fetch(entity_id, token)
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

        categories.reset()
        items = []
        for section in self._sections:
            item = xbmcgui.ListItem(label=section.title, label2=section.subtitle,
                                    offscreen=True)
            item.setProperty("count", str(len(section)))
            items.append(item)
        if items:
            categories.addItems(items)

        index = 0
        for position, section in enumerate(self._sections):
            if section.key == self._section_key:
                index = position
                break

        self._show_section(index)
        self._select(categories, index)
        if items and self._focused_control() not in (CATEGORY_LIST, ROW_LIST):
            self._set_focus(CATEGORY_LIST)

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
            self._set_label(LABEL_SECTION, "")
            self._set_label(LABEL_EMPTY, kodi.tr("empty_section"))
            return

        index = max(0, min(index, len(self._sections) - 1))
        section = self._sections[index]
        self._section_index = index
        self._section_key = section.key

        title = section.title
        if section.subtitle:
            title = "%s  -  %s" % (section.subtitle, section.title)
        self._set_label(LABEL_SECTION, title)
        self._fill_rows(section)

    def _fill_rows(self, section):
        try:
            rows = self.getControl(ROW_LIST)
        except RuntimeError:
            return

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
            self._select(rows, first)
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
                                                 self._image_token)})
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
            item = rows.getListItem(rows.getSelectedPosition())
        except (RuntimeError, ValueError):
            return ""
        return item.getProperty("entity_id")

    def _show_menu(self):
        if self._focused_control() != ROW_LIST:
            # In the section list there is nothing to act on but a reload.
            if xbmcgui.Dialog().contextmenu([kodi.tr("action_refresh")]) == 0:
                self._refresh()
            return

        entity_id = self._focused_entity()
        if not entity_id:
            return
        menu = ha_actions.menu_actions(self._store, entity_id)
        labels = [kodi.tr(action.label_key) for action in menu]
        labels.append(kodi.tr("action_refresh"))

        choice = xbmcgui.Dialog().contextmenu(labels)
        if choice < 0:
            return
        if choice == len(menu):
            self._refresh()
            return
        self._execute(entity_id, menu[choice])

    def _execute(self, entity_id, action):
        if action.kind == ha_actions.DETAILS:
            self._show_details(entity_id)
            return

        if action.kind == ha_actions.COMMANDS:
            self._ask_command(entity_id)
            return

        client = self._session.client
        if client is None:
            kodi.notify(kodi.tr("disconnected"), error=True)
            return

        data = self._collect_input(entity_id, action)
        if data is None:
            return

        try:
            client.call_service(action.domain, action.service, data=data,
                                target={"entity_id": entity_id})
        except ha_client.HomeAssistantError as error:
            kodi.notify(kodi.tr("error_service") % error, error=True)

    def _ask_command(self, entity_id):
        """Offer what the entity says it can do, then carry it out."""
        state = self._store.states.get(entity_id)
        if state is None:
            return
        commands = ha_actions.commands_for(self._store, state)
        if not commands:
            kodi.notify(kodi.tr("read_only"))
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
            return dict(action.data)

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
            labels, values = _choices(action, attributes)
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

        if action.kind == ha_actions.VOLUME:
            # Home Assistant takes a fraction, people think in percent.
            current = round((attributes.get("volume_level") or 0) * 100)
            value = dialog.numeric(0, kodi.tr("action_volume"), str(current))
            if value in (None, ""):
                return None
            return {"volume_level": max(0.0, min(1.0, float(value) / 100.0))}

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

    def _refresh(self):
        client = self._session.client
        if client is None:
            kodi.notify(kodi.tr("disconnected"), error=True)
            return
        try:
            self._store.load(client)
        except ha_client.HomeAssistantError as error:
            kodi.notify(kodi.tr("error_service") % error, error=True)
            return
        self._rebuild()

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


def _is_entity_row(rows, position):
    try:
        return rows.getListItem(position).getProperty("kind") == "entity"
    except (RuntimeError, ValueError):
        return False


def _shipped_icons():
    """Icon names available as PNG; anything else falls back to the circle."""
    directory = os.path.join(kodi.ADDON_PATH, "resources", "skins", "Default",
                             "media", "icons")
    try:
        return {name[:-4] for name in os.listdir(directory) if name.endswith(".png")}
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


def _choices(action, attributes):
    """What to offer, and the value behind each line.

    Fixed steps travel with the action and carry their own label; everything
    else the entity names itself, where label and value are the same string.
    """
    steps = action.data.get("choices")
    if steps is not None:
        say = kodi.tr if action.data.get("translate") else (lambda label: label)
        return [say(label) for label, _ in steps], [value for _, value in steps]
    named = attributes.get(action.data["from"]) or []
    return named, named


def _as_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0
