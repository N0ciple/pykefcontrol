"""A fake KEF speaker for tests: stdlib HTTP server in background threads.

Serves the same API on HTTP and/or HTTPS (``trustme`` certificates), so it works
for both the blocking and the asyncio client. All listeners of one
:class:`FakeSpeaker` share the same state (store, event queues, users).

The request signature check (``require_auth``) is an INDEPENDENT implementation
written from ``kef-app/findings/secure_api.md`` section 3b; it deliberately does
not import ``pykefcontrol._auth``.
"""

from __future__ import annotations

import base64
import contextlib
import copy
import hashlib
import hmac
import json
import socket
import ssl
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

import trustme

HOST = "127.0.0.1"
CONTROL_PATH = "player:player/control"
PLAY_DATA_PATH = "player:player/data"


ADD_USER_EXISTS = (
    b'{"error":{"name":"error","message":"Error while adding a new user: '
    b'given name already exists","title":"Error"}}'
)


def _not_found(path: str) -> dict[str, Any]:
    return {
        "error": {
            "name": "CMAbstractWorker::invalidPath",
            "message": f"Node at path '{path}' does not exist",
            "title": "Error",
        }
    }


def typed(type_name: str, value: Any) -> dict[str, Any]:
    """``{"type": t, t: value}`` (the API's typed value)."""
    return {"type": type_name, type_name: value}


def free_port() -> int:
    """A TCP port nobody listens on (connection refused)."""
    with socket.socket() as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def player_data(state: str = "playing") -> dict[str, Any]:
    return {
        "state": state,
        "status": {"duration": 215000},
        "controls": {"pause": True, "next_": True, "previous": False, "seekTime": True},
        "trackRoles": {
            "title": "Song",
            "icon": "http://img/cover.jpg",
            "mediaData": {
                "metaData": {"artist": "Artist", "album": "Album", "serviceID": "spotify"},
                "resources": [
                    {"codec": "flac", "sampleFrequency": 44100, "nrAudioChannels": 2},
                ],
            },
        },
    }


def default_store() -> dict[str, Any]:
    return {
        "player:volume": typed("i32_", 30),
        "settings:/mediaPlayer/mute": typed("bool_", False),
        "settings:/mediaPlayer/playMode": typed("playerPlayMode", "normal"),
        "settings:/kef/play/physicalSource": typed("kefPhysicalSource", "wifi"),
        "settings:/kef/host/speakerStatus": typed("kefSpeakerStatus", "powerOn"),
        "settings:/deviceName": typed("string_", "Living room"),
        "settings:/kef/host/modelName": typed("string_", "LS50WII"),
        "settings:/kef/host/firmwareVersion": typed("string_", "420.390.\ufffd.070.0000"),
        "settings:/version": typed("string_", "4.2.1.0x869cad1"),
        "settings:/releasetext": typed("string_", "LS50WII_V42100"),
        "settings:/kef/host/serialNumber": typed("string_", "SN123"),
        "settings:/kef/host/hardwareVersion": typed("string_", "HW1"),
        "settings:/system/primaryMacAddress": typed("string_", "AA:BB:CC:DD:EE:FF"),
        "settings:/kef/host/maximumVolume": typed("i32_", 80),
        "settings:/kef/host/volumeStep": typed("i32_", 5),
        PLAY_DATA_PATH: player_data("playing"),
        "player:player/data/playTime": typed("i64_", 42000),
    }


@dataclass
class Recorded:
    """One request received by the fake speaker."""

    method: str
    path: str  #: without query string
    query: dict[str, str]
    headers: dict[str, str]  #: lower-case names
    body: bytes
    scheme: str
    target: str = ""  #: raw request target (path + query)
    status: int | None = None
    auth_ok: bool | None = None  #: signature verdict (TLS POSTs only)

    @property
    def json(self) -> Any:
        return json.loads(self.body) if self.body else None


@dataclass
class _Queue:
    subs: dict[str, str] = field(default_factory=dict)  # path -> subscription type
    events: list[dict[str, Any]] = field(default_factory=list)


class PKI:
    """A trustme CA with a good leaf (IP 127.0.0.1) and a bad one (other IP)."""

    def __init__(self) -> None:
        self.ca = trustme.CA()
        self.good = self.ca.issue_cert("127.0.0.1")
        self.bad = self.ca.issue_cert("192.0.2.1")
        self.ca_pem: str = self.ca.cert_pem.bytes().decode()


