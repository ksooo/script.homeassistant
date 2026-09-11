"""What pressing OK on a tile does, and what the context menu offers.

Actions are described here and executed by the window, so the mapping stays
testable without Kodi. Anything that could surprise - installing an update,
triggering an automation - is menu only and never bound to OK.
"""

SERVICE = "service"
NUMBER = "number"
TEMPERATURE = "temperature"
VOLUME = "volume"
# One list to choose from, named by the entity: data carries which attribute
# holds the choices and under which key the answer goes back.
PICK = "pick"
# Several rooms at once, named by the area registry.
AREAS = "areas"
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
        actions.append(Action("action_turn_on", SERVICE, "homeassistant", "turn_on"))
        actions.append(Action("action_turn_off", SERVICE, "homeassistant", "turn_off"))

    if domain == "automation":
        actions.append(Action("action_trigger", SERVICE, "automation", "trigger"))

    if domain == "cover":
        features = features_of(state)
        actions.append(Action("action_open", SERVICE, "cover", "open_cover"))
        actions.append(Action("action_close", SERVICE, "cover", "close_cover"))
        actions.append(Action("action_stop", SERVICE, "cover", "stop_cover"))
        if features & _COVER_SET_POSITION:
            actions.append(Action("action_position", NUMBER, "cover",
                                  "set_cover_position"))
        actions.extend(_tilt_actions(features))

    if domain in ("number", "input_number"):
        actions.append(Action("action_set_value", NUMBER, domain, "set_value"))

    if domain in ("select", "input_select"):
        actions.append(Action("action_select_option", PICK, domain,
                              "select_option", {"from": "options", "as": "option"}))

    if domain in ("scene", "script"):
        actions.append(Action("action_run", SERVICE, domain, "turn_on"))

    if domain == "update":
        actions.append(Action("action_run", SERVICE, "update", "install"))

    actions.append(Action("action_details", DETAILS))
    return actions


def features_of(state):
    return state.attributes.get("supported_features") or 0


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


def _vacuum_commands(store, state):
    features = features_of(state)
    commands = [Action(label, SERVICE, "vacuum", service)
                for bit, label, service in _VACUUM if features & bit]
    if (features & _VACUUM_CLEAN_AREA
            and cleanable_areas(store.entities.get(state.entity_id))):
        commands.append(Action("action_clean_areas", AREAS, "vacuum",
                               "clean_area", {"as": "cleaning_area_id"}))
    if features & _VACUUM_FAN_SPEED and state.attributes.get("fan_speed_list"):
        commands.append(Action("action_fan_speed", PICK, "vacuum",
                               "set_fan_speed",
                               {"from": "fan_speed_list", "as": "fan_speed"}))
    return commands


# MediaPlayerEntityFeature
_MEDIA = ((16384, "action_play", "media_play"),
          (1, "action_pause", "media_pause"),
          (4096, "action_stop", "media_stop"),
          (16, "action_previous", "media_previous_track"),
          (32, "action_next", "media_next_track"))
_MEDIA_VOLUME_SET = 4
_MEDIA_VOLUME_MUTE = 8
_MEDIA_SELECT_SOURCE = 2048
_MEDIA_SELECT_SOUND_MODE = 65536
_MEDIA_TURN_ON = 128
_MEDIA_TURN_OFF = 256
_MEDIA_VOLUME_STEP = 1024
_MEDIA_SHUFFLE = 32768
_MEDIA_REPEAT = 262144
_MEDIA_PLAY_MEDIA = 512
_MEDIA_BROWSE = 131072

# Home Assistant names these three itself rather than listing them on the
# entity, so they are spelled out here and translated when the list is shown.
_REPEAT_MODES = (("repeat_off", "off"), ("repeat_all", "all"),
                 ("repeat_one", "one"))


def _media_commands(store, state):
    features = features_of(state)
    commands = [Action(label, SERVICE, "media_player", service)
                for bit, label, service in _MEDIA if features & bit]

    if features & _MEDIA_SHUFFLE:
        commands.append(Action("action_shuffle", SERVICE, "media_player",
                               "shuffle_set", {"flip": "shuffle"}))
    if features & _MEDIA_REPEAT:
        commands.append(Action("action_repeat", PICK, "media_player",
                               "repeat_set",
                               {"as": "repeat", "choices": list(_REPEAT_MODES),
                                "translate": True}))
    if features & _MEDIA_VOLUME_SET:
        commands.append(Action("action_volume", VOLUME, "media_player",
                               "volume_set"))
    if features & _MEDIA_VOLUME_STEP:
        commands.append(Action("action_volume_up", SERVICE, "media_player",
                               "volume_up"))
        commands.append(Action("action_volume_down", SERVICE, "media_player",
                               "volume_down"))
    if features & _MEDIA_VOLUME_MUTE:
        commands.append(Action("action_mute", SERVICE, "media_player",
                               "volume_mute", {"flip": "is_volume_muted"}))
    if features & _MEDIA_SELECT_SOURCE and state.attributes.get("source_list"):
        commands.append(Action("action_source", PICK, "media_player",
                               "select_source",
                               {"from": "source_list", "as": "source"}))
    if (features & _MEDIA_SELECT_SOUND_MODE
            and state.attributes.get("sound_mode_list")):
        commands.append(Action("action_sound_mode", PICK, "media_player",
                               "select_sound_mode",
                               {"from": "sound_mode_list", "as": "sound_mode"}))
    if features & _MEDIA_TURN_ON:
        commands.append(Action("action_turn_on", SERVICE, "media_player",
                               "turn_on"))
    if features & _MEDIA_TURN_OFF:
        commands.append(Action("action_turn_off", SERVICE, "media_player",
                               "turn_off"))
    return commands


