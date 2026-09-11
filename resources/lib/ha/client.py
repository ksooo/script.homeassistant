"""Home Assistant WebSocket API client."""

import json
import threading
import time
from urllib.parse import urlparse, urlunparse

from . import auth as ha_auth
from .wsclient import WebSocket, WebSocketClosed, WebSocketError, WebSocketTimeout

# Long enough to sit through Home Assistant's own heartbeat; liveness is
# checked by the ping command in Session instead.
_READ_TIMEOUT = 120.0
_COMMAND_TIMEOUT = 30.0
_PING_INTERVAL = 30.0
_RECONNECT_DELAYS = (2, 5, 10, 20, 30, 60)

# A refused handshake is often transient, so a few quick tries beat waiting
# out the backoff: an endpoint that answers one connection in three is then
# reached in seconds rather than minutes.
_CONNECT_ATTEMPTS = 4
_CONNECT_PAUSE = 1.0


class HomeAssistantError(Exception):
    def __init__(self, message, code=""):
        super().__init__(message)
        self.code = code


class AuthFailed(HomeAssistantError):
    pass


class NotConnected(HomeAssistantError):
    pass


def websocket_url(base_url):
    parsed = urlparse(base_url.rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = (parsed.path or "") + "/api/websocket"
    return urlunparse((scheme, parsed.netloc, path, "", "", ""))


class _Pending:
    __slots__ = ("event", "result", "error")

    def __init__(self):
        self.event = threading.Event()
        self.result = None
        self.error = None


class HomeAssistant:
    """A single authenticated WebSocket connection."""

    def __init__(self, base_url, authenticator, verify_ssl=True, log=None):
        self._url = websocket_url(base_url)
        self._auth = authenticator
        self._verify_ssl = verify_ssl
        self._log = log or (lambda message, level=0: None)

        self._ws = None
        self._id_lock = threading.Lock()
        self._next_id = 1
        self._pending = {}
        self._subscriptions = {}
        self._reader = None
        self._closing = False
        self.version = ""
        self.transport = ""
        # Invoked when the reader thread stops, so a drop is noticed at once
        # instead of at the next keepalive ping.
        self.on_close = None

    @property
    def connected(self):
        return self._ws is not None and self._ws.connected

    def connect(self):
        token = self._auth.access_token()
        websocket = WebSocket(self._url, timeout=15.0, verify_ssl=self._verify_ssl)
        websocket.connect()

        greeting = websocket.recv_json()
        if greeting.get("type") != "auth_required":
            websocket.close()
            raise HomeAssistantError("unexpected greeting: %s" % greeting.get("type"))

        websocket.send_json({"type": "auth", "access_token": token})
        reply = websocket.recv_json()
        if reply.get("type") == "auth_invalid":
            websocket.close()
            self._auth.invalidate()
            raise AuthFailed(reply.get("message", "authentication rejected"))
        if reply.get("type") != "auth_ok":
            websocket.close()
            raise HomeAssistantError("unexpected auth reply: %s" % reply.get("type"))

        self.version = reply.get("ha_version", "")
        websocket.settimeout(_READ_TIMEOUT)
        self._ws = websocket
        self._closing = False
        self._reader = threading.Thread(target=self._read_loop, name="ha-reader")
        self._reader.daemon = True
        self._reader.start()
        self.transport = "%s %s%s" % (
            websocket.peer, websocket.tls,
            " (%s)" % websocket.strategy if websocket.strategy else "")
        # At info level on purpose: without debug logging on, a log that shows
        # only the failures says nothing about what a success looked like.
        self._log("connected to Home Assistant %s via %s"
                  % (self.version, self.transport), 1)

    def close(self):
        self._closing = True
        websocket, self._ws = self._ws, None
        if websocket is not None:
            websocket.close()
        for pending in list(self._pending.values()):
            pending.error = NotConnected("connection closed")
            pending.event.set()
        self._pending.clear()
        self._subscriptions.clear()

    def command(self, type_, **payload):
        """Send a command and return its result."""
        message = dict(payload)
        message["type"] = type_
        message_id = self._send(message)
        pending = self._pending[message_id]
        try:
            if not pending.event.wait(_COMMAND_TIMEOUT):
                raise HomeAssistantError("timeout waiting for '%s'" % type_)
            if pending.error:
                raise pending.error
            return pending.result
        finally:
            self._pending.pop(message_id, None)

    def subscribe(self, callback, type_="subscribe_events", **payload):
        """Subscribe and return the subscription id."""
        message = dict(payload)
        message["type"] = type_
        message_id = self._send(message, subscription=callback)
        pending = self._pending[message_id]
        try:
            if not pending.event.wait(_COMMAND_TIMEOUT):
                raise HomeAssistantError("timeout waiting for subscription")
            if pending.error:
                self._subscriptions.pop(message_id, None)
                raise pending.error
            return message_id
        finally:
            self._pending.pop(message_id, None)

    def unsubscribe(self, subscription_id):
        self._subscriptions.pop(subscription_id, None)
        try:
            self.command("unsubscribe_events", subscription=subscription_id)
        except HomeAssistantError:
            pass

    def call_service(self, domain, service, data=None, target=None):
        payload = {"domain": domain, "service": service}
        if data:
            payload["service_data"] = data
        if target:
            payload["target"] = target
        return self.command("call_service", **payload)

    def _send(self, message, subscription=None):
        websocket = self._ws
        if websocket is None:
            raise NotConnected("not connected")
        with self._id_lock:
            message_id = self._next_id
            self._next_id += 1
            message["id"] = message_id
            self._pending[message_id] = _Pending()
            if subscription is not None:
                self._subscriptions[message_id] = subscription
            try:
                websocket.send_json(message)
            except WebSocketError as error:
                self._pending.pop(message_id, None)
                self._subscriptions.pop(message_id, None)
                raise NotConnected(str(error))
        return message_id

    def _read_loop(self):
        while True:
            try:
                message = self._ws.recv_json()
            except WebSocketTimeout:
                continue
            except (WebSocketClosed, WebSocketError, AttributeError, ValueError) as error:
                if not self._closing:
                    self._log("connection lost: %s" % error)
                self._fail_pending(NotConnected(str(error)))
                self._reader_stopped()
                return
            self._dispatch(message)

    def _dispatch(self, message):
        message_type = message.get("type")
        message_id = message.get("id")

        if message_type == "event":
            callback = self._subscriptions.get(message_id)
            if callback:
                try:
                    callback(message.get("event"))
                except Exception as error:  # a broken handler must not kill the reader
                    self._log("event handler failed: %s" % error, 4)
            return

        if message_type == "result":
            pending = self._pending.get(message_id)
            if pending is None:
                return
            if message.get("success"):
                pending.result = message.get("result")
            else:
                error = message.get("error") or {}
                pending.error = HomeAssistantError(
                    error.get("message", "unknown error"), error.get("code", ""))
            pending.event.set()
            return

        if message_type == "pong":
            pending = self._pending.get(message_id)
            if pending is not None:
                pending.event.set()

    def _reader_stopped(self):
        websocket, self._ws = self._ws, None
        if websocket is not None:
            try:
                websocket.close()
            except Exception:
                pass
        if self.on_close is not None and not self._closing:
            self.on_close()

    def _fail_pending(self, error):
        for pending in list(self._pending.values()):
            pending.error = error
            pending.event.set()


class Session:
    """Keeps a connection alive and rebuilds it after a drop.

    ``on_ready`` runs after every successful (re)connect and is where
    subscriptions and the initial data load belong.
    """

    def __init__(self, base_url, authenticator, on_ready=None, on_lost=None,
                 verify_ssl=True, log=None):
        self._base_url = base_url
        self._auth = authenticator
        self._on_ready = on_ready
        self._on_lost = on_lost
        self._verify_ssl = verify_ssl
        self._log = log or (lambda message, level=0: None)

        self._client = None
        self._thread = None
        self._wake = threading.Event()
        self._stopped = False
        self.last_error = ""

    @property
    def client(self):
        return self._client

    @property
    def connected(self):
        return self._client is not None and self._client.connected

    def start(self):
        self._stopped = False
        self._thread = threading.Thread(target=self._run, name="ha-session")
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        self._stopped = True
        self._wake.set()
        client, self._client = self._client, None
        if client is not None:
            client.close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def forget(self):
        """Let go of the callbacks. Only ever after stop().

        They are usually bound methods of whatever is being told about the
        connection, so a session that outlives its owner keeps the owner
        alive with it.
        """
        self._on_ready = self._on_lost = None

    def _run(self):
        attempt = 0
        while not self._stopped:
            client = None
            phase = "connect"
            try:
                client = self._connect()
                self._client = client
                self.last_error = ""
                attempt = 0
                phase = "load"
                on_ready = self._on_ready
                if on_ready:
                    on_ready(client)
                phase = "run"
                self._keepalive(client)
            except ha_auth.AbortedError:
                self.last_error = "cancelled"
                on_lost = self._on_lost
                if on_lost:
                    on_lost(self.last_error)
                return
            except Exception as error:
                self.last_error = str(error)
                self._log("session error while %s: %s" % (phase, error), 3)
            finally:
                # Without this a connection whose load failed would stay open,
                # reader thread and all, and every retry would add another.
                if client is not None:
                    client.close()

            self._client = None
            on_lost = self._on_lost
            if on_lost and not self._stopped:
                on_lost(self.last_error)
            if self._stopped:
                return

            delay = _RECONNECT_DELAYS[min(attempt, len(_RECONNECT_DELAYS) - 1)]
            attempt += 1
            self._wake.wait(delay)
            self._wake.clear()

    def _connect(self):
        """Open a connection, giving a refused handshake a few quick tries."""
        last = None
        for attempt in range(1, _CONNECT_ATTEMPTS + 1):
            client = HomeAssistant(self._base_url, self._auth,
                                   verify_ssl=self._verify_ssl, log=self._log)
            client.on_close = self._wake.set
            try:
                client.connect()
                return client
            except (ha_auth.AbortedError, AuthFailed):
                client.close()
                raise
            except Exception as error:
                last = error
                client.close()
                if attempt == _CONNECT_ATTEMPTS or self._stopped:
                    break
                self._wake.wait(_CONNECT_PAUSE)
                self._wake.clear()
        raise last

    def _keepalive(self, client):
        try:
            while not self._stopped and client.connected:
                self._wake.wait(_PING_INTERVAL)
                self._wake.clear()
                if self._stopped or not client.connected:
                    break
                client.command("ping")
        finally:
            client.close()
