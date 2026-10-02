"""What pressing OK on a tile does, and what the context menu offers.

Actions are described here and executed by the window, so the mapping stays
testable without Kodi. Anything that could surprise - installing an update,
triggering an automation - is menu only and never bound to OK.
"""

SERVICE = "service"
NUMBER = "number"
TEMPERATURE = "temperature"
# One list to choose from, named by the entity: data carries which attribute
# holds the choices and under which key the answer goes back.
PICK = "pick"
# Several rooms at once, named by the area registry.
AREAS = "areas"
# A slider; data carries the service field, the range, the step and the unit.
SLIDER = "slider"
# A service the panel may want its code for.
ALARM = "alarm"
# The media player's own window.
MEDIA = "media"
COMMANDS = "commands"
DETAILS = "details"

# Domains where homeassistant.toggle does the right thing.
_TOGGLE_DOMAINS = ("light", "switch", "fan", "input_boolean", "siren",
                   "humidifier", "remote", "automation", "valve")

_READ_ONLY_DOMAINS = ("sensor", "binary_sensor", "person", "device_tracker",
                      "weather", "sun", "calendar", "image", "camera",
                      "conversation", "stt", "tts", "event")


class Action:
    __slots__ = ("label_key", "kind", "domain", "service", "data")

    def __init__(self, label_key, kind, domain="", service="", data=None):
        self.label_key = label_key
        self.kind = kind
        self.domain = domain
        self.service = service
        self.data = data or {}


def default_action(store, entity_id):
    """The action bound to OK, or None for a read-only entity."""
    state = store.states.get(entity_id)
    if state is None:
        return None
    domain = state.domain

    if domain in _READ_ONLY_DOMAINS or domain == "update":
        return None

    if domain in _TOGGLE_DOMAINS:
        return Action("action_toggle", SERVICE, "homeassistant", "toggle")

    if domain == "cover":
        return Action("action_toggle", SERVICE, "cover", "toggle")

    if domain == "scene":
        return Action("action_run", SERVICE, "scene", "turn_on")

    if domain == "script":
        return Action("action_run", SERVICE, "script", "turn_on")

    if domain in ("button", "input_button"):
        return Action("action_press", SERVICE, domain, "press")

    if domain == "media_player":
        return Action("action_media", MEDIA)

    if domain in _ASK_DOMAINS:
        # These do more than one useful thing, and which of them is wanted
        # does not follow from the state - so ask.
        return Action("action_commands", COMMANDS)

    if domain in ("number", "input_number"):
        return Action("action_set_value", NUMBER, domain, "set_value")

    if domain in ("select", "input_select"):
        return Action("action_select_option", PICK, domain, "select_option",
                      {"from": "options", "as": "option"})

    return None


def menu_actions(store, entity_id):
    """Everything the context menu offers, details last."""
    state = store.states.get(entity_id)
    if state is None:
        return [Action("action_details", DETAILS)]

    domain = state.domain
    actions = list(commands_for(store, state))

    if domain in _TOGGLE_DOMAINS or domain in ("light", "switch"):
        actions.extend(_power_actions(state, "homeassistant"))

    if domain == "automation":
        actions.append(Action("action_trigger", SERVICE, "automation", "trigger"))

    if domain == "media_player":
        # The window is what a player has instead of commands, so the menu
        # names it too - otherwise a player is left there with nothing but its
        # own details.
        actions.append(Action("action_media", MEDIA))

    if domain == "cover":
        actions.extend(_cover_actions(state))

    if domain in ("number", "input_number"):
        actions.append(Action("action_set_value", NUMBER, domain, "set_value"))

    if domain in ("select", "input_select"):
        actions.append(Action("action_select_option", PICK, domain,
                              "select_option", {"from": "options", "as": "option"}))

    if domain == "scene":
        actions.append(Action("action_run", SERVICE, "scene", "turn_on"))

    if domain == "script":
        actions.extend(_script_actions(state))

    if domain == "update" and _can_install(state):
        actions.append(Action("action_install", SERVICE, "update", "install"))

    actions.append(Action("action_details", DETAILS))
    return actions


