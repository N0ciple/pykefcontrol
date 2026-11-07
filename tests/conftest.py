"""Shared fixtures: fake speakers (HTTP, HTTPS, both) and TLS material."""

from __future__ import annotations

import ssl
from collections.abc import Iterator

import pytest

from pykefcontrol import const, create_ssl_context

from .fake_speaker import PKI, FakeSpeaker


@pytest.fixture(scope="session")
def pki() -> PKI:
    return PKI()


@pytest.fixture
def ssl_context(pki: PKI) -> ssl.SSLContext:
    """Client context trusting the test CA (verifies the 127.0.0.1 IP SAN)."""
    return create_ssl_context(ca_pem=pki.ca_pem)


@pytest.fixture
def speaker() -> Iterator[FakeSpeaker]:
    """Plain HTTP speaker."""
    fake = FakeSpeaker()
    fake.add_http()
    yield fake
    fake.stop()


@pytest.fixture
def tls_speaker(pki: PKI) -> Iterator[FakeSpeaker]:
    """HTTPS-only speaker; POSTs must be signed."""
    fake = FakeSpeaker(require_auth=True)
    fake.add_https(pki.good)
    yield fake
    fake.stop()


@pytest.fixture
def auto_speaker(pki: PKI) -> Iterator[FakeSpeaker]:
    """HTTP and HTTPS ports sharing one state (HTTPS POSTs must be signed)."""
    fake = FakeSpeaker(require_auth=True)
    fake.add_http()
    fake.add_https(pki.good)
    yield fake
    fake.stop()


@pytest.fixture(params=["http", "https"])
def transport_mode(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture
def fast_reconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(const, "RECONNECT_DELAY_MIN", 0.05)
    monkeypatch.setattr(const, "RECONNECT_DELAY_MAX", 0.1)
