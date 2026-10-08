"""What pressing OK offers, for entities that can do more than one thing."""

import types
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


def menu(entity_id, value="idle", **attributes):
    store = one(entity_id, value, None, **attributes)
    return [a.label_key for a in actions.menu_actions(store, entity_id)]


MAPPED = {"vacuum": {"area_mapping": {"kueche": ["1_18"], "flur_ug": ["2_19"]}}}


class Switching(unittest.TestCase):
    """Only the half of the switch the entity has not reached."""

    def power(self, entity_id, value):
        return [label for label in menu(entity_id, value)
                if label.startswith("action_turn")]

    def test_what_is_on_is_only_offered_switching_off(self):
        for entity_id in ("light.a", "switch.a", "fan.a", "input_boolean.a",
                          "siren.a", "humidifier.a", "remote.a",
                          "automation.a"):
            self.assertEqual(self.power(entity_id, "on"),
                             ["action_turn_off"], entity_id)

    def test_what_is_off_is_only_offered_switching_on(self):
        for entity_id in ("light.a", "switch.a", "automation.a"):
            self.assertEqual(self.power(entity_id, "off"),
                             ["action_turn_on"], entity_id)

    def test_a_valve_counts_closed_as_off(self):
        # Toggling an open valve shuts it, which is what the question before
        # switching something off is about; toggling a closed one is not.
        self.assertTrue(actions.switches_off(one("valve.a", "open"),
                                             "valve.a", "toggle"))
        self.assertFalse(actions.switches_off(one("valve.a", "closed"),
                                              "valve.a", "toggle"))

    def test_a_state_that_says_nothing_leaves_both(self):
        for value in ("unavailable", "unknown"):
            self.assertEqual(self.power("light.a", value),
                             ["action_turn_on", "action_turn_off"], value)


class Confirming(unittest.TestCase):
    """What the user is asked about before it happens."""

    def question(self, entity_id, value, service, **settings):
        options = types.SimpleNamespace(confirm_off=True, confirm_off_lights=True,
                                        confirm_open=True)
        for key, setting in settings.items():
            setattr(options, key, setting)
        store = one(entity_id, value)
        return actions.confirmation(store, entity_id, service, options)

    def asked(self, *args, **kwargs):
        return self.question(*args, **kwargs) is not None

    def test_turning_something_off_is_asked_about(self):
        for entity_id in ("switch.a", "fan.a", "siren.a", "media_player.a",
                          "climate.a", "water_heater.a"):
            self.assertTrue(self.asked(entity_id, "on", "turn_off"), entity_id)

    def test_a_toggle_is_asked_about_only_where_it_switches_off(self):
        self.assertTrue(self.asked("switch.a", "on", "toggle"))
        self.assertFalse(self.asked("switch.a", "off", "toggle"))

    def test_nothing_else_is_asked_about(self):
        for service in ("turn_on", "close_cover", "open_cover", "lock",
                        "unlock", "open_valve", "media_pause"):
            self.assertFalse(self.asked("switch.a", "on", service), service)

    def test_a_light_is_spared_while_the_second_setting_stands(self):
        self.assertFalse(self.asked("light.a", "on", "turn_off"))
        self.assertTrue(self.asked("light.a", "on", "turn_off",
                                   confirm_off_lights=False))

    def test_the_first_setting_turns_the_whole_thing_off(self):
        self.assertFalse(self.asked("switch.a", "on", "turn_off",
                                    confirm_off=False))

    def test_an_entity_with_no_state_is_not_toggled_off(self):
        store = one("switch.a", "on")
        store.states.clear()
        options = types.SimpleNamespace(confirm_off=True, confirm_off_lights=True,
                                        confirm_open=True)
        self.assertIsNone(actions.confirmation(store, "switch.a", "toggle", options))

    def test_opening_a_door_is_asked_about(self):
        self.assertEqual(self.question("lock.a", "locked", "open"),
                         ("confirm_open_title", "confirm_open_text"))

    def test_opening_a_door_has_its_own_setting(self):
        self.assertFalse(self.asked("lock.a", "locked", "open",
                                    confirm_open=False))
        self.assertTrue(self.asked("lock.a", "locked", "open",
                                   confirm_off=False))

    def test_switching_off_names_its_own_question(self):
        self.assertEqual(self.question("switch.a", "on", "turn_off"),
                         ("confirm_off_title", "confirm_off_text"))


