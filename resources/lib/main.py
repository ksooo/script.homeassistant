"""Entry points: the dashboard window and the buttons in the settings."""

import os

import xbmc
import xbmcaddon
import xbmcgui

from . import direct, kodi
from .ha import auth as ha_auth
from .ha import client as ha_client
from .window import Dashboard

_WINDOW_XML = "script.homeassistant-dashboard.xml"

# How often the window applies what the background session left for it.
_PUMP_INTERVAL = 0.1

_CAMERA_ICON = os.path.join(kodi.ADDON_PATH, "resources", "skins", "Default", "media",
                            "icons", "video.png")


def run(argv):
    if "action=test" in argv[1:]:
        test_connection()
    elif "action=direct" in argv[1:]:
        edit_direct_addresses()
    else:
        show_dashboard()


def show_dashboard():
    settings = kodi.Settings()
    error = settings.validate()
    if error:
        kodi.notify(error, error=True)
        xbmcaddon.Addon().openSettings()
        return

    # Shown rather than run modally: doModal() blocks, and the live updates
    # need a thread of their own to be applied on - the window's, not the
    # session's.
    window = Dashboard(_WINDOW_XML, kodi.ADDON_PATH, "Default", "1080i",
                       settings=settings)
    monitor = xbmc.Monitor()
    try:
        window.show()
        while not window.closed:
            window.pump()
            if monitor.waitForAbort(_PUMP_INTERVAL):
                break
    finally:
        window.close()
        window.shutdown()
        del window


def _client(settings):
    authenticator = ha_auth.Authenticator(
        settings.url, token=settings.token, username=settings.username,
        password=settings.password, prompt=kodi.prompt_login_field,
        verify_ssl=settings.verify_ssl)
    return ha_client.HomeAssistant(settings.url, authenticator,
                                   verify_ssl=settings.verify_ssl, log=kodi.log)


def test_connection():
    settings = kodi.Settings()
    error = settings.validate()
    if error:
        kodi.notify(error, error=True)
        return

    client = _client(settings)
    try:
        client.connect()
        kodi.log("connection test succeeded via %s" % client.transport, 1)
        kodi.notify("%s\n%s" % (kodi.tr("test_ok") % client.version,
                                client.transport))
    except ha_auth.AbortedError:
        pass
    except Exception as failure:
        kodi.log("connection test failed: %s" % failure, 3)
        kodi.notify(kodi.tr("test_failed") % failure, error=True)
    finally:
        client.close()


def edit_direct_addresses():
    """Let a camera's own address be entered for each camera Home Assistant has.

    An address emptied and confirmed asks before it is removed: Kodi's input
    dialog answers a cancel with an empty text too.
    """
    settings = kodi.Settings()
    error = settings.validate()
    if error:
        kodi.notify(error, error=True)
        return

    client = _client(settings)
    try:
        client.connect()
        cameras = direct.cameras(client.command("get_states"),
                                 client.command("config/entity_registry/list"),
                                 client.command("config/device_registry/list"))
    except ha_auth.AbortedError:
        return
    except Exception as failure:
        kodi.notify(kodi.tr("test_failed") % failure, error=True)
        return
    finally:
        client.close()
    if not cameras:
        kodi.notify(kodi.tr("direct_no_cameras"))
        return

    directory = kodi.profile_directory()
    addresses = direct.load(directory)
    dialog = xbmcgui.Dialog()
    monitor = xbmc.Monitor()
    chosen = 0
    while not monitor.abortRequested():
        items = [xbmcgui.ListItem(name, direct.masked(addresses[entity_id])
                                  if entity_id in addresses else kodi.tr("direct_none"))
                 for name, entity_id in cameras]
        for item in items:
            item.setArt({"icon": _CAMERA_ICON})
        chosen = dialog.select(kodi.tr("direct_title"), items, useDetails=True,
                               preselect=chosen)
        if chosen < 0:
            return
        name, entity_id = cameras[chosen]
        entered = dialog.input(kodi.tr("direct_heading") % name,
                               defaultt=addresses.get(entity_id, "")).strip()
        if entered:
            if direct.endpoint(entered) is None:
                kodi.notify(kodi.tr("direct_invalid"), error=True)
                continue
            addresses[entity_id] = entered
        elif entity_id in addresses and dialog.yesno(
                kodi.tr("direct_title"), kodi.tr("direct_remove") % name):
            del addresses[entity_id]
        else:
            continue
        direct.save(directory, addresses)
