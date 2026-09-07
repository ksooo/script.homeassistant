# Home Assistant Dashboard for Kodi

Shows the contents of the Home Assistant **Home** dashboard inside Kodi: your
favourites, the light, climate, security, maintenance, weather and energy
summaries, and every area grouped by floor, floors in the order Home Assistant
lists them. Inside an area the entities sit under their device. Every entity
carries its Material Design icon in a tinted circle, coloured by state the way
Home Assistant colours it - a locked lock green, an unlocked one red. States update live, and devices can be
switched with the remote.

![icon](resources/icon.png)

## Requirements

* Kodi 19 (Matrix) or newer
* Home Assistant 2026.4 or newer, reachable from the Kodi machine

No Python modules besides Kodi's own are needed. The addon speaks the Home
Assistant WebSocket API through a small RFC 6455 client of its own, because
Kodi ships none and the registries are not available over REST.

## Setup

1. Copy the addon into Kodi's `addons` directory, then **enable** it in
   *Add-ons -> My add-ons -> Program add-ons*. Kodi installs add-ons found
   there in a disabled state, and *Run* stays greyed out until you do.
2. Open its settings.
3. Enter the address of your Home Assistant instance, for example
   `http://homeassistant.local:8123` or your Nabu Casa URL.
4. Enter user name and password, or paste a long-lived access token under
   *Advanced*. A token takes precedence when both are set.
5. Press **Test connection**.

The password is stored unencrypted in `userdata/addon_data/script.homeassistant/settings.xml`,
as Kodi stores all settings. A long-lived token is the safer choice where the
Kodi machine is not fully under your control: it can be revoked on its own in
Home Assistant under *Profile -> Security*.

If two-factor authentication is enabled, the addon asks for the code during
login; it walks whatever steps Home Assistant declares.

## Usage

| Key | Action |
|---|---|
| Up / down on the left | Pick a section - the rows follow at once, no OK needed |
| OK on a section | Move on to the rows |
| Left / right | Switch between the section list and the rows |
| OK on a row | Act on the entity, or offer the commands it understands |
| Up / down on the right | Device headings are stepped over, they hold no selection |
| C | Context menu: all other actions, entity details, refresh |
| Back | Close |

OK does what the entity's domain suggests - toggling a light, opening a cover,
running a scene. Where the state does not say what is wanted it asks instead,
offering the commands the entity reports: a vacuum, a media player, a lock, a
thermostat, an alarm panel and a water heater all do that. Anything that could
surprise is in the context menu only: installing an update, triggering an
automation.

## How the dashboard is reconstructed

Home is not a Lovelace dashboard. `get_panels` reports it as a panel of its
own - `component_name: "home"`, with a panel each for its summaries - so there
are no views, no cards and no configuration to fetch. Nor is it a Lovelace
strategy, which would at least leave a declaration behind to read. What is
stored is the input the panel works from, and that is what this addon reads:

| Section | Source |
|---|---|
| Favourites | `frontend/get_system_data` key `home` |
| Summaries | the `shortcuts` in the same data, hidden ones skipped |
| Areas | floor, area, device and entity registries; entities grouped under their device |
| Grouping | a room's section groups by device, a summary groups by floor and room; favourites keep the order Home Assistant holds them in |
| Values | `get_states` plus a `state_changed` subscription |
| Energy | `energy/get_prefs` |

Everything is read at runtime and kept current by subscriptions. Adding a
favourite in Home Assistant, renaming an entity, moving it to another room or
hiding it shows up in Kodi without a restart.

## Cameras

A camera row carries a still from `/api/camera_proxy`, refreshed on the
interval set in the addon settings and only for the section on screen. The
still is written to a file under `special://temp` rather than handed to Kodi
as a URL: Kodi caches images by URL, and a picture that changes every ten
seconds would fill its texture database. Two file names per camera alternate,
because Kodi holds on to a file it has already read under the same path.

There is no live video. Kodi's own cURL reaches Home Assistant fine, but the
player hands an HLS URL to ffmpeg, which opens the segments itself and fails
its TLS handshake against a Nabu Casa address - a property of the ffmpeg the
Kodi build carries, not something an addon can reach into.

## Limits

* **The summary rules live in the addon.** Which device class counts as
  "security" and what belongs under "maintenance" is decided in Home
  Assistant's frontend code, and no API exposes it. `resources/lib/sections.py`
  reimplements those rules; if Home Assistant changes them, this addon needs
  an update to follow.
* **Icons are shipped, not fetched.** Kodi renders no SVG, so the icons are
  rasterised to PNG at build time: every Material Design icon tagged Home
  Automation, Weather, Battery or Lock, plus everything the addon's rules and
  the integrations name - 1259 in all and 838 KB together. An entity whose
  icon is outside that set shows the plain circle; running
  `tools/make_icons.py` after adding the name to `tools/icons.txt` fixes that.
* **Only the last icon rule lives in the addon.** An explicit `icon`
  attribute and the icons an integration declares both come from Home
  Assistant, over `frontend/get_icons`. Just the fallback by domain and device
  class is decided in the frontend with no API to ask, so
  `resources/lib/icons.py` mirrors that step - the same maintenance caveat as
  the summaries above.
* **Only the Home dashboard.** A storage dashboard with custom cards is not
  rendered; its card types would each need an equivalent here.

## Development

Everything these scripts produce is checked in, so nothing here needs running
to use the addon. Each has one occasion to be run:

| Run | After changing |
|---|---|
| `python3 tools/make_icons.py` | `tools/icons.txt`, when an entity icon joins the shipped set |
| `python3 tools/make_textures.py` | the colours or geometry in that script, when a skin texture should look different |

Both are deterministic, so a rerun without changes produces no diff.
`make_icons.py` fetches the Material Design path data once and rasterises with
`rsvg-convert`, falling back to macOS QuickLook.

The addon icon is the Home Assistant logo from
https://thesvg.org/icon/home-assistant, kept as `tools/icon.svg` with a margin
so Kodi cannot clip it. No script turns it into `resources/icon.png` - that was
done once by hand.

The modules under `resources/lib` that build the dashboard - `model`, `sections`,
`formatting`, `actions` and everything under `ha` - do not import Kodi and can
be exercised outside it.

## Licence

GPL-2.0-or-later, see [LICENSE.txt](LICENSE.txt).
