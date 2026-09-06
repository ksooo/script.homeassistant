"""Getting a connection open when the endpoint is unreliable."""

import unittest

from . import support  # noqa: F401  (puts the addon on the path)
from resources.lib.ha import client as ha_client


class FakeClient:
    """Stands in for HomeAssistant: fails a set number of handshakes."""

    made = []

    def __init__(self, *args, **kwargs):
        self.closed = False
        self.on_close = None
        FakeClient.made.append(self)

    def connect(self):
        failures = FakeClient.failures
        if len(FakeClient.made) <= failures:
            raise ha_client.HomeAssistantError("TLS handshake refused")
        if FakeClient.refuse_auth:
            raise ha_client.AuthFailed("token rejected")

    def close(self):
        self.closed = True


class Connecting(unittest.TestCase):
    def setUp(self):
        FakeClient.made = []
        FakeClient.failures = 0
        FakeClient.refuse_auth = False
        self.original = ha_client.HomeAssistant
        self.pause = ha_client._CONNECT_PAUSE
        ha_client.HomeAssistant = FakeClient
        ha_client._CONNECT_PAUSE = 0  # the pause is real, and not the point here
        self.session = ha_client.Session("http://ha.invalid", authenticator=None)

    def tearDown(self):
        ha_client.HomeAssistant = self.original
        ha_client._CONNECT_PAUSE = self.pause

    def test_a_flaky_endpoint_is_reached_without_waiting_out_the_backoff(self):
        FakeClient.failures = 2
        connected = self.session._connect()
        self.assertEqual(len(FakeClient.made), 3)
        self.assertFalse(connected.closed)

    def test_the_attempts_that_failed_are_closed_again(self):
        FakeClient.failures = 2
        self.session._connect()
        self.assertEqual([c.closed for c in FakeClient.made], [True, True, False])

    def test_giving_up_reports_the_last_failure(self):
        FakeClient.failures = 99
        with self.assertRaises(ha_client.HomeAssistantError) as caught:
            self.session._connect()
        self.assertIn("handshake refused", str(caught.exception))
        self.assertEqual(len(FakeClient.made), ha_client._CONNECT_ATTEMPTS)

    def test_a_rejected_token_is_not_worth_retrying(self):
        FakeClient.refuse_auth = True
        self.assertRaises(ha_client.AuthFailed, self.session._connect)
        self.assertEqual(len(FakeClient.made), 1)


class Urls(unittest.TestCase):
    def test_the_websocket_url_follows_the_scheme(self):
        self.assertEqual(ha_client.websocket_url("https://ha.invalid"),
                         "wss://ha.invalid/api/websocket")
        self.assertEqual(ha_client.websocket_url("http://ha.invalid:8123/"),
                         "ws://ha.invalid:8123/api/websocket")


if __name__ == "__main__":
    unittest.main()
