"""The registry cache: what belongs where, and what stays hidden."""

import unittest

from . import support
from resources.lib import model


class Lookups(unittest.TestCase):
    def setUp(self):
        self.store = support.build(
            entities=[support.entity("light.a", "Decke", device_id="dev_lamp"),
                      support.entity("sensor.b", "Wert", area_id="kueche",
                                     device_id="dev_lamp"),
                      support.entity("sensor.c", "Frei")],
            states=[support.state("light.a", "on"), support.state("sensor.b", "1"),
                    support.state("sensor.c", "2")],
            devices=support.DEVICES, areas=support.AREAS, floors=support.FLOORS)

    def test_a_room_comes_from_the_device_when_the_entity_names_none(self):
        self.assertEqual(self.store.area_of("light.a"), "vorraum")

    def test_the_entity_wins_over_its_device(self):
        self.assertEqual(self.store.area_of("sensor.b"), "kueche")

    def test_an_entity_may_belong_nowhere(self):
        self.assertIsNone(self.store.area_of("sensor.c"))

    def test_the_floor_is_found_through_the_room(self):
        self.assertEqual(self.store.floor_of("kueche"), "eg")

    def test_rooms_are_listed_in_registry_order(self):
        self.assertEqual([a["name"] for a in self.store.areas_on_floor("keller")],
                         ["Kellervorraum", "Flur UG"])
        self.assertEqual([a["name"] for a in self.store.areas_without_floor()],
                         ["Mobile Geräte"])

    def test_floors_keep_registry_order_too(self):
        self.assertEqual([f["name"] for f in self.store.sorted_floors()],
                         ["Keller", "Erdgeschoss"])


class Visibility(unittest.TestCase):
    def store(self, **kwargs):
        return support.build(entities=[support.entity("sensor.a", **kwargs)],
                             states=[support.state("sensor.a", "1")])

    def test_hidden_entities_stay_out(self):
        self.assertFalse(self.store(hidden=True).is_visible("sensor.a"))

    def test_so_do_config_and_diagnostic_ones(self):
        for category in ("config", "diagnostic"):
            self.assertFalse(self.store(category=category).is_visible("sensor.a"))

    def test_maintenance_may_ask_for_diagnostics(self):
        store = self.store(category="diagnostic")
        self.assertTrue(store.is_visible("sensor.a", include_diagnostic=True))

    def test_but_never_for_hidden_ones(self):
        store = self.store(category="diagnostic", hidden=True)
        self.assertFalse(store.is_visible("sensor.a", include_diagnostic=True))

    def test_an_entity_without_a_registry_entry_still_counts(self):
        store = support.build(states=[support.state("sensor.template", "1")])
        self.assertTrue(store.is_visible("sensor.template"))


class DisplayNames(unittest.TestCase):
    """Home Assistant puts the device in front where nothing else names it."""

    def store(self, registry_name, friendly_name):
        return support.build(
            entities=[support.entity("sensor.a", registry_name, device_id="dev_lamp")],
            states=[support.state("sensor.a", "1", friendly_name=friendly_name)],
            devices=support.DEVICES)

    def test_under_a_device_heading_the_short_name_belongs_there(self):
        store = self.store("Realtime Gas Flow", "gasleser Realtime Gas Flow")
        self.assertEqual(store.name_of("sensor.a"), "Realtime Gas Flow")

    def test_elsewhere_the_composed_name_is_shown(self):
        store = self.store("Realtime Gas Flow", "gasleser Realtime Gas Flow")
        self.assertEqual(store.display_name_of("sensor.a"),
                         "gasleser Realtime Gas Flow")

    def test_a_name_the_user_set_is_not_composed_by_home_assistant(self):
        # Home Assistant has already made that call; both forms agree.
        store = self.store("Tür Geschirrspüler", "Tür Geschirrspüler")
        self.assertEqual(store.display_name_of("sensor.a"), "Tür Geschirrspüler")
        self.assertEqual(store.name_of("sensor.a"), "Tür Geschirrspüler")

    def test_without_a_state_name_the_short_one_stands_in(self):
        store = support.build(
            entities=[support.entity("sensor.a", "Wert")],
            states=[support.state("sensor.a", "1")])
        self.assertEqual(store.display_name_of("sensor.a"), "Wert")


class Names(unittest.TestCase):
    def test_a_state_change_replaces_what_the_cache_holds(self):
        store = support.build(entities=[support.entity("light.a", "Decke")],
                              states=[support.state("light.a", "off")])
        store._on_state_changed({"data": {
            "entity_id": "light.a",
            "new_state": support.state("light.a", "on", brightness=10)}})
        self.assertEqual(store.states["light.a"].state, "on")
        self.assertEqual(store.states["light.a"].attributes["brightness"], 10)

    def test_a_removed_entity_leaves_the_cache(self):
        store = support.build(entities=[support.entity("light.a", "Decke")],
                              states=[support.state("light.a", "off")])
        store._on_state_changed({"data": {"entity_id": "light.a", "new_state": None}})
        self.assertNotIn("light.a", store.states)

    def test_an_integration_icon_is_looked_up_by_platform_and_key(self):
        store = support.build(
            entities=[support.entity("light.a", platform="reolink",
                                     translation_key="floodlight")],
            states=[support.state("light.a", "on")],
            icons={"reolink": {"light": {"floodlight": {
                "default": "mdi:spotlight-beam"}}}})
        self.assertEqual(store.icon_translation("light.a", "on"), "mdi:spotlight-beam")
        self.assertEqual(store.icon_translation("light.unknown", "on"), "")


if __name__ == "__main__":
    unittest.main()
