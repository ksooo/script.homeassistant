"""Which Material Design icon an entity gets.

Home Assistant looks in three places, and so does this: an explicit ``icon``
attribute on the entity, then the icons an integration declares for its
entities, then a default by domain and device class. Only that last step is
decided in the frontend, in JavaScript, with no API to ask - it is mirrored
here.

Only icons shipped under ``resources/skins/Default/media/icons`` can be drawn;
``tools/make_icons.py`` regenerates that set from ``tools/icons.txt``.
"""

# Domain -> icon, for entities without a device class.
_BY_DOMAIN = {
    "alarm_control_panel": "shield",
    "automation": "robot",
    "binary_sensor": "checkbox-marked-circle",
    "button": "gesture-tap-button",
    "calendar": "calendar",
    "camera": "video",
    "climate": "thermostat",
    "conversation": "forum-outline",
    "counter": "counter",
    "cover": "window-shutter",
    "device_tracker": "account",
    "event": "eye",
    "fan": "fan",
    "humidifier": "air-humidifier",
    "image": "image",
    "input_boolean": "toggle-switch-variant",
    "input_button": "gesture-tap-button",
    "input_datetime": "calendar-clock",
    "input_number": "ray-vertex",
    "input_select": "format-list-bulleted",
    "input_text": "form-textbox",
    "light": "lightbulb",
    "lock": "lock",
    "media_player": "cast-connected",
    "notify": "message-alert",
    "number": "ray-vertex",
    "person": "account",
    "remote": "remote",
    "scene": "palette",
    "script": "script-text",
    "select": "format-list-bulleted",
    "sensor": "eye",
    "siren": "bullhorn",
    "stt": "microphone-message",
    "sun": "white-balance-sunny",
    "switch": "toggle-switch-variant",
    "text": "form-textbox",
    "timer": "timer-outline",
    "todo": "clipboard-list",
    "tts": "speaker-message",
    "update": "package-up",
    "vacuum": "robot-vacuum",
    "valve": "pipe-valve",
    "water_heater": "water-boiler",
    "weather": "weather-partly-cloudy",
    "zone": "map-marker-radius",
}

# (domain, device_class) -> icon for entities whose state does not matter.
_BY_CLASS = {
    ("cover", "awning"): "awning-outline",
    ("cover", "blind"): "blinds",
    ("cover", "curtain"): "curtains",
    ("cover", "damper"): "circle",
    ("cover", "door"): "door",
    ("cover", "garage"): "garage",
    ("cover", "gate"): "gate",
    ("cover", "shade"): "roller-shade",
    ("cover", "shutter"): "window-shutter",
    ("cover", "window"): "window-closed-variant",
    ("event", "button"): "gesture-tap-button",
    ("event", "doorbell"): "doorbell",
    ("event", "motion"): "motion-sensor",
    ("media_player", "receiver"): "audio-video",
    ("media_player", "speaker"): "speaker",
    ("media_player", "tv"): "television",
    ("number", "temperature"): "thermometer",
    ("sensor", "aqi"): "air-filter",
    ("sensor", "atmospheric_pressure"): "thermometer-lines",
    ("sensor", "carbon_dioxide"): "molecule-co2",
    ("sensor", "carbon_monoxide"): "molecule-co",
    ("sensor", "current"): "current-ac",
    ("sensor", "data_rate"): "transmission-tower",
    ("sensor", "data_size"): "database",
    ("sensor", "distance"): "arrow-left-right",
    ("sensor", "duration"): "timer-outline",
    ("sensor", "energy"): "lightning-bolt",
    ("sensor", "enum"): "eye",
    ("sensor", "frequency"): "sine-wave",
    ("sensor", "gas"): "meter-gas",
    ("sensor", "humidity"): "water-percent",
    ("sensor", "illuminance"): "brightness-5",
    ("sensor", "moisture"): "water-percent",
    ("sensor", "monetary"): "cash",
    ("sensor", "power"): "flash",
    ("sensor", "power_factor"): "angle-acute",
    ("sensor", "precipitation"): "weather-rainy",
    ("sensor", "pressure"): "gauge",
    ("sensor", "signal_strength"): "wifi",
    ("sensor", "sound_pressure"): "ear-hearing",
    ("sensor", "speed"): "speedometer",
    ("sensor", "temperature"): "thermometer",
    ("sensor", "timestamp"): "clock",
    ("sensor", "voltage"): "sine-wave",
    ("sensor", "volume"): "car-coolant-level",
    ("sensor", "volume_flow_rate"): "pipe",
    ("sensor", "water"): "water",
    ("sensor", "wind_speed"): "weather-windy",
    ("switch", "outlet"): "power-socket-de",
    ("switch", "switch"): "toggle-switch-variant",
    ("update", "firmware"): "chip",
}

