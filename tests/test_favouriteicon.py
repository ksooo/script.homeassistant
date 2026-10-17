"""A Kodi favourite's icon with Home Assistant's logo in its corner."""

import os
import shutil
import struct
import tempfile
import unittest
import zlib

from . import support  # noqa: F401  (puts the addon on the path)
from resources.lib import favouriteicon

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(ROOT, "resources", "media")


def solid(width, height, colour):
    return bytearray(bytes(colour) * (width * height))


class Drawing(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory)

    def path(self, name, width, height, pixels):
        path = os.path.join(self.directory, name)
        with open(path, "wb") as handle:
            handle.write(favouriteicon.encode_png(width, height, pixels))
        return path

    def draw(self):
        icon = self.path("icon.png", 8, 8, solid(8, 8, (255, 255, 255, 255)))
        badge = self.path("badge.png", 2, 2, solid(2, 2, (0, 0, 255, 255)))
        cut = self.path("cut.png", 3, 3, solid(3, 3, (255, 255, 255, 255)))
        target = os.path.join(self.directory, "out.png")
        favouriteicon.draw(icon, badge, cut, target)
        width, height, pixels = favouriteicon.read_png(target)
        self.assertEqual((width, height), (8, 8))
        return lambda x, y: tuple(pixels[(y * 8 + x) * 4:(y * 8 + x) * 4 + 4])

    def test_the_badge_covers_the_corner(self):
        self.assertEqual(self.draw()(1, 1), (0, 0, 255, 255))

    def test_the_icon_is_cleared_around_the_badge(self):
        self.assertEqual(self.draw()(2, 2)[3], 0)

    def test_the_rest_of_the_icon_stays(self):
        self.assertEqual(self.draw()(5, 5), (255, 255, 255, 255))

    def test_nothing_half_written_is_left_behind(self):
        self.draw()
        self.assertFalse([name for name in os.listdir(self.directory)
                          if name.endswith(".part")])

    def test_the_shipped_badge_fits_inside_its_cut(self):
        badge = favouriteicon.read_png(os.path.join(MEDIA, "badge.png"))
        cut = favouriteicon.read_png(os.path.join(MEDIA, "badge_cut.png"))
        self.assertLess(badge[0], cut[0])
        self.assertLess(badge[1], cut[1])


class Naming(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory)

    def name(self, badge):
        paths = []
        for name, data in (("badge.png", badge), ("cut.png", b"cut")):
            paths.append(os.path.join(self.directory, name))
            with open(paths[-1], "wb") as handle:
                handle.write(data)
        return favouriteicon.file_name("/icons/video.png", *paths)

    def test_the_name_keeps_the_icon_s(self):
        self.assertTrue(self.name(b"logo").startswith("video-"))
        self.assertTrue(self.name(b"logo").endswith(".png"))

    def test_another_logo_gives_another_name(self):
        self.assertNotEqual(self.name(b"logo"), self.name(b"new logo"))


class Reading(unittest.TestCase):
    def test_every_filter_comes_back_to_the_same_pixels(self):
        # Two RGBA pixels per row; each row stored with another PNG filter.
        rows = [bytes((10, 20, 30, 40, 50, 60, 70, 80)) for _ in range(5)]
        raw = b""
        previous = bytes(8)
        for method, row in enumerate(rows):
            encoded = bytearray(8)
            for x in range(8):
                left = row[x - 4] if x >= 4 else 0
                above = previous[x]
                corner = previous[x - 4] if x >= 4 else 0
                predictor = (0, left, above, (left + above) // 2,
                             _paeth(left, above, corner))[method]
                encoded[x] = (row[x] - predictor) & 255
            raw += bytes((method,)) + bytes(encoded)
            previous = row
        data = (b"\x89PNG\r\n\x1a\n"
                + _chunk(b"IHDR", struct.pack("!2I5B", 2, 5, 8, 6, 0, 0, 0))
                + _chunk(b"IDAT", zlib.compress(raw))
                + _chunk(b"IEND", b""))
        path = os.path.join(tempfile.mkdtemp(), "filtered.png")
        self.addCleanup(shutil.rmtree, os.path.dirname(path))
        with open(path, "wb") as handle:
            handle.write(data)
        self.assertEqual(favouriteicon.read_png(path)[2], bytearray(b"".join(rows)))


def _chunk(tag, body):
    return (struct.pack("!I", len(body)) + tag + body
            + struct.pack("!I", zlib.crc32(tag + body) & 0xFFFFFFFF))


def _paeth(left, above, corner):
    estimate = left + above - corner
    distances = (abs(estimate - left), abs(estimate - above), abs(estimate - corner))
    if distances[0] <= distances[1] and distances[0] <= distances[2]:
        return left
    return above if distances[1] <= distances[2] else corner


class Pruning(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory)
        for name in ("lightbulb.png", "cctv.png", "lock.png.part"):
            open(os.path.join(self.directory, name), "wb").close()

    def test_only_the_icons_a_favourite_names_are_kept(self):
        favouriteicon.prune(self.directory,
                            [os.path.join(self.directory, "lightbulb.png")])
        self.assertEqual(os.listdir(self.directory), ["lightbulb.png"])

    def test_a_directory_not_there_yet_is_fine(self):
        favouriteicon.prune(os.path.join(self.directory, "missing"), [])
