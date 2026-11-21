"""How the dashboard is cut into sections and groups."""

import unittest

from . import support
from resources.lib import sections


def house(extra_entities=(), extra_states=(), home=None, energy=None):
    entities = [
        support.entity("light.decke", "Deckenlampe", device_id="dev_lamp"),
        support.entity("binary_sensor.fenster", "Fenster", device_id="dev_sensor",
                       device_class="window"),
        support.entity("sensor.kueche_temperatur", "Temperatur", area_id="kueche",
                       device_class="temperature"),
        support.entity("sensor.cpu", "CPU Temperatur", area_id="kueche",
                       device_class="temperature"),
        support.entity("sensor.batterie", "Batterie", device_id="dev_sensor",
                       device_class="battery", category="diagnostic"),
        support.entity("lock.tuer", "Schloss", area_id="flur_ug"),
    ]
    states = [
        support.state("light.decke", "off"),
        support.state("binary_sensor.fenster", "on"),
        support.state("sensor.kueche_temperatur", "21.5"),
        support.state("sensor.cpu", "48"),
        support.state("sensor.batterie", "94"),
        support.state("lock.tuer", "locked"),
    ]
    return support.build(
        entities=list(entities) + list(extra_entities),
        states=list(states) + list(extra_states),
        devices=support.DEVICES, areas=support.AREAS, floors=support.FLOORS,
        home=home, energy=energy)


class AreaSections(unittest.TestCase):
    def test_groups_by_device_and_collects_the_rest(self):
        store = house()
        built = {s.key: s for s in sections.build(store, translate=support.untranslated)}
        kitchen = built["area:kueche"]

        self.assertEqual([g.title for g in kitchen.groups],
                         ["Fenstersensor", "others"])
        # The battery is diagnostic, so it belongs to maintenance, not here.
        self.assertEqual(kitchen.groups[0].entity_ids, ["binary_sensor.fenster"])
        self.assertEqual(sorted(kitchen.groups[1].entity_ids),
                         ["sensor.cpu", "sensor.kueche_temperatur"])

    def test_scenes_open_the_room_and_automations_close_it(self):
        store = house(
            extra_entities=[
                support.entity("automation.lueften", "Lüften", device_id="dev_sensor"),
                support.entity("automation.heizen", "Heizen", area_id="kueche"),
                support.entity("scene.kochen", "Kochen", device_id="dev_sensor"),
            ],
            extra_states=[
                support.state("automation.lueften", "on"),
                support.state("automation.heizen", "on"),
                support.state("scene.kochen", "2026-10-02T07:00:00+00:00"),
            ])
        built = {s.key: s for s in sections.build(store, translate=support.untranslated)}
        kitchen = built["area:kueche"]
        self.assertEqual([g.title for g in kitchen.groups],
                         ["scenes", "Fenstersensor", "others", "automations"])
        self.assertEqual(kitchen.groups[0].entity_ids, ["scene.kochen"])
        self.assertEqual(kitchen.groups[-1].entity_ids,
                         ["automation.heizen", "automation.lueften"])

    def test_a_devices_entities_stand_by_doing_then_kind_then_name(self):
        """What can be acted on first, and each kind together within that."""
        store = house(
            extra_entities=[
                support.entity("switch.zzz", "Zuletzt", device_id="dev_sensor"),
                support.entity("switch.aaa", "Anfang", device_id="dev_sensor"),
                support.entity("light.mitte", "Mitte", device_id="dev_sensor"),
            ],
            extra_states=[
                support.state("switch.zzz", "on"),
                support.state("switch.aaa", "on"),
                support.state("light.mitte", "off"),
            ])
        built = {s.key: s for s in sections.build(store, translate=support.untranslated)}
        sensor = built["area:kueche"].groups[0]
        # The binary sensor only reports, so it falls behind the switches even
        # though its kind sorts ahead of theirs.
        self.assertEqual(sensor.entity_ids,
                         ["light.mitte", "switch.aaa", "switch.zzz",
                          "binary_sensor.fenster"])

    def test_floors_and_rooms_keep_registry_order(self):
        store = house()
        options = sections.Options(hide_empty_areas=False)
        areas = [s for s in sections.build(store, options, translate=support.untranslated)
                 if s.kind == sections.AREA]
        self.assertEqual([(s.subtitle, s.title) for s in areas],
                         [("Keller", "Kellervorraum"), ("Keller", "Flur UG"),
                          ("Erdgeschoss", "Küche"), ("", "Mobile Geräte")])

    def test_empty_rooms_can_be_hidden(self):
        store = house()
        options = sections.Options(hide_empty_areas=True)
        titles = [s.title for s in sections.build(store, options, translate=support.untranslated)]
        self.assertNotIn("Mobile Geräte", titles)

    def test_empty_rooms_are_shown_by_default(self):
        titles = [s.title for s in sections.build(house(), translate=support.untranslated)]
        self.assertIn("Mobile Geräte", titles)


