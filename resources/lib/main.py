"""Entry points: the dashboard window and the settings connection test."""

import xbmc
import xbmcaddon

from . import kodi
from .ha import auth as ha_auth
from .ha import client as ha_client
from .window import Dashboard

_WINDOW_XML = "script.homeassistant-dashboard.xml"

# How often the window applies what the background session left for it.
_PUMP_INTERVAL = 0.1


def run(argv):
    if "action=test" in argv[1:]:
        test_connection()
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
    window = Dashboard(_WINDOW_XML, kodi.ADDON_PATH, "Default", "720p",
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


def test_connection():
    settings = kodi.Settings()
    error = settings.validate()
    if error:
        kodi.notify(error, error=True)
        return

    authenticator = ha_auth.Authenticator(
        settings.url, token=settings.token, username=settings.username,
        password=settings.password, prompt=kodi.prompt_login_field,
        verify_ssl=settings.verify_ssl)
    client = ha_client.HomeAssistant(settings.url, authenticator,
                                     verify_ssl=settings.verify_ssl, log=kodi.log)
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
