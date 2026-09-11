"""Turns a Home Assistant state into what a Kodi tile shows."""

from . import strings

# Home Assistant's state colours. It picks these in the frontend, so the
# mapping is mirrored here - the same maintenance caveat as the summaries.
AMBER = "FFFFC107"
GREEN = "FF4CAF50"
RED = "FFF44336"
ORANGE = "FFFF9800"
BLUE = "FF2196F3"
CYAN = "FF00BCD4"
GREY = "FF9CA3AF"
DIM = "FF5A6472"

# Domains whose "on" is simply active.
_ACTIVE_COLOUR = AMBER

# state -> colour, per domain, for the domains Home Assistant colours apart.
_BY_DOMAIN_STATE = {
    "lock": {"locked": GREEN, "unlocked": RED, "open": RED, "jammed": RED,
             "locking": ORANGE, "unlocking": ORANGE, "opening": ORANGE},
    "alarm_control_panel": {
        "disarmed": GREEN, "triggered": RED, "pending": ORANGE, "arming": ORANGE,
        "armed_home": RED, "armed_away": RED, "armed_night": RED,
        "armed_vacation": RED, "armed_custom_bypass": RED},
    "person": {"home": GREEN, "not_home": GREY},
    "device_tracker": {"home": GREEN, "not_home": GREY},
    "climate": {"heat": ORANGE, "cool": BLUE, "heat_cool": AMBER, "auto": GREEN,
                "dry": ORANGE, "fan_only": CYAN},
    "vacuum": {"cleaning": AMBER, "returning": AMBER, "error": RED},
    "water_heater": {"heat_pump": ORANGE, "eco": GREEN, "performance": ORANGE},
}

# Binary sensors whose "on" means trouble rather than activity.
_ALARMING_CLASSES = ("problem", "safety", "smoke", "gas", "moisture", "co",
                     "carbon_monoxide", "tamper", "battery")


_UNAVAILABLE_STATES = ("unavailable", "unknown", "none", "")

_ACTIVE_STATES = ("on", "open", "opening", "closing", "unlocked", "home",
                  "playing", "cleaning", "returning", "heat", "cool", "auto",
                  "heat_cool", "dry", "fan_only", "active")

# Wording per binary sensor device class: (state on, state off).
_BINARY_WORDS = {
    "door": ("open", "closed"),
    "window": ("open", "closed"),
    "garage_door": ("open", "closed"),
    "opening": ("open", "closed"),
    "lock": ("unlocked", "locked"),
    "motion": ("detected", "clear"),
    "occupancy": ("detected", "clear"),
    "presence": ("at_home", "away"),
    "moisture": ("wet", "dry"),
    "problem": ("problem", "ok"),
    "safety": ("problem", "ok"),
    "battery": ("low", "ok"),
    "update": ("update_available", "up_to_date"),
}

_SIMPLE_WORDS = {
    "on": "on",
    "off": "off",
    "open": "open",
    "closed": "closed",
    "opening": "opening",
    "closing": "closing",
    "locked": "locked",
    "unlocked": "unlocked",
    "locking": "locking",
    "unlocking": "unlocking",
    "jammed": "jammed",
    "home": "at_home",
    "not_home": "away",
}

_RUNNABLE_DOMAINS = ("scene", "script", "button", "input_button")


def state_text(store, entity_id, translate=None):
    """The value line of a tile."""
    tr = translate or strings.fallback
    state = store.states.get(entity_id)
    if state is None:
        return tr("unavailable")
    if state.state in _UNAVAILABLE_STATES:
        return tr("unavailable")

    domain = state.domain
    attributes = state.attributes

    if domain in _RUNNABLE_DOMAINS:
        return tr("run")

    if domain == "binary_sensor":
        words = _BINARY_WORDS.get(store.device_class_of(entity_id))
        if words:
            return tr(words[0] if state.state == "on" else words[1])
        return tr("on" if state.state == "on" else "off")

    if domain == "update":
        return tr("update_available" if state.state == "on" else "up_to_date")

    if domain == "light":
        if state.state != "on":
            return tr("off")
        brightness = attributes.get("brightness")
        if brightness is None:
            return tr("on")
        return "%s  %d %%" % (tr("on"), round(float(brightness) / 255.0 * 100))

    if domain == "cover":
        text = tr(_SIMPLE_WORDS.get(state.state, state.state))
        position = attributes.get("current_position")
        if position is not None and state.state in ("open", "opening", "closing"):
            return "%s  %d %%" % (text, int(position))
        return text

    if domain == "climate":
        text = _hvac_text(state, tr)
        current = attributes.get("current_temperature")
        target = attributes.get("temperature")
        unit = store.unit_of_temperature
        if current is not None and target is not None:
            return "%s  %s -> %s %s" % (text, _number(current), _number(target), unit)
        if current is not None:
            return "%s  %s %s" % (text, _number(current), unit)
        return text

    if domain == "media_player":
        title = attributes.get("media_title")
        if title and state.state in ("playing", "paused"):
            return "%s: %s" % (_word(tr, state.state), title)
        return _word(tr, state.state)

    if domain == "weather":
        temperature = attributes.get("temperature")
        condition = state.state.replace("-", " ").capitalize()
        if temperature is None:
            return condition
        return "%s  %s %s" % (condition, _number(temperature),
                              attributes.get("temperature_unit", ""))

    if domain in ("person", "device_tracker"):
        return tr(_SIMPLE_WORDS.get(state.state, state.state))

    if domain in ("sensor", "number", "input_number", "counter"):
        unit = attributes.get("unit_of_measurement")
        value = _number(state.state) if _is_number(state.state) else state.state
        return "%s %s" % (value, unit) if unit else str(value)

    return _word(tr, state.state, state_word(store, entity_id, state.state))


