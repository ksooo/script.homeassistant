"""Minimal RFC 6455 WebSocket client.

Kodi ships no WebSocket module and the Home Assistant registries are only
reachable over the WebSocket API, so the protocol is implemented here using
the standard library alone. Scope is deliberately narrow: client side, text
frames, no extensions.
"""

import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import threading
from urllib.parse import urlparse

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

_OP_CONT = 0x0
_OP_TEXT = 0x1
_OP_BINARY = 0x2
_OP_CLOSE = 0x8
_OP_PING = 0x9
_OP_PONG = 0xA

_MAX_PAYLOAD = 64 * 1024 * 1024


def _handshakes(secure):
    """The handshakes to try, in order.

    One classical curve comes first because the library's own choice is what
    breaks: OpenSSL 3.5 offers a hybrid post-quantum key share by default,
    which makes the hello large enough to be split over several TCP segments,
    and Home Assistant Cloud's SNI router hangs up on that without a word.
    Measured against it: as offered refused five times out of five, one
    classical curve carried the same connection in the same second.

    Every current server understands X25519, so leading with it costs nothing
    where the default would have worked. The rest of the ladder is for
    endpoints that want something else, and a server that hangs up mid
    handshake says nothing about why - the only way to learn is to offer less
    and see.
    """
    if not secure:
        return [("plain", None)]

    ladder = []
    if hasattr(ssl.SSLContext, "set_ecdh_curve"):
        ladder.append(("with one classical curve",
                       lambda context: context.set_ecdh_curve("X25519")))
    ladder.append(("as offered", None))
    if hasattr(ssl, "TLSVersion"):
        ladder.append(("over TLS 1.2",
                       lambda context: setattr(context, "maximum_version",
                                               ssl.TLSVersion.TLSv1_2)))
    return ladder


class WebSocketError(Exception):
    pass


class WebSocketTimeout(WebSocketError):
    pass


class WebSocketClosed(WebSocketError):
    def __init__(self, code=None, reason=""):
        super().__init__("connection closed (%s %s)" % (code, reason))
        self.code = code
        self.reason = reason


