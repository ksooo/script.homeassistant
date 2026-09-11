"""What one level of the media tree offers, checked without Kodi.

The replies quoted here are Home Assistant's own, taken from the players in
the installation this was written against.
"""

import unittest

from resources.lib import browse

PLAY = "action_play"


class Levels(unittest.TestCase):
    def test_a_library_offers_its_children_in_home_assistants_order(self):
        node = {"title": "Media Library", "can_play": False, "children": [
            {"title": "Music", "media_content_type": "library_music",
             "media_content_id": "", "can_expand": True, "can_play": False,
             "thumbnail": "/api/brands/integration/kodi/logo.png"},
            {"title": "Movies", "media_content_type": "movie",
             "media_content_id": "", "can_expand": True, "can_play": False}]}
        listing = browse.rows(node, PLAY)
        self.assertEqual([row.title for row in listing], ["Music", "Movies"])
        self.assertTrue(all(row.expand and not row.play for row in listing))

    def test_a_level_that_can_be_played_offers_itself_first(self):
        node = {"title": "Popular", "can_play": True, "can_expand": True,
                "media_content_type": "music",
                "media_content_id": "media-source://radio_browser/popular",
                "children": [
                    {"title": "RTL", "can_play": True, "can_expand": False,
                     "media_content_type": "audio/aac",
                     "media_content_id": "media-source://radio_browser/042d"}]}
        listing = browse.rows(node, PLAY)
        self.assertEqual(listing[0].title, PLAY)
        self.assertEqual(listing[0].content_id,
                         "media-source://radio_browser/popular")
        self.assertTrue(listing[0].play)
        self.assertFalse(listing[0].expand)

    def test_a_station_carries_what_play_media_needs(self):
        node = {"children": [
            {"title": "RTL", "can_play": True, "can_expand": False,
             "media_content_type": "audio/aac",
             "media_content_id": "media-source://radio_browser/042d",
             "thumbnail": "https://duckduckgo.com/i/035a.png"}]}
        row = browse.rows(node, PLAY)[0]
        self.assertEqual((row.content_type, row.content_id),
                         ("audio/aac", "media-source://radio_browser/042d"))
        self.assertEqual(row.thumbnail, "https://duckduckgo.com/i/035a.png")
        self.assertTrue(row.play)

    def test_an_album_that_opens_and_plays_says_both(self):
        node = {"children": [
            {"title": "Rumours", "can_play": True, "can_expand": True,
             "media_content_type": "album", "media_content_id": "42"}]}
        row = browse.rows(node, PLAY)[0]
        self.assertTrue(row.expand and row.play)

    def test_a_missing_thumbnail_is_no_thumbnail(self):
        node = {"children": [{"title": "Albums", "can_expand": True,
                              "thumbnail": None}]}
        self.assertEqual(browse.rows(node, PLAY)[0].thumbnail, "")

    def test_an_empty_level_offers_nothing(self):
        # How the Shield's own remote answers while the box is asleep.
        node = {"title": "Applications", "can_play": False, "children": []}
        self.assertEqual(browse.rows(node, PLAY), [])


if __name__ == "__main__":
    unittest.main()
