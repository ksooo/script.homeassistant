"""Home Assistant authentication.

Two ways to obtain a bearer token for the WebSocket API:

* a long-lived access token, used as is
* username and password, exchanged via ``/auth/login_flow`` for a short lived
  access token plus a refresh token

The login flow is walked step by step. Home Assistant declares the fields of
every step, so an instance with MFA enabled asks for its second factor through
the same code path, provided the caller supplies a ``prompt`` callback.
"""

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

# IndieAuth accepts a redirect_uri sharing the client_id's origin without
# fetching it, so any URL identifying the addon works. It is what Home
# Assistant shows for the session under Settings -> Security.
CLIENT_ID = "https://github.com/ksooo/script.homeassistant/"
REDIRECT_URI = CLIENT_ID

HANDLER = ["homeassistant", None]

# Renew this long before the token actually expires.
_EXPIRY_MARGIN = 60.0


class AuthError(Exception):
    pass


class AbortedError(AuthError):
    """The user cancelled an interactive login step."""


def _request(url, data=None, headers=None, form=False, timeout=15, verify_ssl=True):
    body = None
    request_headers = dict(headers or {})
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode("utf-8")
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode("utf-8")
            request_headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=body, headers=request_headers)
    context = None
    if url.startswith("https://") and not verify_ssl:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        payload = error.read().decode("utf-8", "replace")
        try:
            detail = json.loads(payload)
        except ValueError:
            detail = {}
        message = detail.get("error_description") or detail.get("message") or payload
        raise AuthError("%s: %s" % (error.code, message.strip()[:200]))
    except urllib.error.URLError as error:
        raise AuthError(str(error.reason))


class Authenticator:
    """Supplies bearer tokens, renewing them as needed."""

    def __init__(self, base_url, token="", username="", password="",
                 prompt=None, verify_ssl=True):
        self._base_url = base_url.rstrip("/")
        self._token = token.strip()
        self._username = username
        self._password = password
        self._prompt = prompt
        self._verify_ssl = verify_ssl
        self._access_token = ""
        self._refresh_token = ""
        self._expires_at = 0.0

    @property
    def uses_long_lived_token(self):
        return bool(self._token)

    def access_token(self):
        if self._token:
            return self._token
        if self._access_token and time.time() < self._expires_at - _EXPIRY_MARGIN:
            return self._access_token
        if self._refresh_token:
            try:
                return self._refresh()
            except AuthError:
                self._refresh_token = ""
        return self._login()

    def invalidate(self):
        """Drop the cached access token so the next call authenticates again."""
        self._access_token = ""
        self._expires_at = 0.0

    def _login(self):
        if not self._username or not self._password:
            raise AuthError("no credentials configured")

        flow = self._post("/auth/login_flow", {
            "client_id": CLIENT_ID,
            "handler": HANDLER,
            "redirect_uri": REDIRECT_URI,
        })

        answers = {"username": self._username, "password": self._password}
        while flow.get("type") == "form":
            step = self._answer_step(flow, answers)
            answers = {}
            flow = self._post("/auth/login_flow/%s" % flow["flow_id"],
                              dict(step, client_id=CLIENT_ID))

        if flow.get("type") != "create_entry":
            raise AuthError("login failed: %s" % flow.get("reason", flow.get("type")))

        return self._exchange_code(flow["result"])

    def _answer_step(self, flow, answers):
        errors = flow.get("errors") or {}
        if errors and not self._prompt:
            raise AuthError(errors.get("base", "invalid_auth"))

        step = {}
        for field in flow.get("data_schema") or []:
            name = field.get("name")
            if not name:
                continue
            if name in answers and not errors:
                step[name] = answers[name]
                continue
            if not self._prompt:
                raise AuthError(errors.get("base") or "step '%s' needs input" % name)
            value = self._prompt(field, flow.get("step_id", ""), errors)
            if value is None:
                raise AbortedError("login cancelled")
            step[name] = value
        return step

    def _exchange_code(self, code):
        token = self._post("/auth/token", {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": CLIENT_ID,
        }, form=True)
        self._refresh_token = token.get("refresh_token", "")
        return self._store(token)

    def _refresh(self):
        token = self._post("/auth/token", {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": CLIENT_ID,
        }, form=True)
        return self._store(token)

    def _store(self, token):
        self._access_token = token["access_token"]
        self._expires_at = time.time() + float(token.get("expires_in", 1800))
        return self._access_token

    def _post(self, path, data, form=False):
        return _request(self._base_url + path, data=data, form=form,
                        verify_ssl=self._verify_ssl)
