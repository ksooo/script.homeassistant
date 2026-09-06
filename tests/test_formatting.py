"""What a row says and which colour it says it in."""

import unittest

from . import support
from resources.lib import formatting


def one(entity_id, value, device_class=None, **attributes):
    return support.build(
        entities=[support.entity(entity_id, device_class=device_class)],
        states=[support.state(entity_id, value, **attributes)])


class StateText(unittest.TestCase):
    def text(self, *args, **kwargs):
        entity_id = args[0]
        return formatting.state_text(one(*args, **kwargs), entity_id,
                                     support.untranslated)

    def test_binary_sensors_speak_in_their_device_class(self):
        self.assertEqual(self.text("binary_sensor.a", "on", "window"), "open")
        self.assertEqual(self.text("binary_sensor.a", "off", "window"), "closed")
        self.assertEqual(self.text("binary_sensor.a", "on", "motion"), "detected")
        self.assertEqual(self.text("binary_sensor.a", "on", "lock"), "unlocked")

    def test_a_lit_lamp_reports_its_brightness(self):
        self.assertEqual(self.text("light.a", "on", brightness=128), "on  50 %")
        self.assertEqual(self.text("light.a", "on"), "on")

    def test_measurements_carry_their_unit(self):
        self.assertEqual(self.text("sensor.a", "21.50", unit_of_measurement="°C"),
                         "21.5 °C")
        self.assertEqual(self.text("sensor.a", "0.000000",
                                   unit_of_measurement="m³/h"), "0 m³/h")

    def test_unavailable_is_said_once_for_everything(self):
        for value in ("unavailable", "unknown"):
            self.assertEqual(self.text("sensor.a", value), "unavailable")

    def test_states_without_a_word_are_still_readable(self):
        self.assertEqual(self.text("sun.sun", "below_horizon"), "Below horizon")
        self.assertEqual(self.text("media_player.a", "off"), "off")


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


if __name__ == "__main__":
    unittest.main()
