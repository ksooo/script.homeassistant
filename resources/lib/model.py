"""Registry and state cache mirroring the parts of Home Assistant the
dashboard is built from.

Everything here is filled at runtime and kept current by subscriptions, so a
change made in Home Assistant shows up in Kodi without a restart.
"""

import threading

# Bus events Home Assistant fires when a registry changes. There is no
# dedicated subscribe command for the registries, so the affected one is
# fetched again when its event arrives.
_REGISTRY_EVENTS = {
    "entity_registry_updated": "entities",
    "device_registry_updated": "devices",
    "area_registry_updated": "areas",
    "floor_registry_updated": "floors",
}

# Entities Home Assistant keeps out of its dashboards.
_HIDDEN_CATEGORIES = ("config", "diagnostic")

_RELOAD_DELAY = 1.0


class Entity:
    __slots__ = ("entity_id", "domain", "name", "area_id", "device_id",
                 "device_class", "entity_category", "hidden", "disabled", "platform",
                 "translation_key", "options")

    def __init__(self, entry):
        self.entity_id = entry["entity_id"]
        self.domain = self.entity_id.split(".", 1)[0]
        self.name = entry.get("name") or entry.get("original_name") or ""
        self.area_id = entry.get("area_id")
        self.device_id = entry.get("device_id")
        self.device_class = entry.get("device_class") or entry.get("original_device_class")
        self.entity_category = entry.get("entity_category")
        self.hidden = bool(entry.get("hidden_by"))
        self.disabled = bool(entry.get("disabled_by"))
        self.platform = entry.get("platform", "")
        self.translation_key = entry.get("translation_key") or ""
        # Per-integration settings. Home Assistant keeps things here that are
        # neither state nor attribute, such as which rooms a vacuum has mapped.
        self.options = entry.get("options") or {}


class State:
    __slots__ = ("entity_id", "domain", "state", "attributes")

    def __init__(self, payload):
        self.entity_id = payload["entity_id"]
        self.domain = self.entity_id.split(".", 1)[0]
        self.state = payload.get("state", "unknown")
        self.attributes = payload.get("attributes") or {}

    @property
    def name(self):
        return self.attributes.get("friendly_name", "")

    @property
    def device_class(self):
        return self.attributes.get("device_class")

    @property
    def available(self):
        return self.state not in ("unavailable", "unknown")