# (domain, device_class) -> (icon when on, icon when off). Home Assistant
# swaps these the same way, which is what makes a closed door read as closed.
_BY_STATE = {
    ("binary_sensor", None): ("checkbox-marked-circle", "checkbox-blank-circle-outline"),
    ("binary_sensor", "battery"): ("battery-alert", "battery"),
    ("binary_sensor", "battery_charging"): ("battery-charging", "battery"),
    ("binary_sensor", "carbon_monoxide"): ("alert-circle", "check-circle"),
    ("binary_sensor", "cold"): ("snowflake", "thermometer"),
    ("binary_sensor", "connectivity"): ("check-network-outline", "close-network-outline"),
    ("binary_sensor", "door"): ("door-open", "door-closed"),
    ("binary_sensor", "garage_door"): ("garage-open", "garage"),
    ("binary_sensor", "gas"): ("alert-circle", "check-circle"),
    ("binary_sensor", "heat"): ("fire", "thermometer"),
    ("binary_sensor", "light"): ("brightness-7", "brightness-5"),
    ("binary_sensor", "lock"): ("lock-open", "lock"),
    ("binary_sensor", "moisture"): ("water", "water-off"),
    ("binary_sensor", "motion"): ("motion-sensor", "motion-sensor-off"),
    ("binary_sensor", "occupancy"): ("home", "home-outline"),
    ("binary_sensor", "opening"): ("square-outline", "square"),
    ("binary_sensor", "plug"): ("power-plug", "power-plug-off"),
    ("binary_sensor", "power"): ("power-plug", "power-plug-off"),
    ("binary_sensor", "presence"): ("home", "home-outline"),
    ("binary_sensor", "problem"): ("alert-circle", "check-circle"),
    ("binary_sensor", "running"): ("play", "stop"),
    ("binary_sensor", "safety"): ("alert-circle", "check-circle"),
    ("binary_sensor", "smoke"): ("smoke-detector-variant-alert", "smoke-detector-variant"),
    ("binary_sensor", "sound"): ("music-note", "music-note-off"),
    ("binary_sensor", "tamper"): ("alert-circle", "check-circle"),
    ("binary_sensor", "update"): ("package-up", "package"),
    ("binary_sensor", "vibration"): ("vibrate", "crop-portrait"),
    ("binary_sensor", "window"): ("window-open", "window-closed"),
    ("lock", None): ("lock-open", "lock"),
    ("update", None): ("package-up", "package"),
    ("person", None): ("account", "account-arrow-right"),
    ("device_tracker", None): ("account", "account-arrow-right"),
}

_ON_STATES = ("on", "home", "open", "unlocked", "detected")


def icon_for(store, entity_id):
    """The MDI name for an entity, without the ``mdi:`` prefix."""
    state = store.states.get(entity_id)
    if state is None:
        return ""

    explicit = state.attributes.get("icon")
    if explicit:
        return explicit.split(":", 1)[-1]

    declared = store.icon_translation(entity_id, state.state)
    if declared:
        return declared.split(":", 1)[-1]

    domain = state.domain
    device_class = store.device_class_of(entity_id)

    if domain == "sensor" and device_class == "battery":
        return _battery_icon(state)

    pair = _BY_STATE.get((domain, device_class)) or (
        _BY_STATE.get((domain, None)) if device_class is None else None)
    if pair:
        return pair[0] if state.state in _ON_STATES else pair[1]

    by_class = _BY_CLASS.get((domain, device_class))
    if by_class:
        return by_class

    return _BY_DOMAIN.get(domain, "")


def _battery_icon(state):
    """The battery ladder Home Assistant draws, in ten percent steps."""
    level = _as_number(state.state)
    if level is None:
        return "battery-unknown"

    rounded = int(round(level / 10.0) * 10)
    if _is_charging(state):
        return "battery-charging-%d" % rounded if level >= 10 else "battery-charging-outline"
    if level <= 5:
        return "battery-alert-variant-outline"
    return "battery" if rounded == 100 else "battery-%d" % rounded


def _is_charging(state):
    for key in ("is_charging", "battery_charging", "charging"):
        if key in state.attributes:
            return bool(state.attributes[key])
    return False


def _as_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def names_in_use():
    """Every icon this table can produce, for the generator."""
    names = set(_BY_DOMAIN.values()) | set(_BY_CLASS.values())
    for on_icon, off_icon in _BY_STATE.values():
        names.add(on_icon)
        names.add(off_icon)

    names.update({"battery", "battery-outline", "battery-unknown",
                  "battery-alert-variant-outline", "battery-charging-outline"})
    for step in range(10, 100, 10):
        names.add("battery-%d" % step)
        names.add("battery-charging-%d" % step)
    names.add("battery-charging-100")
    return names
