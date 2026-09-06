"""Reconstruction of the Home Assistant "Home" dashboard.

Home is not a Lovelace dashboard: ``get_panels`` reports it as a panel of its
own, ``component_name: "home"``, with a panel each for its summaries. It has
no views, no cards and no configuration to fetch - not even the strategy
declaration a generated Lovelace dashboard would carry. What Home Assistant
does store is the input the panel works from: the favourites and shortcuts
under ``frontend/get_system_data`` key ``home``, plus the registries. Those
are read live; only the rules deciding which entity belongs to which summary
live here, because Home Assistant does not expose them.
"""

FAVOURITES = "favourites"
SUMMARY = "summary"
AREA = "area"

# Which entities each summary shortcut collects. Domains match on the entity
# domain, classes on the device class, both taken from the live state where
# available. Keep in sync with Home Assistant's frontend when its summaries
# change - this is the one part that does not follow along by itself.
_SUMMARY_DOMAINS = {
    "light": ("light",),
    "climate": ("climate", "water_heater", "humidifier", "fan"),
    "security": ("lock", "alarm_control_panel", "camera"),
    "media_players": ("media_player",),
    "weather": ("weather", "sun"),
}

_SUMMARY_CLASSES = {
    "security": {
        "cover": ("garage", "door", "gate"),
        "binary_sensor": ("door", "window", "garage_door", "opening",
                          "lock", "safety", "tamper"),
    },
}

# What Home Assistant's maintenance view holds: the battery of every device
# that runs on one, at any level, plus anything with an update waiting. Not a
# list of faults - problem sensors and unavailable entities stay out.
_MAINTENANCE_CLASSES = {
    "binary_sensor": ("battery",),
    "sensor": ("battery",),
}


class Group:
    """Entities under one heading. An empty title means no heading is drawn."""

    __slots__ = ("title", "entity_ids")

    def __init__(self, title, entity_ids):
        self.title = title
        self.entity_ids = entity_ids


class Section:
    __slots__ = ("key", "kind", "title", "subtitle", "entity_ids", "area_id",
                 "groups")

    def __init__(self, key, kind, title, entity_ids, subtitle="", area_id=None,
                 groups=None):
        self.key = key
        self.kind = kind
        self.title = title
        self.subtitle = subtitle
        self.entity_ids = entity_ids
        self.area_id = area_id
        self.groups = groups or [Group("", entity_ids)]

    def __len__(self):
        return len(self.entity_ids)


class Options:
    def __init__(self, favourites=True, summaries=True, areas=True,
                 hide_empty_areas=True):
        self.favourites = favourites
        self.summaries = summaries
        self.areas = areas
        self.hide_empty_areas = hide_empty_areas


def build(store, options=None, translate=None):
    """Return the dashboard sections in the order Home Assistant shows them."""
    options = options or Options()
    label = translate or (lambda key: key)
    sections = []

    if options.favourites:
        favourites = [entity_id for entity_id in store.home.get("favorite_entities") or []
                      if entity_id in store.states]
        if favourites:
            # Kept in the order Home Assistant holds them: that order is the
            # user's own, and grouping would throw it away.
            sections.append(Section(FAVOURITES, FAVOURITES,
                                    label("favourites"), favourites))

    if options.summaries:
        for shortcut in store.home.get("shortcuts") or []:
            # Summaries only. Home Assistant lets a shortcut be added by hand
            # as well; what such an entry looks like has not been examined, so
            # it is passed over rather than guessed at.
            if shortcut.get("type") != "summary" or shortcut.get("hidden"):
                continue
            key = shortcut.get("key", "")
            # Shown even when empty: the shortcut is configured in Home
            # Assistant, and "nothing needs attention" is worth seeing.
            sections.append(_by_room(store, key, SUMMARY, label(key),
                                     _summary_entities(store, key), label))

    if options.areas:
        sections.extend(_area_sections(store, options, label))

    return sections


def _by_room(store, key, kind, title, entity_ids, label):
    """A section that spans the house, grouped under its rooms.

    Rooms come in the order the floors and areas are listed, so the headings
    run in step with the section list rather than alphabetically.
    """
    by_area = {}
    without = []
    for entity_id in entity_ids:
        area_id = store.area_of(entity_id)
        if area_id:
            by_area.setdefault(area_id, []).append(entity_id)
        else:
            without.append(entity_id)

    groups = []
    for heading, area_id in room_headings(store):
        members = by_area.get(area_id)
        if members:
            groups.append(Group(heading, _sorted(store, members)))
    if without:
        groups.append(Group(label("no_room"), _sorted(store, without)))

    ordered = [entity_id for group in groups for entity_id in group.entity_ids]
    return Section(key, kind, title, ordered, groups=groups)


