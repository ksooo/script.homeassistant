"""What a row says and which colour it says it in."""

import unittest

from . import support
from resources.lib import formatting


# What Home Assistant answers for the states these tests use, taken from a
# real installation over frontend/get_translations.
WORDS = {
    "component.binary_sensor.entity_component.window.state.on": "Open",
    "component.binary_sensor.entity_component.window.state.off": "Closed",
    "component.binary_sensor.entity_component.motion.state.on": "Detected",
    "component.binary_sensor.entity_component.lock.state.on": "Unlocked",
    "component.light.entity_component._.state.on": "On",
    "component.light.entity_component._.state.off": "Off",
    "component.media_player.entity_component._.state.off": "Off",
    "component.sun.entity_component._.state.below_horizon": "Below horizon",
    "component.update.entity_component._.state.on": "Update available",
    "component.vacuum.entity_component._.state.cleaning": "Cleaning",
    "component.climate.entity_component._.state.heat": "Heat",
    "component.climate.entity_component._.state_attributes"
    ".hvac_action.state.heating": "Heating",
}


def one(entity_id, value, device_class=None, registry=True, **attributes):
    return support.build(
        entities=([support.entity(entity_id, device_class=device_class)]
                  if registry else []),
        states=[support.state(entity_id, value, **attributes)],
        translations=WORDS)


class StateText(unittest.TestCase):
    def text(self, *args, **kwargs):
        entity_id = args[0]
        return formatting.state_text(one(*args, **kwargs), entity_id,
                                     support.untranslated)

    def test_binary_sensors_speak_in_their_device_class(self):
        # A window sensor is open, not on: that is the device class key.
        self.assertEqual(self.text("binary_sensor.a", "on", "window"), "Open")
        self.assertEqual(self.text("binary_sensor.a", "off", "window"), "Closed")
        self.assertEqual(self.text("binary_sensor.a", "on", "motion"), "Detected")
        self.assertEqual(self.text("binary_sensor.a", "on", "lock"), "Unlocked")

    def test_a_lit_lamp_reports_its_brightness(self):
        self.assertEqual(self.text("light.a", "on", brightness=128), "On  50 %")
        self.assertEqual(self.text("light.a", "on"), "On")

    def test_measurements_carry_their_unit(self):
        self.assertEqual(self.text("sensor.a", "21.50", unit_of_measurement="°C"),
                         "21.5 °C")
        self.assertEqual(self.text("sensor.a", "0.000000",
                                   unit_of_measurement="m³/h"), "0 m³/h")

    def test_unavailable_is_the_addons_own_word(self):
        # Home Assistant has no state for it, so this one stays in strings.po.
        for value in ("unavailable", "unknown"):
            self.assertEqual(self.text("sensor.a", value), "unavailable")

    def test_a_state_home_assistant_has_no_word_for_stays_readable(self):
        self.assertEqual(self.text("vacuum.a", "returning"), "Returning")

    def test_an_entity_outside_the_registry_still_has_its_domain(self):
        # sun.sun carries no registry entry, so the domain comes from the id.
        self.assertEqual(self.text("sun.sun", "below_horizon", registry=False),
                         "Below horizon")

    def test_an_update_says_what_home_assistant_says(self):
        self.assertEqual(self.text("update.a", "on"), "Update available")

    def test_a_thermostat_shows_what_it_is_doing(self):
        # hvac_action is an attribute value, the mode a state - different keys.
        self.assertEqual(self.text("climate.a", "heat", hvac_action="heating"),
                         "Heating")
        self.assertEqual(self.text("climate.a", "heat"), "Heat")