class Asking(unittest.TestCase):
    def test_ok_asks_where_the_state_does_not_say_what_is_wanted(self):
        for entity_id in ("vacuum.a", "lock.a", "climate.a"):
            store = one(entity_id)
            self.assertEqual(actions.default_action(store, entity_id).kind,
                             actions.COMMANDS, entity_id)

    def test_ok_on_a_media_player_opens_its_window(self):
        store = one("media_player.a")
        self.assertEqual(actions.default_action(store, "media_player.a").kind,
                         actions.MEDIA)

    def test_a_lamp_still_just_toggles(self):
        store = one("light.a", "off")
        action = actions.default_action(store, "light.a")
        self.assertEqual((action.kind, action.service), (actions.SERVICE, "toggle"))


class Vacuum(unittest.TestCase):
    ROBOROCK = 30524  # start, pause, stop, return, fan speed, locate, spot, ...

    def test_only_what_the_vacuum_reports_is_offered(self):
        self.assertEqual(
            labels("vacuum.a", "error", supported_features=self.ROBOROCK,
                   fan_speed_list=["quiet", "max"]),
            ["action_start", "action_stop", "action_return",
             "action_clean_spot", "action_locate", "action_fan_speed"])

    def test_a_simpler_vacuum_gets_a_shorter_list(self):
        self.assertEqual(labels("vacuum.a", supported_features=8192 | 16),
                         ["action_start", "action_return"])

    def test_suction_needs_a_list_to_choose_from(self):
        self.assertNotIn("action_fan_speed",
                         labels("vacuum.a", supported_features=self.ROBOROCK))

    def commands(self, value):
        return [label for label in labels("vacuum.a", value,
                                          supported_features=self.ROBOROCK)
                if label in ("action_start", "action_pause", "action_stop",
                             "action_return")]

    def test_in_the_dock_only_starting(self):
        self.assertEqual(self.commands("docked"), ["action_start"])

    def test_cleaning_swaps_start_for_pause(self):
        self.assertEqual(self.commands("cleaning"),
                         ["action_pause", "action_stop", "action_return"])

    def test_paused_resumes_stops_or_goes_home(self):
        self.assertEqual(self.commands("paused"),
                         ["action_start", "action_stop", "action_return"])

    def test_on_its_way_home_not_sent_home_again(self):
        self.assertEqual(self.commands("returning"),
                         ["action_start", "action_stop"])

    def test_idle_is_at_rest(self):
        self.assertEqual(self.commands("idle"), ["action_start", "action_return"])

    def test_nothing_while_unavailable(self):
        self.assertEqual(labels("vacuum.a", "unavailable",
                                supported_features=self.ROBOROCK), [])


class MediaPlayer(unittest.TestCase):
    def test_a_player_keeps_no_commands_in_the_menu(self):
        # Everything it used to offer is in the window that OK opens.
        self.assertEqual(labels("media_player.a", supported_features=186303), [])

    def test_the_menu_names_the_window_itself(self):
        self.assertEqual(menu("media_player.a", supported_features=186303),
                         ["action_media", "action_details"])