def features_of(state):
    return state.attributes.get("supported_features") or 0


# stateActive() in Home Assistant's frontend: every state but off counts as
# on, and a valve says closed where everything else says off.
_OFF_STATE = {"valve": "closed"}

_UNTOLD_STATES = ("unavailable", "unknown", "none", "")


def _switched_on(state):
    """True on, False off, None where the state does not say."""
    if state.state in _UNTOLD_STATES:
        return None
    return state.state != _OFF_STATE.get(state.domain, "off")


def _power_actions(state, domain, on=True, off=True):
    """Turning on and turning off, less whichever the entity already is.

    A lit lamp has nothing to gain from being switched on again, and a context
    menu is meant to carry what a press would change. Where the state does not
    say - a device out of reach - both are offered, because either might be
    the one that is wanted.
    """
    switched = _switched_on(state)
    actions = []
    if on and switched is not True:
        actions.append(Action("action_turn_on", SERVICE, domain, "turn_on"))
    if off and switched is not False:
        actions.append(Action("action_turn_off", SERVICE, domain, "turn_off"))
    return actions


def switches_off(store, entity_id, service):
    """Whether carrying this service out would leave the entity off.

    A turn_off says so itself; a toggle only when the thing is on. Every
    domain with an off to reach has a turn_off, so nothing else needs listing.
    A script's turn_off cancels a run and switches nothing off.
    """
    if entity_id.startswith("script."):
        return False
    if service == "turn_off":
        return True
    if service != "toggle":
        return False
    state = store.states.get(entity_id)
    return state is not None and _switched_on(state) is True


def confirmation(store, entity_id, service, settings):
    """The heading and the question to put before this service, or None.

    Settings is read for confirm_off, confirm_off_lights and confirm_open -
    anything carrying those three will do, which is what the tests hand it.
    A socket may be holding up the router or the machine Home Assistant runs
    on, where a light costs nothing but switching it back on; and a door that
    opens is a door anyone can walk through.
    """
    domain = entity_id.split(".")[0]
    if settings.confirm_open and domain == "lock" and service == "open":
        return "confirm_open_title", "confirm_open_text"
    if (settings.confirm_off and switches_off(store, entity_id, service)
            and not (settings.confirm_off_lights and domain == "light")):
        return "confirm_off_title", "confirm_off_text"
    return None


def service_data(action, state=None):
    """The data a service call carries, with any flip resolved now.

    A command that turns something around - muting, shuffle, oscillation,
    away mode - has to read the state at the moment it is pressed, not when
    the menu was built: between the two, someone else may have flipped it.
    """
    data = {key: value for key, value in action.data.items() if key != "flip"}
    attribute = action.data.get("flip")
    if attribute and state is not None:
        data[attribute] = not _is_on(state.attributes.get(attribute))
    return data


def _is_on(value):
    """A flag an attribute reports either as a boolean or as on and off."""
    if isinstance(value, str):
        return value.lower() == "on"
    return bool(value)


def commands_for(store, state):
    """The commands an entity reports it understands.

    Read from supported_features, so a device that can do less is offered
    less. Commands that would need input this dialog cannot ask for - a raw
    command, a media item to play - are left out.
    """
    builder = _COMMANDS.get(state.domain)
    return builder(store, state) if builder else []


def cleanable_areas(entity):
    """The rooms a vacuum can be sent to.

    Home Assistant stores which map segments a room stands for in the entity
    registry rather than on the entity, and offers a room exactly when it is
    mapped there. A vacuum that reports the feature but has no map yet - a
    second vacuum, a fresh install - therefore offers nothing.
    """
    if entity is None:
        return ()
    mapping = (entity.options.get("vacuum") or {}).get("area_mapping") or {}
    return tuple(mapping)


# VacuumEntityFeature
_VACUUM = ((8192, "action_start", "start"),
           (4, "action_pause", "pause"),
           (8, "action_stop", "stop"),
           (16, "action_return", "return_to_base"),
           (1024, "action_clean_spot", "clean_spot"),
           (512, "action_locate", "locate"))