class Colour(unittest.TestCase):
    def colour(self, *args, **kwargs):
        return formatting.colour(one(*args, **kwargs), args[0])

    def test_a_lock_is_green_shut_and_red_open(self):
        self.assertEqual(self.colour("lock.a", "locked"), formatting.GREEN)
        self.assertEqual(self.colour("lock.a", "unlocked"), formatting.RED)
        self.assertEqual(self.colour("lock.a", "jammed"), formatting.RED)

    def test_batteries_use_three_bands(self):
        self.assertEqual(self.colour("sensor.a", "100", "battery"), formatting.GREEN)
        self.assertEqual(self.colour("sensor.a", "70", "battery"), formatting.GREEN)
        self.assertEqual(self.colour("sensor.a", "69", "battery"), formatting.ORANGE)
        self.assertEqual(self.colour("sensor.a", "30", "battery"), formatting.ORANGE)
        self.assertEqual(self.colour("sensor.a", "29", "battery"), formatting.RED)

    def test_trouble_reads_red_but_an_open_window_does_not(self):
        self.assertEqual(self.colour("binary_sensor.a", "on", "problem"),
                         formatting.RED)
        self.assertEqual(self.colour("binary_sensor.a", "on", "smoke"),
                         formatting.RED)
        self.assertEqual(self.colour("binary_sensor.a", "on", "window"),
                         formatting.AMBER)

    def test_presence_is_green_at_home_and_grey_away(self):
        self.assertEqual(self.colour("person.a", "home"), formatting.GREEN)
        self.assertEqual(self.colour("person.a", "not_home"), formatting.GREY)

    def test_anything_unreachable_is_dimmed(self):
        self.assertEqual(self.colour("light.a", "unavailable"), formatting.DIM)


class OptionWords(unittest.TestCase):
    """The four key shapes, with keys and texts taken from a real install."""

    SOUND = ("component.yamaha_musiccast.entity.media_player.zone"
             ".state_attributes.sound_mode.state.action_game")
    MOP = "component.roborock.entity.select.mop_mode.state.deep"
    MOP_PLUS = "component.roborock.entity.select.mop_mode.state.deep_plus"
    HVAC = "component.climate.entity_component._.state.heat"
    LOCK = "component.lock.entity_component._.state.unlocked"

    def store(self, entity_id, platform, translation_key, translations, state="on"):
        return support.build(
            entities=[support.entity(entity_id, "Thing", platform=platform,
                                     translation_key=translation_key)],
            states=[support.state(entity_id, state)],
            translations=translations)

    def test_an_integration_words_its_own_attribute_values(self):
        store = self.store("media_player.avr", "yamaha_musiccast", "zone",
                           {self.SOUND: "Action game"})
        self.assertEqual(
            formatting.option_text(store, "media_player.avr", "sound_mode",
                                   "action_game"), "Action game")

    def test_an_option_that_is_really_a_state_is_found_too(self):
        # A select's options are its states, so they carry no attribute key.
        store = self.store("select.mop", "roborock", "mop_mode", {self.MOP: "Deep"})
        self.assertEqual(
            formatting.option_text(store, "select.mop", "option", "deep"), "Deep")

    def test_the_domain_answers_where_the_integration_does_not(self):
        store = self.store("climate.socket", "meross_lan", "mts_climate",
                           {self.HVAC: "Heat"})
        self.assertEqual(
            formatting.option_text(store, "climate.socket", "hvac_mode", "heat"),
            "Heat")

    def test_an_untranslated_value_reads_as_it_arrived(self):
        store = self.store("media_player.avr", "yamaha_musiccast", "zone", {})
        self.assertEqual(
            formatting.option_text(store, "media_player.avr", "sound_mode",
                                   "cellar_club"), "cellar_club")

    def test_a_whole_list_keeps_home_assistants_order(self):
        store = self.store("media_player.avr", "yamaha_musiccast", "zone",
                           {self.SOUND: "Action game"})
        self.assertEqual(
            formatting.option_texts(store, "media_player.avr", "sound_mode",
                                    ["munich", "action_game"]),
            ["munich", "Action game"])

    def test_a_row_takes_home_assistants_word_where_the_addon_has_none(self):
        # "deep_plus" used to read "Deep plus"; Home Assistant calls it "Deep+".
        store = self.store("select.mop", "roborock", "mop_mode",
                           {self.MOP_PLUS: "Deep+"}, state="deep_plus")
        self.assertEqual(
            formatting.state_text(store, "select.mop", support.untranslated),
            "Deep+")

    def test_a_row_says_what_home_assistant_says(self):
        # This addon kept its own lock words until they were taken out of
        # strings.po; Home Assistant's wording is the wording now.
        store = self.store("lock.door", "matter", "", {self.LOCK: "Unlocked"},
                           state="unlocked")
        self.assertEqual(
            formatting.state_text(store, "lock.door", support.untranslated),
            "Unlocked")


if __name__ == "__main__":
    unittest.main()
