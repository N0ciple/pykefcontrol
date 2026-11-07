"""Sans-I/O protocol layer: builds requests and parses responses.

Nothing here touches the network, which keeps it shared by the async and sync
clients and trivially unit-testable.

HTTP API of the speaker (identical on HTTP:80 and HTTPS:4430)::

    GET  /api/getData?path=<p>&roles=value          -> [ <typed value> ]
    POST /api/setData {"path", "role", "value"}      -> anything
    GET  /api/getRows?path=<p>&roles=@all&from=&to=  -> {"rows": [...], "rowsCount": n, ...}
    POST /api/event/modifyQueue {"queueId"?, "subscribe", "unsubscribe"} -> "<queue id>"
    GET  /api/event/pollQueue?queueId=<id>&timeout=<s> -> [ <event>, ... ]
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlencode

from . import const
from .exceptions import KefProtocolError
from .models import Event, Subscription


@dataclass(frozen=True, slots=True)
class Request:
    """An HTTP request to send to the speaker."""

    method: Literal["GET", "POST"]
    endpoint: str
    params: tuple[tuple[str, str], ...] = ()
    body: bytes | None = None
    timeout: float | None = None
    path: str | None = None  #: API path concerned (for error messages)

    @property
    def target(self) -> str:
        """Endpoint plus query string."""
        if not self.params:
            return self.endpoint
        return f"{self.endpoint}?{urlencode(self.params)}"


def dumps(obj: Any) -> bytes:
    """Serialize a request body (compact, UTF-8). Signed bytes == sent bytes."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def loads(body: bytes) -> Any:
    """Parse a response body (empty body → ``None``)."""
    if not body.strip():
        return None
    try:
        return json.loads(body)
    except ValueError as err:
        raise KefProtocolError(f"Invalid JSON from speaker: {body[:200]!r}") from err


# --- request builders ----------------------------------------------------------


def get_data(path: str, roles: str = "value") -> Request:
    return Request("GET", const.ENDPOINT_GET_DATA, (("path", path), ("roles", roles)), path=path)


def set_data(path: str, value: Any, role: str = "value") -> Request:
    body = dumps({"path": path, "role": role, "value": value})
    return Request("POST", const.ENDPOINT_SET_DATA, body=body, path=path)


def activate(path: str, value: Any = None) -> Request:
    """Trigger an action node (``role: activate``)."""
    return set_data(path, {} if value is None else value, role="activate")


def get_rows(path: str, start: int = 0, end: int = 19, roles: str = "@all") -> Request:
    """List rows ``start``..``end`` (inclusive) of a container node."""
    if start < 0 or end < start:
        raise ValueError(f"Invalid row range {start}..{end}")
    params = (("path", path), ("roles", roles), ("from", str(start)), ("to", str(end)))
    return Request("GET", const.ENDPOINT_GET_ROWS, params, path=path)


def modify_queue(
    subscribe: Iterable[Subscription],
    unsubscribe: Iterable[Subscription] = (),
    queue_id: str | None = None,
) -> Request:
    payload: dict[str, Any] = {
        "subscribe": [s.to_api() for s in subscribe],
        "unsubscribe": [s.to_api() for s in unsubscribe],
    }
    if queue_id is not None:
        payload = {"queueId": queue_id, **payload}
    return Request("POST", const.ENDPOINT_MODIFY_QUEUE, body=dumps(payload))


def poll_queue(queue_id: str, timeout: int = const.POLL_TIMEOUT) -> Request:
    if timeout < 0:
        raise ValueError("timeout must be >= 0")
    return Request(
        "GET",
        const.ENDPOINT_POLL_QUEUE,
        (("queueId", queue_id), ("timeout", str(timeout))),
        timeout=timeout + const.POLL_HTTP_MARGIN,
    )


# --- response parsers -----------------------------------------------------------


def error_message(body: bytes) -> str:
    """Human message of an error answer.

    Errors look like ``{"error": {"name": "CMAbstractWorker::invalidPath",
    "message": "Node at path 'x' does not exist", ...}}``.
    """
    text = body.decode("utf-8", "replace").strip()
    try:
        data = json.loads(text)
    except ValueError:
        return text[:500]
    error = data.get("error") if isinstance(data, Mapping) else None
    if isinstance(error, Mapping) and error.get("message"):
        name = error.get("name")
        return f"{error['message']} ({name})" if name else str(error["message"])
    return text[:500]


def parse_get_data(data: Any, path: str | None = None) -> Any:
    """``getData`` returns a one-element list; return that element."""
    if isinstance(data, list):
        if not data:
            raise KefProtocolError(f"Empty getData answer for {path}")
        return data[0]
    if isinstance(data, Mapping):  # tolerate firmwares answering with the bare object
        return data
    raise KefProtocolError(f"Unexpected getData answer for {path}: {data!r}")


def parse_rows(data: Any, path: str | None = None) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise KefProtocolError(f"Unexpected getRows answer for {path}: {data!r}")
    return dict(data)


def parse_queue_id(data: Any) -> str:
    """The queue id is a JSON string (usually ``"{uuid}"``), passed back verbatim."""
    if isinstance(data, str) and data:
        return data
    raise KefProtocolError(f"Unexpected modifyQueue answer: {data!r}")


def parse_events(data: Any) -> list[Event]:
    """Parse a ``pollQueue`` answer (``[]`` or ``None`` = long-poll timed out)."""
    if data is None:
        return []
    if not isinstance(data, list):
        raise KefProtocolError(f"Unexpected pollQueue answer: {data!r}")
    return [Event.from_api(item) for item in data if isinstance(item, Mapping)]


def latest_per_path(events: Sequence[Event]) -> list[Event]:
    """Keep only the last event of each path, ordered by last occurrence."""
    latest: dict[str, Event] = {}
    for event in events:
        latest.pop(event.path, None)
        latest[event.path] = event
    return list(latest.values())