_VACUUM_FAN_SPEED = 32
_VACUUM_CLEAN_AREA = 16384


_VACUUM_CLEANING = ("cleaning", "on")
_VACUUM_AT_REST = ("docked", "off", "idle")


def _vacuum_commands(store, state):
    """What the vacuum can be told now, by Home Assistant's own rules.

    Start where it is not cleaning and pause only where it is - Home Assistant
    swaps the one for the other - stop where it is not at rest, and send it
    home where it is not on its way there. One rule is the addon's own: a
    vacuum standing in its dock is not sent there again.
    """
    if state.state == "unavailable":
        return []
    allowed = {"start": state.state not in _VACUUM_CLEANING,
               "pause": state.state in _VACUUM_CLEANING,
               "stop": state.state not in _VACUUM_AT_REST,
               "return_to_base": state.state not in ("returning", "docked")}
    features = features_of(state)
    commands = [Action(label, SERVICE, "vacuum", service)
                for bit, label, service in _VACUUM
                if features & bit and allowed.get(service, True)]
    if (features & _VACUUM_CLEAN_AREA
            and cleanable_areas(store.entities.get(state.entity_id))):
        commands.append(Action("action_clean_areas", AREAS, "vacuum",
                               "clean_area", {"as": "cleaning_area_id"}))
    if features & _VACUUM_FAN_SPEED and state.attributes.get("fan_speed_list"):
        commands.append(Action("action_fan_speed", PICK, "vacuum",
                               "set_fan_speed",
                               {"from": "fan_speed_list", "as": "fan_speed"}))
    return commands


# MediaPlayerEntityFeature. Every one of these is acted on by the media window
# rather than by a command here, so the bits are only listed: PAUSE, SEEK,
# VOLUME_SET, VOLUME_MUTE, PREVIOUS, NEXT, TURN_ON, TURN_OFF, PLAY_MEDIA,
# VOLUME_STEP, SELECT_SOURCE, STOP, PLAY, SHUFFLE_SET, SELECT_SOUND_MODE,
# BROWSE_MEDIA, REPEAT_SET, GROUPING. What is left of them here is telling
# tools/unknown_features.py that they are known.
_MEDIA_WINDOW = (1 | 2 | 4 | 8 | 16 | 32 | 128 | 256 | 512 | 1024 | 2048
                 | 4096 | 16384 | 32768 | 65536 | 131072 | 262144 | 524288)


_LOCK_OPEN = 1  # LockEntityFeature.OPEN: draws the latch, not just the bolt


def _lock_commands(store, state):
    """What the lock can be told now, by Home Assistant's own rules.

    Whatever it is not already, and nothing while it is on its way somewhere.
    A lock that only assumes its state is offered everything, since what it
    reports may not be so. Two rules are the addon's own: an opened lock is
    not offered unlocking, since drawing the latch drew the bolt with it; and
    while the door stands open, neither locking nor opening it is offered -
    the bolt would shoot into thin air, and the door is open already.
    """
    if state.state == "unavailable":
        return []
    assumed = state.attributes.get("assumed_state") is True
    waiting = state.state in ("locking", "unlocking", "opening")
    door_open = _door_open(store, state)

    def can(*already):
        return assumed or (state.state not in already and not waiting)

    commands = []
    if can("locked") and not door_open:
        commands.append(Action("action_lock", SERVICE, "lock", "lock"))
    if can("unlocked", "open"):
        commands.append(Action("action_unlock", SERVICE, "lock", "unlock"))
    if features_of(state) & _LOCK_OPEN and can("open") and not door_open:
        commands.append(Action("action_unlatch", SERVICE, "lock", "open"))
    return commands


def _door_open(store, state):
    """Whether a door contact on the lock's own device reports the door open.

    The lock knows its bolt and its latch, not the door. A lock that senses
    the door as well, as a Nuki does, reports it as a binary sensor of the
    door class on the same device.
    """
    entity = store.entities.get(state.entity_id)
    device_id = entity.device_id if entity is not None else None
    if not device_id:
        return False
    for entity_id, other in store.entities.items():
        if (other.device_id == device_id and entity_id.startswith("binary_sensor.")
                and store.device_class_of(entity_id) == "door"):
            sensor = store.states.get(entity_id)
            if sensor is not None and sensor.state == "on":
                return True
    return False


