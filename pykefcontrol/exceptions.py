"""Exceptions raised by pykefcontrol.

Every exception raised by the library derives from :class:`KefError`, so callers
can catch a single type. Network-level problems are :class:`KefConnectionError`
(with :class:`KefTimeoutError` as a subclass), so "speaker unreachable" can be
handled separately from "speaker refused the request".
"""

from __future__ import annotations


class KefError(Exception):
    """Base class for all pykefcontrol errors."""


class KefConnectionError(KefError):
    """The speaker could not be reached (connection refused, DNS, TLS failure...)."""


class KefTimeoutError(KefConnectionError):
    """The speaker did not answer in time."""


class KefAuthError(KefError):
    """The speaker rejected our credentials (HTTP 401 after re-provisioning)."""


class KefApiError(KefError):
    """The speaker answered with an HTTP error status."""

    def __init__(self, status: int, message: str, *, path: str | None = None) -> None:
        self.status = status
        self.message = message
        self.path = path
        where = f" ({path})" if path else ""
        super().__init__(f"HTTP {status}{where}: {message}")


class KefProtocolError(KefError):
    """The speaker answered with something we could not understand."""


class KefUnsupportedError(KefError):
    """The requested feature is not supported by this speaker / firmware."""
