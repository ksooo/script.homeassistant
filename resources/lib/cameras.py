"""Camera stills for the row list.

Kodi caches every image it loads by URL, which a picture that changes every
few seconds would fill the texture database with. The still is therefore
written to a local file instead - alternating between two names per camera,
because Kodi holds on to a file it has already read under the same path.
The files are kept, so that a row has the last still at once, even after a
restart, until a fresh one arrives.
"""

import hashlib
import os
import ssl
import threading
import urllib.error
import urllib.request

_TIMEOUT = 15
# The size a still is asked for, which Home Assistant scales the camera's
# picture down to as its frontend has it do for a preview: twice the row's
# 72 pixels high at 16:9, so it stays sharp on a 4K screen.
_STILL_SIZE = (256, 144)
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
        # The slot each camera's newest still is in, None for none yet.
        self._slots = {}
        self._lock = threading.Lock()

    def fetch(self, entity_id, picture):
        """Returns the path of a freshly written still, or an empty string.

        The picture is the camera's own entity_picture, whose token Home
        Assistant renews by itself, as its own frontend uses it - so the still
        does not depend on how the addon signed in, or for how long.
        """
        separator = "&" if "?" in picture else "?"
        url = "%s%s%swidth=%d&height=%d" % (self._base_url, picture, separator,
                                            *_STILL_SIZE)
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
        return self.keep(entity_id, data)

    def keep(self, entity_id, data):
        """Write a still into the camera's other slot, and make it the
        newest only once it is written whole."""
        with self._lock:
            slot = 1 if self._newest(entity_id) == 0 else 0
        path = self._path(entity_id, slot)
        try:
            with open(path, "wb") as handle:
                handle.write(data)
        except OSError as error:
            self._log("cannot write camera still: %s" % error, 3)
            return ""
        with self._lock:
            self._slots[entity_id] = slot
        return path

    def latest(self, entity_id):
        """The camera's newest still, from this run or an earlier one, or an
        empty string."""
        with self._lock:
            slot = self._newest(entity_id)
        return "" if slot is None else self._path(entity_id, slot)

    def _newest(self, entity_id):
        # A camera not seen yet in this run starts from what is on disk.
        if entity_id not in self._slots:
            ages = []
            for slot in (0, 1):
                try:
                    ages.append((os.path.getmtime(self._path(entity_id, slot)), slot))
                except OSError:
                    pass
            self._slots[entity_id] = max(ages)[1] if ages else None
        return self._slots[entity_id]

    def _path(self, entity_id, slot):
        digest = hashlib.md5(entity_id.encode("utf-8")).hexdigest()[:12]
        return os.path.join(self._directory, "%s-%d.jpg" % (digest, slot))
