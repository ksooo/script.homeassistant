"""The cameras' own addresses kept per camera."""

import os
import shutil
import socket
import tempfile
import unittest

from . import support  # noqa: F401  (puts the addon on the path)
from resources.lib import direct


class Addresses(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.directory)

    def test_what_is_saved_is_loaded(self):
        addresses = {"camera.a": "rtsp://user:secret@192.168.1.20:554/Preview_01_main"}
        direct.save(self.directory, addresses)
        self.assertEqual(direct.load(self.directory), addresses)

    def test_nothing_saved_is_nothing_loaded(self):
        self.assertEqual(direct.load(self.directory), {})

    def test_a_damaged_file_is_nothing_loaded(self):
        with open(os.path.join(self.directory, direct.FILE_NAME), "w") as handle:
            handle.write("{not json")
        self.assertEqual(direct.load(self.directory), {})


class Cameras(unittest.TestCase):
    ENTITIES = [{"entity_id": "camera.garden", "device_id": "d1"},
                {"entity_id": "camera.door", "device_id": "d2"},
                {"entity_id": "camera.named", "device_id": "d1"}]
    DEVICES = [{"id": "d1", "name": "Reolink", "name_by_user": "Garden"},
               {"id": "d2", "name": "Door", "name_by_user": None}]

    def test_the_device_goes_in_front_of_the_entity(self):
        states = [{"entity_id": "camera.garden", "attributes": {"friendly_name": "Lens 1"}},
                  {"entity_id": "camera.door", "attributes": {"friendly_name": "Lens 1"}},
                  {"entity_id": "light.lamp", "attributes": {"friendly_name": "Lamp"}}]
        self.assertEqual(direct.cameras(states, self.ENTITIES, self.DEVICES),
                         [("Door Lens 1", "camera.door"), ("Garden Lens 1", "camera.garden")])

    def test_a_name_that_carries_the_device_is_left_as_it_is(self):
        states = [{"entity_id": "camera.named",
                   "attributes": {"friendly_name": "Garden Lens 2"}}]
        self.assertEqual(direct.cameras(states, self.ENTITIES, self.DEVICES),
                         [("Garden Lens 2", "camera.named")])

    def test_a_camera_without_a_device_keeps_its_name(self):
        states = [{"entity_id": "camera.yaml", "attributes": {"friendly_name": "Yard"}},
                  {"entity_id": "camera.bare", "attributes": {}}]
        self.assertEqual(direct.cameras(states, self.ENTITIES, self.DEVICES),
                         [("camera.bare", "camera.bare"), ("Yard", "camera.yaml")])


class Endpoint(unittest.TestCase):
    def test_host_and_port_as_given_or_by_default(self):
        self.assertEqual(direct.endpoint("rtsp://u:p@192.168.1.20:8554/a"),
                         ("192.168.1.20", 8554))
        self.assertEqual(direct.endpoint("rtsp://192.168.1.20/a"), ("192.168.1.20", 554))
        self.assertEqual(direct.endpoint("rtsps://camera.local/a"), ("camera.local", 322))
        self.assertEqual(direct.endpoint("http://192.168.1.20/flv?a=b"), ("192.168.1.20", 80))
        self.assertEqual(direct.endpoint("https://camera.local/a"), ("camera.local", 443))

    def test_other_schemes_are_not_an_address(self):
        for url in ("ftp://192.168.1.20/a", "rtsp:///a", "nonsense", ""):
            self.assertIsNone(direct.endpoint(url), url)

    def test_a_camera_that_does_not_answer_is_not_reachable(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        listener.close()
        self.assertFalse(direct.reachable("rtsp://127.0.0.1:%d/a" % port, timeout=0.5))

    def test_a_camera_that_answers_is_reachable(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        try:
            port = listener.getsockname()[1]
            self.assertTrue(direct.reachable("rtsp://127.0.0.1:%d/a" % port, timeout=0.5))
        finally:
            listener.close()


class Masked(unittest.TestCase):
    def test_the_password_is_left_out(self):
        self.assertEqual(direct.masked("rtsp://admin:secret@192.168.1.20:554/a"),
                         "rtsp://admin:***@192.168.1.20:554/a")

    def test_a_password_in_the_query_is_left_out(self):
        self.assertEqual(
            direct.masked("http://192.168.1.20/flv?port=1935&user=admin&password=secret"),
            "http://192.168.1.20/flv?port=1935&user=admin&password=***")

    def test_an_address_without_a_password_is_shown_as_it_is(self):
        self.assertEqual(direct.masked("rtsp://192.168.1.20/a"), "rtsp://192.168.1.20/a")
