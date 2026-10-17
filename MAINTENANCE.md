# Keeping up with Home Assistant

The add-on reads as much as it can from Home Assistant and reimplements only
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
| `camera/capabilities` | which ways Home Assistant streams a camera: HLS, WebRTC or both |

A renamed entity, a moved room, a reordered favourite or a changed energy
configuration needs no code change.

## Reimplemented - keep an eye on this

### Breaks loudly

| What | Where | Symptom |
| --- | --- | --- |
| WebSocket command names | `resources/lib/model.py` (`load`, `subscribe`) | connects, stays empty |
| IndieAuth `client_id`/`redirect_uri`, `/auth/login_flow`, `/auth/token` with `authorization_code` and `refresh_token` | `resources/lib/ha/auth.py` | user name and password stop working; a long-lived token still does |
| `/api/camera_proxy/<entity>`, with `width` and `height` for the size | `resources/lib/cameras.py` | camera rows stay blank, or their stills come at full size again |
| The camera and image proxy paths the media tree lists as thumbnails, swapped for the entity's own picture | `resources/lib/browse.py` (`proxied_entity`), `resources/lib/window.py` | those thumbnails stay blank in the browser |
| Service field names: `cleaning_area_id`, `brightness_pct`, `color_temp_kelvin`, `hs_color`, `effect`, `fan_speed`, `option`, `hvac_mode`, `preset_mode`, `volume_level`, `position`, `value` | `resources/lib/actions.py` | the call comes back as an error |
| `media_player/browse_media`, and `play_media` with `media_content_type` and `media_content_id` | `resources/lib/window.py`, `resources/lib/mediadialog.py` | the browse button reports an error, or a pick plays nothing |
| `media_player.join` and `unjoin` with `group_members` | `resources/lib/mediadialog.py` | connecting players reports an error |
| `camera/stream` for HLS, and what the WebRTC inputstream takes from 22.1.0 on: Home Assistant's URL with the camera in its `ha_entity_id` parameter, and the token in `bearer_token` | `resources/lib/window.py`, `addon.xml` | a camera's live picture fails |
| The rest of the player's services and their fields: `media_seek` with `seek_position`, `shuffle_set` with `shuffle`, `repeat_set` with `repeat`, `select_source` with `source`, `select_sound_mode` with `sound_mode` | `resources/lib/mediadialog.py` | that one button or slider reports an error |

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
| Kodi's own action ids, written as numbers: the context menu, info, back, the digit keys, the five transport actions, and for the steering cross the arrows, page up and down and zoom in and out. The Python API names none of them, so they are copied out of Kodi's `ActionIDs.h` | `resources/lib/window.py`, `resources/lib/mediadialog.py`, `resources/lib/ptzdialog.py`, `resources/lib/detailsdialog.py`, `resources/lib/dialogs.py` | an action does the wrong thing, or nothing |
| How a live picture is had: the camera's own URL, then WebRTC before HLS as the frontend prefers them | `resources/lib/actions.py` (`live_ways`) | a camera plays a worse way than Home Assistant would |
| Reolink's steering: the button translation keys `ptz_left` to `ptz_zoom_out` and `guard_go_to`, `reolink.ptz_move` with `speed` where a button's feature bit says so, and the lens a zoom belongs to, read from the channel in Reolink's unique ids (`<device>_<channel>_<key>`) | `resources/lib/actions.py` (`ptz_buttons`) | the steering cross or the lenses no longer appear |
| Which states are a point in time and say how long ago - `TIMESTAMP_STATE_DOMAINS` and `SENSOR_TIMESTAMP_DEVICE_CLASSES` - and when the wording moves from seconds to minutes and on, `selectUnit`'s thresholds, and the words `Intl.RelativeTimeFormat` with `numeric: "auto"` says instead of a count: now, yesterday, last week. `ha-relative-time` redraws them every second under a minute, so the rows work them out every second | `resources/lib/formatting.py`, `resources/lib/window.py` (`_tick_clock`) | a row shows a raw date again |
| How the details dialog words an attribute: the name and value key shapes of `compute_attribute_display.ts`, `DOMAIN_ATTRIBUTES_UNITS`, `DOMAIN_ATTRIBUTES_FORMATERS`, `TEMPERATURE_ATTRIBUTES`, `DOMAIN_OPTIONS_ATTRIBUTES` and `getWeatherUnit` | `resources/lib/details.py` | an attribute reads raw, or without its unit |
| When a number is a slider: `showNumberSlider` and its `AUTO_MODE_MAX_STEPS` | `resources/lib/actions.py` (`_number_action`) | a number opens the pad where Home Assistant shows a slider, or the reverse |
| The bounds a number pad entry is held to: `min` and `max` of a number, `min_temp` and `max_temp` of a thermostat or water heater, `min_humidity` and `max_humidity` of a humidifier, 0 to 100 for positions and speeds | `resources/lib/actions.py` (`number_bounds`) | a value Home Assistant refuses is sent, and only its error says why |
| The step the pad's minus and plus move by, and the places it takes: `step` of a number, `target_temp_step` of a thermostat or water heater, otherwise the frontend's 0.5 (1 in Fahrenheit) | `resources/lib/actions.py` (`number_step`) | a fraction cannot be entered, or the steps are too coarse |
| A lamp's favourite colours: the registry's `options.light.favorite_colors`, and where none were saved `computeDefaultFavoriteColors`; which lamps have them, `lightSupportsFavoriteColors` and `shouldShowFavoriteOptions` | `resources/lib/actions.py` (`favourite_colours`) | a lamp offers other favourites than Home Assistant, or none |
| What the media window draws: which buttons a state and a feature mask earn, which icon each of them carries, which attribute the description line is taken from, and how a reported title is tidied - `computeMediaControls`, `computeMediaDescription` and `cleanupMediaTitle`, all three in the frontend | `resources/lib/media.py` | the window offers buttons Home Assistant would not, or says the wrong thing about what is playing |