class Store:
    def __init__(self, log=None):
        self._log = log or (lambda message, level=0: None)
        self._lock = threading.RLock()
        self._reload_timer = None

        self.entities = {}
        self.devices = {}
        self.areas = {}
        self.floors = {}
        self.states = {}
        self.home = {}
        self.energy = {}
        self.config = {}
        self.icon_translations = {}

        self.on_states_changed = None
        self.on_structure_changed = None

    # -- loading ---------------------------------------------------------

    def load(self, client):
        with self._lock:
            self.config = client.command("get_config") or {}
            self._load_registries(client)
            self.states = {
                payload["entity_id"]: State(payload)
                for payload in client.command("get_states")
            }
            try:
                self.energy = client.command("energy/get_prefs") or {}
            except Exception as error:
                self._log("energy preferences unavailable: %s" % error, 2)
                self.energy = {}

            # Integrations ship their own entity icons; without these a Reolink
            # floodlight would get the generic lamp instead of its spotlight.
            try:
                self.icon_translations = (client.command(
                    "frontend/get_icons", category="entity") or {}).get("resources", {})
            except Exception as error:
                self._log("icon translations unavailable: %s" % error, 2)
                self.icon_translations = {}

    def _load_registries(self, client):
        self.entities = {
            entry["entity_id"]: Entity(entry)
            for entry in client.command("config/entity_registry/list")
        }
        self.devices = {
            entry["id"]: entry
            for entry in client.command("config/device_registry/list")
        }
        self.areas = {
            entry["area_id"]: entry
            for entry in client.command("config/area_registry/list")
        }
        self.floors = {
            entry["floor_id"]: entry
            for entry in client.command("config/floor_registry/list")
        }

    def subscribe(self, client):
        """Attach all subscriptions that keep the cache current."""
        client.subscribe(self._on_state_changed,
                         type_="subscribe_events", event_type="state_changed")
        for event_type in _REGISTRY_EVENTS:
            client.subscribe(self._make_registry_handler(client),
                             type_="subscribe_events", event_type=event_type)
        client.subscribe(self._on_system_data,
                         type_="frontend/subscribe_system_data", key="home")

    # -- subscription handlers -------------------------------------------

    def _on_state_changed(self, event):
        data = event.get("data") or {}
        entity_id = data.get("entity_id")
        if not entity_id:
            return
        new_state = data.get("new_state")
        with self._lock:
            if new_state is None:
                self.states.pop(entity_id, None)
            else:
                self.states[entity_id] = State(new_state)
        if self.on_states_changed:
            self.on_states_changed([entity_id])

    def _on_system_data(self, event):
        with self._lock:
            self.home = (event or {}).get("value") or {}
        self._notify_structure()

    def _make_registry_handler(self, client):
        def handler(_event):
            self._schedule_reload(client)
        return handler

    def _schedule_reload(self, client):
        with self._lock:
            if self._reload_timer is not None:
                self._reload_timer.cancel()
            self._reload_timer = threading.Timer(_RELOAD_DELAY, self._reload, [client])
            self._reload_timer.daemon = True
            self._reload_timer.start()

    def _reload(self, client):
        try:
            with self._lock:
                self._load_registries(client)
        except Exception as error:
            self._log("registry reload failed: %s" % error, 3)
            return
        self._notify_structure()

    def _notify_structure(self):
        if self.on_structure_changed:
            self.on_structure_changed()

    def cancel_pending_reload(self):
        with self._lock:
            if self._reload_timer is not None:
                self._reload_timer.cancel()
                self._reload_timer = None

    # -- lookups ---------------------------------------------------------

    @property
    def unit_of_temperature(self):
        return (self.config.get("unit_system") or {}).get("temperature", "\u00b0C")

    def area_of(self, entity_id):
        entity = self.entities.get(entity_id)
        if entity is None:
            return None
        if entity.area_id:
            return entity.area_id
        device = self.devices.get(entity.device_id) if entity.device_id else None
        return device.get("area_id") if device else None

    def floor_of(self, area_id):
        area = self.areas.get(area_id)
        return area.get("floor_id") if area else None

    def name_of(self, entity_id):
        entity = self.entities.get(entity_id)
        if entity is not None and entity.name:
            return entity.name
        state = self.states.get(entity_id)
        if state is not None and state.name:
            return state.name
        return entity_id

    def icon_translation(self, entity_id, state):
        """The icon an integration declares for this entity, if any."""
        entity = self.entities.get(entity_id)
        if entity is None or not entity.translation_key:
            return ""
        entry = ((self.icon_translations.get(entity.platform) or {})
                 .get(entity.domain, {}).get(entity.translation_key))
        if not entry:
            return ""
        return (entry.get("state") or {}).get(state) or entry.get("default", "")

    def device_name(self, device_id):
        device = self.devices.get(device_id)
        if device is None:
            return ""
        return device.get("name_by_user") or device.get("name") or ""

    def display_name_of(self, entity_id):
        """The name as Home Assistant writes it where nothing else names the device.

        Home Assistant puts the device in front - "gasleser Realtime Gas Flow" -
        unless the entity carries a name of its own, and it has already made
        that decision in friendly_name. Under a device heading the short
        :meth:`name_of` is what belongs there instead.
        """
        state = self.states.get(entity_id)
        if state is not None and state.name:
            return state.name
        return self.name_of(entity_id)

    def device_class_of(self, entity_id):
        state = self.states.get(entity_id)
        if state is not None and state.device_class:
            return state.device_class
        entity = self.entities.get(entity_id)
        return entity.device_class if entity is not None else None

    def is_visible(self, entity_id, include_diagnostic=False):
        """Whether Home Assistant would place this entity on a dashboard.

        Diagnostic entities are the ones carrying battery and problem state,
        so the maintenance summary asks for them explicitly.
        """
        entity = self.entities.get(entity_id)
        if entity is None:
            # Entities without a registry entry (YAML templates, groups) are
            # shown as long as they have a state.
            return entity_id in self.states
        if entity.hidden or entity.disabled:
            return False
        if entity.entity_category in _HIDDEN_CATEGORIES:
            if not (include_diagnostic and entity.entity_category == "diagnostic"):
                return False
        return entity_id in self.states

    def entities_in_area(self, area_id):
        result = []
        for entity_id in self.states:
            if self.area_of(entity_id) == area_id and self.is_visible(entity_id):
                result.append(entity_id)
        return result

    def sorted_floors(self):
        """Floors in registry order, which is the order Home Assistant shows.

        Sorting by level looks tempting but puts a floor like "Draussen" in
        the middle, because it shares its level with an indoor floor.
        """
        return list(self.floors.values())

    def areas_on_floor(self, floor_id):
        """Rooms of a floor, in registry order - the order Home Assistant shows."""
        return [area for area in self.areas.values()
                if area.get("floor_id") == floor_id]

    def areas_without_floor(self):
        return [area for area in self.areas.values() if not area.get("floor_id")]
