# Keeping up with Home Assistant

The addon reads as much as it can from Home Assistant and reimplements only
what Home Assistant keeps in its frontend, where a script cannot reach it. This
note lists the second part, because that is what a Home Assistant release can
quietly invalidate.

## Read live - nothing to maintain

| Source | Supplies |
| --- | --- |
| `frontend/subscribe_system_data`, key `home` | favourites and the shortcut list, with order and `hidden` |
| `config/{entity,device,area,floor}_registry/list` and the four `*_registry_updated` events | names, rooms, floors, registry order, `hidden_by`/`disabled_by`, `options` |
| `get_states` and `state_changed` | states, attributes, `friendly_name`, `supported_features`, units |
| `energy/get_prefs` | which statistics the energy summary is made of |
| `frontend/get_icons`, category `entity` | the icons an integration declares per state |
| `get_config` | temperature unit, version |

A renamed entity, a moved room, a reordered favourite or a changed energy
configuration needs no code change.

## Reimplemented - keep an eye on this

### Breaks loudly

| What | Where | Symptom |
| --- | --- | --- |
| WebSocket command names | `resources/lib/model.py` (`load`, `subscribe`) | connects, stays empty |
| IndieAuth `client_id`/`redirect_uri`, `/auth/login_flow`, `/auth/token` with `authorization_code` and `refresh_token` | `resources/lib/ha/auth.py` | user name and password stop working; a long-lived token still does |
| `/api/camera_proxy/<entity>` | `resources/lib/cameras.py` | camera rows stay blank |
| Service field names: `cleaning_area_id`, `brightness_pct`, `color_temp_kelvin`, `effect`, `fan_speed`, `option`, `hvac_mode`, `preset_mode`, `volume_level`, `position`, `value` | `resources/lib/actions.py` | the call comes back as an error |
| `media_player/browse_media`, and `play_media` with `media_content_type` and `media_content_id` | `resources/lib/window.py`, `resources/lib/mediadialog.py` | the browse button reports an error, or a pick plays nothing |
| `media_player.join` and `unjoin` with `group_members` | `resources/lib/mediadialog.py` | connecting players reports an error |

### Breaks quietly

This is the group that needs looking after.

| What | Where | Symptom |
| --- | --- | --- |
| `supported_features` bit masks for vacuum, media player, lock, climate and cover, written as numbers | `resources/lib/actions.py` | a command Home Assistant gained is never offered |
| Which entity belongs in which summary: the domain table, the device class table, the maintenance rule, and climate following the sensors a room is measured by | `resources/lib/sections.py` | a summary holds too much or too little |
| Whether an entity belongs on a dashboard at all: `hidden_by`, `disabled_by`, `entity_category`, and entities with no registry entry | `resources/lib/model.py` (`is_visible`) | entities appear that Home Assistant hides, or the reverse |
| How the Home panel is assembled: favourites, then shortcuts in their own order, then rooms by floor | `resources/lib/sections.py` (`build`) | a new kind of shortcut never arrives |
| How a row is named: `friendly_name` for rows, the registry name under a device heading, `name_by_user or name` for a device | `resources/lib/model.py` | rows are named differently from Home Assistant |
| What OK does per domain, and which domains are read only | `resources/lib/actions.py` (`default_action`) | a new domain is treated as display only |
| `frontend/get_translations` and the four key shapes an option value is looked up under | `resources/lib/formatting.py` (`option_text`) | option lists read as raw values again |

### Cosmetic

| What | Where |
| --- | --- |
| The icon fallback chain: state pairs, device class table, domain table, and the battery ladder in ten percent steps | `resources/lib/icons.py` |
| State wording and colours, the active and unavailable state lists, the alarming device classes | `resources/lib/formatting.py` |
| The shipped Material Design Icons, frozen at whatever `tools/icons.txt` lists | `tools/icons.txt` |
| The addon's own translations of state words, rather than Home Assistant's frontend translations | `resources/language/*/strings.po` |

A new or renamed icon in Home Assistant ends as an empty square here, not as an
error.

The last row of that table has a limit worth knowing: the *values* in an option
list are not translated here at all, they come from Home Assistant over
`frontend/get_translations`. The same channel carries the state words, which
this addon still translates itself - moving those over is a decision, not an
oversight.

## Tried against one installation only

The addon was written against a single Home Assistant installation, and that
one has no cover, fan, humidifier, valve, water heater, alarm panel or lawn
mower. Everything below therefore rests on Home Assistant's documentation
rather than on a device that answered back.

| Domain | State of affairs |
| --- | --- |
| `alarm_control_panel` | arming and disarming are implemented, including asking for the code where the panel reports a `code_format`; setting the alarm off is deliberately not offered. Never run against a panel. |
| `water_heater` | operating mode, target temperature, away mode and power are implemented. Never run against a boiler. |
| `cover` | open, close, stop, position and all four tilt features are implemented. Never run against a blind. |
| `fan` | speed, preset, oscillation and direction are implemented. Never run against a fan. |
| `humidifier` | target humidity and mode are implemented. Never run against a humidifier. |
| `valve` | open, close, stop and position are implemented. Never run against a valve. |
| `siren`, `remote` | switched on and off only; tones, duration, volume and learning commands are not offered. |
| `lawn_mower` | not handled anywhere - a command list like the vacuum's is the obvious shape. |
| `text`, `date`, `time`, `datetime` | no way to enter a value. |