class Summaries(unittest.TestCase):
    def summary(self, key, **kwargs):
        home = {"shortcuts": [{"type": "summary", "key": key}]}
        store = house(home=home, **kwargs)
        return next(s for s in sections.build(store, translate=support.untranslated) if s.key == key)

    def test_room_headings_carry_the_floor(self):
        security = self.summary("security")
        self.assertEqual([g.title for g in security.groups],
                         ["Keller  -  Flur UG", "Erdgeschoss  -  Küche"])

    def test_climate_takes_the_rooms_own_sensors_only(self):
        climate = self.summary("climate")
        # sensor.cpu is a temperature too, but no room is measured by it.
        self.assertIn("sensor.kueche_temperatur", climate.entity_ids)
        self.assertNotIn("sensor.cpu", climate.entity_ids)

    def test_maintenance_lists_batteries_at_any_level(self):
        maintenance = self.summary("maintenance")
        self.assertEqual(maintenance.entity_ids, ["sensor.batterie"])

    def test_maintenance_keeps_a_battery_that_cannot_be_reached(self):
        maintenance = self.summary(
            "maintenance",
            extra_entities=[support.entity("sensor.batterie_2", "Batterie",
                                           device_id="dev_lamp", device_class="battery",
                                           category="diagnostic")],
            extra_states=[support.state("sensor.batterie_2", "unavailable")])
        self.assertEqual(sorted(maintenance.entity_ids),
                         ["sensor.batterie", "sensor.batterie_2"])

    def test_maintenance_leaves_updates_out(self):
        maintenance = self.summary(
            "maintenance",
            extra_entities=[support.entity("update.firmware", "Firmware",
                                           device_id="dev_sensor")],
            extra_states=[support.state("update.firmware", "on")])
        self.assertEqual(maintenance.entity_ids, ["sensor.batterie"])

    def test_maintenance_lists_problem_sensors_whatever_they_report(self):
        maintenance = self.summary(
            "maintenance",
            extra_entities=[support.entity("binary_sensor.stoerung", "Störung",
                                           device_id="dev_sensor",
                                           device_class="problem")],
            extra_states=[support.state("binary_sensor.stoerung", "off")])
        self.assertEqual(sorted(maintenance.entity_ids),
                         ["binary_sensor.stoerung", "sensor.batterie"])

    def test_media_players_are_a_summary_of_their_own(self):
        players = self.summary(
            "media_players",
            extra_entities=[support.entity("media_player.tv", "Fernseher",
                                           area_id="kueche")],
            extra_states=[support.state("media_player.tv", "playing")])
        self.assertEqual(players.entity_ids, ["media_player.tv"])
        self.assertEqual(players.title, "media_players")

    def test_a_shortcut_that_is_not_a_summary_is_passed_over(self):
        store = house(home={"shortcuts": [{"type": "entity",
                                           "entity_id": "light.decke"}]})
        self.assertEqual([s.key for s in sections.build(store, translate=support.untranslated)
                          if s.kind == sections.SUMMARY], [])

    def test_a_summary_with_nothing_to_show_is_left_out(self):
        store = house(home={"shortcuts": [{"type": "summary", "key": "weather"},
                                          {"type": "summary", "key": "energy"}]})
        self.assertEqual([s.key for s in sections.build(store, translate=support.untranslated)
                          if s.kind == sections.SUMMARY], [])

    def test_climate_takes_blinds_and_window_sensors(self):
        climate = self.summary(
            "climate",
            extra_entities=[support.entity("cover.rollladen", "Rollladen",
                                           device_class="shutter"),
                            support.entity("cover.markise", "Markise"),
                            support.entity("cover.tor", "Tor", device_class="garage")],
            extra_states=[support.state("cover.rollladen", "open"),
                          support.state("cover.markise", "closed"),
                          support.state("cover.tor", "closed")])
        # binary_sensor.fenster from the house is a window as well.
        self.assertEqual(sorted(climate.entity_ids),
                         ["binary_sensor.fenster", "cover.markise", "cover.rollladen",
                          "sensor.kueche_temperatur"])

    def test_security_takes_detectors_and_diagnostic_tamper_sensors(self):
        security = self.summary(
            "security",
            extra_entities=[support.entity("binary_sensor.rauch", "Rauch",
                                           device_class="smoke"),
                            support.entity("binary_sensor.sabotage", "Sabotage",
                                           device_class="tamper", category="diagnostic"),
                            support.entity("binary_sensor.batterie", "Batterie",
                                           device_class="battery", category="diagnostic")],
            extra_states=[support.state("binary_sensor.rauch", "off"),
                          support.state("binary_sensor.sabotage", "off"),
                          support.state("binary_sensor.batterie", "off")])
        self.assertIn("binary_sensor.rauch", security.entity_ids)
        self.assertIn("binary_sensor.sabotage", security.entity_ids)
        self.assertNotIn("binary_sensor.batterie", security.entity_ids)

    def test_hidden_shortcuts_are_skipped(self):
        store = house(home={"shortcuts": [
            {"type": "summary", "key": "light", "hidden": True}]})
        self.assertEqual([s.key for s in sections.build(store, translate=support.untranslated)
                          if s.kind == sections.SUMMARY], [])


