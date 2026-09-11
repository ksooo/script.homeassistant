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

    def test_a_player_of_unknown_state_is_offered_the_way_on(self):
        # Home Assistant treats unknown as asleep rather than as missing.
        self.assertEqual(self.services("unknown", self.BOTH), ["turn_on"])

    def test_the_icon_says_standby_unless_the_state_is_assumed(self):
        icons = lambda value, features, assumed: [
            icon for icon, _ in media.power(player(
                value, supported_features=features,
                **({"assumed_state": True} if assumed else {})))]
        self.assertEqual(icons("off", self.BOTH, False), ["power_standby"])
        self.assertEqual(icons("playing", self.BOTH, False), ["power_standby"])
        self.assertEqual(icons("on", self.BOTH, True), ["power_on", "power_off"])

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

    def test_a_player_that_can_only_mute_has_no_volume_row(self):
        # Home Assistant asks for a level or steps before it draws the row.
        self.assertEqual(media.volume(player("on", supported_features=8)),
                         (False, None, False))

    def test_an_assumed_player_that_is_off_keeps_its_volume_row(self):
        state = player("off", supported_features=4 | 8, assumed_state=True,
                       volume_level=0.4)
        self.assertEqual(media.volume(state), (True, 0.4, False))


class Sources(unittest.TestCase):
    def test_the_inputs_come_from_the_player(self):
        # The Yamaha is the only one here that offers this at all.
        self.assertEqual(
            media.sources(player("on", supported_features=2048,
                                 source_list=["SHIELD", "HDMI 2", "TUNER"])),
            ["SHIELD", "HDMI 2", "TUNER"])

    def test_a_player_that_cannot_switch_inputs_offers_none(self):
        self.assertEqual(media.sources(player("on", supported_features=4,
                                              source_list=["HDMI 1"])), [])

    def test_a_player_naming_no_inputs_offers_none(self):
        self.assertEqual(media.sources(player("on", supported_features=2048)), [])

    def test_the_state_does_not_take_the_inputs_away(self):
        # Home Assistant asks the feature bit alone, whatever the state.
        self.assertEqual(media.sources(player("unavailable",
                                              supported_features=2048,
                                              source_list=["HDMI 1"])),
                         ["HDMI 1"])


class Browsing(unittest.TestCase):
    def test_a_player_with_the_browse_bit_offers_the_tree(self):
        # 186303: Kodi on the Shield, and off, which changes nothing here.
        self.assertTrue(media.can_browse(player("off", supported_features=186303)))

    def test_a_receiver_without_the_bit_does_not(self):
        # 888716: the Yamaha, which takes a source but browses nothing.
        self.assertFalse(media.can_browse(player("on", supported_features=888716)))

    def test_an_unavailable_player_offers_nothing(self):
        self.assertFalse(
            media.can_browse(player("unavailable", supported_features=186303)))


class Settings(unittest.TestCase):
    """Shuffle and repeat, which report a state rather than a command."""

    RECEIVER = 1019788                   # the Yamaha: both bits
    KODI = 186303                        # shuffle, but no repeat

    def test_a_receiver_playing_offers_both(self):
        state = player("playing", supported_features=self.RECEIVER,
                       shuffle=False, repeat="off")
        self.assertEqual(media.shuffle(state), ("shuffle-disabled", True))
        self.assertEqual(media.repeat(state), ("repeat-off", "all"))

    def test_the_icon_says_how_it_stands(self):
        state = player("playing", supported_features=self.RECEIVER,
                       shuffle=True, repeat="one")
        self.assertEqual(media.shuffle(state)[0], "shuffle")
        self.assertEqual(media.repeat(state)[0], "repeat-once")

    def test_repeat_goes_round(self):
        def following(value):
            return media.repeat(player("playing", supported_features=self.RECEIVER,
                                       repeat=value))[1]
        self.assertEqual([following("off"), following("all"), following("one")],
                         ["all", "one", "off"])

    def test_a_player_with_one_bit_offers_one_button(self):
        state = player("playing", supported_features=self.KODI)
        self.assertIsNotNone(media.shuffle(state))
        self.assertIsNone(media.repeat(state))

    def test_neither_applies_unless_something_is_going(self):
        for value in ("on", "idle", "off", "unavailable"):
            state = player(value, supported_features=self.RECEIVER)
            self.assertIsNone(media.shuffle(state), value)
            self.assertIsNone(media.repeat(state), value)

    def test_a_player_taken_on_trust_offers_them(self):
        state = player("on", supported_features=self.RECEIVER, assumed_state=True)
        self.assertIsNotNone(media.shuffle(state))
        self.assertIsNotNone(media.repeat(state))