class Lock(unittest.TestCase):
    def test_only_what_the_lock_is_not_already(self):
        self.assertEqual(labels("lock.a", "locked", supported_features=1),
                         ["action_unlock", "action_unlatch"])
        self.assertEqual(labels("lock.a", "unlocked", supported_features=1),
                         ["action_lock", "action_unlatch"])
        self.assertEqual(labels("lock.a", "open", supported_features=1),
                         ["action_lock"])

    def test_the_latch_only_where_the_lock_can_draw_it(self):
        self.assertEqual(labels("lock.a", "locked", supported_features=0),
                         ["action_unlock"])

    def test_a_jammed_lock_is_offered_every_way_out(self):
        self.assertEqual(labels("lock.a", "jammed", supported_features=1),
                         ["action_lock", "action_unlock", "action_unlatch"])

    def test_nothing_while_it_moves_or_is_gone(self):
        for value in ("locking", "unlocking", "opening", "unavailable"):
            self.assertEqual(labels("lock.a", value, supported_features=1), [],
                             value)

    def test_neither_bolt_nor_latch_while_the_locks_own_door_is_open(self):
        def offered(door):
            store = support.build(
                entities=[support.entity("lock.a", "Schloss", device_id="dev_lock"),
                          support.entity("binary_sensor.tuer", "Tür",
                                         device_id="dev_lock", device_class="door"),
                          support.entity("binary_sensor.anderswo", "Andere Tür",
                                         device_id="dev_other", device_class="door")],
                states=[support.state("lock.a", "unlocked", supported_features=1),
                        support.state("binary_sensor.tuer", door),
                        support.state("binary_sensor.anderswo", "on")])
            return [a.label_key
                    for a in actions.commands_for(store, store.states["lock.a"])]
        self.assertEqual(offered("on"), [])
        self.assertEqual(offered("off"), ["action_lock", "action_unlatch"])

    def test_an_assumed_state_is_not_taken_at_its_word(self):
        self.assertEqual(labels("lock.a", "locked", supported_features=1,
                                assumed_state=True),
                         ["action_lock", "action_unlock", "action_unlatch"])