def _word(tr, state, offered=""):
    """This addon's wording first, Home Assistant's next, readable text last.

    The addon's own words stay in front: they are hand-kept and cover the
    states a dashboard shows all day. Home Assistant is asked for the rest - a
    select's options, a vacuum's own vocabulary - which used to arrive as a
    slug with its underscores rubbed out.
    """
    if state in _SIMPLE_WORDS:
        return tr(_SIMPLE_WORDS[state])
    return offered or str(state).replace("_", " ").capitalize()


def colour(store, entity_id):
    """The tint for an entity's icon, as an ARGB string for the skin."""
    state = store.states.get(entity_id)
    if state is None or state.state in _UNAVAILABLE_STATES:
        return DIM

    by_state = _BY_DOMAIN_STATE.get(state.domain)
    if by_state and state.state in by_state:
        return by_state[state.state]

    device_class = store.device_class_of(entity_id)
    if state.state == "on" and device_class in _ALARMING_CLASSES:
        return RED
    if state.domain == "sensor" and device_class == "battery":
        value = _as_number(state.state)
        if value is not None:
            # The three bands Home Assistant paints a battery in.
            return GREEN if value >= 70 else ORANGE if value >= 30 else RED
    if state.state in ("jammed", "error"):
        return RED
    if state.domain in _RUNNABLE_DOMAINS:
        return GREY
    if state.state in _ACTIVE_STATES:
        return _ACTIVE_COLOUR
    return GREY


def _as_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def room_text(store, entity_id):
    """The room a row belongs to."""
    area_id = store.area_of(entity_id)
    area = store.areas.get(area_id) if area_id else None
    return area.get("name", "") if area else ""


def option_text(store, entity_id, attribute, value):
    """Home Assistant's own wording for one value out of an option list.

    Four keys, most specific first: what the integration calls that
    attribute's values, what the domain calls them, and the same two again for
    values that are really states - a select's options, a thermostat's modes.
    An untranslated value reads as it arrived, which is what every list showed
    before: "cellar_club" rather than the sound field's name.
    """
    keys = (_attribute_keys(store, entity_id, attribute, value)
            + _state_keys(store, entity_id, value))
    return _translated(store, keys) or str(value)


def option_texts(store, entity_id, attribute, values):
    """The same for a whole list, in the order Home Assistant gave it."""
    return [option_text(store, entity_id, attribute, value) for value in values]


def state_word(store, entity_id, state):
    """Home Assistant's own word for a state, or "" where it has none."""
    return _translated(store, _state_keys(store, entity_id, state))


def _attribute_keys(store, entity_id, attribute, value):
    entity = store.entities.get(entity_id)
    if entity is None or not attribute:
        return []
    keys = []
    if entity.translation_key:
        keys.append("component.%s.entity.%s.%s.state_attributes.%s.state.%s"
                    % (entity.platform, entity.domain, entity.translation_key,
                       attribute, value))
    keys.append("component.%s.entity_component._.state_attributes.%s.state.%s"
                % (entity.domain, attribute, value))
    return keys


def _state_keys(store, entity_id, value):
    entity = store.entities.get(entity_id)
    if entity is None:
        return []
    keys = []
    if entity.translation_key:
        keys.append("component.%s.entity.%s.%s.state.%s"
                    % (entity.platform, entity.domain, entity.translation_key,
                       value))
    keys.append("component.%s.entity_component._.state.%s"
                % (entity.domain, value))
    return keys


def _translated(store, keys):
    for key in keys:
        text = store.translations.get(key)
        if text:
            return str(text)
    return ""


def _hvac_text(state, tr):
    action = state.attributes.get("hvac_action")
    text = action or state.state
    return str(text).replace("_", " ").capitalize()


def _is_number(value):
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number == int(number):
        return str(int(number))
    return ("%.2f" % number).rstrip("0").rstrip(".")