class WebSocket:
    def __init__(self, url, timeout=10.0, verify_ssl=True):
        self._url = url
        self._timeout = timeout
        self._verify_ssl = verify_ssl
        self._sock = None
        self._buf = b""
        self._send_lock = threading.Lock()
        self.peer = ""
        self.tls = ""
        self.strategy = ""

    def connect(self):
        parsed = urlparse(self._url)
        if parsed.scheme not in ("ws", "wss"):
            raise WebSocketError("unsupported scheme: %s" % parsed.scheme)

        secure = parsed.scheme == "wss"
        host = parsed.hostname
        port = parsed.port or (443 if secure else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = "%s?%s" % (path, parsed.query)

        sock, refused = None, []
        for label, tune in _handshakes(secure):
            try:
                sock = self._open(host, port, secure, tune)
                self.strategy = label
                break
            except ssl.SSLError as error:
                refused.append("%s (%s)" % (label, error))
        if sock is None:
            raise WebSocketError(
                "no handshake with %s succeeded (%s): %s"
                % (self.peer, ssl.OPENSSL_VERSION, "; ".join(refused)))

        self._sock = sock
        try:
            self._handshake(host, port, path, secure)
        except Exception:
            self.close()
            raise

    def _open(self, host, port, secure, tune=None):
        sock = socket.create_connection((host, port), self._timeout)
        sock.settimeout(self._timeout)
        try:
            self.peer = "%s:%d" % sock.getpeername()[:2]
        except OSError:
            self.peer = "%s:%d" % (host, port)
        if not secure:
            self.tls = ""
            return sock

        context = ssl.create_default_context()
        if not self._verify_ssl:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        if tune is not None:
            tune(context)
        try:
            wrapped = context.wrap_socket(sock, server_hostname=host)
        except Exception:
            sock.close()
            raise
        self.tls = "%s / %s" % (wrapped.version(), (wrapped.cipher() or ("?",))[0])
        return wrapped

    def settimeout(self, timeout):
        if self._sock is not None:
            self._sock.settimeout(timeout)

    def send(self, text):
        self._send_frame(_OP_TEXT, text.encode("utf-8"))

    def send_json(self, obj):
        self.send(json.dumps(obj, separators=(",", ":")))

    def recv(self):
        """Return the next text message, transparently handling control frames."""
        message = b""
        message_op = None
        while True:
            fin, opcode, payload = self._read_frame()

            if opcode == _OP_PING:
                self._send_frame(_OP_PONG, payload)
                continue
            if opcode == _OP_PONG:
                continue
            if opcode == _OP_CLOSE:
                code, reason = None, ""
                if len(payload) >= 2:
                    code = struct.unpack("!H", payload[:2])[0]
                    reason = payload[2:].decode("utf-8", "replace")
                try:
                    self._send_frame(_OP_CLOSE, payload[:2])
                except WebSocketError:
                    pass
                raise WebSocketClosed(code, reason)

            if opcode == _OP_CONT:
                if message_op is None:
                    raise WebSocketError("continuation frame without start")
            else:
                if message_op is not None:
                    raise WebSocketError("interleaved message frames")
                message_op = opcode

            message += payload
            if len(message) > _MAX_PAYLOAD:
                raise WebSocketError("message too large")
            if fin:
                if message_op == _OP_BINARY:
                    message, message_op = b"", None
                    continue
                return message.decode("utf-8")

    def recv_json(self):
        return json.loads(self.recv())

    def close(self):
        sock = self._sock
        if sock is None:
            return
        try:
            self._send_frame(_OP_CLOSE, struct.pack("!H", 1000))
        except Exception:
            pass
        self._sock = None
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()

    @property
    def connected(self):
        return self._sock is not None

    def _handshake(self, host, port, path, secure):
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        default_port = 443 if secure else 80
        host_header = host if port == default_port else "%s:%d" % (host, port)
        request = (
            "GET %s HTTP/1.1\r\n"
            "Host: %s\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n" % (path, host_header, key)
        )
        self._sock.sendall(request.encode("ascii"))

        header = self._read_until(b"\r\n\r\n")
        lines = header.decode("iso-8859-1").split("\r\n")
        status = lines[0].split(" ", 2)
        if len(status) < 2 or status[1] != "101":
            raise WebSocketError("handshake failed: %s" % lines[0])

        headers = {}
        for line in lines[1:]:
            if ":" in line:
                name, _, value = line.partition(":")
                headers[name.strip().lower()] = value.strip()

        expected = base64.b64encode(
            hashlib.sha1((key + _GUID).encode("ascii")).digest()
        ).decode("ascii")
        if headers.get("sec-websocket-accept") != expected:
            raise WebSocketError("handshake failed: bad accept token")

    def _read_until(self, marker):
        while marker not in self._buf:
            self._buf += self._read_some()
        index = self._buf.index(marker) + len(marker)
        data, self._buf = self._buf[:index], self._buf[index:]
        return data

    def _read_some(self):
        sock = self._sock
        if sock is None:
            raise WebSocketClosed()
        try:
            chunk = sock.recv(8192)
        except socket.timeout:
            raise WebSocketTimeout()
        except ssl.SSLWantReadError:
            raise WebSocketTimeout()
        except OSError as error:
            raise WebSocketError(str(error))
        if not chunk:
            raise WebSocketClosed()
        return chunk

    def _read_exact(self, count):
        while len(self._buf) < count:
            self._buf += self._read_some()
        data, self._buf = self._buf[:count], self._buf[count:]
        return data

    def _read_frame(self):
        first, second = struct.unpack("!BB", self._read_exact(2))
        fin = bool(first & 0x80)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F

        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        if length > _MAX_PAYLOAD:
            raise WebSocketError("frame too large")

        mask = self._read_exact(4) if masked else None
        payload = self._read_exact(length) if length else b""
        if mask:
            payload = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        return fin, opcode, payload

    def _send_frame(self, opcode, payload):
        header = struct.pack("!B", 0x80 | opcode)
        length = len(payload)
        if length < 126:
            header += struct.pack("!B", 0x80 | length)
        elif length < 65536:
            header += struct.pack("!BH", 0x80 | 126, length)
        else:
            header += struct.pack("!BQ", 0x80 | 127, length)

        mask = os.urandom(4)
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))

        with self._send_lock:
            sock = self._sock
            if sock is None:
                raise WebSocketClosed()
            try:
                sock.sendall(header + mask + masked)
            except OSError as error:
                raise WebSocketError(str(error))