class Climate(unittest.TestCase):
    THERMOSTAT = 401  # target temperature, preset mode, turn on, turn off

    def test_modes_temperature_and_presets(self):
        self.assertEqual(
            labels("climate.a", supported_features=self.THERMOSTAT,
                   hvac_modes=["off", "heat"], preset_modes=["eco", "comfort"]),
            ["action_set_hvac", "action_set_temperature", "action_preset",
             "action_turn_off"])

    def test_a_thermostat_that_is_off_is_only_offered_switching_on(self):
        self.assertEqual(
            [label for label in labels("climate.a", "off",
                                       supported_features=self.THERMOSTAT,
                                       hvac_modes=["off", "heat"])
             if label.startswith("action_turn")],
            ["action_turn_on"])

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

    def test_a_dimmable_lamp_is_offered_a_brightness_slider(self):
        store = one("light.a", "on", supported_color_modes=["brightness"])
        [action] = actions.commands_for(store, store.states["light.a"])
        self.assertEqual((action.label_key, action.kind, action.data),
                         ("action_brightness", actions.SLIDER,
                          {"as": "brightness_pct", "min": 1, "max": 100,
                           "step": 5, "unit": "%"}))

    def test_colour_temperature_is_a_slider_over_the_lamps_range(self):
        store = one("light.a", "on", supported_color_modes=["color_temp"],
                    min_color_temp_kelvin=2202, max_color_temp_kelvin=4000)
        action = actions.commands_for(store, store.states["light.a"])[1]
        self.assertEqual((action.kind, action.data),
                         (actions.SLIDER, {"as": "color_temp_kelvin",
                                           "min": 2202, "max": 4000,
                                           "step": 100, "unit": "K"}))

    def test_a_lamp_that_names_no_range_gets_home_assistants(self):
        store = one("light.a", "on", supported_color_modes=["color_temp"])
        action = actions.commands_for(store, store.states["light.a"])[1]
        self.assertEqual((action.data["min"], action.data["max"]), (2700, 6500))

    def test_the_brightness_slider_starts_at_the_lamps_brightness(self):
        def start(value, **attributes):
            store = one("light.a", value, supported_color_modes=["brightness"],
                        **attributes)
            state = store.states["light.a"]
            return actions.slider_start(state, actions.commands_for(store, state)[0])
        self.assertEqual(start("on", brightness=128), 50)
        self.assertEqual(start("on", brightness=1), 1)
        self.assertEqual(start("off"), 1)

    def test_the_kelvin_slider_starts_where_the_lamp_is_only_in_white(self):
        def start(value, **attributes):
            store = one("light.a", value, supported_color_modes=["color_temp"],
                        min_color_temp_kelvin=2000, max_color_temp_kelvin=6000,
                        **attributes)
            state = store.states["light.a"]
            return actions.slider_start(state, actions.commands_for(store, state)[1])
        self.assertEqual(start("on", color_mode="color_temp",
                               color_temp_kelvin=3100), 3100)
        self.assertEqual(start("on", color_mode="hs", color_temp_kelvin=3100), 4000)
        self.assertEqual(start("off"), 4000)

    def test_a_press_lands_on_the_step_grid_and_the_ends_stay_reachable(self):
        brightness = {"min": 1, "max": 100, "step": 5}
        self.assertEqual(actions.slider_value(6, brightness), 5)
        self.assertEqual(actions.slider_value(1, brightness), 1)
        self.assertEqual(actions.slider_value(100, brightness), 100)
        kelvin = {"min": 2202, "max": 9009, "step": 100}
        self.assertEqual(actions.slider_value(2302, kelvin), 2300)
        self.assertEqual(actions.slider_value(9009, kelvin), 9009)
        self.assertEqual(actions.slider_value(8909, kelvin), 8900)

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
                          "action_arm_night"])

    def test_disarming_is_offered_even_where_no_arming_is(self):
        self.assertEqual(labels("alarm_control_panel.a", "armed_home",
                                supported_features=0),
                         ["action_disarm"])

    def test_setting_the_alarm_off_is_not_offered(self):
        actions_offered = labels("alarm_control_panel.a", "disarmed",
                                 supported_features=self.PANEL)
        self.assertNotIn("action_trigger", actions_offered)

    def test_not_the_mode_it_is_in_already(self):
        self.assertEqual(labels("alarm_control_panel.a", "armed_away",
                                supported_features=self.PANEL),
                         ["action_arm_home", "action_arm_night", "action_disarm"])

    def test_only_disarming_while_it_arms_counts_down_or_rings(self):
        for value in ("arming", "pending", "triggered"):
            self.assertEqual(labels("alarm_control_panel.a", value,
                                    supported_features=self.PANEL),
                             ["action_disarm"], value)

    def test_nothing_while_unavailable(self):
        self.assertEqual(labels("alarm_control_panel.a", "unavailable",
                                supported_features=self.PANEL), [])


class WaterHeater(unittest.TestCase):
    BOILER = 1 | 2 | 4 | 8

    def test_modes_temperature_away_and_power(self):
        self.assertEqual(
            labels("water_heater.a", "eco", supported_features=self.BOILER,
                   operation_list=["eco", "performance"]),
            ["action_operation_mode", "action_set_temperature",
             "action_away_mode", "action_turn_off"])

    def test_away_mode_says_what_to_flip(self):
        store = one("water_heater.a", "eco", supported_features=4)
        action = actions.commands_for(store, store.states["water_heater.a"])[0]
        self.assertEqual(action.data, {"flip": "away_mode"})

    def test_a_boiler_that_names_no_modes_is_not_offered_them(self):
        self.assertEqual(labels("water_heater.a", "eco", supported_features=2), [])


class CoverTilt(unittest.TestCase):
    VENETIAN = 1 | 2 | 4 | 8 | 16 | 32 | 64 | 128
    ROLLER = 1 | 2 | 4 | 8

    def menu(self, features):
        store = one("cover.a", "open", supported_features=features,
                    current_position=50, current_tilt_position=50)
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


