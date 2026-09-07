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


class CoverTilt(unittest.TestCase):
    VENETIAN = 1 | 2 | 4 | 8 | 16 | 32 | 64 | 128
    ROLLER = 1 | 2 | 4 | 8

    def menu(self, features):
        store = one("cover.a", "open", supported_features=features)
        return [a.label_key for a in actions.menu_actions(store, "cover.a")]

    def test_a_venetian_blind_is_offered_its_slats(self):
        self.assertEqual(self.menu(self.VENETIAN),
                         ["action_open", "action_close", "action_stop",
                          "action_position", "action_open_tilt",
                          "action_close_tilt", "action_stop_tilt",
                          "action_set_tilt", "action_details"])

    def test_a_roller_shutter_is_offered_none_of_them(self):
        self.assertEqual(self.menu(self.ROLLER),
                         ["action_open", "action_close", "action_stop",
                          "action_position", "action_details"])

    def test_each_tilt_command_is_asked_for_on_its_own(self):
        self.assertEqual([label for label in self.menu(1 | 2 | 16 | 64)
                          if label.endswith("_tilt")],
                         ["action_open_tilt", "action_stop_tilt"])

    def test_the_angle_goes_to_the_tilt_service(self):
        store = one("cover.a", "open", supported_features=128)
        action = next(a for a in actions.menu_actions(store, "cover.a")
                      if a.label_key == "action_set_tilt")
        self.assertEqual((action.kind, action.domain, action.service),
                         (actions.NUMBER, "cover", "set_cover_tilt_position"))


class Fan(unittest.TestCase):
    TOWER = 1 | 2 | 4 | 8 | 16 | 32

    def test_everything_the_fan_reports(self):
        self.assertEqual(
            labels("fan.a", "on", supported_features=self.TOWER,
                   preset_modes=["eco", "sleep"]),
            ["action_speed", "action_preset", "action_oscillate",
             "action_direction"])

    def test_a_fan_that_only_switches_is_offered_nothing(self):
        self.assertEqual(labels("fan.a", "on", supported_features=8 | 16), [])

    def test_oscillating_flips_the_state_it_finds(self):
        for swinging, expected in ((False, True), (True, False)):
            store = one("fan.a", "on", supported_features=2,
                        oscillating=swinging)
            action = actions.commands_for(store, store.states["fan.a"])[0]
            self.assertEqual(action.data, {"oscillating": expected})

    def test_ok_still_toggles_a_fan(self):
        store = one("fan.a", "on", supported_features=self.TOWER)
        self.assertEqual(actions.default_action(store, "fan.a").service, "toggle")


class Humidifier(unittest.TestCase):
    def test_the_target_humidity_needs_no_feature_bit(self):
        self.assertEqual(labels("humidifier.a", "on", supported_features=0),
                         ["action_target_humidity"])

    def test_modes_come_from_the_humidifier(self):
        self.assertEqual(
            labels("humidifier.a", "on", supported_features=1,
                   available_modes=["normal", "boost"]),
            ["action_target_humidity", "action_operation_mode"])

    def test_a_humidifier_naming_no_modes_is_not_offered_them(self):
        self.assertEqual(labels("humidifier.a", "on", supported_features=1),
                         ["action_target_humidity"])


class Valve(unittest.TestCase):
    def test_only_what_the_valve_reports(self):
        self.assertEqual(
            labels("valve.a", "open", supported_features=1 | 2 | 4 | 8),
            ["action_open", "action_close", "action_stop", "action_position"])

    def test_a_valve_without_a_position_is_not_offered_one(self):
        self.assertEqual(labels("valve.a", "open", supported_features=1 | 2),
                         ["action_open", "action_close"])


class Picking(unittest.TestCase):
    def test_a_choice_names_where_it_reads_from_and_writes_to(self):
        store = one("select.a", "one", options=["one", "two"])
        action = actions.default_action(store, "select.a")
        self.assertEqual(action.kind, actions.PICK)
        self.assertEqual(action.data, {"from": "options", "as": "option"})


if __name__ == "__main__":
    unittest.main()
