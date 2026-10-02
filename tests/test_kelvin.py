"""The colours behind the colour temperature slider."""

import struct
import unittest
import zlib

from . import support  # noqa: F401  (puts the addon on the path)
from resources.lib import kelvin


class Colours(unittest.TestCase):
    def test_warm_light_is_orange_and_cold_light_bluish(self):
        self.assertEqual(kelvin.rgb(2000), (255, 137, 14))
        self.assertEqual(kelvin.rgb(6600), (255, 255, 255))
        red, green, blue = kelvin.rgb(9000)
        self.assertLess(red, blue)


class Gradient(unittest.TestCase):
    def test_the_strip_runs_from_the_low_end_to_the_high_end(self):
        data = kelvin.gradient_png(2000, 6600, width=8)
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack("!2I", data[16:24])
        self.assertEqual((width, height), (8, 1))
        start = data.index(b"IDAT") + 4
        length = struct.unpack("!I", data[start - 8:start - 4])[0]
        row = zlib.decompress(data[start:start + length])
        self.assertEqual(tuple(row[1:4]), kelvin.rgb(2000))
        self.assertEqual(tuple(row[-3:]), kelvin.rgb(6600))