def room_headings(store):
    """(heading, area id) for every room, floors in registry order.

    The floor rides along in the heading rather than as a level of its own -
    a Kodi list is flat, and a second kind of heading row would only be one
    more thing the selection has to step over.
    """
    headings = []
    for floor in store.sorted_floors():
        for area in store.areas_on_floor(floor["floor_id"]):
            headings.append(("%s  -  %s" % (floor.get("name", ""),
                                            area.get("name", "")),
                             area["area_id"]))
    for area in store.areas_without_floor():
        headings.append((area.get("name", ""), area["area_id"]))
    return headings


def _summary_entities(store, key):
    if key == "maintenance":
        return _sorted(store, _maintenance_entities(store))
    if key == "energy":
        return _energy_entities(store)

    domains = _SUMMARY_DOMAINS.get(key, ())
    classes = _SUMMARY_CLASSES.get(key, {})
    matches = _room_climate_sensors(store) if key == "climate" else []
    if not domains and not classes and not matches:
        return []

    for entity_id, state in store.states.items():
        if not store.is_visible(entity_id):
            continue
        if state.domain in domains:
            matches.append(entity_id)
            continue
        allowed = classes.get(state.domain)
        if allowed and store.device_class_of(entity_id) in allowed:
            matches.append(entity_id)
    return _sorted(store, matches)


def _room_climate_sensors(store):
    """The sensors each room is measured by, as named in the area registry.

    Matching on the temperature device class instead would pull in every
    other thermometer in the house, down to the CPUs of the routers.
    """
    sensors = []
    for area in store.areas.values():
        for key in ("temperature_entity_id", "humidity_entity_id"):
            entity_id = area.get(key)
            if entity_id and entity_id in store.states:
                sensors.append(entity_id)
    return sensors


def _maintenance_entities(store):
    matches = []
    for entity_id, state in store.states.items():
        if not store.is_visible(entity_id, include_diagnostic=True):
            continue
        if state.domain == "update":
            if state.state == "on":
                matches.append(entity_id)
            continue
        if not state.available:
            continue
        device_class = store.device_class_of(entity_id)
        allowed = _MAINTENANCE_CLASSES.get(state.domain)
        if allowed and device_class in allowed:
            matches.append(entity_id)
    return matches


def _energy_entities(store):
    """The statistics configured in the energy dashboard, sources first."""
    entity_ids = []
    for source in store.energy.get("energy_sources") or []:
        for key in ("stat_rate", "stat_energy_from", "stat_energy_to"):
            entity_id = source.get(key)
            if isinstance(entity_id, str) and entity_id in store.states:
                entity_ids.append(entity_id)
        for flow_key in ("flow_from", "flow_to"):
            for flow in source.get(flow_key) or []:
                entity_id = flow.get("stat_energy_from") or flow.get("stat_energy_to")
                if isinstance(entity_id, str) and entity_id in store.states:
                    entity_ids.append(entity_id)
    for device in store.energy.get("device_consumption") or []:
        for key in ("stat_rate", "stat_consumption"):
            entity_id = device.get(key)
            if isinstance(entity_id, str) and entity_id in store.states:
                entity_ids.append(entity_id)

    seen = set()
    return [entity_id for entity_id in entity_ids
            if not (entity_id in seen or seen.add(entity_id))]


def _area_sections(store, options, label):
    sections = []
    by_floor = [(floor, store.areas_on_floor(floor["floor_id"]))
                for floor in store.sorted_floors()]
    by_floor.append(({"floor_id": None, "name": ""}, store.areas_without_floor()))

    for floor, areas in by_floor:
        for area in areas:
            entity_ids = store.entities_in_area(area["area_id"])
            if not entity_ids and options.hide_empty_areas:
                continue
            groups = _device_groups(store, entity_ids, label("no_device"))
            sections.append(Section(
                "area:%s" % area["area_id"], AREA, area.get("name", ""),
                [entity_id for group in groups for entity_id in group.entity_ids],
                subtitle=floor.get("name", ""), area_id=area["area_id"],
                groups=groups))
    return sections


def _device_groups(store, entity_ids, no_device_title):
    """One group per device, entities without one collected at the end."""
    by_device = {}
    orphans = []
    for entity_id in entity_ids:
        entity = store.entities.get(entity_id)
        device_id = entity.device_id if entity is not None else None
        if device_id and store.device_name(device_id):
            by_device.setdefault(device_id, []).append(entity_id)
        else:
            orphans.append(entity_id)

    groups = [Group(store.device_name(device_id), _sorted(store, members))
              for device_id, members in by_device.items()]
    groups.sort(key=lambda group: group.title.lower())
    if orphans:
        groups.append(Group(no_device_title, _sorted(store, orphans)))
    return groups


def _sorted(store, entity_ids):
    return sorted(set(entity_ids), key=lambda entity_id: store.name_of(entity_id).lower())


