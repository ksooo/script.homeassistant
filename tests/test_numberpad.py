"""Typing into the number dialog, checked without Kodi."""

import unittest

from . import support  # noqa: F401  (puts the addon on the path)
from resources.lib import numberpad


class Typing(unittest.TestCase):
    def test_the_first_digit_replaces_the_value_it_opened_with(self):
        entry = numberpad.Entry(30, 1, 120)
        self.assertEqual(entry.shown(), "30")
        entry.digit(4)
        entry.digit(5)
        self.assertEqual(entry.value(), 45)

    def test_a_fraction_is_typed_with_the_languages_separator(self):
        entry = numberpad.Entry(21, 7, 35, 0.5, separator=",")
        self.assertEqual(entry.shown(), "21,0")
        entry.digit(2)
        entry.point()
        entry.digit(5)
        self.assertEqual(entry.shown(), "2,5")
        self.assertEqual(entry.value(), 2.5)

    def test_no_more_places_than_the_step_has(self):
        entry = numberpad.Entry(None, 7, 35, 0.5)
        for key in (2, 1):
            entry.digit(key)
        entry.point()
        entry.digit(5)
        entry.digit(5)
        self.assertEqual(entry.value(), 21.5)

    def test_a_whole_number_takes_no_separator(self):
        entry = numberpad.Entry(None, 1, 120, 1)
        entry.digit(3)
        entry.point()
        entry.digit(0)
        self.assertEqual(entry.value(), 30)

    def test_deleting_edits_the_value_it_opened_with(self):
        entry = numberpad.Entry(120, 1, 120)
        entry.delete()
        self.assertEqual(entry.value(), 12)

    def test_a_leading_zero_gives_way(self):
        entry = numberpad.Entry(None)
        entry.digit(0)
        entry.digit(7)
        self.assertEqual(entry.shown(), "7")


class Stepping(unittest.TestCase):
    def test_a_step_moves_the_value_and_keeps_to_the_bounds(self):
        entry = numberpad.Entry(21.5, 7, 22, 0.5)
        entry.nudge(1)
        self.assertEqual(entry.value(), 22.0)
        entry.nudge(1)
        self.assertEqual(entry.value(), 22.0)

    def test_stepping_from_nothing_starts_at_the_lowest(self):
        entry = numberpad.Entry(None, 1, 120)
        entry.nudge(1)
        self.assertEqual(entry.value(), 2)


class Range(unittest.TestCase):
    def test_a_value_outside_the_bounds_is_out_of_range(self):
        entry = numberpad.Entry(None, 1, 120)
        for key in (5, 0, 0):
            entry.digit(key)
        self.assertFalse(entry.in_range())

    def test_nothing_typed_is_not_a_value(self):
        entry = numberpad.Entry(None, 1, 120)
        self.assertFalse(entry.in_range())


class Code(unittest.TestCase):
    def test_a_code_is_hidden_and_kept_as_typed(self):
        entry = numberpad.Entry(code=True)
        for key in (0, 4, 2):
            entry.digit(key)
        entry.point()
        self.assertEqual(entry.shown(), "●●●")
        self.assertEqual(entry.text, "042")