# ClimateEntityFeature
_CLIMATE_TARGET_TEMPERATURE = 1
_CLIMATE_FAN_MODE = 8
_CLIMATE_PRESET_MODE = 16
_CLIMATE_TURN_OFF = 128
_CLIMATE_TURN_ON = 256


def _climate_commands(store, state):
    features = features_of(state)
    commands = []
    if state.attributes.get("hvac_modes"):
        commands.append(Action("action_set_hvac", PICK, "climate",
                               "set_hvac_mode",
                               {"from": "hvac_modes", "as": "hvac_mode"}))
    if features & _CLIMATE_TARGET_TEMPERATURE:
        commands.append(Action("action_set_temperature", TEMPERATURE, "climate",
                               "set_temperature"))
    if features & _CLIMATE_PRESET_MODE and state.attributes.get("preset_modes"):
        commands.append(Action("action_preset", PICK, "climate",
                               "set_preset_mode",
                               {"from": "preset_modes", "as": "preset_mode"}))
    if features & _CLIMATE_FAN_MODE and state.attributes.get("fan_modes"):
        commands.append(Action("action_fan_mode", PICK, "climate",
                               "set_fan_mode",
                               {"from": "fan_modes", "as": "fan_mode"}))
    commands.extend(_power_actions(state, "climate",
                                   on=bool(features & _CLIMATE_TURN_ON),
                                   off=bool(features & _CLIMATE_TURN_OFF)))
    return commands


# How far one press moves a light's sliders. Home Assistant steps by one,
# which would take a remote a hundred presses for the brightness and
# thousands for the colour temperature.
_BRIGHTNESS_STEP = 5
_KELVIN_STEP = 100
# Home Assistant's range for a lamp that names none of its own.
_DEFAULT_KELVIN = (2700, 6500)


def _light_commands(store, state):
    modes = set(state.attributes.get("supported_color_modes") or [])
    commands = []
    if modes - {"onoff"}:
        commands.append(Action("action_brightness", SLIDER, "light", "turn_on",
                               {"as": "brightness_pct", "min": 1, "max": 100,
                                "step": _BRIGHTNESS_STEP, "unit": "%"}))
    kelvins = _kelvin_range(state)
    if kelvins:
        commands.append(Action("action_colour_temperature", SLIDER, "light",
                               "turn_on", {"as": "color_temp_kelvin",
                                           "min": kelvins[0], "max": kelvins[1],
                                           "step": _KELVIN_STEP, "unit": "K"}))
    if state.attributes.get("effect_list"):
        commands.append(Action("action_effect", PICK, "light", "turn_on",
                               {"from": "effect_list", "as": "effect"}))
    return commands


def _kelvin_range(state):
    if "color_temp" not in (state.attributes.get("supported_color_modes") or []):
        return None
    low = state.attributes.get("min_color_temp_kelvin") or _DEFAULT_KELVIN[0]
    high = state.attributes.get("max_color_temp_kelvin") or _DEFAULT_KELVIN[1]
    return (low, high) if low < high else None


def slider_start(state, action):
    """Where a slider opens: at the lamp's own value where it has one.

    Without one, Home Assistant leaves the brightness slider empty and shows
    no position on the colour temperature; a Kodi slider needs a position,
    so the one starts at its low end and the other in the middle.
    """
    data = action.data
    attributes = state.attributes if state is not None else {}
    if data["as"] == "brightness_pct":
        brightness = attributes.get("brightness")
        if brightness is None:
            return data["min"]
        return max(int(brightness * 100 / 255.0 + 0.5), 1)
    if (state is not None and state.state == "on"
            and attributes.get("color_mode") == "color_temp"
            and attributes.get("color_temp_kelvin")):
        return attributes["color_temp_kelvin"]
    return (data["min"] + data["max"]) // 2


