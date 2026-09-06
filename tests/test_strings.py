"""The string table against the language files.

The language files are the original - Kodi reads them, and translations come
from Kodi's translation system, which a generator here would overwrite. What
these tests hold is what generating both files from one table used to
guarantee: that no id exists in one file only.
"""

import os
import re
import unittest

from . import support  # noqa: F401  (sets up the import path)
from resources.lib import strings

LANGUAGES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "resources", "language")

_ENTRY = re.compile(r'^msgctxt "#(\d+)"\nmsgid (".*")\nmsgstr (".*")$', re.M)


def entries(language):
    path = os.path.join(LANGUAGES, "resource.language.%s" % language, "strings.po")
    with open(path, encoding="utf-8") as handle:
        body = handle.read()
    found = {int(number): (msgid, msgstr)
             for number, msgid, msgstr in _ENTRY.findall(body)}
    # A string wrapped over several lines would be dropped by the pattern
    # rather than reported, which would make every test below pass wrongly.
    assert len(found) == body.count("\nmsgctxt "), language
    return found


class Names(unittest.TestCase):
    def test_every_name_has_a_string(self):
        english = entries("en_gb")
        missing = {name: number for name, number in strings.IDS.items()
                   if number not in english}
        self.assertEqual(missing, {})

    def test_no_two_names_share_an_id(self):
        self.assertEqual(len(set(strings.IDS.values())), len(strings.IDS))

    def test_ids_are_in_the_range_kodi_gives_an_addon(self):
        outside = {name: number for name, number in strings.IDS.items()
                   if not 30000 <= number <= 30999}
        self.assertEqual(outside, {})


class Languages(unittest.TestCase):
    def test_a_translation_carries_the_same_ids(self):
        self.assertEqual(set(entries("de_de")), set(entries("en_gb")))

    def test_a_translation_keeps_the_english_source(self):
        english, german = entries("en_gb"), entries("de_de")
        differing = {number for number, (msgid, _) in german.items()
                     if msgid != english[number][0]}
        self.assertEqual(differing, set())

    def test_english_is_the_source_and_translates_nothing(self):
        translated = {number for number, (_, msgstr) in entries("en_gb").items()
                      if msgstr != '""'}
        self.assertEqual(translated, set())

    def test_nothing_is_left_untranslated(self):
        empty = {number for number, (_, msgstr) in entries("de_de").items()
                 if msgstr == '""'}
        self.assertEqual(empty, set())


if __name__ == "__main__":
    unittest.main()
