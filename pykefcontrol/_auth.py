"""Authentication used by the speaker's secure API (HTTPS, port 4430).

Reverse-engineered from KEF Connect 1.32 (Android):

* The client creates a user on the speaker with an *unauthenticated* POST of
  ``webserver:addUser`` (an "already exists" error counts as success).
* Every POST is then signed with a custom ``HMAC_SHA256`` ``Authorization``
  header. GET requests are not signed.

The default credentials are the ones used by the official app when no KEF
account is logged in. They are the same for every user, and the speaker accepts
new users without authentication: this scheme authenticates *clients*, it is not
a security boundary on the local network.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from typing import Any, Final

from . import const

DEFAULT_USERNAME: Final = "7f3c2a91-4d0b-4f65-9b3a-8e2f1c6d4a13"


def derive_password(username: str) -> str:
    """Password derivation used by the official app: ``md5("yek_<user>_user")``."""
    return hashlib.md5(f"yek_{username}_user".encode(), usedforsecurity=False).hexdigest()


@dataclass(frozen=True, slots=True)
class Credentials:
    """User created on, and used to sign requests to, the speaker."""

    username: str
    password: str

    @classmethod
    def default(cls) -> Credentials:
        """Credentials used by KEF Connect when no account is logged in."""
        return cls.for_username(DEFAULT_USERNAME)

    @classmethod
    def for_username(cls, username: str) -> Credentials:
        """Credentials for ``username`` with the app's password derivation."""
        return cls(username, derive_password(username))

    def __repr__(self) -> str:  # never leak the password in logs
        return f"Credentials(username={self.username!r}, password='***')"


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def sign(
    credentials: Credentials,
    url: str,
    body: bytes | None,
    *,
    nonce: str | None = None,
    timestamp_ms: int | None = None,
) -> str:
    """Return the ``Authorization`` header value for a request.

    :param url: full URL exactly as sent, e.g. ``https://192.168.1.20:4430/api/setData``.
    :param body: exact request body bytes (``None`` for GET).
    :param nonce/timestamp_ms: only for deterministic tests.
    """
    if nonce is None:
        nonce = b64(os.urandom(6))
    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)
    nonce_b64 = b64(nonce.encode())
    ts = str(timestamp_ms)
    key = hashlib.sha256((nonce + credentials.password).encode()).digest()
    message = f"{credentials.username}.{nonce_b64}.{ts}.{url}"
    if body is not None:
        message += "." + body.decode("utf-8")
    signature = b64(hmac.new(key, message.encode(), hashlib.sha256).digest())
    return f"HMAC_SHA256 {b64(credentials.username.encode())}.{nonce_b64}.{ts}.{signature}"


def add_user_payload(credentials: Credentials) -> dict[str, Any]:
    """Body of the ``webserver:addUser`` provisioning request."""
    return {
        "path": "webserver:addUser",
        "role": "activate",
        "value": {"name": credentials.username, "password": credentials.password, "title": ""},
    }


def is_already_provisioned(status: int, body: bytes) -> bool:
    """Whether an ``addUser`` answer means the user exists (success or duplicate)."""
    return 200 <= status < 300 or b"already exists" in body


__all__ = [
    "DEFAULT_USERNAME",
    "Credentials",
    "add_user_payload",
    "const",
    "derive_password",
    "is_already_provisioned",
    "sign",
]
