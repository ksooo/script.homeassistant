"""What pressing OK offers, for entities that can do more than one thing."""

import unittest

from . import support
from resources.lib import actions


def one(entity_id, value="idle", options=None, **attributes):
    entry = support.entity(entity_id, "Ding")
    entry["options"] = options or {}
    return support.build(
        entities=[entry],
        states=[support.state(entity_id, value, **attributes)])


def labels(entity_id, value="idle", options=None, **attributes):
    store = one(entity_id, value, options, **attributes)
    return [a.label_key
            for a in actions.commands_for(store, store.states[entity_id])]


MAPPED = {"vacuum": {"area_mapping": {"kueche": ["1_18"], "flur_ug": ["2_19"]}}}


class Asking(unittest.TestCase):
    def test_ok_asks_where_the_state_does_not_say_what_is_wanted(self):
        for entity_id in ("vacuum.a", "media_player.a", "lock.a", "climate.a"):
            store = one(entity_id)
            self.assertEqual(actions.default_action(store, entity_id).kind,
                             actions.COMMANDS, entity_id)

    def test_a_lamp_still_just_toggles(self):
        store = one("light.a", "off")
        action = actions.default_action(store, "light.a")
        self.assertEqual((action.kind, action.service), (actions.SERVICE, "toggle"))


class Vacuum(unittest.TestCase):
    ROBOROCK = 30524  # start, pause, stop, return, fan speed, locate, spot, ...

    def test_only_what_the_vacuum_reports_is_offered(self):
        self.assertEqual(
            labels("vacuum.a", supported_features=self.ROBOROCK,
                   fan_speed_list=["quiet", "max"]),
            ["action_start", "action_pause", "action_stop", "action_return",
             "action_clean_spot", "action_locate", "action_fan_speed"])

    def test_a_simpler_vacuum_gets_a_shorter_list(self):
        self.assertEqual(labels("vacuum.a", supported_features=8192 | 16),
                         ["action_start", "action_return"])

    def test_suction_needs_a_list_to_choose_from(self):
        self.assertNotIn("action_fan_speed",
                         labels("vacuum.a", supported_features=self.ROBOROCK))


class MediaPlayer(unittest.TestCase):
    KODI = 186303      # everything but source and sound mode
    TELEVISION = 24381  # includes source selection

    def test_transport_and_volume_come_from_the_features(self):
        self.assertEqual(
            labels("media_player.a", supported_features=self.KODI),
            ["action_play", "action_pause", "action_stop", "action_previous",
             "action_next", "action_shuffle", "action_volume",
             "action_volume_up", "action_volume_down", "action_mute",
             "action_turn_on", "action_turn_off"])

    def test_a_television_adds_its_sources(self):
        self.assertIn("action_source",
                      labels("media_player.a", supported_features=self.TELEVISION,
                             source_list=["HDMI 1", "HDMI 2"]))

    def test_shuffle_flips_the_state_it_finds(self):
        for shuffling, expected in ((False, True), (True, False)):
            store = one("media_player.a", supported_features=32768,
                        shuffle=shuffling)
            action = actions.commands_for(store, store.states["media_player.a"])[0]
            self.assertEqual(action.data, {"shuffle": expected})

    def test_repeat_names_the_three_modes_home_assistant_takes(self):
        store = one("media_player.a", supported_features=262144)
        action = actions.commands_for(store, store.states["media_player.a"])[0]
        self.assertEqual((action.service, action.data["as"]),
                         ("repeat_set", "repeat"))
        self.assertEqual([value for _, value in action.data["choices"]],
                         ["off", "all", "one"])

    def test_stepping_the_volume_is_two_commands(self):
        self.assertEqual(labels("media_player.a", supported_features=1024),
                         ["action_volume_up", "action_volume_down"])

    def test_muting_flips_the_state_it_finds(self):
        for muted, expected in ((False, True), (True, False)):
            store = one("media_player.a", supported_features=8,
                        is_volume_muted=muted)
            mute = actions.commands_for(store, store.states["media_player.a"])[0]
            self.assertEqual(mute.data, {"is_volume_muted": expected})


class Lock(unittest.TestCase):
    def test_a_lock_that_can_only_bolt_offers_two_commands(self):
        self.assertEqual(labels("lock.a", "locked", supported_features=0),
                         ["action_lock", "action_unlock"])

    def test_one_that_can_draw_the_latch_offers_three(self):
        self.assertEqual(labels("lock.a", "locked", supported_features=1),
                         ["action_lock", "action_unlock", "action_unlatch"])


class Climate(unittest.TestCase):
    THERMOSTAT = 401  # target temperature, preset mode, turn on, turn off

    def test_modes_temperature_and_presets(self):
        self.assertEqual(
            labels("climate.a", supported_features=self.THERMOSTAT,
                   hvac_modes=["off", "heat"], preset_modes=["eco", "comfort"]),
            ["action_set_hvac", "action_set_temperature", "action_preset",
             "action_turn_on", "action_turn_off"])

    def test_what_the_thermostat_cannot_do_is_not_offered(self):
        self.assertEqual(labels("climate.a", supported_features=0,
                                hvac_modes=["off", "heat"]),
                         ["action_set_hvac"])


