"""Tests for pykefcontrol._auth (request signing and default credentials)."""

from __future__ import annotations

import base64
import hashlib
import hmac

from pykefcontrol import Credentials, _auth

USER = "7f3c2a91-4d0b-4f65-9b3a-8e2f1c6d4a13"
PASSWORD = "92313c2d5b721cd1541642a5f3db3db0"
URL = "https://192.168.1.20:4430/api/setData"
BODY = b'{"path":"player:volume","role":"value","value":{"type":"i32_","i32_":30}}'
VECTOR = (
    "HMAC_SHA256 N2YzYzJhOTEtNGQwYi00ZjY1LTliM2EtOGUyZjFjNmQ0YTEz.QWJDZEVmMTI=."
    "1700000000000.4vSRaLUe/1tOYpPZ83g2KqfImCRZ1PoV4CTV+Teex9M="
)


def reference_sign(user: str, password: str, url: str, body: bytes, nonce: str, ts: int) -> str:
    """Independent implementation of secure_api.md section 3b."""

    def b64(data: bytes) -> str:
        return base64.b64encode(data).decode()

    nonce_b64 = b64(nonce.encode())
    key = hashlib.sha256((nonce + password).encode()).digest()
    msg = f"{user}.{nonce_b64}.{ts}.{url}.{body.decode()}"
    sig = b64(hmac.new(key, msg.encode(), hashlib.sha256).digest())
    return f"HMAC_SHA256 {b64(user.encode())}.{nonce_b64}.{ts}.{sig}"


def test_default_credentials() -> None:
    creds = Credentials.default()
    assert creds.username == USER == _auth.DEFAULT_USERNAME
    assert creds.password == PASSWORD
    assert hashlib.md5(f"yek_{USER}_user".encode()).hexdigest() == PASSWORD


def test_for_username_derives_password() -> None:
    creds = Credentials.for_username("alice")
    assert creds.password == hashlib.md5(b"yek_alice_user").hexdigest()


def test_credentials_repr_hides_password() -> None:
    text = repr(Credentials.default())
    assert PASSWORD not in text
    assert USER in text
    assert "***" in text


def test_signature_vector() -> None:
    header = _auth.sign(
        Credentials.default(), URL, BODY, nonce="AbCdEf12", timestamp_ms=1700000000000
    )
    assert header == VECTOR
    assert header == reference_sign(USER, PASSWORD, URL, BODY, "AbCdEf12", 1700000000000)


def test_signature_depends_on_every_input() -> None:
    creds = Credentials.default()
    base = _auth.sign(creds, URL, BODY, nonce="n1", timestamp_ms=1)
    assert base != _auth.sign(creds, URL + "x", BODY, nonce="n1", timestamp_ms=1)
    assert base != _auth.sign(creds, URL, BODY + b" ", nonce="n1", timestamp_ms=1)
    assert base != _auth.sign(creds, URL, BODY, nonce="n2", timestamp_ms=1)
    assert base != _auth.sign(creds, URL, BODY, nonce="n1", timestamp_ms=2)
    assert base != _auth.sign(Credentials("bob", "x"), URL, BODY, nonce="n1", timestamp_ms=1)


def test_random_nonce_and_timestamp_are_fresh() -> None:
    creds = Credentials.default()
    assert _auth.sign(creds, URL, BODY) != _auth.sign(creds, URL, BODY)
    token = _auth.sign(creds, URL, BODY).split(" ", 1)[1]
    user_b64, nonce_b64, ts, _sig = token.split(".")
    assert base64.b64decode(user_b64).decode() == USER
    assert len(base64.b64decode(nonce_b64)) == 8  # base64 of 6 random bytes
    assert ts.isdigit() and len(ts) == 13


def test_add_user_payload_and_already_provisioned() -> None:
    payload = _auth.add_user_payload(Credentials.default())
    assert payload == {
        "path": "webserver:addUser",
        "role": "activate",
        "value": {"name": USER, "password": PASSWORD, "title": ""},
    }
    assert _auth.is_already_provisioned(200, b"")
    assert _auth.is_already_provisioned(500, b"User already exists")
    assert not _auth.is_already_provisioned(500, b"boom")
    assert not _auth.is_already_provisioned(401, b"")