class CoverState(unittest.TestCase):
    VENETIAN = 1 | 2 | 4 | 8 | 16 | 32 | 64 | 128

    def menu(self, value, **attributes):
        store = one("cover.a", value, supported_features=self.VENETIAN,
                    **attributes)
        return [a.label_key for a in actions.menu_actions(store, "cover.a")]

    def test_the_position_decides_where_there_is_one(self):
        self.assertNotIn("action_open", self.menu("open", current_position=100))
        self.assertIn("action_close", self.menu("open", current_position=100))
        self.assertNotIn("action_close", self.menu("closed", current_position=0))
        self.assertIn("action_open", self.menu("open", current_position=30))

    def test_the_state_decides_where_there_is_none(self):
        self.assertNotIn("action_open", self.menu("open"))
        self.assertNotIn("action_close", self.menu("closed"))

    def test_not_the_way_it_is_already_going_but_stop_always(self):
        opening = self.menu("opening", current_position=40)
        self.assertNotIn("action_open", opening)
        self.assertIn("action_stop", opening)
        self.assertNotIn("action_close", self.menu("closing", current_position=40))
        self.assertIn("action_stop", self.menu("closed", current_position=0))

    def test_slats_fully_one_way_are_not_offered_that_way(self):
        self.assertNotIn("action_open_tilt",
                         self.menu("open", current_tilt_position=100))
        self.assertNotIn("action_close_tilt",
                         self.menu("open", current_tilt_position=0))

    def test_nothing_but_details_while_unavailable(self):
        self.assertEqual(self.menu("unavailable"), ["action_details"])

    def test_an_assumed_state_is_not_taken_at_its_word(self):
        offered = self.menu("open", current_position=100,
                            current_tilt_position=100, assumed_state=True)
        self.assertIn("action_open", offered)
        self.assertIn("action_open_tilt", offered)


class Camera(unittest.TestCase):
    def test_ok_shows_the_live_picture_where_it_can_be_streamed(self):
        store = one("camera.a", "idle", supported_features=2)
        self.assertEqual(actions.default_action(store, "camera.a").kind,
                         actions.LIVE)
        self.assertEqual(menu("camera.a", "idle", supported_features=2),
                         ["action_live", "action_details"])

    def test_a_camera_without_a_stream_stays_a_picture(self):
        store = one("camera.a", "idle", supported_features=0)
        self.assertIsNone(actions.default_action(store, "camera.a"))
        self.assertEqual(menu("camera.a", "idle", supported_features=0),
                         ["action_details"])

    def test_nothing_while_unavailable(self):
        store = one("camera.a", "unavailable", supported_features=2)
        self.assertIsNone(actions.default_action(store, "camera.a"))


class Script(unittest.TestCase):
    def offered(self, value, **attributes):
        return [label for label in menu("script.a", value, **attributes)
                if label != "action_details"]

    def test_an_idle_script_can_be_run(self):
        self.assertEqual(self.offered("off", mode="single"), ["action_run"])

    def test_a_running_single_script_can_only_be_cancelled(self):
        self.assertEqual(self.offered("on", mode="single", current=1),
                         ["action_cancel"])

    def test_a_queue_with_room_takes_another_run(self):
        self.assertEqual(self.offered("on", mode="queued", current=1, max=10),
                         ["action_run", "action_cancel"])
        self.assertEqual(self.offered("on", mode="queued", current=10, max=10),
                         ["action_cancel"])

    def test_nothing_while_unavailable(self):
        self.assertEqual(self.offered("unavailable"), [])

    def test_cancelling_is_not_asked_about_as_switching_off(self):
        store = one("script.a", "on")
        self.assertFalse(actions.switches_off(store, "script.a", "turn_off"))


