"""What a media player's dialog shows, worked out without Kodi.

Home Assistant sends no position ticks: media_position moves only when
someone seeks, pauses or starts something. A progress bar therefore has to
carry the last report forward, which is what elapsed() does and what Home
Assistant's own frontend does too.
"""

import datetime
import time

PLAYING = "playing"

# MediaPlayerEntityFeature, the transport half.
_PAUSE = 1
_PREVIOUS = 16
_NEXT = 32
_STOP = 4096
_PLAY = 16384
_TURN_ON = 128
_TURN_OFF = 256
_VOLUME_SET = 4
_VOLUME_MUTE = 8
_VOLUME_STEP = 1024
_SELECT_SOURCE = 2048
_BROWSE = 131072
_SOUND_MODE = 65536
_GROUPING = 524288
_SHUFFLE = 32768
_REPEAT = 262144

# Where the outer transport buttons and the playback settings apply, which is
# Home Assistant's rule rather than a guess at it: computeMediaControls in its
# frontend asks for a player that is playing, paused or taken on trust.
_TRANSPORTING = ("playing", "paused")

# What repeat steps through, and the icon that says where it stands.
_REPEAT_ORDER = ("off", "all", "one")
_REPEAT_ICONS = {"off": "repeat-off", "all": "repeat", "one": "repeat-once"}


def _features(state):
    return state.attributes.get("supported_features") or 0


def _assumed(state):
    """Whether the player's state is taken on trust rather than reported."""
    return state.attributes.get("assumed_state") is True


def _active(state):
    """stateActive() for a media player: off, unknown and unavailable are not."""
    return state.state not in ("off", "unknown", "unavailable")


def _playback(state):
    """Whether playback settings apply: playing, paused, or taken on trust."""
    return (state.state != "unavailable"
            and (state.state in _TRANSPORTING or _assumed(state)))


def elapsed(state, now=None):
    """Seconds into the medium, carried forward while it plays."""
    position = _number(state.attributes.get("media_position"))
    if position is None:
        return None
    if state.state != PLAYING:
        return position
    return position + _since(state.attributes.get("media_position_updated_at"), now)


def duration(state):
    """Length of the medium, or None where there is no such thing.

    Live television and radio report zero, and a bar that can never fill
    says less than no bar at all.
    """
    return _number(state.attributes.get("media_duration")) or None


def fraction(state, now=None):
    """How far along, 0.0 to 1.0, or None when that cannot be said."""
    total = duration(state)
    position = elapsed(state, now)
    if not total or position is None:
        return None
    return max(0.0, min(1.0, position / float(total)))


def power(state):
    """The power buttons, as Home Assistant computes them.

    A player that is off, unknown or asleep offers only the way on - not the
    way off, whatever bit it reports. One that is awake offers the way off,
    and one taken on trust offers both, its icons saying which is which where
    a known player's icon only says standby.
    """
    features = _features(state)
    assumed = _assumed(state)
    if state.state == "unavailable":
        return []
    if not _active(state) and not assumed:
        return [("power_standby", "turn_on")] if features & _TURN_ON else []

    buttons = []
    if assumed and features & _TURN_ON:
        buttons.append(("power_on", "turn_on"))
    if features & _TURN_OFF:
        buttons.append(("power_off" if assumed else "power_standby", "turn_off"))
    return buttons


def volume(state):
    """What the volume row offers: (mute, level, steps).

    level is where the volume stands, for a player that takes one; steps says
    it only takes up and down. Home Assistant shows a slider for the first and
    two buttons for the second - the Shield's own remote takes steps only, the
    television beside it takes a level - and draws the row at all only for a
    player that takes one of the two, while it is awake or taken on trust.
    """
    features = _features(state)
    if not features & (_VOLUME_SET | _VOLUME_STEP):
        return (False, None, False)
    if not _active(state) and not _assumed(state):
        return (False, None, False)
    takes_level = bool(features & _VOLUME_SET)
    return (bool(features & _VOLUME_MUTE),
            (state.attributes.get("volume_level") or 0.0) if takes_level else None,
            bool(features & _VOLUME_STEP) and not takes_level)


def muted(state):
    """Whether the player says it is muted.

    Unlike a water heater's away mode this one is a real boolean - the volume
    row only needs to know which way round to draw its speaker.
    """
    return bool(state.attributes.get("is_volume_muted"))


def sources(state):
    """The inputs the player can be switched to, if it offers that.

    Not gated on the player's state: Home Assistant asks the feature bit
    alone, and an amplifier woken by its input choice is a reasonable thing to
    want.
    """
    if not _features(state) & _SELECT_SOURCE:
        return []
    return [str(name) for name in state.attributes.get("source_list") or []]


def can_browse(state):
    """Whether the player offers a media tree to walk.

    Home Assistant compares against unavailable only, so a player whose state
    it cannot read still offers its tree, and picking something there is a
    fair way to wake a box.
    """
    return state.state != "unavailable" and bool(_features(state) & _BROWSE)