def slider_value(raw, data):
    """Where a press leaves the slider: on the step grid, ends included.

    Kodi steps from wherever the slider stood, so from a range that starts
    at 1 or 2202 it would count 6, 11 or 2302, 2402.
    """
    low, high = data["min"], data["max"]
    if raw <= low or raw >= high:
        return min(max(raw, low), high)
    step = data["step"]
    return min(max(int(raw / float(step) + 0.5) * step, low), high)


# AlarmControlPanelEntityFeature
_ALARM = ((1, "action_arm_home", "alarm_arm_home"),
          (2, "action_arm_away", "alarm_arm_away"),
          (4, "action_arm_night", "alarm_arm_night"),
          (32, "action_arm_vacation", "alarm_arm_vacation"),
          (16, "action_arm_custom", "alarm_arm_custom_bypass"))
_ALARM_TRIGGER = 8


_ALARM_BUSY = ("arming", "pending", "triggered")


def _alarm_commands(store, state):
    """Arming and disarming, by Home Assistant's rules for its alarm panel.

    Every way of arming the panel reports, and disarming, less the mode it is
    in already; while it is arming, counting down or ringing, only disarming.

    Setting the alarm off is left out although panels offer it: on a remote
    control it is one wrong press away, and nothing here is worth waking the
    street for.
    """
    if state.state == "unavailable":
        return []
    disarm = Action("action_disarm", ALARM, "alarm_control_panel", "alarm_disarm")
    if state.state in _ALARM_BUSY:
        return [disarm]
    features = features_of(state)
    commands = [Action(label, ALARM, "alarm_control_panel", service)
                for bit, label, service in _ALARM
                if features & bit
                and state.state != service.replace("alarm_arm_", "armed_")]
    if state.state != "disarmed":
        commands.append(disarm)
    return commands


# WaterHeaterEntityFeature
_WATER_TARGET_TEMPERATURE = 1
_WATER_OPERATION_MODE = 2
_WATER_AWAY_MODE = 4
_WATER_ON_OFF = 8


def _water_heater_commands(store, state):
    features = features_of(state)
    commands = []
    if features & _WATER_OPERATION_MODE and state.attributes.get("operation_list"):
        commands.append(Action("action_operation_mode", PICK, "water_heater",
                               "set_operation_mode",
                               {"from": "operation_list", "as": "operation_mode"}))
    if features & _WATER_TARGET_TEMPERATURE:
        commands.append(Action("action_set_temperature", TEMPERATURE,
                               "water_heater", "set_temperature"))
    if features & _WATER_AWAY_MODE:
        commands.append(Action("action_away_mode", SERVICE, "water_heater",
                               "set_away_mode", {"flip": "away_mode"}))
    if features & _WATER_ON_OFF:
        commands.extend(_power_actions(state, "water_heater"))
    return commands


# FanEntityFeature
_FAN_SET_SPEED = 1
_FAN_OSCILLATE = 2
_FAN_DIRECTION = 4
_FAN_ON_OFF = 8 | 16
_FAN_PRESET_MODE = 32

_DIRECTIONS = (("direction_forward", "forward"),
               ("direction_reverse", "reverse"))


def _fan_commands(store, state):
    features = features_of(state)
    attributes = state.attributes
    commands = []
    if features & _FAN_SET_SPEED:
        commands.append(Action("action_speed", NUMBER, "fan", "set_percentage"))
    if features & _FAN_PRESET_MODE and attributes.get("preset_modes"):
        commands.append(Action("action_preset", PICK, "fan", "set_preset_mode",
                               {"from": "preset_modes", "as": "preset_mode"}))
    if features & _FAN_OSCILLATE:
        commands.append(Action("action_oscillate", SERVICE, "fan", "oscillate",
                               {"flip": "oscillating"}))
    if features & _FAN_DIRECTION:
        commands.append(Action("action_direction", PICK, "fan", "set_direction",
                               {"as": "direction", "choices": list(_DIRECTIONS),
                                "translate": True}))
    return commands


