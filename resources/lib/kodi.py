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


class Settings:
    """Snapshot of the addon settings."""

    def __init__(self):
        addon = xbmcaddon.Addon()
        self.url = addon.getSettingString("url").strip().rstrip("/")
        self.username = addon.getSettingString("username")
        self.password = addon.getSettingString("password")
        self.token = addon.getSettingString("token").strip()
        self.verify_ssl = addon.getSettingBool("verify_ssl")
        self.favourites = addon.getSettingBool("show_favourites")
        self.summaries = addon.getSettingBool("show_summaries")
        self.areas = addon.getSettingBool("show_areas")
        self.hide_empty_areas = addon.getSettingBool("hide_empty_areas")
        self.camera_refresh = addon.getSettingInt("camera_refresh")

    @property
    def has_credentials(self):
        return bool(self.token) or bool(self.username and self.password)

    def validate(self):
        """Returns an error message, or an empty string when usable."""
        if not self.url:
            return tr("error_no_url")
        if not self.has_credentials:
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
    """A writable place for the camera stills, created on first use."""
    path = xbmcvfs.translatePath("special://temp/%s/" % ADDON_ID)
    if not xbmcvfs.exists(path):
        xbmcvfs.mkdirs(path)
    return path


def image_url(base_url, path, token):
    """A Home Assistant image URL Kodi can fetch, carrying the bearer token."""
    if not path:
        return ""
    if path.startswith("http"):
        url = path
    else:
        url = base_url.rstrip("/") + path
    if token and "/api/" in url:
        return "%s|Authorization=Bearer %s" % (url, token)
    return url
