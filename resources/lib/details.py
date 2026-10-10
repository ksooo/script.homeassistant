"""What the details dialog shows of an entity.

Worded the way Home Assistant's own details view words it
(ha-more-info-details.ts and compute_attribute_display.ts): the entity's id,
state and times, then every attribute under its translated name, sorted by
that name, with its value formatted. Home Assistant decides all of this in
the frontend, so the tables below mirror it - the same maintenance caveat as
the summaries.
"""

import datetime
import json
import re

from . import formatting

# DOMAIN_ATTRIBUTES_UNITS: units the frontend adds to bare numbers.
_UNITS = {
    "climate": {"humidity": "%", "current_humidity": "%", "target_humidity_low": "%",
                "target_humidity_high": "%", "target_humidity_step": "%",
                "min_humidity": "%", "max_humidity": "%"},
    "cover": {"current_position": "%", "current_tilt_position": "%"},
    "fan": {"percentage": "%"},
    "humidifier": {"humidity": "%", "current_humidity": "%", "min_humidity": "%",
                   "max_humidity": "%", "target_humidity_step": "%"},
    "light": {"color_temp": "mired", "max_mireds": "mired", "min_mireds": "mired",
              "color_temp_kelvin": "K", "min_color_temp_kelvin": "K",
              "max_color_temp_kelvin": "K", "brightness": "%"},
    "sun": {"azimuth": "°", "elevation": "°"},
    "valve": {"current_position": "%"},
    "sensor": {"battery_level": "%"},
    "media_player": {"volume_level": "%"},
}

# DOMAIN_ATTRIBUTES_FORMATERS: numbers the frontend scales first.
_SCALED = {
    ("light", "brightness"): lambda value: round(value / 255.0 * 100),
    ("media_player", "volume_level"): lambda value: round(value * 100),
}

# TEMPERATURE_ATTRIBUTES: in the installation's temperature unit.
_TEMPERATURES = {"temperature", "current_temperature", "target_temperature",
                 "target_temp_temp", "target_temp_high", "target_temp_low",
                 "target_temp_step", "min_temp", "max_temp"}

# getWeatherUnit: a weather entity names its own units.
_WEATHER_UNITS = {
    "visibility": "visibility_unit", "precipitation": "precipitation_unit",
    "pressure": "pressure_unit", "apparent_temperature": "temperature_unit",
    "dew_point": "temperature_unit", "temperature": "temperature_unit",
    "templow": "temperature_unit", "wind_gust_speed": "wind_speed_unit",
    "wind_speed": "wind_speed_unit",
}
_WEATHER_PERCENT = {"cloud_coverage", "humidity", "precipitation_probability"}

# DOMAIN_OPTIONS_ATTRIBUTES, turned round: an option list and the attribute
# its values are worded under ("_" is the state itself).
_VALUE_ATTRIBUTES = {
    "climate": {"hvac_modes": "_", "fan_modes": "fan_mode",
                "preset_modes": "preset_mode", "swing_modes": "swing_mode",
                "swing_horizontal_modes": "swing_horizontal_mode"},
    "cover": {"supported_speeds": "speed"},
    "event": {"event_types": "event_type"},
    "fan": {"preset_modes": "preset_mode"},
    "humidifier": {"available_modes": "mode"},
    "input_select": {"options": "_"},
    "select": {"options": "_"},
    "light": {"effect_list": "effect", "supported_color_modes": "color_mode"},
    "media_player": {"sound_mode_list": "sound_mode", "source_list": "source"},
    "remote": {"activity_list": "current_activity"},
    "sensor": {"options": "_"},
    "vacuum": {"fan_speed_list": "fan_speed"},
    "water_heater": {"operation_list": "operation_mode"},
}

# Attributes every entity can have, which the frontend words itself
# (ui.components.attributes.names) - out of reach of the API, so the addon
# carries them.
_COMMON_NAMES = {
    "assumed_state": "attribute_assumed_state",
    "attribution": "attribute_attribution",
    "device_class": "attribute_device_class",
    "entity_picture": "attribute_entity_picture",
    "friendly_name": "attribute_friendly_name",
    "icon": "attribute_icon",
    "supported_features": "attribute_supported_features",
    "unit_of_measurement": "attribute_unit_of_measurement",
}

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")

# selectUnit's thresholds: a unit holds until the count reaches the limit,
# then the next takes over - 44 seconds, but 1 minute rather than 45 seconds.
_RELATIVE = ((45, 1, "ago_second", "ago_seconds"),
             (45, 60, "ago_minute", "ago_minutes"),
             (22, 3600, "ago_hour", "ago_hours"),
             (5, 86400, "ago_day", "ago_days"),
             (4, 7 * 86400, "ago_week", "ago_weeks"),
             (11, 30.44 * 86400, "ago_month", "ago_months"),
             (None, 365.25 * 86400, "ago_year", "ago_years"))


