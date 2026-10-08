"""Camera stills for the row list.

Kodi caches every image it loads by URL, which a picture that changes every
few seconds would fill the texture database with. The still is therefore
written to a local file instead - alternating between two names per camera,
because Kodi holds on to a file it has already read under the same path.
"""

import hashlib
import os
import ssl
import urllib.error
import urllib.request

_TIMEOUT = 15
# How long the first request for a stream may take: Home Assistant answers
# it only once the stream has its first segments.
_STREAM_TIMEOUT = 30


def stream_ready(url, verify_ssl=True):
    """Whether Home Assistant serves the stream's playlist yet.

    Kodi makes this first request itself before it plays, on the thread that
    draws and reads keys - so for as long as the stream takes to start, Kodi
    would stand still. Made here first, Kodi finds the stream running.
    """
    try:
        with urllib.request.urlopen(urllib.request.Request(url),
                                    timeout=_STREAM_TIMEOUT,
                                    context=_context(url, verify_ssl)) as response:
            response.read()
        return True
    except (urllib.error.URLError, OSError):
        return False


def _context(url, verify_ssl):
    if not url.startswith("https://") or verify_ssl:
        return None
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


class Snapshots:
    def __init__(self, base_url, directory, verify_ssl=True, log=None):
        self._base_url = base_url.rstrip("/")
        self._directory = directory
        self._verify_ssl = verify_ssl
        self._log = log or (lambda message, level=0: None)
        self._slots = {}

    def fetch(self, entity_id, picture):
        """Returns the path of a freshly written still, or an empty string.

        The picture is the camera's own entity_picture, whose token Home
        Assistant renews by itself, as its own frontend uses it - so the still
        does not depend on how the addon signed in, or for how long.
        """
        url = self._base_url + picture
        try:
            with urllib.request.urlopen(url, timeout=_TIMEOUT,
                                        context=_context(url, self._verify_ssl)) as response:
                if not response.headers.get("Content-Type", "").startswith("image/"):
                    return ""
                data = response.read()
        except (urllib.error.URLError, OSError) as error:
            self._log("camera still failed for %s: %s" % (entity_id, error))
            return ""
        if not data:
            return ""

        slot = self._slots.get(entity_id, 1) ^ 1
        self._slots[entity_id] = slot
        name = "%s-%d.jpg" % (hashlib.md5(entity_id.encode("utf-8")).hexdigest()[:12],
                              slot)
        path = os.path.join(self._directory, name)
        try:
            with open(path, "wb") as handle:
                handle.write(data)
        except OSError as error:
            self._log("cannot write camera still: %s" % error, 3)
            return ""
        return path

    def clean_up(self):
        for entity_id, slot in self._slots.items():
            digest = hashlib.md5(entity_id.encode("utf-8")).hexdigest()[:12]
            for index in (0, 1):
                try:
                    os.remove(os.path.join(self._directory,
                                           "%s-%d.jpg" % (digest, index)))
                except OSError:
                    pass
        self._slots.clear()