class SoundModes(unittest.TestCase):
    RECEIVER = 1019788                   # the Yamaha while it plays

    def test_a_receiver_offers_its_sound_fields(self):
        state = player("playing", supported_features=self.RECEIVER,
                       sound_mode="standard",
                       sound_mode_list=["munich", "standard"])
        self.assertEqual(media.sound_modes(state), ["munich", "standard"])

    def test_a_player_without_the_bit_offers_none(self):
        state = player("playing", supported_features=186303,
                       sound_mode_list=["munich"])
        self.assertEqual(media.sound_modes(state), [])

    def test_a_receiver_listing_none_offers_none(self):
        self.assertEqual(
            media.sound_modes(player("playing",
                                     supported_features=self.RECEIVER)), [])


class Grouping(unittest.TestCase):
    RECEIVER = 1019788
    KODI = 186303                        # browses and plays, but cannot group

    def store(self, *rows):
        """One store from (entity_id, name, platform, features, members)."""
        return support.build(
            entities=[support.entity(entity_id, name, platform=platform)
                      for entity_id, name, platform, _, _ in rows],
            states=[support.state(entity_id, "playing", friendly_name=name,
                                  supported_features=features,
                                  group_members=members)
                    for entity_id, name, platform, features, members in rows])

    def yamahas(self, members=("media_player.main",)):
        return self.store(
            ("media_player.main", "Yamaha", "yamaha_musiccast",
             self.RECEIVER, list(members)),
            ("media_player.zone2", "Yamaha Zone 2", "yamaha_musiccast",
             self.RECEIVER, ["media_player.zone2"]))

    def test_a_receiver_is_offered_the_other_zone(self):
        self.assertEqual(media.group_choices(self.yamahas(), "media_player.main"),
                         [("media_player.zone2", "Yamaha Zone 2", False)])

    def test_a_player_already_in_comes_back_ticked(self):
        store = self.yamahas(("media_player.main", "media_player.zone2"))
        self.assertEqual(media.group_choices(store, "media_player.main"),
                         [("media_player.zone2", "Yamaha Zone 2", True)])

    def test_another_integration_is_not_offered(self):
        # A group forms inside one integration, whatever the bits say.
        store = self.store(
            ("media_player.main", "Yamaha", "yamaha_musiccast",
             self.RECEIVER, ["media_player.main"]),
            ("media_player.cast", "Chromecast", "cast",
             self.RECEIVER, ["media_player.cast"]))
        self.assertEqual(media.group_choices(store, "media_player.main"), [])

    def test_a_player_that_cannot_group_is_not_offered(self):
        store = self.store(
            ("media_player.main", "Yamaha", "yamaha_musiccast",
             self.RECEIVER, ["media_player.main"]),
            ("media_player.kodi", "Kodi", "yamaha_musiccast", self.KODI, []))
        self.assertEqual(media.group_choices(store, "media_player.main"), [])

    def test_a_player_that_cannot_group_is_offered_nobody(self):
        store = self.store(
            ("media_player.kodi", "Kodi", "kodi", self.KODI, []),
            ("media_player.main", "Yamaha", "kodi",
             self.RECEIVER, ["media_player.main"]))
        self.assertEqual(media.group_choices(store, "media_player.kodi"), [])