def sound_modes(state):
    """The sound fields the player can be put into, if it offers them.

    The Yamaha names them as it stores them - "munich", "cellar_club" - and
    Home Assistant passes them through, so this does too. The button follows
    the list rather than the state: what a player has, it shows.
    """
    if not _features(state) & _SOUND_MODE:
        return []
    return [str(name) for name in state.attributes.get("sound_mode_list") or []]


def group_choices(store, entity_id):
    """The players this one could be grouped with, and who is in already.

    Only the same integration is offered: a group forms inside one, and there
    is no service to join across. The player itself is left out - it is always
    in its own group. Returns (entity_id, name, joined), in name order.
    """
    state = store.states.get(entity_id)
    if state is None or not can_group(state):
        return []
    platform = _platform(store, entity_id)
    members = [str(member) for member in state.attributes.get("group_members") or []]
    choices = [(other_id, store.display_name_of(other_id), other_id in members)
               for other_id, other in store.states.items()
               if other_id != entity_id and other.domain == "media_player"
               and can_group(other) and _platform(store, other_id) == platform]
    return sorted(choices, key=lambda choice: choice[1])


def group_plan(current, wanted):
    """The calls that make a group hold exactly the wanted players.

    Home Assistant has no service that sets a group: join adds to the target's
    group, unjoin takes a single player out of its own. So a change is one join
    for what came in, and one unjoin per player that left.
    """
    added = [entity_id for entity_id in wanted if entity_id not in current]
    removed = [entity_id for entity_id in current if entity_id not in wanted]
    return added, removed


def can_group(state):
    """Whether the group button shows.

    Unavailable is the only state that takes it away - a player Home Assistant
    knows nothing about keeps it, and so does one with nobody to group with.
    """
    return state.state != "unavailable" and bool(_features(state) & _GROUPING)


def can_select_source(state):
    """Whether the input button shows.

    The feature bit alone decides, as in Home Assistant, so a player that
    lists no inputs shows it and opens on an empty choice.
    """
    return bool(_features(state) & _SELECT_SOURCE)


def shuffle(state):
    """The shuffle button: (icon, what a press would set), or None.

    The icon says how the player stands, which is Home Assistant's way here
    even though the transport beside it shows the press instead.
    """
    if not _playback(state) or not _features(state) & _SHUFFLE:
        return None
    on = state.attributes.get("shuffle") is True
    return ("shuffle" if on else "shuffle-disabled", not on)


def repeat(state):
    """The repeat button: (icon, the next setting round), or None."""
    if not _playback(state) or not _features(state) & _REPEAT:
        return None
    current = str(state.attributes.get("repeat") or "off")
    if current not in _REPEAT_ORDER:
        current = "off"
    following = _REPEAT_ORDER[(_REPEAT_ORDER.index(current) + 1) % len(_REPEAT_ORDER)]
    return (_REPEAT_ICONS[current], following)


def _platform(store, entity_id):
    entity = store.entities.get(entity_id)
    return entity.platform if entity is not None else ""


def clock(seconds):
    """34:32, and 1:34:32 once it runs to hours."""
    if seconds is None:
        return ""
    hours, rest = divmod(int(max(0, seconds)), 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, seconds)
    return "%d:%02d" % (minutes, seconds)


def subtitle(state):
    """The line under the title: whatever names the medium next best."""
    for key in ("media_series_title", "app_name", "source"):
        value = state.attributes.get(key)
        if value:
            return str(value)
    return ""


def controls(state):
    """The transport buttons, as Home Assistant's frontend computes them.

    Its computeMediaControls decides this and the rules are its own: skipping
    a track needs a player that is playing, paused or taken on trust; the
    middle button is the one the state calls for; a player taken on trust gets
    play, pause and stop side by side, because nothing says which applies; and
    one that is merely "on" gets the single play-pause button.
    """
    features = _features(state)
    assumed = _assumed(state)
    if state.state == "unavailable" or (not _active(state) and not assumed):
        return []

    moving = state.state in _TRANSPORTING or assumed
    buttons = []
    if moving and features & _PREVIOUS:
        buttons.append(("previous", "media_previous_track"))

    if assumed:
        if features & _PLAY:
            buttons.append(("play", "media_play"))
        if features & _PAUSE:
            buttons.append(("pause", "media_pause"))
        if features & _STOP:
            buttons.append(("stop", "media_stop"))
    elif state.state == PLAYING and features & (_PAUSE | _STOP):
        buttons.append(("pause", "media_pause") if features & _PAUSE
                       else ("stop", "media_stop"))
    elif state.state in ("paused", "idle") and features & _PLAY:
        buttons.append(("play", "media_play"))
    elif state.state == "on" and features & (_PLAY | _PAUSE):
        buttons.append(("play_pause", "media_play"))

    if moving and features & _NEXT:
        buttons.append(("next", "media_next_track"))
    return buttons


def _since(stamp, now=None):
    when = _epoch(stamp)
    if when is None:
        return 0.0
    return max(0.0, (time.time() if now is None else now) - when)


def _epoch(stamp):
    """Epoch seconds of an ISO 8601 timestamp, or None.

    Home Assistant writes an offset of +00:00, but a trailing Z is the same
    instant and fromisoformat refuses it before Python 3.11.
    """
    if not stamp:
        return None
    text = str(stamp).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