### Cosmetic

| What | Where |
| --- | --- |
| The icon fallback chain: state pairs, device class table, domain table, and the battery ladder in ten percent steps | `resources/lib/icons.py` |
| State colours, the active and unavailable state lists, the alarming device classes | `resources/lib/formatting.py` |
| A lit lamp's own colour, from `rgb_color` and strengthened as the tile card's `_computeStateColor` does it | `resources/lib/formatting.py` (`_lamp_colour`) |
| The colour picker: hue and saturation as Home Assistant's `ha-hs-color-picker` takes them, the colour modes it is offered for, and `hsv2rgb` at full value for the swatch | `resources/lib/actions.py`, `resources/lib/formatting.py` |
| A favourite's swatch: `ha-favorite-color-button` and the conversions it uses, `temperature2rgb`, `rgbw2rgb` and `rgbww2rgb` | `resources/lib/formatting.py` (`favourite_swatch`), `resources/lib/kelvin.py` |
| The shipped Material Design Icons, frozen at whatever `tools/icons.txt` lists | `tools/icons.txt` |
| The two words Home Assistant has no state for: a row that cannot be reached, and one that is there to be run | `resources/language/*/strings.po` |
| The media window's button labels, and the hint each of them puts at the foot of the dialog | `resources/language/*/strings.po` |
| The words on the dialogs' buttons, Kodi's own strings 106, 107 and 186 (No, Yes, OK) | `resources/lib/dialogs.py` |
| The dialogs' opening and closing: `ha-dialog`'s `show-dialog` from Web Awesome, fading in from 80 % of the size over 200 ms and back out the same way | `resources/skins/Default/1080i/*.xml` |
| The details dialog's labels, the relative times, and the names of the eight attributes every entity can have, which the frontend words itself (`ui.components.attributes.names`) | `resources/language/*/strings.po` |

A new or renamed icon in Home Assistant ends as an empty square here, not as an
error.

Almost no wording is decided here any more. What a row says about a state, and
what the values in an option list are called, both come from Home Assistant
over `frontend/get_translations` - down to the device class of a binary sensor,
so that a window reads as open rather than as on. Only two words are the
add-on's own, because Home Assistant has no state for them: a row it cannot
reach, and one that is there to be run.

The media window's buttons are named here as well, for a different reason.
Those labels are `ui.card.media_player.*`, and the `ui` category of
`frontend/get_translations` answers with nothing at all - the frontend keeps
its own interface strings in its bundle, the same wall the summary titles run
into further down.

The price is a dependency. Before the first connection there is no wording, and
in a language Home Assistant does not ship, a row falls back to the state as it
arrived while the rest of the add-on still speaks Kodi's language. A state that
Home Assistant does not translate at all is shown as it arrived, tidied only
where it is a plain slug.

## Tried against one installation only

The add-on was written against a single Home Assistant installation, and that
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
settings page. The English ones are this add-on's rendering of the same, not
verified against an English Home Assistant - the frontend keeps those strings
in its own bundle, out of reach of both the WebSocket API and
`frontend/get_translations`.

Two departures are deliberate. One is the energy summary. Home Assistant's title
names the day, which its own version earns: it can show a day's statistics.
This one only lists the entities the energy dashboard is built from, with no
notion of a day, so it is titled just "Energy".

The other is the context menu of anything that switches. Home Assistant's
dialog shows a toggle with both halves, and the on half can be pressed while
the entity is already on; the menu here names only the half the entity has not
reached. Home Assistant has no context menu to be faithful to, and a context
menu is by definition about what makes sense where it is opened - so the rule
that Home Assistant decides does not reach this far. `_power_actions` in
`resources/lib/actions.py` is where it is decided, from `stateActive`'s rule
that everything but off counts as on, plus the valve's closed. A state that
says nothing - out of reach, not yet known - still gets both.

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

## What the media window leaves out