_LOCK_OPEN = 1  # LockEntityFeature.OPEN: draws the latch, not just the bolt


def _lock_commands(store, state):
    commands = [Action("action_lock", SERVICE, "lock", "lock"),
                Action("action_unlock", SERVICE, "lock", "unlock")]
    if features_of(state) & _LOCK_OPEN:
        commands.append(Action("action_unlatch", SERVICE, "lock", "open"))
    return commands


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
    if features & _CLIMATE_TURN_ON:
        commands.append(Action("action_turn_on", SERVICE, "climate", "turn_on"))
    if features & _CLIMATE_TURN_OFF:
        commands.append(Action("action_turn_off", SERVICE, "climate", "turn_off"))
    return commands


# The steps offered for a dimmable light. Fixed steps rather than a slider:
# a remote control has no thumb to drag with, and the round numbers are what
# people ask for anyway.
_BRIGHTNESS_STEPS = (10, 25, 50, 75, 100)
_KELVIN_STEPS = (2200, 2700, 3000, 4000, 5000, 6500)


def _light_commands(store, state):
    modes = set(state.attributes.get("supported_color_modes") or [])
    commands = []
    if modes - {"onoff"}:
        commands.append(Action("action_brightness", PICK, "light", "turn_on",
                               {"as": "brightness_pct",
                                "choices": [("%d %%" % step, step)
                                            for step in _BRIGHTNESS_STEPS]}))
    kelvins = _colour_temperatures(state)
    if kelvins:
        commands.append(Action("action_colour_temperature", PICK, "light",
                               "turn_on", {"as": "color_temp_kelvin",
                                           "choices": kelvins}))
    if state.attributes.get("effect_list"):
        commands.append(Action("action_effect", PICK, "light", "turn_on",
                               {"from": "effect_list", "as": "effect"}))
    return commands


def _colour_temperatures(state):
    """The usual steps, kept within what this lamp says it can reach."""
    if "color_temp" not in (state.attributes.get("supported_color_modes") or []):
        return []
    low = state.attributes.get("min_color_temp_kelvin")
    high = state.attributes.get("max_color_temp_kelvin")
    if not low or not high or low >= high:
        return []
    steps = sorted({low, high}.union(k for k in _KELVIN_STEPS if low < k < high))
    return [("%d K" % kelvin, kelvin) for kelvin in steps]


# AlarmControlPanelEntityFeature
_ALARM = ((1, "action_arm_home", "alarm_arm_home"),
          (2, "action_arm_away", "alarm_arm_away"),
          (4, "action_arm_night", "alarm_arm_night"),
          (32, "action_arm_vacation", "alarm_arm_vacation"),
          (16, "action_arm_custom", "alarm_arm_custom_bypass"))
_ALARM_TRIGGER = 8


def _alarm_commands(store, state):
    """Arming and disarming.

    Setting the alarm off is left out although panels offer it: on a remote
    control it is one wrong press away, and nothing here is worth waking the
    street for.
    """
    features = features_of(state)
    commands = [Action(label, ALARM, "alarm_control_panel", service)
                for bit, label, service in _ALARM if features & bit]
    commands.append(Action("action_disarm", ALARM, "alarm_control_panel",
                           "alarm_disarm"))
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
        commands.append(Action("action_turn_on", SERVICE, "water_heater",
                               "turn_on"))
        commands.append(Action("action_turn_off", SERVICE, "water_heater",
                               "turn_off"))
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
    "media_player": _media_commands,
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
# for, and for most of them it is all there is. Nor is media_player, which has
# a window of its own. All of them keep their commands in the context menu.
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


def _tilt_actions(features):
    """The slats, each asked for by its own bit.

    Opening and closing a cover are offered whatever it reports, because every
    cover does them. Tilt is the opposite: offering it where there are no slats
    would be offering nothing.
    """
    actions = [Action(label, SERVICE, "cover", service)
               for bit, label, service in _TILT if features & bit]
    if features & _COVER_SET_TILT_POSITION:
        actions.append(Action("action_set_tilt", NUMBER, "cover",
                              "set_cover_tilt_position"))
    return actions


_LIGHT_EFFECT = 4

_SIREN_ON_OFF = 1 | 2
_UPDATE_INSTALL = 1


def _mask(table):
    return sum(bit for bit, _, _ in table)


# Every feature bit this addon acts on, per domain. Derived from the same
# constants the commands are built from, so it cannot drift from them - a newly
# supported command belongs in both its table and here.
KNOWN_FEATURES = {
    "vacuum": _mask(_VACUUM) | _VACUUM_FAN_SPEED | _VACUUM_CLEAN_AREA,
    "media_player": (_mask(_MEDIA) | _MEDIA_VOLUME_SET | _MEDIA_VOLUME_MUTE
                     | _MEDIA_SELECT_SOURCE | _MEDIA_SELECT_SOUND_MODE
                     | _MEDIA_TURN_ON | _MEDIA_TURN_OFF | _MEDIA_VOLUME_STEP
                     | _MEDIA_SHUFFLE | _MEDIA_REPEAT | _MEDIA_PLAY_MEDIA
                     | _MEDIA_BROWSE),
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
# on a timeline, another player to group with.
IGNORED_FEATURES = {
    "vacuum": 256 | 4096,                       # SEND_COMMAND, STATE
    "media_player": (2 | 524288                 # SEEK, GROUPING
                     | 1048576 | 2097152 | 4194304),  # ANNOUNCE, ENQUEUE, SEARCH
    "light": 8 | 32,                            # FLASH, TRANSITION: call parameters
    "alarm_control_panel": _ALARM_TRIGGER,      # see _alarm_commands
    "siren": 4 | 8 | 16,                        # TONES, DURATION, VOLUME_SET
    "update": 2 | 4 | 8 | 16,                   # version, progress, backup, notes
}
