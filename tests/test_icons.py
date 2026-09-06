"""Which icon an entity gets, and in which order the three sources win."""

import unittest

from . import support
from resources.lib import icons


def one(entity_id, value, device_class=None, translation_key=None,
        platform="demo", icon_resources=None, **attributes):
    return support.build(
        entities=[support.entity(entity_id, device_class=device_class,
                                 platform=platform,
                                 translation_key=translation_key)],
        states=[support.state(entity_id, value, **attributes)],
        icons=icon_resources)


class Precedence(unittest.TestCase):
    REOLINK = {"reolink": {"light": {"floodlight": {"default": "mdi:spotlight-beam"}}}}

    def test_the_entity_decides_first(self):
        store = one("light.a", "on", icon="mdi:candle",
                    platform="reolink", translation_key="floodlight",
                    icon_resources=self.REOLINK)
        self.assertEqual(icons.icon_for(store, "light.a"), "candle")

    def test_then_what_the_integration_declares(self):
        store = one("light.a", "on", platform="reolink",
                    translation_key="floodlight", icon_resources=self.REOLINK)
        self.assertEqual(icons.icon_for(store, "light.a"), "spotlight-beam")

    def test_and_only_then_the_rule_by_domain(self):
        store = one("light.a", "on")
        self.assertEqual(icons.icon_for(store, "light.a"), "lightbulb")

    def test_an_integration_may_switch_on_state(self):
        resources = {"demo": {"binary_sensor": {"door": {
            "default": "mdi:door-closed", "state": {"on": "mdi:door-open"}}}}}
        for value, expected in (("on", "door-open"), ("off", "door-closed")):
            store = one("binary_sensor.a", value, translation_key="door",
                        icon_resources=resources)
            self.assertEqual(icons.icon_for(store, "binary_sensor.a"), expected)


class ByState(unittest.TestCase):
    def test_a_door_looks_open_when_it_is(self):
        self.assertEqual(icons.icon_for(one("binary_sensor.a", "on", "door"),
                                        "binary_sensor.a"), "door-open")
        self.assertEqual(icons.icon_for(one("binary_sensor.a", "off", "door"),
                                        "binary_sensor.a"), "door-closed")

    def test_someone_away_gets_the_other_person_icon(self):
        self.assertEqual(icons.icon_for(one("person.a", "home"), "person.a"),
                         "account")
        self.assertEqual(icons.icon_for(one("person.a", "not_home"), "person.a"),
                         "account-arrow-right")


class Batteries(unittest.TestCase):
    def icon(self, value, **attributes):
        return icons.icon_for(one("sensor.a", value, "battery", **attributes),
                              "sensor.a")

    def test_the_ladder_rounds_to_ten_percent_steps(self):
        self.assertEqual(self.icon("100"), "battery")
        self.assertEqual(self.icon("96"), "battery")
        self.assertEqual(self.icon("94"), "battery-90")
        self.assertEqual(self.icon("85"), "battery-80")
        self.assertEqual(self.icon("32"), "battery-30")
        self.assertEqual(self.icon("6"), "battery-10")

    def test_an_empty_one_calls_for_attention(self):
        self.assertEqual(self.icon("5"), "battery-alert-variant-outline")
        self.assertEqual(self.icon("0"), "battery-alert-variant-outline")

    def test_charging_has_its_own_ladder(self):
        self.assertEqual(self.icon("60", is_charging=True), "battery-charging-60")
        self.assertEqual(self.icon("4", is_charging=True),
                         "battery-charging-outline")

    def test_a_reading_that_is_no_number_says_so(self):
        self.assertEqual(self.icon("unavailable"), "battery-unknown")


class Coverage(unittest.TestCase):
    def test_every_icon_the_rules_can_name_is_shipped(self):
        import os
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "tools", "icons.txt"), encoding="utf-8") as handle:
            listed = {line.strip() for line in handle
                      if line.strip() and not line.startswith("#")}
        self.assertEqual(icons.names_in_use() - listed, set())


if __name__ == "__main__":
    unittest.main()