class GroupPlan(unittest.TestCase):
    def test_a_player_added_is_joined(self):
        self.assertEqual(media.group_plan(["a"], ["a", "b"]), (["b"], []))

    def test_a_player_dropped_leaves_on_its_own(self):
        self.assertEqual(media.group_plan(["a", "b"], ["a"]), ([], ["b"]))

    def test_a_swap_needs_both_calls(self):
        self.assertEqual(media.group_plan(["b"], ["c"]), (["c"], ["b"]))

    def test_a_membership_unchanged_needs_no_call(self):
        self.assertEqual(media.group_plan(["a"], ["a"]), ([], []))


class Naming(unittest.TestCase):
    """The description line, which Home Assistant picks by content type."""

    def subtitle(self, kind=None, **attributes):
        return media.subtitle(player(media_content_type=kind, **attributes))

    def test_music_is_named_by_its_artist(self):
        self.assertEqual(self.subtitle("music", media_artist="Fleetwood Mac",
                                       app_name="Kodi"), "Fleetwood Mac")

    def test_a_playlist_falls_back_from_its_name_to_the_artist(self):
        self.assertEqual(self.subtitle("playlist", media_playlist="Abendmusik"),
                         "Abendmusik")
        self.assertEqual(self.subtitle("playlist", media_artist="Fleetwood Mac"),
                         "Fleetwood Mac")

    def test_a_programme_carries_its_season_and_episode(self):
        self.assertEqual(
            self.subtitle("tvshow", media_series_title="In aller Freundschaft",
                          media_season=27, media_episode=14),
            "In aller Freundschaft S27E14")
        self.assertEqual(
            self.subtitle("tvshow", media_series_title="In aller Freundschaft"),
            "In aller Freundschaft")

    def test_television_is_named_by_its_channel(self):
        self.assertEqual(self.subtitle("channel", media_channel="Das Erste HD",
                                       app_name="Kodi"), "Das Erste HD")

    def test_anything_else_is_named_by_its_app(self):
        self.assertEqual(self.subtitle(None, app_name="Kodi", source="SHIELD"),
                         "Kodi")

    def test_the_input_is_not_a_description(self):
        # Home Assistant never puts the source here; this addon used to.
        self.assertEqual(self.subtitle(None, source="SHIELD"), "")


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

    def test_an_idle_player_is_offered_play(self):
        # What Home Assistant shows for the Kodi player sitting idle.
        self.assertEqual(self.names("idle", self.PLAYER), ["play"])

    def test_a_player_on_standby_is_offered_nothing(self):
        # Home Assistant names idle and paused, and standby is neither.
        self.assertEqual(self.names("standby", self.PLAYER), [])

    def test_a_player_that_is_off_is_offered_nothing(self):
        # What Home Assistant shows for the Chromecast: a power button only,
        # which is not one of these.
        self.assertEqual(self.names("off", self.PLAYER), [])

    def test_a_sleeping_player_that_cannot_play_is_offered_nothing(self):
        self.assertEqual(self.names("idle", 1 | 4096), [])

    def test_an_unavailable_player_is_offered_nothing(self):
        self.assertEqual(self.names("unavailable", self.PLAYER), [])

    def test_a_television_whose_state_is_assumed_gets_all_three(self):
        # What Home Assistant shows for the LG: nothing says which applies,
        # and it lists them play, pause, stop.
        state = player("on", supported_features=self.TELEVISION,
                       assumed_state=True)
        self.assertEqual([name for name, _ in media.controls(state)],
                         ["previous", "play", "pause", "stop", "next"])

    def test_a_known_player_merely_on_gets_the_double_button(self):
        # Home Assistant offers one button that does both, and no skipping:
        # a player that is not going has no track to skip.
        self.assertEqual(self.names("on", self.PLAYER), ["play_pause"])

    def test_skipping_needs_a_player_that_is_going(self):
        for value in ("playing", "paused"):
            self.assertIn("previous", self.names(value, self.PLAYER), value)
        for value in ("on", "idle"):
            self.assertNotIn("previous", self.names(value, self.PLAYER), value)


if __name__ == "__main__":
    unittest.main()
