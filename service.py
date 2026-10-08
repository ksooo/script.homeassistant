"""Runs whenever Kodi signs a profile in, and after the addon is updated.

It only brings settings from an older version forward, so they read right
before anyone opens them, and then ends.
"""

from resources.lib import kodi

kodi.migrate_settings()
