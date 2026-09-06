"""The hand written WebSocket framing.

The client is only ever exercised against Home Assistant, so these tests feed
it frames built by hand and read back what it writes.
"""

import struct
import unittest

from . import support  # noqa: F401  (puts the addon on the path)
from resources.lib.ha import wsclient


class FakeSocket:
    """Stands in for a connected socket: canned input, recorded output."""

    def __init__(self, incoming=b""):
        self.incoming = incoming
        self.sent = b""

    def recv(self, size):
        chunk, self.incoming = self.incoming[:size], self.incoming[size:]
        return chunk

    def sendall(self, data):
        self.sent += data

    def settimeout(self, timeout):
        pass


def server_frame(opcode, payload, fin=True):
    """A frame as a server sends it: no mask, minimal length encoding."""
    header = struct.pack("!B", (0x80 if fin else 0) | opcode)
    if len(payload) < 126:
        header += struct.pack("!B", len(payload))
    elif len(payload) < 65536:
        header += struct.pack("!BH", 126, len(payload))
    else:
        header += struct.pack("!BQ", 127, len(payload))
    return header + payload


def socket_with(*frames):
    websocket = wsclient.WebSocket("wss://example.invalid/api/websocket")
    websocket._sock = FakeSocket(b"".join(frames))
    return websocket


class Reading(unittest.TestCase):
    def test_a_text_frame_comes_back_as_text(self):
        websocket = socket_with(server_frame(0x1, "häuser".encode("utf-8")))
        self.assertEqual(websocket.recv(), "häuser")

    def test_a_split_message_is_put_back_together(self):
        websocket = socket_with(server_frame(0x1, b"Ho", fin=False),
                                server_frame(0x0, b"me", fin=True))
        self.assertEqual(websocket.recv(), "Home")

    def test_the_long_length_forms_are_understood(self):
        for size in (125, 126, 70000):
            websocket = socket_with(server_frame(0x1, b"x" * size))
            self.assertEqual(len(websocket.recv()), size)

    def test_a_ping_is_answered_and_does_not_surface(self):
        websocket = socket_with(server_frame(0x9, b"beat"),
                                server_frame(0x1, b"after"))
        self.assertEqual(websocket.recv(), "after")
        self.assertEqual(websocket._sock.sent[0] & 0x0F, 0xA)  # pong
        self.assertIn(b"beat", _unmask(websocket._sock.sent))

    def test_a_close_frame_ends_the_conversation(self):
        websocket = socket_with(server_frame(0x8, struct.pack("!H", 1000) + b"bye"))
        with self.assertRaises(wsclient.WebSocketClosed) as caught:
            websocket.recv()
        self.assertEqual(caught.exception.code, 1000)

    def test_a_silent_socket_counts_as_closed(self):
        websocket = socket_with(b"")
        self.assertRaises(wsclient.WebSocketClosed, websocket.recv)


class Writing(unittest.TestCase):
    def test_what_is_sent_is_masked_as_the_protocol_demands(self):
        websocket = socket_with()
        websocket.send("Home")
        sent = websocket._sock.sent
        self.assertEqual(sent[0], 0x81)          # final text frame
        self.assertTrue(sent[1] & 0x80)          # mask bit set
        self.assertEqual(sent[1] & 0x7F, 4)      # payload length
        self.assertEqual(_unmask(sent), b"Home")

    def test_a_long_payload_switches_length_form(self):
        websocket = socket_with()
        websocket.send("x" * 200)
        self.assertEqual(websocket._sock.sent[1] & 0x7F, 126)
        self.assertEqual(_unmask(websocket._sock.sent), b"x" * 200)

    def test_json_goes_out_compactly(self):
        websocket = socket_with()
        websocket.send_json({"type": "auth", "id": 1})
        self.assertEqual(_unmask(websocket._sock.sent),
                         b'{"type":"auth","id":1}')

    def test_sending_without_a_socket_says_so(self):
        websocket = wsclient.WebSocket("wss://example.invalid/")
        self.assertRaises(wsclient.WebSocketClosed, websocket.send, "hello")


def _unmask(frame):
    """Strips a client frame back down to its payload."""
    length = frame[1] & 0x7F
    offset = 2
    if length == 126:
        length = struct.unpack("!H", frame[2:4])[0]
        offset = 4
    elif length == 127:
        length = struct.unpack("!Q", frame[2:10])[0]
        offset = 10
    mask = frame[offset:offset + 4]
    payload = frame[offset + 4:offset + 4 + length]
    return bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))


if __name__ == "__main__":
    unittest.main()
