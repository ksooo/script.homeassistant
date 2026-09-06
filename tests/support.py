"""Fixtures for the Kodi-free modules.

A Store is a plain container, so the tests fill it directly rather than
talking to Home Assistant.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resources.lib import model  # noqa: E402  (path set up above)


def entity(entity_id, name="", area_id=None, device_id=None, device_class=None,
           platform="demo", translation_key=None, category=None, hidden=False):
    return {
        "entity_id": entity_id,
        "original_name": name,
        "area_id": area_id,
        "device_id": device_id,
        "original_device_class": device_class,
        "entity_category": category,
        "hidden_by": "user" if hidden else None,
        "disabled_by": None,
        "platform": platform,
        "translation_key": translation_key,
    }


def untranslated(name):
    """A translator for the tests: a string stands in for its own text.

    Asserting on the name keeps a test about which string was chosen, not
    about how it happens to be worded in the language file.
    """
    return name


def state(entity_id, value, **attributes):
    return {"entity_id": entity_id, "state": value, "attributes": attributes}


def build(entities=(), states=(), devices=(), areas=(), floors=(),
          home=None, icons=None, energy=None):
    store = model.Store()
    store.entities = {e["entity_id"]: model.Entity(e) for e in entities}
    store.states = {s["entity_id"]: model.State(s) for s in states}
    store.devices = {d["id"]: d for d in devices}
    store.areas = {a["area_id"]: a for a in areas}
    store.floors = {f["floor_id"]: f for f in floors}
    store.home = home or {}
    store.icon_translations = icons or {}
    store.energy = energy or {}
    return store


# A small house: two floors, three rooms, registry order deliberately not
# alphabetical so that ordering bugs show up.
FLOORS = [
    {"floor_id": "keller", "name": "Keller", "level": -1},
    {"floor_id": "eg", "name": "Erdgeschoss", "level": 0},
]

AREAS = [
    {"area_id": "vorraum", "name": "Kellervorraum", "floor_id": "keller"},
    {"area_id": "flur_ug", "name": "Flur UG", "floor_id": "keller"},
    {"area_id": "kueche", "name": "Küche", "floor_id": "eg",
     "temperature_entity_id": "sensor.kueche_temperatur"},
    {"area_id": "mobil", "name": "Mobile Geräte", "floor_id": None},
]

DEVICES = [
    {"id": "dev_lamp", "name": "Deckenlampe", "area_id": "vorraum"},
    {"id": "dev_sensor", "name": "Fenstersensor", "area_id": "kueche"},
]
