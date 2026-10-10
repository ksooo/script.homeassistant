"""What the details dialog lists, worded as Home Assistant words it."""

import unittest

from . import support  # noqa: F401  (puts the addon on the path)
from resources.lib import details, formatting

NOW = 1791009600.0  # 2026-10-03 06:40:00 UTC


def tr(name):
    return {"ago_minute": "1 minute ago", "ago_minutes": "%d minutes ago",
            "ago_seconds": "%d seconds ago", "ago_hours": "%d hours ago",
            "unknown": "Unknown", "attribute_friendly_name": "Friendly name"}.get(name, name)


def stamp(iso):
    return "<%s>" % iso


def light(**attributes):
    store = support.build(
        entities=[support.entity("light.a", "Lampe", device_id="dev")],
        states=[dict(support.state("light.a", "on", **attributes),
                     last_changed="2026-10-03T06:35:00+00:00",
                     last_updated="2026-10-03T06:39:00+00:00")],
        devices=[{"id": "dev", "name": "Deckenlampe"}])
    store.translations = {
        "component.light.entity_component._.state_attributes.color_mode.name": "Farbmodus",
        "component.light.entity_component._.state_attributes.color_mode.state.onoff": "Ein/Aus",
        "component.light.entity_component._.state_attributes.effect.state.rainbow": "Regenbogen",
    }
    return store


def value(store, attribute, entity_id="light.a"):
    state = store.states[entity_id]
    return details.attribute_value(store, entity_id, attribute,
                                   state.attributes[attribute], tr, stamp)


class Groups(unittest.TestCase):
    def test_the_entity_then_its_attributes_by_name(self):
        store = light(friendly_name="Lampe", color_mode="onoff")
        entity, attributes = details.groups(store, "light.a", tr, stamp)
        self.assertEqual(entity[1], [
            ("details_id", "light.a"),
            ("details_changed", "<2026-10-03T06:35:00+00:00>"),
            ("details_updated", "<2026-10-03T06:39:00+00:00>")])
        self.assertEqual(attributes[1], [("Farbmodus", "Ein/Aus"),
                                         ("Friendly name", "Lampe")])

    def test_no_attributes_says_so(self):
        store = light()
        self.assertEqual(details.groups(store, "light.a", tr, stamp)[1][1],
                         [("details_none", "")])


class Names(unittest.TestCase):
    def test_an_untranslated_name_is_made_readable(self):
        store = light()
        self.assertEqual(details.attribute_name(store, "light.a", "min_color_temp_kelvin", tr),
                         "Min color temp kelvin")
        self.assertEqual(details.attribute_name(store, "light.a", "device_ip", tr),
                         "Device IP")


class Values(unittest.TestCase):
    def test_numbers_get_the_units_and_scale_home_assistant_gives_them(self):
        store = light(brightness=204, color_temp_kelvin=2700, min_temp=7.5)
        self.assertEqual(value(store, "brightness"), "80 %")
        self.assertEqual(value(store, "color_temp_kelvin"), "2700 K")
        self.assertEqual(value(store, "min_temp"), "7.5 °C")

    def test_an_option_list_is_worded_through_its_value_attribute(self):
        store = light(effect_list=["rainbow", "colorloop"],
                      supported_color_modes=["onoff"])
        self.assertEqual(value(store, "effect_list"), "Regenbogen, colorloop")
        self.assertEqual(value(store, "supported_color_modes"), "Ein/Aus")

    def test_nothing_is_unknown_and_a_flag_reads_as_home_assistant_writes_it(self):
        store = light(color_mode=None, assumed=True)
        self.assertEqual(value(store, "color_mode"), "Unknown")
        self.assertEqual(value(store, "assumed"), "true")

    def test_a_time_and_a_structure(self):
        store = light(next_run="2026-10-04T05:00:00+00:00", segments=[{"id": 1}])
        self.assertEqual(value(store, "next_run"), "<2026-10-04T05:00:00+00:00>")
        self.assertEqual(value(store, "segments"), '[{"id": 1}]')


class RelativeTime(unittest.TestCase):
    def test_each_unit_holds_until_the_next_takes_over(self):
        self.assertEqual(formatting.relative_time("2026-10-03T06:39:30+00:00", NOW, tr),
                         "30 seconds ago")
        self.assertEqual(formatting.relative_time("2026-10-03T06:39:10+00:00", NOW, tr),
                         "1 minute ago")
        self.assertEqual(formatting.relative_time("2026-10-03T06:35:00+00:00", NOW, tr),
                         "5 minutes ago")
        self.assertEqual(formatting.relative_time("2026-10-03T03:40:00+00:00", NOW, tr),
                         "3 hours ago")

    def test_a_time_that_cannot_be_read_says_nothing(self):
        self.assertEqual(formatting.relative_time("", NOW, tr), "")