class Listener:
    """One HTTP or HTTPS port of a :class:`FakeSpeaker`."""

    def __init__(self, speaker: FakeSpeaker, cert: trustme.LeafCert | None, port: int = 0) -> None:
        self.speaker = speaker
        self.scheme = "https" if cert else "http"
        self.port = port
        self._ctx: ssl.SSLContext | None = None
        if cert is not None:
            self._ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            cert.configure_cert(self._ctx)
        self._conns: set[socket.socket] = set()
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.start()

    def start(self) -> None:
        listener = self

        class Server(ThreadingHTTPServer):
            daemon_threads = True
            allow_reuse_address = True

            def get_request(self) -> tuple[Any, Any]:
                sock, addr = super().get_request()
                if listener._ctx is not None:
                    sock = listener._ctx.wrap_socket(
                        sock, server_side=True, do_handshake_on_connect=False
                    )
                with listener._lock:
                    listener._conns.add(sock)
                return sock, addr

            def shutdown_request(self, request: Any) -> None:
                with listener._lock:
                    listener._conns.discard(request)
                super().shutdown_request(request)

            def handle_error(self, request: Any, client_address: Any) -> None:
                pass  # TLS failures and aborted connections are expected in tests

        handler = type("Handler", (_Handler,), {"listener": self})
        self._server = Server((HOST, self.port), handler)
        self.port = int(self._server.server_address[1])
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop listening and cut open connections (the port then refuses connections)."""
        server, self._server = self._server, None
        if server is None:
            return
        server.shutdown()
        server.server_close()
        with self._lock:
            conns, self._conns = list(self._conns), set()
        for sock in conns:
            with contextlib.suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)
        with self.speaker.cond:
            self.speaker.cond.notify_all()


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"  # one request per connection: no stale keep-alive
    listener: Listener

    def setup(self) -> None:
        super().setup()
        if self.listener.scheme == "https":
            self.connection.do_handshake()

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        self._serve("GET")

    def do_POST(self) -> None:
        self._serve("POST")

    def _serve(self, method: str) -> None:
        speaker = self.listener.speaker
        parts = urlsplit(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        rec = Recorded(
            method=method,
            path=parts.path,
            query={k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()},
            headers={k.lower(): v for k, v in self.headers.items()},
            body=body,
            scheme=self.listener.scheme,
            target=self.path,
        )
        with speaker.cond:
            speaker.requests.append(rec)
        if speaker.drop_connections:
            self.close_connection = True
            with contextlib.suppress(OSError):
                self.connection.shutdown(socket.SHUT_RDWR)
            return
        if speaker.response_delay:
            time.sleep(speaker.response_delay)
        status, payload = speaker.handle(rec)
        rec.status = status
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class FakeSpeaker:
    """In-memory speaker. Tests may mutate it from the test thread.

    Knobs:

    * ``require_auth``: POSTs over TLS (except ``webserver:addUser``) need a valid
      ``Authorization: HMAC_SHA256`` header for a provisioned user, else 401.
    * ``fail_signed``: the next N signed POSTs answer 401 (valid signature or not).
    * ``drop_connections``: accept, read the request, close without answering.
    * ``response_delay``: seconds to wait before answering (timeouts).
    * ``max_poll_wait``: cap on a long-poll duration (keeps tests fast).
    * ``overrides``: API path -> fixed (status, body) answer, for error cases.
    * ``new_queue_on_modify``: next ``modifyQueue`` returns a *new* queue id even if
      an existing one is passed (the speaker "lost" the queue).
    * ``apply_delay``: API path -> seconds before a ``setData`` value becomes
      visible (the real speaker applies EQ profile writes ~70 ms later).
    """

    def __init__(self, *, require_auth: bool = False, max_poll_wait: float = 0.2) -> None:
        self.cond = threading.Condition()
        self.store: dict[str, Any] = default_store()
        self.rows: dict[str, list[dict[str, Any]]] = {}
        self.users: dict[str, str] = {}
        self.requests: list[Recorded] = []
        self.activations: list[tuple[str, Any]] = []
        self.controls: list[dict[str, Any]] = []
        self.queues: dict[str, _Queue] = {}
        self.listeners: list[Listener] = []
        self.require_auth = require_auth
        self.fail_signed = 0
        self.drop_connections = False
        self.response_delay = 0.0
        self.max_poll_wait = max_poll_wait
        self.overrides: dict[str, tuple[int, bytes]] = {}
        self.new_queue_on_modify = False
        self.apply_delay: dict[str, float] = {}

    # --- lifecycle ---------------------------------------------------------------

    host = HOST

    def add_http(self, port: int = 0) -> Listener:
        listener = Listener(self, None, port)
        self.listeners.append(listener)
        return listener

    def add_https(self, cert: trustme.LeafCert, port: int = 0) -> Listener:
        listener = Listener(self, cert, port)
        self.listeners.append(listener)
        return listener

    def _port(self, scheme: str) -> int:
        for listener in self.listeners:
            if listener.scheme == scheme:
                return listener.port
        raise LookupError(f"no {scheme} listener")

    @property
    def http_port(self) -> int:
        return self._port("http")

    @property
    def https_port(self) -> int:
        return self._port("https")

    def stop(self) -> None:
        """Stop every listener (clients get connection errors)."""
        for listener in self.listeners:
            listener.stop()

    def restart(self) -> None:
        """Listen again on the same ports."""
        for listener in self.listeners:
            if listener._server is None:
                listener.start()

    close = stop

    # --- test helpers -------------------------------------------------------------

    def set(self, path: str, value: Any) -> None:
        """Change a value as if done from the speaker's front panel (emits events)."""
        with self.cond:
            self.store[path] = value
            self._notify(path, value)

    def emit(self, event: dict[str, Any]) -> None:
        """Push a raw event to every queue subscribed to ``event["path"]``."""
        with self.cond:
            for queue in self.queues.values():
                if event["path"] in queue.subs:
                    queue.events.append(copy.deepcopy(event))
            self.cond.notify_all()

    def forget_queues(self) -> None:
        """Simulate queue expiry: pollQueue then answers 500."""
        with self.cond:
            self.queues.clear()
            self.cond.notify_all()

    def forget_users(self) -> None:
        """Simulate a speaker that lost its users (e.g. factory reset)."""
        self.users.clear()

    def clear_requests(self) -> None:
        with self.cond:
            self.requests.clear()

    def requests_to(self, path: str, method: str | None = None) -> list[Recorded]:
        with self.cond:
            return [
                r
                for r in self.requests
                if r.path == path and (method is None or r.method == method)
            ]

    def posts(self, scheme: str | None = None) -> list[Recorded]:
        with self.cond:
            return [
                r
                for r in self.requests
                if r.method == "POST" and (scheme is None or r.scheme == scheme)
            ]

    def set_data_calls(self) -> list[dict[str, Any]]:
        """Decoded bodies of every ``setData`` POST, minus provisioning."""
        calls = [r.json for r in self.requests_to("/api/setData", "POST")]
        return [c for c in calls if c["path"] != "webserver:addUser"]

    # --- request handling ------------------------------------------------------------

    def handle(self, rec: Recorded) -> tuple[int, Any]:
        if rec.method == "POST" and rec.scheme == "https" and self.require_auth:
            exempt = rec.path == "/api/setData" and _json_or_none(rec.body, "path") == (
                "webserver:addUser"
            )
            if not exempt:
                rec.auth_ok = self._check_signature(rec)
                if not rec.auth_ok:
                    return 401, b"unauthorized"
        api_path = rec.query.get("path") or _json_or_none(rec.body, "path")
        if api_path in self.overrides:
            return self.overrides[api_path]
        try:
            if rec.method == "GET":
                if rec.path == "/api/getData":
                    return self._get_data(rec)
                if rec.path == "/api/getRows":
                    return self._get_rows(rec)
                if rec.path == "/api/event/pollQueue":
                    return self._poll(rec)
            elif rec.method == "POST":
                if rec.path == "/api/setData":
                    return self._set_data(rec)
                if rec.path == "/api/event/modifyQueue":
                    return self._modify_queue(rec)
        except (ValueError, KeyError, TypeError) as err:
            return 400, f"bad request: {err!r}".encode()
        return 404, b"not found"

    def _get_data(self, rec: Recorded) -> tuple[int, Any]:
        path = rec.query["path"]
        with self.cond:
            if path not in self.store:
                return 500, _not_found(path)
            return 200, [copy.deepcopy(self.store[path])]

    def _get_rows(self, rec: Recorded) -> tuple[int, Any]:
        path = rec.query["path"]
        first, last = int(rec.query["from"]), int(rec.query["to"])
        with self.cond:
            if path not in self.rows:
                return 500, _not_found(path)
            rows = self.rows[path]
            return 200, {"rows": rows[first : last + 1], "rowsCount": len(rows), "rowsVersion": 1}

    def _set_data(self, rec: Recorded) -> tuple[int, Any]:
        payload = json.loads(rec.body)
        path, role = payload["path"], payload.get("role")
        if role is None:
            return 400, b"missing role"
        value = payload.get("value")
        with self.cond:
            if role == "value":
                delay = self.apply_delay.get(path)
                if delay:
                    timer = threading.Timer(delay, self.set, (path, value))
                    timer.daemon = True
                    timer.start()
                else:
                    self.store[path] = value
                    self._notify(path, value)
            elif role == "activate":
                self.activations.append((path, value))
                if path == "webserver:addUser":
                    name = value["name"]
                    if name in self.users:
                        return 500, ADD_USER_EXISTS
                    self.users[name] = value["password"]
                    return 200, b"null"
                elif path == CONTROL_PATH:
                    self._control(value)
            else:
                return 400, b"unknown role"
        return 200, {}

    def _control(self, value: dict[str, Any]) -> None:
        self.controls.append(value)
        if value.get("control") == "pause":
            data = copy.deepcopy(self.store[PLAY_DATA_PATH])
            data["state"] = "paused" if data["state"] == "playing" else "playing"
            self.store[PLAY_DATA_PATH] = data
            self._notify(PLAY_DATA_PATH, data)

    def _notify(self, path: str, value: Any) -> None:
        """Queue an event (caller holds ``cond``)."""
        for queue in self.queues.values():
            kind = queue.subs.get(path)
            if kind is None or kind.startswith("rows"):
                continue
            event: dict[str, Any] = {"path": path, "itemType": "update"}
            if kind in ("itemWithValue", "itemWithRoles"):
                event["itemValue"] = copy.deepcopy(value)
            queue.events.append(event)
        self.cond.notify_all()

    def _modify_queue(self, rec: Recorded) -> tuple[int, Any]:
        payload = json.loads(rec.body)
        queue_id = payload.get("queueId")
        with self.cond:
            if self.new_queue_on_modify or queue_id not in self.queues:
                self.new_queue_on_modify = False
                queue_id = "{" + str(uuid.uuid4()) + "}"
                self.queues[queue_id] = _Queue()
            queue = self.queues[queue_id]
            for sub in payload.get("unsubscribe", []):
                queue.subs.pop(sub["path"], None)
            for sub in payload.get("subscribe", []):
                queue.subs[sub["path"]] = sub["type"]
        return 200, queue_id  # a JSON string

    def _poll(self, rec: Recorded) -> tuple[int, Any]:
        queue_id = rec.query["queueId"]
        wait = min(float(rec.query.get("timeout", "0")), self.max_poll_wait)
        deadline = time.monotonic() + wait
        with self.cond:
            while True:
                queue = self.queues.get(queue_id)
                if queue is None:
                    return 500, {"error": {"message": "Unknown queue"}}
                remaining = deadline - time.monotonic()
                if queue.events or remaining <= 0:
                    events, queue.events = queue.events, []
                    return 200, events
                self.cond.wait(remaining)

    # --- signature check (independent of pykefcontrol._auth) ---------------------------

    def _check_signature(self, rec: Recorded) -> bool:
        header = rec.headers.get("authorization")
        if not header:
            return False
        with self.cond:
            if self.fail_signed > 0:
                self.fail_signed -= 1
                return False
        scheme, _, token = header.partition(" ")
        if scheme != "HMAC_SHA256":
            return False
        try:
            user_b64, nonce_b64, ts, signature = token.split(".")
            user = base64.b64decode(user_b64, validate=True).decode()
            nonce = base64.b64decode(nonce_b64, validate=True).decode()
            password = self.users[user]
            key = hashlib.sha256((nonce + password).encode()).digest()
            url = f"{rec.scheme}://{rec.headers['host']}{rec.target}"
            message = f"{user}.{nonce_b64}.{ts}.{url}.{rec.body.decode('utf-8')}"
            expected = base64.b64encode(
                hmac.new(key, message.encode(), hashlib.sha256).digest()
            ).decode()
            fresh = abs(time.time() * 1000 - int(ts)) < 5 * 60 * 1000
        except (ValueError, KeyError):
            return False
        return fresh and hmac.compare_digest(expected, signature)


def _json_or_none(body: bytes, key: str) -> Any:
    try:
        data = json.loads(body)
    except ValueError:
        return None
    return data.get(key) if isinstance(data, dict) else None