Every `MediaPlayerEntityFeature` bit earns something in the window except
four, and those four are listed in `actions.IGNORED_FEATURES` so the feature
check stays quiet about them: `CLEAR_PLAYLIST`, which Home Assistant's own
dialog has no button for either, and `MEDIA_ENQUEUE`, `MEDIA_ANNOUNCE` and
`SEARCH_MEDIA`, which are about how something is played rather than about
playing it.

Home Assistant browses in a grid of tiles with a search box; this browses in a
list, one level per dialog. Left out on purpose: searching a level
(`can_search`, the browser's half of `SEARCH_MEDIA`), and the note Home
Assistant adds when it hides children a player cannot play (`not_shown`, zero
on every level of every player here).

Two things to know before changing the browser. A level's reply is not about
that level: browsing a Radio Browser directory answers with the integration's
own root as the node, and only the children belong to where the walk actually
is. The dialog therefore keeps its own way back rather than reading it out of
the reply.

And a player's feature mask is not fixed. The Yamaha reports 888716 while it is
off and 1019788 while it plays, gaining `BROWSE_MEDIA` on the way. The row is
drawn from the live state on every redraw, so nothing needs to notice this -
but a cache put in front of it would break the button.

Connecting players is a plain multi-select where Home Assistant has a list of
its own, and two things of that list are missing. Its "select all" was judged
not to be worth the work for the number of players anyone has. And the second
line under each player, naming what that player is playing, was dropped for
want of a use: the dialog is opened to decide who plays along, not to read
what they are at. Kodi's `multiselect` does take a details layout that could
carry such a line, but whether Estuary draws a tick in that layout was never
established, and a list of players whose ticks cannot be seen would be worse
than one line each.

## What Kodi does not lend a script

Both sliders in the media window - volume and position - behave differently
from every other slider in Kodi. The convention is that one takes left and
right only after it has been clicked, and hands the move on to its neighbour
before that; these take them straight away and are left with up or down.

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

A slider does say when it is out of use, at least: Kodi draws
`texturesliderbardisabled` and `textureslidernibdisabled` for one that is not
enabled, which is how a player that reports no `SEEK` gets a dimmed bar rather
than no bar at all.

Kodi tells a script nothing about a slider being moved, for the same family
of reasons: the control sends a click that the Python wrapper refuses,
`ControlSlider` not overriding `canAcceptMessages`. The value is read back
in `onAction` instead.

There is no release event either, so nothing can be sent when the key comes
up. The position slider waits for half a second of standing still and seeks
then, because seeking on every keypress would set the player going a dozen
times across one drag; the volume slider sends what it was left at a few times
a second instead, volume being cheap to set. The cost is that a long drag of
the position slider lands in one jump at the end rather than following the
thumb.

Nor can a script fetch a scrollbar: the control factory that refuses
`sliderex` has no case for it either. The select dialog, which moves its
rows to centre itself, therefore moves the group they sit in, scrollbar and
all. Its OK button stays outside the group: inside it, `setPosition` left the
button where the skin put it.

`Control.HasFocus` in a list layout is not asked of the window the list is
in: without a window to go by, Kodi asks the topmost modal dialog. Behind a
dialog of the add-on's own, the dashboard therefore names those dialogs to
keep its row marked.

Kodi's number pad takes whole numbers only: `Dialog().numeric` has types for
a number, a date, a time and an IP address, none of them with a decimal
point, so a target temperature of 21.5 °C could not be entered on it. The
add-on draws its own pad instead (`resources/lib/dialogs.py`, with the entry
worked out in `resources/lib/numberpad.py`); only a code that is text still
goes to Kodi's keyboard.

A script cannot claim an action either. Kodi acts on it first and tells the
script afterwards, and the answer that decides whether it goes further comes
from the native window, not from Python. A dialog without controls of its
own handles nothing natively, so Kodi hands every action on: volume up and
down would zoom the camera and change the volume along with it. That is why
the steering cross zooms on page up and down, and on a remote without them
switches the arrows over on the context menu action, which Kodi's player
does nothing with.

A Kodi favourite of a script keeps only the script's id: `CFavouritesURL`
takes the first parameter of `RunScript` as the target, so `AddOrRemove`
holds every entity's favourite for the same one and `Favourites.GetFavourites`
returns no more than the id. A plugin URL is kept whole, which is what the
plugin entry point is for.

Nor can a favourite be changed: JSON-RPC has `Favourites.AddFavourite`, which
adds or removes one, and nothing that edits one in place. A favourite added
before its icon carried Home Assistant's logo keeps the plain one, since
removing and adding it again would move it to the end of Kodi's list. Kodi's
Python brings no imaging library either, so the logo is drawn into the icon
in plain Python (`resources/lib/favouriteicon.py`).

And a Python window's class makes its Kodi object from the first Kodi base it
has. A dialog cannot be had by deriving one from the dashboard's window, so
the dashboard's workings sit in a class of their own that the window and the
favourite's dialog each put on their Kodi base.

## Checking a real install

`tools/unknown_features.py` compares the `supported_features` of every entity
against the bits the add-on acts on, and names what is left over:

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