Two parts of the Home dashboard are read but not acted on. A shortcut the user
adds by hand - Home Assistant offers this next to the summaries - is passed
over, because what such an entry carries has not been examined and guessing at
it would be worse than ignoring it. And the media player summary is switched
off in the installation this was written against; it is implemented and covered
by a test, but has never been seen on a screen.

The summary titles are Home Assistant's own German wording, taken from its
settings page. The English ones are this addon's rendering of the same, not
verified against an English Home Assistant - the frontend keeps those strings
in its own bundle, out of reach of both the WebSocket API and
`frontend/get_translations`.

The one deliberate departure is the energy summary. Home Assistant's title
names the day, which its own version earns: it can show a day's statistics.
This one only lists the entities the energy dashboard is built from, with no
notion of a day, so it is titled just "Energy".

Some choices are calibrated against that one installation as well, and are
merely useless rather than wrong elsewhere: the TLS handshake ladder comes from
a cloud endpoint that refuses a post-quantum key share, the reconnect timings
from the same endpoint's habit of dropping connections, and camera stills
instead of live video from ffmpeg failing its own handshake against that
address. A local installation may well manage video.

Two things that look installation-shaped and are not: nothing is hardcoded to
an installation - no entity id, no area id, no address - and the shipped icons
are chosen by Material Design Icons category rather than harvested from a
particular set of entities. Measured against 1121 visible entities, none was
left without an icon.

## What the media browser leaves out

Home Assistant browses in a grid of tiles with a search box; this browses in a
list, one level per dialog. Left out on purpose: searching a level
(`can_search`), queueing rather than playing (`MEDIA_ENQUEUE`), announcing over
what is playing (`MEDIA_ANNOUNCE`), and the note Home Assistant adds when it
hides children a player cannot play (`not_shown`, zero on every level of every
player here).

Two things to know before changing it. A level's reply is not about that
level.
Browsing a Radio Browser directory answers with the integration's own root as
the node, and only the children belong to where the walk actually is. The
dialog therefore keeps its own way back rather than reading it out of the
reply.

And a player's feature mask is not fixed. The Yamaha reports 888716 while it is
off and 1019788 while it plays, gaining `BROWSE_MEDIA` on the way. The row is
drawn from the live state on every redraw, so nothing needs to notice this -
but a cache put in front of it would break the button.

## What Kodi does not lend a script

The volume slider in the media window behaves differently from every other
slider in Kodi. The convention is that one takes left and right only after
it has been clicked, and hands the move on to its neighbour before that;
this one takes them straight away and is left with up or down.

The convention lives in `CGUISettingsSliderControl`, the `sliderex` control
type, whose `IsActive()` reports whether it has been clicked - where the
plain `slider`'s returns true for good. And `sliderex` cannot be used:
Kodi's Python control factory has no case for it, so `getControl()` on one
raises "Unknown control type for python", and nothing about it could then be
read, set, placed or navigated.

Emulating the convention would mean putting the value back and moving the
focus on by hand, after the control has already acted on the key, and with
no way to show that the slider is armed - a slider's textures cannot be
swapped from Python either. Left as it is on purpose.

Kodi tells a script nothing about a slider being moved, for the same family
of reasons: the control sends a click that the Python wrapper refuses,
`ControlSlider` not overriding `canAcceptMessages`. The value is read back
in `onAction` instead.

## Checking a real install

`tools/unknown_features.py` compares the `supported_features` of every entity
against the bits the addon acts on, and names what is left over:

```
python3 tools/unknown_features.py https://homeassistant.example.com <token>
```

The address and token may also come from `HA_URL` and `HA_TOKEN`. Two masks
feed it: `actions.KNOWN_FEATURES`, the bits acted on, derived from the same
constants the commands are built from so the tool cannot drift from the code,
and `actions.IGNORED_FEATURES`, the bits looked at and passed over - a marker
that is no command, or one needing input this dialog cannot ask for. What the
tool reports is therefore genuinely unaccounted for. A newly supported command
belongs in both its feature table and `KNOWN_FEATURES`.

What the tool cannot see:

* Capabilities that are attributes rather than bits. A light's brightness and
  colour temperature come from `supported_color_modes`, a thermostat's modes
  from `hvac_modes`, a vacuum's rooms from the entity registry. Only a reading
  of the release notes catches a change there.
* Whether a summary still holds what Home Assistant's own dashboard holds.
  Compare against the Home dashboard by eye; that is how the climate and
  maintenance rules were arrived at.

After a Home Assistant release, running the tool and looking at one room and
one summary side by side with the real dashboard is the whole check.
