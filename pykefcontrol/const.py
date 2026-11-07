"""Constants shared by the transports and clients."""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class TransportMode(StrEnum):
    """How the client talks to the speaker.

    * ``AUTO``: probe HTTPS on port 4430 (recent firmware), fall back to HTTP on
      port 80 (older firmware). This is what the official app does.
    * ``HTTPS``: HTTPS only (fails if the speaker does not support it).
    * ``HTTP``: plain HTTP only (legacy firmware, or troubleshooting).
    """

    AUTO = "auto"
    HTTPS = "https"
    HTTP = "http"


HTTP_PORT: Final = 80
HTTPS_PORT: Final = 4430

#: Default timeout (seconds) for ordinary requests.
DEFAULT_TIMEOUT: Final = 10.0
#: Minimum timeout of signed (HTTPS POST) requests: the speaker delays its 401
#: answer to an unknown user by about 10 s (measured on LS50 Wireless II 4.1).
SIGNED_REQUEST_TIMEOUT: Final = 15.0
#: Timeout (seconds) of the HTTPS probe in ``AUTO`` mode.
PROBE_TIMEOUT: Final = 3.0
#: Long-poll duration requested from the speaker (same as the official app).
POLL_TIMEOUT: Final = 25
#: Extra time granted to the HTTP request on top of the long-poll duration.
POLL_HTTP_MARGIN: Final = 15.0

#: In ``AUTO`` mode, retry HTTPS this often (seconds) while using HTTP.
HTTPS_REPROBE_INTERVAL: Final = 300.0

#: Path used to probe the API (cheap, always present).
PROBE_PATH: Final = "settings:/deviceName"

#: Minimum interval between two polls when the speaker answers immediately (seconds).
MIN_POLL_INTERVAL: Final = 1.0

# EQ writes are applied asynchronously by the speaker (~70 ms measured on an LS50WII).
EQ_APPLY_TIMEOUT: Final = 2.0
EQ_APPLY_POLL_INTERVAL: Final = 0.05

#: Reconnection back-off of :meth:`watch` / :meth:`events` (seconds).
RECONNECT_DELAY_MIN: Final = 1.0
RECONNECT_DELAY_MAX: Final = 30.0

ENDPOINT_GET_DATA: Final = "/api/getData"
ENDPOINT_SET_DATA: Final = "/api/setData"
ENDPOINT_GET_ROWS: Final = "/api/getRows"
ENDPOINT_MODIFY_QUEUE: Final = "/api/event/modifyQueue"
ENDPOINT_POLL_QUEUE: Final = "/api/event/pollQueue"

JSON_CONTENT_TYPE: Final = "application/json; charset=utf-8"
