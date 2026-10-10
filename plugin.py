"""Where a Kodi favourite of an entity lands.

A favourite of RunScript keeps only the script's id, so every entity would be
the same favourite. A plugin URL is kept whole; the plugin hands the entity
on to the script and plays nothing itself.
"""

import sys
import urllib.parse

import xbmc
import xbmcgui
import xbmcplugin

entity_id = dict(urllib.parse.parse_qsl(sys.argv[2].lstrip("?"))).get("entity_id", "")
if entity_id:
    xbmc.executebuiltin("RunScript(script.homeassistant,entity_id=%s)" % entity_id)
xbmcplugin.setResolvedUrl(int(sys.argv[1]), False, xbmcgui.ListItem())