# HumidifierEntityFeature. Only the modes carry a bit: a target humidity is
# what a humidifier is for, so it is offered whatever the entity reports.
_HUMIDIFIER_MODES = 1


def _humidifier_commands(store, state):
    commands = [Action("action_target_humidity", NUMBER, "humidifier",
                       "set_humidity")]
    if (features_of(state) & _HUMIDIFIER_MODES
            and state.attributes.get("available_modes")):
        commands.append(Action("action_operation_mode", PICK, "humidifier",
                               "set_mode",
                               {"from": "available_modes", "as": "mode"}))
    return commands


# ValveEntityFeature
_VALVE = ((1, "action_open", "open_valve"),
          (2, "action_close", "close_valve"),
          (8, "action_stop", "stop_valve"))
_VALVE_SET_POSITION = 4


def _valve_commands(store, state):
    features = features_of(state)
    commands = [Action(label, SERVICE, "valve", service)
                for bit, label, service in _VALVE if features & bit]
    if features & _VALVE_SET_POSITION:
        commands.append(Action("action_position", NUMBER, "valve",
                               "set_valve_position"))
    return commands


_COMMANDS = {
    "vacuum": _vacuum_commands,
    "lock": _lock_commands,
    "climate": _climate_commands,
    "light": _light_commands,
    "alarm_control_panel": _alarm_commands,
    "water_heater": _water_heater_commands,
    "fan": _fan_commands,
    "humidifier": _humidifier_commands,
    "valve": _valve_commands,
}

# Light, fan, humidifier and valve are not among them: switching is what OK is
# for, and for most of them it is all there is. All of them keep their commands
# in the context menu. media_player keeps none: its window offers everything the
# menu used to, and offers it better.
_ASK_DOMAINS = ("vacuum", "lock", "climate",
                "alarm_control_panel", "water_heater")

# Offered without asking: a cover that reports none of these still opens and
# closes, and every cover integration supports them.
_COVER_OPEN_CLOSE_STOP = 1 | 2 | 8
_COVER_SET_POSITION = 4

# CoverEntityFeature, the tilt half. Home Assistant calls it the tilt; a
# venetian blind has it, a roller shutter has not.
_TILT = ((16, "action_open_tilt", "open_cover_tilt"),
         (32, "action_close_tilt", "close_cover_tilt"),
         (64, "action_stop_tilt", "stop_cover_tilt"))
_COVER_SET_TILT_POSITION = 128


def _cover_actions(state):
    """What the cover can be told now, by Home Assistant's own rules.

    Open where it is not fully open and not opening already, close likewise,
    stop whenever it can be reached - many covers never say they are moving.
    Nothing while it is unavailable, and everything for a cover that only
    assumes its state, since what it reports may not be so.
    """
    if state.state == "unavailable":
        return []
    features = features_of(state)
    attributes = state.attributes
    assumed = attributes.get("assumed_state") is True
    position = attributes.get("current_position")
    if position is not None:
        fully_open, fully_closed = position == 100, position == 0
    else:
        fully_open, fully_closed = state.state == "open", state.state == "closed"

    actions = []
    if assumed or not (fully_open or state.state == "opening"):
        actions.append(Action("action_open", SERVICE, "cover", "open_cover"))
    if assumed or not (fully_closed or state.state == "closing"):
        actions.append(Action("action_close", SERVICE, "cover", "close_cover"))
    actions.append(Action("action_stop", SERVICE, "cover", "stop_cover"))
    if features & _COVER_SET_POSITION:
        actions.append(Action("action_position", NUMBER, "cover",
                              "set_cover_position"))
    actions.extend(_tilt_actions(features, attributes.get("current_tilt_position"),
                                 assumed))
    return actions


def _tilt_actions(features, tilt, assumed):
    """The slats, each asked for by its own bit.

    Opening and closing a cover are offered whatever it reports, because every
    cover does them. Tilt is the opposite: offering it where there are no slats
    would be offering nothing. Slats already fully open or shut are not
    offered that way again; they have only their position to tell.
    """
    done = {"open_cover_tilt": tilt == 100, "close_cover_tilt": tilt == 0}
    actions = [Action(label, SERVICE, "cover", service)
               for bit, label, service in _TILT
               if features & bit and (assumed or not done.get(service))]
    if features & _COVER_SET_TILT_POSITION:
        actions.append(Action("action_set_tilt", NUMBER, "cover",
                              "set_cover_tilt_position"))
    return actions