class Update(unittest.TestCase):
    def offered(self, value, features=1, **attributes):
        return "action_install" in menu("update.a", value,
                                        supported_features=features, **attributes)

    def test_only_where_an_update_is_waiting(self):
        self.assertTrue(self.offered("on"))
        self.assertFalse(self.offered("off"))
        self.assertFalse(self.offered("unavailable"))

    def test_a_skipped_version_can_still_be_installed(self):
        self.assertTrue(self.offered("off", latest_version="2.0",
                                     skipped_version="2.0"))
        self.assertFalse(self.offered("off", latest_version="2.1",
                                      skipped_version="2.0"))

    def test_not_where_the_integration_cannot_install(self):
        self.assertFalse(self.offered("on", features=0))

    def test_not_while_it_is_installing(self):
        self.assertFalse(self.offered("on", in_progress=True))


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

    def test_oscillating_says_what_to_flip(self):
        store = one("fan.a", "on", supported_features=2)
        action = actions.commands_for(store, store.states["fan.a"])[0]
        self.assertEqual(action.data, {"flip": "oscillating"})

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
            labels("valve.a", "open", supported_features=1 | 2 | 4 | 8,
                   current_position=50),
            ["action_open", "action_close", "action_stop", "action_position"])

    def test_a_valve_without_a_position_is_not_offered_one(self):
        self.assertNotIn("action_position",
                         labels("valve.a", "open", supported_features=1 | 2))

    def offered(self, value, **attributes):
        return labels("valve.a", value, supported_features=1 | 2 | 8,
                      **attributes)

    def test_not_the_way_it_is_already(self):
        self.assertEqual(self.offered("open"), ["action_close", "action_stop"])
        self.assertEqual(self.offered("closed"), ["action_open", "action_stop"])
        self.assertEqual(self.offered("open", current_position=100),
                         ["action_close", "action_stop"])

    def test_not_the_way_it_is_going(self):
        self.assertEqual(self.offered("opening", current_position=40),
                         ["action_close", "action_stop"])

    def test_nothing_while_unavailable(self):
        self.assertEqual(self.offered("unavailable"), [])

    def test_an_assumed_state_is_not_taken_at_its_word(self):
        self.assertEqual(self.offered("open", assumed_state=True),
                         ["action_open", "action_close", "action_stop"])

    def test_the_menu_says_open_and_close_not_on_and_off_as_well(self):
        self.assertEqual(menu("valve.a", "open", supported_features=1 | 2 | 8),
                         ["action_close", "action_stop", "action_details"])


class Flipping(unittest.TestCase):
    def resolve(self, attribute, value):
        store = one("media_player.a", **{attribute: value})
        action = actions.Action("x", actions.SERVICE, "d", "s",
                                {"flip": attribute})
        return actions.service_data(action, store.states["media_player.a"])

    def test_a_boolean_attribute_turns_around(self):
        self.assertEqual(self.resolve("is_volume_muted", False),
                         {"is_volume_muted": True})
        self.assertEqual(self.resolve("is_volume_muted", True),
                         {"is_volume_muted": False})

    def test_an_attribute_reported_as_on_or_off_turns_around_too(self):
        # A water heater says away_mode: "on", not True.
        self.assertEqual(self.resolve("away_mode", "off"), {"away_mode": True})
        self.assertEqual(self.resolve("away_mode", "on"), {"away_mode": False})

    def test_an_attribute_the_entity_never_mentions_counts_as_off(self):
        self.assertEqual(self.resolve("shuffle", None), {"shuffle": True})

    def test_the_rest_of_the_data_passes_through(self):
        action = actions.Action("x", actions.SERVICE, "d", "s",
                                {"flip": "shuffle", "entity_id": "light.a"})
        store = one("media_player.a", shuffle=True)
        self.assertEqual(actions.service_data(action,
                                              store.states["media_player.a"]),
                         {"shuffle": False, "entity_id": "light.a"})

    def test_without_a_state_nothing_is_invented(self):
        action = actions.Action("x", actions.SERVICE, "d", "s",
                                {"flip": "shuffle"})
        self.assertEqual(actions.service_data(action, None), {})


class Picking(unittest.TestCase):
    def test_a_choice_names_where_it_reads_from_and_writes_to(self):
        store = one("select.a", "one", options=["one", "two"])
        action = actions.default_action(store, "select.a")
        self.assertEqual(action.kind, actions.PICK)
        self.assertEqual(action.data, {"from": "options", "as": "option"})


if __name__ == "__main__":
    unittest.main()
