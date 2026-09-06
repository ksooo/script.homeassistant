"""How the dashboard is cut into sections and groups."""

import unittest

from . import support
from resources.lib import sections


def house(extra_entities=(), extra_states=(), home=None, energy=None):
    entities = [
        support.entity("light.decke", "Deckenlampe", device_id="dev_lamp"),
        support.entity("binary_sensor.fenster", "Fenster", device_id="dev_sensor",
                       device_class="window"),
        support.entity("sensor.kueche_temperatur", "Temperatur", area_id="kueche",
                       device_class="temperature"),
        support.entity("sensor.cpu", "CPU Temperatur", area_id="kueche",
                       device_class="temperature"),
        support.entity("sensor.batterie", "Batterie", device_id="dev_sensor",
                       device_class="battery", category="diagnostic"),
        support.entity("lock.tuer", "Schloss", area_id="flur_ug"),
    ]
    states = [
        support.state("light.decke", "off"),
        support.state("binary_sensor.fenster", "on"),
        support.state("sensor.kueche_temperatur", "21.5"),
        support.state("sensor.cpu", "48"),
        support.state("sensor.batterie", "94"),
        support.state("lock.tuer", "locked"),
    ]
    return support.build(
        entities=list(entities) + list(extra_entities),
        states=list(states) + list(extra_states),
        devices=support.DEVICES, areas=support.AREAS, floors=support.FLOORS,
        home=home, energy=energy)


class AreaSections(unittest.TestCase):
    def test_groups_by_device_and_collects_the_rest(self):
        store = house()
        built = {s.key: s for s in sections.build(store, translate=support.untranslated)}
        kitchen = built["area:kueche"]

        self.assertEqual([g.title for g in kitchen.groups],
                         ["Fenstersensor", "no_device"])
        # The battery is diagnostic, so it belongs to maintenance, not here.
        self.assertEqual(kitchen.groups[0].entity_ids, ["binary_sensor.fenster"])
        self.assertEqual(sorted(kitchen.groups[1].entity_ids),
                         ["sensor.cpu", "sensor.kueche_temperatur"])

    def test_floors_and_rooms_keep_registry_order(self):
        store = house()
        options = sections.Options(hide_empty_areas=False)
        areas = [s for s in sections.build(store, options, translate=support.untranslated)
                 if s.kind == sections.AREA]
        self.assertEqual([(s.subtitle, s.title) for s in areas],
                         [("Keller", "Kellervorraum"), ("Keller", "Flur UG"),
                          ("Erdgeschoss", "Küche"), ("", "Mobile Geräte")])

    def test_empty_rooms_can_be_hidden(self):
        store = house()
        options = sections.Options(hide_empty_areas=True)
        titles = [s.title for s in sections.build(store, options, translate=support.untranslated)]
        self.assertNotIn("Mobile Geräte", titles)


class Summaries(unittest.TestCase):
    def summary(self, key, **kwargs):
        home = {"shortcuts": [{"type": "summary", "key": key}]}
        store = house(home=home, **kwargs)
        return next(s for s in sections.build(store, translate=support.untranslated) if s.key == key)

    def test_room_headings_carry_the_floor(self):
        security = self.summary("security")
        self.assertEqual([g.title for g in security.groups],
                         ["Keller  -  Flur UG", "Erdgeschoss  -  Küche"])

    def test_climate_takes_the_rooms_own_sensors_only(self):
        climate = self.summary("climate")
        # sensor.cpu is a temperature too, but no room is measured by it.
        self.assertEqual(climate.entity_ids, ["sensor.kueche_temperatur"])

    def test_maintenance_lists_batteries_at_any_level(self):
        maintenance = self.summary("maintenance")
        self.assertEqual(maintenance.entity_ids, ["sensor.batterie"])

    def test_media_players_are_a_summary_of_their_own(self):
        players = self.summary(
            "media_players",
            extra_entities=[support.entity("media_player.tv", "Fernseher",
                                           area_id="kueche")],
            extra_states=[support.state("media_player.tv", "playing")])
        self.assertEqual(players.entity_ids, ["media_player.tv"])
        self.assertEqual(players.title, "media_players")

    def test_a_shortcut_that_is_not_a_summary_is_passed_over(self):
        store = house(home={"shortcuts": [{"type": "entity",
                                           "entity_id": "light.decke"}]})
        self.assertEqual([s.key for s in sections.build(store, translate=support.untranslated)
                          if s.kind == sections.SUMMARY], [])

    def test_a_configured_summary_survives_being_empty(self):
        self.assertEqual(self.summary("weather").entity_ids, [])

    def test_hidden_shortcuts_are_skipped(self):
        store = house(home={"shortcuts": [
            {"type": "summary", "key": "light", "hidden": True}]})
        self.assertEqual([s.key for s in sections.build(store, translate=support.untranslated)
                          if s.kind == sections.SUMMARY], [])


class Favourites(unittest.TestCase):
    def test_order_is_left_as_home_assistant_holds_it(self):
        order = ["lock.tuer", "light.decke", "binary_sensor.fenster"]
        store = house(home={"favorite_entities": order})
        favourites = next(s for s in sections.build(store, translate=support.untranslated)
                          if s.kind == sections.FAVOURITES)
        self.assertEqual(favourites.entity_ids, order)
        self.assertEqual([g.title for g in favourites.groups], [""])

    def test_entities_that_are_gone_drop_out(self):
        store = house(home={"favorite_entities": ["light.decke", "light.weg"]})
        favourites = next(s for s in sections.build(store, translate=support.untranslated)
                          if s.kind == sections.FAVOURITES)
        self.assertEqual(favourites.entity_ids, ["light.decke"])


if __name__ == "__main__":
    unittest.main()