_LIGHT_EFFECT = 4

_SIREN_ON_OFF = 1 | 2
_UPDATE_INSTALL = 1


def _script_actions(state):
    """Running and cancelling, by Home Assistant's rules for its script row.

    Run where the script is idle, or where its mode lets another run start
    alongside and there is room for one; cancel while it runs.
    """
    if state.state == "unavailable":
        return []
    attributes = state.attributes
    room = (attributes.get("mode") in ("queued", "parallel")
            and (attributes.get("current") or 0) < (attributes.get("max") or 0))
    actions = []
    if state.state == "off" or (state.state == "on" and room):
        actions.append(Action("action_run", SERVICE, "script", "turn_on"))
    if state.state == "on":
        actions.append(Action("action_cancel", SERVICE, "script", "turn_off"))
    return actions


def _can_install(state):
    """Whether there is an update to install, by Home Assistant's own rules.

    One is waiting, or the latest version was skipped, which can still be
    installed; the integration can install at all; and it is not installing
    already.
    """
    attributes = state.attributes
    if not features_of(state) & _UPDATE_INSTALL or attributes.get("in_progress"):
        return False
    latest = attributes.get("latest_version")
    return (state.state == "on"
            or bool(latest and attributes.get("skipped_version") == latest))


def _mask(table):
    return sum(bit for bit, _, _ in table)


# Every feature bit this addon acts on, per domain. Derived from the same
# constants the commands are built from, so it cannot drift from them - a newly
# supported command belongs in both its table and here.
KNOWN_FEATURES = {
    "vacuum": _mask(_VACUUM) | _VACUUM_FAN_SPEED | _VACUUM_CLEAN_AREA,
    "media_player": _MEDIA_WINDOW,
    "lock": _LOCK_OPEN,
    "climate": (_CLIMATE_TARGET_TEMPERATURE | _CLIMATE_FAN_MODE
                | _CLIMATE_PRESET_MODE | _CLIMATE_TURN_ON | _CLIMATE_TURN_OFF),
    "cover": (_COVER_OPEN_CLOSE_STOP | _COVER_SET_POSITION | _mask(_TILT)
              | _COVER_SET_TILT_POSITION),
    "light": _LIGHT_EFFECT,
    "alarm_control_panel": _mask(_ALARM),
    "water_heater": (_WATER_TARGET_TEMPERATURE | _WATER_OPERATION_MODE
                     | _WATER_AWAY_MODE | _WATER_ON_OFF),
    "siren": _SIREN_ON_OFF,
    "update": _UPDATE_INSTALL,
    "fan": (_FAN_SET_SPEED | _FAN_OSCILLATE | _FAN_DIRECTION | _FAN_ON_OFF
            | _FAN_PRESET_MODE),
    "humidifier": _HUMIDIFIER_MODES,
    "valve": _mask(_VALVE) | _VALVE_SET_POSITION,
}

# Bits that have been looked at and passed over, so that a run of
# tools/unknown_features.py names only what is genuinely new. Either the bit is
# no command at all, or it needs something this dialog cannot ask for: a place
# on a timeline, a queue, a search.
IGNORED_FEATURES = {
    "vacuum": 256 | 4096,                       # SEND_COMMAND, STATE
    "media_player": (8192                       # CLEAR_PLAYLIST
                     | 1048576 | 2097152 | 4194304),  # ANNOUNCE, ENQUEUE, SEARCH
    "light": 8 | 32,                            # FLASH, TRANSITION: call parameters
    "alarm_control_panel": _ALARM_TRIGGER,      # see _alarm_commands
    "siren": 4 | 8 | 16,                        # TONES, DURATION, VOLUME_SET
    "update": 2 | 4 | 8 | 16,                   # version, progress, backup, notes
}