def groups(store, entity_id, tr, timestamp):
    """The dialog's two lists: the entity, then its attributes. Its state
    is left out, as the head of the dialog shows it.

    ``timestamp`` turns an ISO time into the reader's date and time.
    """
    state = store.states[entity_id]
    entity = [(tr("details_id"), entity_id)]
    if state.last_changed:
        entity.append((tr("details_changed"), timestamp(state.last_changed)))
    if state.last_updated:
        entity.append((tr("details_updated"), timestamp(state.last_updated)))

    attributes = sorted(
        ((attribute_name(store, entity_id, name, tr),
          attribute_value(store, entity_id, name, value, tr, timestamp))
         for name, value in state.attributes.items()),
        key=lambda row: row[0].casefold())
    return [(tr("details_entity"), entity),
            (tr("details_attributes"), attributes or [(tr("details_none"), "")])]


def attribute_name(store, entity_id, attribute, tr):
    domain = entity_id.split(".", 1)[0]
    keys = []
    entity = store.entities.get(entity_id)
    if entity is not None and entity.translation_key:
        keys.append("component.%s.entity.%s.%s.state_attributes.%s.name"
                    % (entity.platform, domain, entity.translation_key, attribute))
    device_class = store.device_class_of(entity_id)
    if device_class:
        keys.append("component.%s.entity_component.%s.state_attributes.%s.name"
                    % (domain, device_class, attribute))
    keys.append("component.%s.entity_component._.state_attributes.%s.name"
                % (domain, attribute))
    for key in keys:
        text = store.translations.get(key)
        if text:
            return str(text)
    if attribute in _COMMON_NAMES:
        return tr(_COMMON_NAMES[attribute])
    text = attribute.replace("_", " ")
    for word in ("id", "ip", "mac", "gps"):
        text = re.sub(r"\b%s\b" % word, word.upper(), text)
    return text[:1].upper() + text[1:]


def attribute_value(store, entity_id, attribute, value, tr, timestamp):
    domain = entity_id.split(".", 1)[0]
    if value is None:
        return tr("unknown")

    if attribute == "device_class" and isinstance(value, str):
        text = store.translations.get(
            "component.%s.entity_component.%s.name" % (domain, value))
        if text:
            return str(text)

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        scale = _SCALED.get((domain, attribute))
        number = formatting.number_text(scale(value) if scale else value)
        unit = _unit(store, entity_id, attribute)
        if not unit:
            return number
        return number + unit if unit == "°" else "%s %s" % (number, unit)

    if isinstance(value, str) and _DATE.match(value):
        shown = timestamp(value)
        if shown:
            return shown

    if isinstance(value, dict) or (
            isinstance(value, list) and any(isinstance(item, dict) for item in value)):
        return json.dumps(value, ensure_ascii=False)

    if isinstance(value, list):
        worded_as = _VALUE_ATTRIBUTES.get(domain, {}).get(attribute)
        if worded_as == "_":
            return ", ".join(formatting.state_word(store, entity_id, item) or str(item)
                             for item in value)
        return ", ".join(attribute_value(store, entity_id, worded_as or attribute,
                                         item, tr, timestamp)
                         for item in value)

    if isinstance(value, bool):
        value = "true" if value else "false"
    return formatting.attribute_word(store, entity_id, attribute, value) or str(value)


def _unit(store, entity_id, attribute):
    domain = entity_id.split(".", 1)[0]
    if domain == "weather":
        if attribute in _WEATHER_PERCENT:
            return "%"
        unit = store.states[entity_id].attributes.get(_WEATHER_UNITS.get(attribute, ""))
        if unit:
            return unit
        return store.unit_of_temperature if "temp" in attribute else ""
    if attribute in _TEMPERATURES:
        return store.unit_of_temperature
    return _UNITS.get(domain, {}).get(attribute, "")


def relative_time(iso, now, tr):
    """How long ago, as Home Assistant puts it under a state: "5 minutes ago"."""
    moment = parse_time(iso)
    if moment is None:
        return ""
    seconds = max(0.0, now - moment.timestamp())
    for limit, size, one, many in _RELATIVE:
        count = int(round(seconds / size))
        if limit is None or count < limit:
            return tr(one) if count == 1 else tr(many) % count
    return ""


def parse_time(iso):
    try:
        moment = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    if moment.tzinfo is None:
        return None
    return moment