class Statuses(unittest.TestCase):
    """The line under a summary, as Home Assistant's summary card writes it."""

    WORDS = {"summary_lights_on": "%d on", "summary_low_batteries": "%d low",
             "summary_locks_unlocked": "%d unlocked", "summary_playing": "%d playing"}

    def status(self, key, **kwargs):
        return sections.status(house(**kwargs), key, lambda name: self.WORDS.get(name, name))

    def test_lights_count_what_is_on(self):
        self.assertEqual(self.status("light"), "summary_lights_off")
        self.assertEqual(self.status(
            "light", extra_entities=[support.entity("light.stehlampe", "Stehlampe")],
            extra_states=[support.state("light.stehlampe", "on")]), "1 on")

    def test_a_light_group_is_not_counted_with_its_members(self):
        self.assertEqual(self.status(
            "light",
            extra_entities=[support.entity("light.alle", "Alle")],
            extra_states=[{"entity_id": "light.alle", "state": "on",
                           "attributes": {"entity_id": ["light.decke"]}}]),
            "summary_lights_off")

    def test_climate_gives_the_rooms_temperatures(self):
        self.assertEqual(self.status("climate"), "21.5°")

    def test_security_reports_an_open_lock_before_all_is_well(self):
        self.assertEqual(self.status("security"), "summary_secure")
        self.assertEqual(self.status(
            "security", extra_entities=[support.entity("lock.keller", "Keller")],
            extra_states=[support.state("lock.keller", "unlocked")]), "1 unlocked")

    def test_media_players_say_nothing_plays(self):
        self.assertEqual(self.status(
            "media_players", extra_entities=[support.entity("media_player.tv", "TV")],
            extra_states=[support.state("media_player.tv", "idle")]), "summary_not_playing")

    def test_maintenance_lists_what_wants_attention(self):
        self.assertEqual(self.status("maintenance"), "summary_all_good")
        self.assertEqual(self.status(
            "maintenance",
            extra_entities=[
                support.entity("sensor.akku", "Akku", device_id="dev_lamp",
                               device_class="battery", category="diagnostic"),
                support.entity("binary_sensor.stoerung", "Störung",
                               device_id="dev_lamp", device_class="problem"),
                support.entity("sensor.akku_2", "Akku", device_id="dev_lamp",
                               device_class="battery", category="diagnostic")],
            extra_states=[support.state("sensor.akku", "12"),
                          support.state("binary_sensor.stoerung", "on"),
                          support.state("sensor.akku_2", "unavailable")]),
            "summary_low_battery, summary_problem, summary_unavailable_device")

    def test_a_battery_on_the_charger_is_not_low(self):
        self.assertEqual(self.status(
            "maintenance",
            extra_entities=[
                support.entity("sensor.akku", "Akku", device_id="dev_lamp",
                               device_class="battery", category="diagnostic"),
                support.entity("binary_sensor.laedt", "Lädt", device_id="dev_lamp",
                               device_class="battery_charging")],
            extra_states=[support.state("sensor.akku", "12"),
                          support.state("binary_sensor.laedt", "on",
                                        device_class="battery_charging")]),
            "summary_all_good")


class Favourites(unittest.TestCase):
    def test_order_is_left_as_home_assistant_holds_it(self):
        order = ["lock.tuer", "light.decke", "binary_sensor.fenster"]
        store = house(home={"favorite_entities": order})
        favourites = next(s for s in sections.build(store, translate=support.untranslated)
                          if s.kind == sections.FAVOURITES)
        self.assertEqual(favourites.entity_ids, order)
        self.assertEqual([g.title for g in favourites.groups], [""])

    def test_entities_that_are_gone_drop_out(self):
        store = house(home={"favorite_entities": ["light.decke", "light.weg"]})
        favourites = next(s for s in sections.build(store, translate=support.untranslated)
                          if s.kind == sections.FAVOURITES)
        self.assertEqual(favourites.entity_ids, ["light.decke"])


if __name__ == "__main__":
    unittest.main()
