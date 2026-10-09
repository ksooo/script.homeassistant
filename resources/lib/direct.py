"""Cameras' own addresses for their live pictures, kept by the addon itself.

Home Assistant does not hand out a camera's own address - it carries the
camera's credentials - so whoever wants the short delay of a direct stream
enters it once per camera. The addresses live in a small JSON file in the
addon's data, unencrypted, like the password in the settings.
"""

import json
import os
import socket
import urllib.parse

FILE_NAME = "camera_urls.json"

_PORTS = {"rtsp": 554, "rtsps": 322, "http": 80, "https": 443}

# Query parameters some cameras take their password or token in.
_SECRETS = {"password", "passwd", "pass", "pwd", "token"}


def cameras(states, entities, devices):
    """Name and entity of each camera, sorted by name.

    The device goes in front, the way Home Assistant writes a friendly name
    - an entity named on its own leaves it out, and the lenses of one camera
    model would otherwise read alike on every camera.
    """
    device_of = {entry["entity_id"]: entry.get("device_id") for entry in entities}
    device_names = {entry["id"]: entry.get("name_by_user") or entry.get("name") or ""
                    for entry in devices}
    found = []
    for state in states:
        entity_id = state["entity_id"]
        if not entity_id.startswith("camera."):
            continue
        name = state.get("attributes", {}).get("friendly_name") or entity_id
        device = device_names.get(device_of.get(entity_id), "")
        if device and not name.startswith(device):
            name = "%s %s" % (device, name)
        found.append((name, entity_id))
    return sorted(found, key=lambda camera: camera[0].lower())


def load(directory):
    """The addresses by camera entity, or none where the file is missing or bad."""
    try:
        with open(os.path.join(directory, FILE_NAME), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {entity_id: url for entity_id, url in data.items()
            if isinstance(entity_id, str) and isinstance(url, str) and url}


def save(directory, addresses):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, FILE_NAME)
    with open(path + ".new", "w", encoding="utf-8") as handle:
        json.dump(addresses, handle, indent=1, sort_keys=True)
    os.replace(path + ".new", path)


def endpoint(url):
    """Host and port a camera address points at, or None for anything else."""
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in _PORTS or not parts.hostname:
        return None
    try:
        port = parts.port
    except ValueError:
        return None
    return parts.hostname, port or _PORTS[scheme]


def reachable(url, timeout=1.5):
    """Whether the camera answers at all - away from home it does not."""
    target = endpoint(url)
    if target is None:
        return False
    try:
        with socket.create_connection(target, timeout=timeout):
            return True
    except OSError:
        return False


def masked(url):
    """The address with its password left out, for showing on screen."""
    parts = urllib.parse.urlsplit(url)
    netloc = parts.netloc
    if parts.password is not None:
        netloc = "%s:***@%s" % (parts.username or "", netloc.rpartition("@")[2])
    query = "&".join(_masked_parameter(parameter)
                     for parameter in parts.query.split("&")) if parts.query else ""
    return urllib.parse.urlunsplit(parts._replace(netloc=netloc, query=query))


def _masked_parameter(parameter):
    key, equals, _value = parameter.partition("=")
    if equals and key.lower() in _SECRETS:
        return key + "=***"
    return parameter
