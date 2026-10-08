"""Everything that talks to Kodi: settings, localisation, logging, dialogs."""

import os

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from . import strings

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_PATH = ADDON.getAddonInfo("path")
ADDON_NAME = ADDON.getAddonInfo("name")
ADDON_ICON = ADDON.getAddonInfo("icon")
# Home Assistant words its option lists per language, and Kodi's is the one
# the rest of this addon speaks.
LANGUAGE = xbmc.getLanguage(xbmc.ISO_639_1) or "en"
# The icons in full, for where a skin-relative path does not resolve: a
# dialog of Kodi's own draws from no skin of ours.
ICON_DIR = os.path.join(ADDON_PATH, "resources", "skins", "Default", "media",
                        "icons")


def tr(key):
    """Localised text for a string name from :mod:`strings`.

    Falls back to the name itself, which says which string is missing from the
    language file rather than leaving a blank on screen.
    """
    string_id = strings.IDS.get(key)
    if string_id is None:
        return key
    return ADDON.getLocalizedString(string_id) or key


def log(message, level=xbmc.LOGDEBUG):
    xbmc.log("[%s] %s" % (ADDON_ID, message), level)


def notify(message, error=False, time=4000):
    icon = xbmcgui.NOTIFICATION_ERROR if error else xbmcgui.NOTIFICATION_INFO
    xbmcgui.Dialog().notification(ADDON_NAME, message, icon, time)


# The two values of the auth_method setting.
AUTH_PASSWORD = 0
AUTH_TOKEN = 1
# Raised whenever migrate_settings learns something new to bring forward.
_SETTINGS_VERSION = 1


def migrate_settings(addon=None):
    """Bring settings from an older version forward, once.

    Before there was a choice of sign-in method, a token on its own was the
    way in. Such a setup would meet the new default and find no user name, so
    the choice is set to the token it has been using all along.
    """
    addon = addon or xbmcaddon.Addon()
    if addon.getSettingInt("settings_version") >= _SETTINGS_VERSION:
        return
    if (addon.getSettingString("token").strip()
            and not (addon.getSettingString("username")
                     and addon.getSettingString("password"))):
        addon.setSettingInt("auth_method", AUTH_TOKEN)
    addon.setSettingInt("settings_version", _SETTINGS_VERSION)


class Settings:
    """Snapshot of the addon settings."""

    def __init__(self):
        addon = xbmcaddon.Addon()
        migrate_settings(addon)
        self.url = addon.getSettingString("url").strip().rstrip("/")
        self.uses_token = uses_token = addon.getSettingInt("auth_method") == AUTH_TOKEN
        self.token = addon.getSettingString("token").strip() if uses_token else ""
        self.username = "" if uses_token else addon.getSettingString("username")
        self.password = "" if uses_token else addon.getSettingString("password")
        self.verify_ssl = addon.getSettingBool("verify_ssl")
        self.favourites = addon.getSettingBool("show_favourites")
        self.summaries = addon.getSettingBool("show_summaries")
        self.areas = addon.getSettingBool("show_areas")
        self.hide_empty_areas = addon.getSettingBool("hide_empty_areas")
        self.camera_refresh = addon.getSettingInt("camera_refresh")
        self.confirm_off = addon.getSettingBool("confirm_off")
        self.confirm_off_lights = addon.getSettingBool("confirm_off_lights")
        self.confirm_open = addon.getSettingBool("confirm_open")

    def validate(self):
        """Returns an error message, or an empty string when usable."""
        if not self.url:
            return tr("error_no_url")
        if self.uses_token and not self.token:
            return tr("error_no_token")
        if not self.uses_token and not (self.username and self.password):
            return tr("error_no_credentials")
        return ""


def prompt_login_field(field, step_id, errors):
    """Asks for one field of a Home Assistant login step.

    Used for anything the addon has no setting for, such as an MFA code.
    Returns None when the user cancels.
    """
    name = field.get("name", "")
    heading = "%s - %s" % (tr("login_prompt"), name)
    if errors:
        heading = "%s (%s)" % (heading, ", ".join(errors.values()))
    hidden = name in ("password", "code")
    value = xbmcgui.Dialog().input(heading, type=xbmcgui.INPUT_ALPHANUM,
                                   option=xbmcgui.ALPHANUM_HIDE_INPUT if hidden else 0)
    return value or None


def temp_directory():
    """A writable place for camera stills and drawn images, created on first use."""
    path = xbmcvfs.translatePath("special://temp/%s/" % ADDON_ID)
    if not xbmcvfs.exists(path):
        xbmcvfs.mkdirs(path)
    return path


def image_url(base_url, path, brands_token=""):
    """A Home Assistant image URL Kodi can fetch as it is.

    Home Assistant's picture addresses carry a token of their own where they
    need one - all but its brand images, which want the token it hands out
    for them. None of them wants the addon's own sign-in.
    """
    if not path:
        return ""
    url = path if path.startswith("http") else base_url.rstrip("/") + path
    if brands_token and "/api/brands/" in url:
        url += ("&" if "?" in url else "?") + "token=" + brands_token
    return url
