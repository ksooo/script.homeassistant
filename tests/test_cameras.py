"""Camera stills kept on disk, so that a row has one at once."""

import os
import shutil
import tempfile
import unittest

from . import support  # noqa: F401  (puts the addon on the path)
from resources.lib import cameras


class Stills(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory)

    def snapshots(self):
        return cameras.Snapshots("http://ha", self.directory)

    def test_a_camera_never_seen_has_no_still(self):
        self.assertEqual(self.snapshots().latest("camera.a"), "")

    def test_the_stills_alternate_and_the_last_one_written_is_the_newest(self):
        snapshots = self.snapshots()
        first = snapshots.keep("camera.a", b"one")
        second = snapshots.keep("camera.a", b"two")
        self.assertNotEqual(first, second)
        self.assertEqual(snapshots.latest("camera.a"), second)
        self.assertEqual(snapshots.keep("camera.a", b"three"), first)

    def test_a_restart_finds_the_newest_still_and_writes_over_the_other(self):
        earlier = self.snapshots()
        older = earlier.keep("camera.a", b"one")
        newer = earlier.keep("camera.a", b"two")
        os.utime(older, (1000, 1000))
        os.utime(newer, (2000, 2000))
        later = self.snapshots()
        self.assertEqual(later.latest("camera.a"), newer)
        self.assertEqual(later.keep("camera.a", b"three"), older)
