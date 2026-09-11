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

# Nothing to transport: for a player that is off, Home Assistant offers a
# power button and nothing else, and that is not part of this row.
_SILENT = ("off", "unavailable", "unknown")
_ASLEEP = ("idle", "standby")
_PAUSED = ("paused", "buffering")


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
    """The power buttons, in Home Assistant's order.

    A player whose state is assumed gets both directions side by side, for
    the same reason its transport does: nothing says which way it would go.
    One whose state is known gets the single button that applies. Either way
    each direction needs its own feature bit, and none of this belongs in
    the transport row - it is the device, not the playback.
    """
    features = state.attributes.get("supported_features") or 0
    if state.state in ("unavailable", "unknown"):
        return []
    if state.attributes.get("assumed_state"):
        buttons = []
        if features & _TURN_ON:
            buttons.append(("power_on", "turn_on"))
        if features & _TURN_OFF:
            buttons.append(("power_off", "turn_off"))
        return buttons
    if state.state == "off":
        return [("power", "turn_on")] if features & _TURN_ON else []
    return [("power", "turn_off")] if features & _TURN_OFF else []


def volume(state):
    """What the volume row offers: (mute, level, steps).

    level is where the volume stands, for a player that takes one; steps
    says it only takes up and down. Home Assistant shows a slider for the
    first and two buttons for the second - the Shield's own remote takes
    steps only, the television beside it takes a level.
    """
    features = state.attributes.get("supported_features") or 0
    if state.state in ("unavailable", "unknown", "off"):
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

    Not gated on the player being off: Home Assistant keeps this row of
    buttons alive there too, and an amplifier woken by its input choice is a
    reasonable thing to want.
    """
    features = state.attributes.get("supported_features") or 0
    if state.state in ("unavailable", "unknown") or not features & _SELECT_SOURCE:
        return []
    return [str(name) for name in state.attributes.get("source_list") or []]


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
    """The transport buttons Home Assistant would draw, in its order.

    Its rule lives in the frontend, so this is reconstructed from what that
    dialog shows, checked against five players. One that is off offers
    nothing; one merely dozing offers play. One whose state is taken on
    trust - assumed_state, as a television bound over its own protocol is -
    offers pause, play and stop side by side, because nothing says which of
    them applies. One whose state is known gets the single button that state
    calls for, and stop only where it cannot pause.
    """
    features = state.attributes.get("supported_features") or 0
    if state.state in _SILENT:
        return []
    if state.state in _ASLEEP:
        return [("play", "media_play")] if features & _PLAY else []

    buttons = []
    if features & _PREVIOUS:
        buttons.append(("previous", "media_previous_track"))
    if state.attributes.get("assumed_state"):
        if features & _PAUSE:
            buttons.append(("pause", "media_pause"))
        if features & _PLAY:
            buttons.append(("play", "media_play"))
        if features & _STOP:
            buttons.append(("stop", "media_stop"))
    elif state.state == PLAYING:
        if features & _PAUSE:
            buttons.append(("pause", "media_pause"))
        elif features & _STOP:
            buttons.append(("stop", "media_stop"))
    elif state.state in _PAUSED and features & _PLAY:
        buttons.append(("play", "media_play"))
    if features & _NEXT:
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
