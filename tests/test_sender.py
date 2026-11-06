"""Commands handed to the background sender."""

import threading
import unittest

from . import support  # noqa: F401  (puts the addon on the path)
from resources.lib import sender


class Sending(unittest.TestCase):
    def test_commands_go_out_in_order_and_every_answer_is_kept(self):
        sent = []
        commands = sender.Sender()
        commands.send(lambda: sent.append("left") or True, "left")
        commands.send(lambda: sent.append("stop") or False, "stop")
        commands.close(5)
        self.assertEqual(sent, ["left", "stop"])
        self.assertEqual(commands.answers(), [("left", True), ("stop", False)])
        self.assertEqual(commands.answers(), [])

    def test_busy_until_the_answer_is_in(self):
        release = threading.Event()
        commands = sender.Sender()
        commands.send(lambda: release.wait(5), "zoom_in")
        self.assertTrue(commands.busy)
        release.set()
        commands.close(5)
        self.assertFalse(commands.busy)


if __name__ == "__main__":
    unittest.main()