class CleaningRooms(unittest.TestCase):
    CLEAN_AREA = 8192 | 16384

    def test_rooms_are_offered_where_the_vacuum_has_a_map(self):
        self.assertEqual(labels("vacuum.a", options=MAPPED,
                                supported_features=self.CLEAN_AREA),
                         ["action_start", "action_clean_areas"])

    def test_a_vacuum_without_a_map_is_not_offered_rooms(self):
        self.assertEqual(labels("vacuum.a", supported_features=self.CLEAN_AREA),
                         ["action_start"])

    def test_a_vacuum_that_cannot_do_it_is_not_offered_rooms(self):
        self.assertEqual(labels("vacuum.a", options=MAPPED,
                                supported_features=8192),
                         ["action_start"])

    def test_the_rooms_go_back_under_the_key_the_service_wants(self):
        store = one("vacuum.a", options=MAPPED,
                    supported_features=self.CLEAN_AREA)
        action = actions.commands_for(store, store.states["vacuum.a"])[1]
        self.assertEqual((action.kind, action.service, action.data),
                         (actions.AREAS, "clean_area",
                          {"as": "cleaning_area_id"}))

    def test_the_mapped_rooms_are_read_from_the_registry(self):
        store = one("vacuum.a", options=MAPPED)
        self.assertEqual(actions.cleanable_areas(store.entities["vacuum.a"]),
                         ("kueche", "flur_ug"))


class Light(unittest.TestCase):
    def test_a_plain_lamp_is_offered_nothing_extra(self):
        self.assertEqual(labels("light.a", "on", supported_color_modes=["onoff"]),
                         [])

    def test_a_dimmable_lamp_is_offered_brightness(self):
        self.assertEqual(
            labels("light.a", "on", supported_color_modes=["brightness"]),
            ["action_brightness"])

    def test_colour_temperature_steps_stay_within_the_lamp(self):
        store = one("light.a", "on", supported_color_modes=["color_temp"],
                    min_color_temp_kelvin=2202, max_color_temp_kelvin=4000)
        action = actions.commands_for(store, store.states["light.a"])[1]
        self.assertEqual(action.data["choices"],
                         [("2202 K", 2202), ("2700 K", 2700), ("3000 K", 3000),
                          ("4000 K", 4000)])

    def test_a_lamp_that_names_no_range_is_offered_no_temperature(self):
        self.assertEqual(
            labels("light.a", "on", supported_color_modes=["color_temp"]),
            ["action_brightness"])

    def test_effects_come_from_the_lamp(self):
        store = one("light.a", "on", supported_color_modes=["onoff"],
                    effect_list=["rainbow", "candle"])
        action = actions.commands_for(store, store.states["light.a"])[0]
        self.assertEqual((action.label_key, action.data),
                         ("action_effect", {"from": "effect_list", "as": "effect"}))

    def test_ok_stays_a_toggle_even_for_a_lamp_that_can_more(self):
        store = one("light.a", "on", supported_color_modes=["color_temp"])
        self.assertEqual(actions.default_action(store, "light.a").service, "toggle")


class Alarm(unittest.TestCase):
    PANEL = 1 | 2 | 4 | 8  # home, away, night, trigger

    def test_only_the_ways_of_arming_the_panel_knows(self):
        self.assertEqual(labels("alarm_control_panel.a", "disarmed",
                                supported_features=self.PANEL),
                         ["action_arm_home", "action_arm_away",
                          "action_arm_night", "action_disarm"])

    def test_disarming_is_offered_even_where_no_arming_is(self):
        self.assertEqual(labels("alarm_control_panel.a", "disarmed",
                                supported_features=0),
                         ["action_disarm"])

    def test_setting_the_alarm_off_is_not_offered(self):
        actions_offered = labels("alarm_control_panel.a", "disarmed",
                                 supported_features=self.PANEL)
        self.assertNotIn("action_trigger", actions_offered)


class WaterHeater(unittest.TestCase):
    BOILER = 1 | 2 | 4 | 8

    def test_modes_temperature_away_and_power(self):
        self.assertEqual(
            labels("water_heater.a", "eco", supported_features=self.BOILER,
                   operation_list=["eco", "performance"]),
            ["action_operation_mode", "action_set_temperature",
             "action_away_mode", "action_turn_on", "action_turn_off"])

    def test_away_mode_flips_what_it_finds(self):
        for away, expected in (("off", True), ("on", False)):
            store = one("water_heater.a", "eco", supported_features=4,
                        away_mode=away)
            action = actions.commands_for(store, store.states["water_heater.a"])[0]
            self.assertEqual(action.data, {"away_mode": expected})

    def test_a_boiler_that_names_no_modes_is_not_offered_them(self):
        self.assertEqual(labels("water_heater.a", "eco", supported_features=2), [])


class Picking(unittest.TestCase):
    def test_a_choice_names_where_it_reads_from_and_writes_to(self):
        store = one("select.a", "one", options=["one", "two"])
        action = actions.default_action(store, "select.a")
        self.assertEqual(action.kind, actions.PICK)
        self.assertEqual(action.data, {"from": "options", "as": "option"})


if __name__ == "__main__":
    unittest.main()
