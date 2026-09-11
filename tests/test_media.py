"""The numbers behind the media window, which need no Kodi to check."""

import unittest

from . import support
from resources.lib import media

STAMP = "2026-09-10T17:30:18+00:00"
AT = 1789061418.0        # the same instant, as epoch seconds


def player(value="playing", **attributes):
    attributes.setdefault("media_position_updated_at", STAMP)
    store = support.build(
        entities=[support.entity("media_player.a", "Player")],
        states=[support.state("media_player.a", value, **attributes)])
    return store.states["media_player.a"]


class Elapsed(unittest.TestCase):
    def test_a_playing_medium_carries_its_position_forward(self):
        state = player(media_position=1825, media_duration=2818)
        self.assertEqual(media.elapsed(state, now=AT + 12), 1837)

    def test_a_paused_medium_stands_still(self):
        state = player("paused", media_position=1825)
        self.assertEqual(media.elapsed(state, now=AT + 600), 1825)

    def test_a_player_reporting_no_position_says_nothing(self):
        self.assertIsNone(media.elapsed(player(), now=AT))

    def test_a_timestamp_with_a_trailing_z_is_the_same_instant(self):
        state = player(media_position=10,
                       media_position_updated_at="2026-09-10T17:30:18Z")
        self.assertEqual(media.elapsed(state, now=AT + 5), 15)


class Progress(unittest.TestCase):
    def test_live_television_reporting_zero_gets_no_bar(self):
        state = player(media_position=0, media_duration=0)
        self.assertIsNone(media.duration(state))
        self.assertIsNone(media.fraction(state, now=AT))

    def test_the_share_is_clamped_to_the_medium(self):
        state = player(media_position=2818, media_duration=2818)
        self.assertEqual(media.fraction(state, now=AT + 600), 1.0)

    def test_the_clock_grows_an_hour_when_it_needs_one(self):
        self.assertEqual(media.clock(2072), "34:32")
        self.assertEqual(media.clock(5672), "1:34:32")
        self.assertEqual(media.clock(None), "")


class Power(unittest.TestCase):
    BOTH = 128 | 256

    def services(self, value, features, assumed=False):
        extra = {"assumed_state": True} if assumed else {}
        state = player(value, supported_features=features, **extra)
        return [service for _, service in media.power(state)]

    def test_a_known_player_gets_the_one_direction_that_applies(self):
        self.assertEqual(self.services("off", self.BOTH), ["turn_on"])
        for value in ("playing", "paused", "idle", "on"):
            self.assertEqual(self.services(value, self.BOTH), ["turn_off"], value)

    def test_an_assumed_player_gets_both(self):
        # What Home Assistant shows for the Shield remote: separate on and
        # off, because its state does not say which applies.
        self.assertEqual(self.services("on", 153529, assumed=True),
                         ["turn_on", "turn_off"])

    def test_an_assumed_player_gets_only_the_bits_it_reports(self):
        # The LG cannot be turned on over its own protocol, only off.
        self.assertEqual(self.services("on", 24381, assumed=True), ["turn_off"])

    def test_each_direction_needs_its_own_bit(self):
        self.assertEqual(self.services("off", 256), [])
        self.assertEqual(self.services("on", 128), [])

    def test_an_unavailable_player_has_no_power_button(self):
        self.assertEqual(self.services("unavailable", self.BOTH), [])


class Volume(unittest.TestCase):
    def test_a_player_taking_a_level_gets_a_slider(self):
        # The television: volume_set, and it sits at zero.
        self.assertEqual(media.volume(player("on", supported_features=4 | 8,
                                             volume_level=0.0)),
                         (True, 0.0, False))

    def test_a_player_taking_only_steps_gets_buttons(self):
        # The Shield's own remote: mute and steps, but no level.
        self.assertEqual(media.volume(player("on", supported_features=8 | 1024)),
                         (True, None, True))

    def test_steps_give_way_to_a_level(self):
        self.assertEqual(media.volume(player("on", supported_features=4 | 1024)),
                         (False, 0.0, False))

    def test_a_player_reporting_no_level_shows_the_slider_at_zero(self):
        self.assertEqual(media.volume(player("idle", supported_features=4)),
                         (False, 0.0, False))

    def test_muting_needs_its_own_bit(self):
        self.assertEqual(media.volume(player("on", supported_features=4))[0], False)

    def test_a_player_says_whether_it_is_muted(self):
        self.assertTrue(media.muted(player("on", is_volume_muted=True)))
        self.assertFalse(media.muted(player("on", is_volume_muted=False)))
        self.assertFalse(media.muted(player("on")))

    def test_a_player_that_is_off_has_no_volume_row(self):
        self.assertEqual(media.volume(player("off", supported_features=4 | 8)),
                         (False, None, False))


class Naming(unittest.TestCase):
    def test_the_subtitle_falls_through_to_what_is_there(self):
        self.assertEqual(
            media.subtitle(player(media_series_title="In aller Freundschaft",
                                  app_name="Kodi")),
            "In aller Freundschaft")
        self.assertEqual(media.subtitle(player(app_name="Kodi", source="SHIELD")),
                         "Kodi")
        self.assertEqual(media.subtitle(player(source="SHIELD")), "SHIELD")
        self.assertEqual(media.subtitle(player()), "")


class Controls(unittest.TestCase):
    TELEVISION = 24381   # the LG: pause, play, stop, prev, next, and more
    PLAYER = 152511      # a Shield: the same transport, state not assumed

    def names(self, value, features):
        return [name for name, _ in
                media.controls(player(value, supported_features=features))]

    def test_a_playing_player_gets_the_one_button_its_state_calls_for(self):
        # No stop beside it: what Home Assistant shows for a playing Shield.
        self.assertEqual(self.names("playing", self.PLAYER),
                         ["previous", "pause", "next"])

    def test_a_paused_player_gets_play(self):
        self.assertEqual(self.names("paused", self.PLAYER),
                         ["previous", "play", "next"])

    def test_stop_stands_in_where_a_player_cannot_pause(self):
        self.assertEqual(self.names("playing", 16 | 32 | 4096),
                         ["previous", "stop", "next"])

    def test_a_sleeping_player_is_offered_only_play(self):
        # What Home Assistant shows for the Kodi player sitting idle.
        for value in ("idle", "standby"):
            self.assertEqual(self.names(value, self.PLAYER), ["play"], value)

    def test_a_player_that_is_off_is_offered_nothing(self):
        # What Home Assistant shows for the Chromecast: a power button only,
        # which is not one of these.
        self.assertEqual(self.names("off", self.PLAYER), [])

    def test_a_sleeping_player_that_cannot_play_is_offered_nothing(self):
        self.assertEqual(self.names("idle", 1 | 4096), [])

    def test_an_unavailable_player_is_offered_nothing(self):
        self.assertEqual(self.names("unavailable", self.PLAYER), [])

    def test_a_television_whose_state_is_assumed_gets_all_three(self):
        # What Home Assistant shows for the LG: nothing says which applies.
        state = player("on", supported_features=self.TELEVISION,
                       assumed_state=True)
        self.assertEqual([name for name, _ in media.controls(state)],
                         ["previous", "pause", "play", "stop", "next"])

    def test_a_known_player_merely_on_gets_no_middle_button(self):
        self.assertEqual(self.names("on", self.PLAYER), ["previous", "next"])


if __name__ == "__main__":
    unittest.main()
