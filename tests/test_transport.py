"""Transport behaviour: scheme selection, TLS verification, signing, provisioning."""

from __future__ import annotations

import ssl
from typing import Any

import pytest

from pykefcontrol import (
    Credentials,
    KefAsyncClient,
    KefAuthError,
    KefClient,
    KefConnectionError,
    KefTimeoutError,
    const,
    create_ssl_context,
)

from .fake_speaker import PKI, FakeSpeaker, free_port, typed

USER = Credentials.default().username


def client_for(
    fake: FakeSpeaker, ssl_context: ssl.SSLContext | None = None, **kwargs: Any
) -> KefClient:
    kwargs.setdefault("http_port", fake.http_port if _has(fake, "http") else free_port())
    kwargs.setdefault("https_port", fake.https_port if _has(fake, "https") else free_port())
    return KefClient(kwargs.pop("host", fake.host), ssl_context=ssl_context, **kwargs)


def _has(fake: FakeSpeaker, scheme: str) -> bool:
    return any(listener.scheme == scheme for listener in fake.listeners)


# --- scheme selection ---------------------------------------------------------------


def test_auto_picks_https_when_tls_answers(
    auto_speaker: FakeSpeaker, ssl_context: ssl.SSLContext
) -> None:
    with client_for(auto_speaker, ssl_context) as c:
        assert c.is_secure is None
        assert c.get_volume() == 30
        assert c.is_secure is True
    assert {r.scheme for r in auto_speaker.requests} == {"https"}
    assert auto_speaker.requests[0].query["path"] == const.PROBE_PATH  # the probe


def test_auto_falls_back_to_http_when_https_port_closed(speaker: FakeSpeaker) -> None:
    with client_for(speaker, https_port=free_port()) as c:
        assert c.get_volume() == 30
        assert c.is_secure is False
        c.set_volume(10)
    assert {r.scheme for r in speaker.requests} == {"http"}
    assert all("authorization" not in r.headers for r in speaker.requests)
    assert speaker.users == {}  # no provisioning over HTTP


def test_http_mode_never_probes_https(
    auto_speaker: FakeSpeaker, ssl_context: ssl.SSLContext
) -> None:
    with client_for(auto_speaker, ssl_context, transport="http") as c:
        c.set_volume(12)
        assert c.is_secure is False
    assert {r.scheme for r in auto_speaker.requests} == {"http"}
    assert all("authorization" not in r.headers for r in auto_speaker.requests)


def test_https_mode_does_not_fall_back(speaker: FakeSpeaker) -> None:
    with client_for(speaker, transport="https", https_port=free_port()) as c:
        with pytest.raises(KefConnectionError):
            c.get_volume()
    assert speaker.requests == []


def test_auto_reprobes_https_when_http_choice_is_stale(
    auto_speaker: FakeSpeaker, ssl_context: ssl.SSLContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(const, "HTTPS_REPROBE_INTERVAL", 0.0)
    https = next(listener for listener in auto_speaker.listeners if listener.scheme == "https")
    https.stop()
    with client_for(auto_speaker, ssl_context) as c:
        c.get_volume()
        assert c.is_secure is False
        https.start()
        c.get_volume()
        assert c.is_secure is True


def test_https_never_falls_back_to_http_once_confirmed(
    auto_speaker: FakeSpeaker, ssl_context: ssl.SSLContext
) -> None:
    https = next(listener for listener in auto_speaker.listeners if listener.scheme == "https")
    with client_for(auto_speaker, ssl_context) as c:
        c.get_volume()
        assert c.is_secure is True
        https.stop()
        auto_speaker.clear_requests()
        for _ in range(2):  # invalidated after the error, yet never downgraded to HTTP
            with pytest.raises(KefConnectionError):
                c.get_volume()
            assert c.is_secure is True  # last known value is kept
        assert auto_speaker.requests == []  # plain HTTP was never tried
        https.start()
        assert c.get_volume() == 30
        assert c.is_secure is True


def test_closed_client_raises(speaker: FakeSpeaker) -> None:
    c = client_for(speaker, transport="http")
    c.get_volume()
    c.close()
    with pytest.raises(KefConnectionError, match="closed"):
        c.get_volume()


def test_url_host_escapes_ipv6_zone_id() -> None:
    from pykefcontrol._async.transport import _url_host

    assert _url_host("192.168.1.2") == "192.168.1.2"
    assert _url_host("speaker.local") == "speaker.local"
    assert _url_host("fe80::1") == "[fe80::1]"
    assert _url_host("fe80::1%eth0") == "[fe80::1%25eth0]"
    assert _url_host("[::1]") == "[::1]"


# --- signing and provisioning ----------------------------------------------------------


def test_https_signs_posts_but_not_gets(
    tls_speaker: FakeSpeaker, ssl_context: ssl.SSLContext
) -> None:
    with client_for(tls_speaker, ssl_context, transport="https") as c:
        assert c.get_volume() == 30
        c.set_volume(20)
        c.activate("player:player/control", {"control": "stop"})
        assert c.get_volume() == 20
    gets = [r for r in tls_speaker.requests if r.method == "GET"]
    assert gets and all("authorization" not in r.headers for r in gets)
    signed = tls_speaker.requests_to("/api/setData", "POST")[1:]  # [0] is addUser
    assert len(signed) == 2
    for rec in signed:
        assert rec.auth_ok is True
        assert rec.headers["authorization"].startswith("HMAC_SHA256 ")
        assert rec.status == 200


def test_signed_modify_queue_over_https(
    tls_speaker: FakeSpeaker, ssl_context: ssl.SSLContext
) -> None:
    with client_for(tls_speaker, ssl_context, transport="https") as c:
        assert c.event_queue().subscribe(["player:volume"]) is True
    (rec,) = tls_speaker.requests_to("/api/event/modifyQueue")
    assert rec.auth_ok is True


def test_unsigned_post_is_rejected_by_the_fake(tls_speaker: FakeSpeaker, pki: PKI) -> None:
    """Sanity check of the fake itself: an unsigned POST gets a 401."""
    import urllib3

    pool = urllib3.PoolManager(ssl_context=create_ssl_context(ca_pem=pki.ca_pem))
    resp = pool.request(
        "POST",
        f"https://127.0.0.1:{tls_speaker.https_port}/api/setData",
        body=b'{"path":"player:volume","role":"value","value":{}}',
    )
    assert resp.status == 401


def test_provisioning_happens_once_before_first_post(
    tls_speaker: FakeSpeaker, ssl_context: ssl.SSLContext
) -> None:
    with client_for(tls_speaker, ssl_context, transport="https") as c:
        c.get_volume()
        assert tls_speaker.posts() == []  # GETs do not provision
        c.set_volume(1)
        c.set_volume(2)
        c.set_volume(3)
    posts = tls_speaker.requests_to("/api/setData", "POST")
    assert [p.json["path"] for p in posts] == ["webserver:addUser"] + ["player:volume"] * 3
    add_user = posts[0]
    assert "authorization" not in add_user.headers  # provisioning is unauthenticated
    assert add_user.json["role"] == "activate"
    assert add_user.json["value"] == {
        "name": USER,
        "password": "92313c2d5b721cd1541642a5f3db3db0",
        "title": "",
    }
    assert tls_speaker.users == {USER: "92313c2d5b721cd1541642a5f3db3db0"}


def test_existing_user_is_not_an_error(
    tls_speaker: FakeSpeaker, ssl_context: ssl.SSLContext
) -> None:
    tls_speaker.users[USER] = Credentials.default().password
    with client_for(tls_speaker, ssl_context, transport="https") as c:
        c.set_volume(5)  # addUser answers 500 "already exists": fine
    assert tls_speaker.store["player:volume"] == typed("i32_", 5)


def test_custom_credentials(tls_speaker: FakeSpeaker, ssl_context: ssl.SSLContext) -> None:
    creds = Credentials.for_username("alice")
    with client_for(tls_speaker, ssl_context, transport="https", credentials=creds) as c:
        c.set_volume(5)
    assert list(tls_speaker.users) == ["alice"]
    assert all(r.auth_ok for r in tls_speaker.requests if r.auth_ok is not None)


def test_401_reprovisions_and_retries_once(
    tls_speaker: FakeSpeaker, ssl_context: ssl.SSLContext
) -> None:
    with client_for(tls_speaker, ssl_context, transport="https") as c:
        c.set_volume(1)
        tls_speaker.clear_requests()
        tls_speaker.fail_signed = 1
        c.set_volume(2)
    paths = [r.json["path"] for r in tls_speaker.requests_to("/api/setData", "POST")]
    assert paths == ["player:volume", "webserver:addUser", "player:volume"]
    statuses = [r.status for r in tls_speaker.requests_to("/api/setData", "POST")]
    assert statuses == [401, 500, 200]  # addUser: "already exists"
    assert tls_speaker.store["player:volume"] == typed("i32_", 2)


def test_401_after_speaker_forgot_user_recreates_it(
    tls_speaker: FakeSpeaker, ssl_context: ssl.SSLContext
) -> None:
    with client_for(tls_speaker, ssl_context, transport="https") as c:
        c.set_volume(1)
        tls_speaker.forget_users()
        c.set_volume(2)
        assert USER in tls_speaker.users
    assert tls_speaker.store["player:volume"] == typed("i32_", 2)


def test_second_401_raises_auth_error(
    tls_speaker: FakeSpeaker, ssl_context: ssl.SSLContext
) -> None:
    tls_speaker.fail_signed = 2
    with client_for(tls_speaker, ssl_context, transport="https") as c:
        with pytest.raises(KefAuthError):
            c.set_volume(3)
        tls_speaker.clear_requests()
        c.set_volume(4)  # the client recovers afterwards
    assert tls_speaker.store["player:volume"] == typed("i32_", 4)
    assert len(tls_speaker.requests_to("/api/setData", "POST")) == 1  # no more provisioning


def test_failed_provisioning_is_not_retried_on_every_request(pki: PKI, caplog: Any) -> None:
    fake = FakeSpeaker()  # accepts unsigned POSTs, like firmware 4.1
    fake.add_https(pki.good)
    fake.overrides["webserver:addUser"] = (500, b'{"error":{"message":"disk full"}}')
    try:
        ctx = create_ssl_context(ca_pem=pki.ca_pem)
        with client_for(fake, ctx, transport="https") as c:
            for volume in (1, 2, 3):
                c.set_volume(volume)
        add_users = [r for r in fake.posts() if r.json["path"] == "webserver:addUser"]
        assert len(add_users) == 1
        assert "disk full" in caplog.text
    finally:
        fake.stop()


def test_signed_requests_get_a_longer_timeout(
    tls_speaker: FakeSpeaker, ssl_context: ssl.SSLContext
) -> None:
    # The speaker delays its 401 for unknown users by ~10 s: signed POSTs wait longer.
    with client_for(tls_speaker, ssl_context, transport="https", timeout=0.2) as c:
        c.set_volume(1)  # provisions
        tls_speaker.response_delay = 0.5
        c.set_volume(2)  # 0.5 s > timeout, but signed requests use SIGNED_REQUEST_TIMEOUT
        with pytest.raises(KefTimeoutError):
            c.get_volume()  # unsigned GET keeps the configured timeout
    assert tls_speaker.store["player:volume"] == typed("i32_", 2)
    assert const.SIGNED_REQUEST_TIMEOUT >= 15


def test_connection_error_on_signed_request_resets_provisioning(
    tls_speaker: FakeSpeaker, ssl_context: ssl.SSLContext
) -> None:
    with client_for(tls_speaker, ssl_context, transport="https") as c:
        c.set_volume(1)
        tls_speaker.drop_connections = True
        with pytest.raises(KefConnectionError):
            c.set_volume(2)
        tls_speaker.drop_connections = False
        c.set_volume(3)
    paths = [r.json["path"] for r in tls_speaker.requests_to("/api/setData", "POST") if r.status]
    assert paths == ["webserver:addUser", "player:volume", "webserver:addUser", "player:volume"]


# --- TLS verification --------------------------------------------------------------------


def test_cert_without_ip_san_fails_verification(pki: PKI, ssl_context: ssl.SSLContext) -> None:
    fake = FakeSpeaker()
    fake.add_https(pki.bad)
    try:
        with client_for(fake, ssl_context, transport="https") as c:
            with pytest.raises(KefConnectionError):
                c.get_volume()
    finally:
        fake.stop()


def test_auto_falls_back_to_http_when_cert_has_wrong_ip(
    pki: PKI, ssl_context: ssl.SSLContext
) -> None:
    fake = FakeSpeaker(require_auth=True)
    fake.add_http()
    fake.add_https(pki.bad)
    try:
        with client_for(fake, ssl_context) as c:
            assert c.get_volume() == 30
            assert c.is_secure is False
    finally:
        fake.stop()


def test_untrusted_ca_fails_with_default_context(tls_speaker: FakeSpeaker) -> None:
    """Without ``ssl_context`` the KEF root CA is used: the test CA is not trusted."""
    with client_for(tls_speaker, transport="https") as c:
        with pytest.raises(KefConnectionError):
            c.get_volume()


@pytest.mark.filterwarnings("ignore::urllib3.exceptions.InsecureRequestWarning")
def test_verify_ssl_false_accepts_any_certificate(pki: PKI) -> None:
    fake = FakeSpeaker(require_auth=True)
    fake.add_https(pki.bad)
    try:
        with client_for(fake, transport="https", verify_ssl=False) as c:
            assert c.get_volume() == 30
            c.set_volume(7)
    finally:
        fake.stop()


def test_hostname_mode_verifies_chain_only(tls_speaker: FakeSpeaker, pki: PKI) -> None:
    # The leaf only lists 127.0.0.1: with a host *name* the chain is verified, not the name.
    lenient = create_ssl_context(ca_pem=pki.ca_pem, check_hostname=False)
    with client_for(tls_speaker, lenient, transport="https", host="localhost") as c:
        assert c.get_volume() == 30
        c.set_volume(9)
    strict = create_ssl_context(ca_pem=pki.ca_pem, check_hostname=True)
    with client_for(tls_speaker, strict, transport="https", host="localhost") as c:
        with pytest.raises(KefConnectionError):
            c.get_volume()


def test_hostname_mode_still_verifies_the_chain(pki: PKI) -> None:
    import trustme

    fake = FakeSpeaker()
    fake.add_https(trustme.CA().issue_cert("127.0.0.1"))  # signed by another CA
    try:
        lenient = create_ssl_context(ca_pem=pki.ca_pem, check_hostname=False)
        with client_for(fake, lenient, transport="https", host="localhost") as c:
            with pytest.raises(KefConnectionError):
                c.get_volume()
    finally:
        fake.stop()


async def test_async_concurrent_first_requests_probe_and_provision_once(
    auto_speaker: FakeSpeaker, ssl_context: ssl.SSLContext
) -> None:
    import asyncio

    async with KefAsyncClient(
        auto_speaker.host,
        ssl_context=ssl_context,
        http_port=auto_speaker.http_port,
        https_port=auto_speaker.https_port,
    ) as c:
        await asyncio.gather(*(c.set_volume(10 + i) for i in range(6)), c.get_mute(), c.get_name())
    probes = auto_speaker.requests_to("/api/getData", "GET")
    assert [r.query["path"] for r in probes].count(const.PROBE_PATH) == 2  # 1 probe + get_name
    first_probe = next(r for r in probes if r.query["path"] == const.PROBE_PATH)
    assert first_probe is auto_speaker.requests[0]
    add_users = [r for r in auto_speaker.posts() if r.json["path"] == "webserver:addUser"]
    assert len(add_users) == 1
    assert {r.scheme for r in auto_speaker.requests} == {"https"}


# --- the same, with the asyncio client ----------------------------------------------------


async def test_async_auto_https_and_signed_post(
    auto_speaker: FakeSpeaker, ssl_context: ssl.SSLContext
) -> None:
    async with KefAsyncClient(
        auto_speaker.host,
        ssl_context=ssl_context,
        http_port=auto_speaker.http_port,
        https_port=auto_speaker.https_port,
    ) as c:
        assert await c.get_volume() == 30
        assert c.is_secure is True
        await c.set_volume(40)
    assert all(r.auth_ok for r in auto_speaker.posts("https")[1:])  # [0]: addUser
    assert auto_speaker.store["player:volume"] == typed("i32_", 40)


async def test_async_fallback_and_bad_cert(pki: PKI, ssl_context: ssl.SSLContext) -> None:
    fake = FakeSpeaker()
    fake.add_http()
    fake.add_https(pki.bad)
    try:
        kwargs: dict[str, Any] = {
            "ssl_context": ssl_context,
            "http_port": fake.http_port,
            "https_port": fake.https_port,
        }
        async with KefAsyncClient(fake.host, transport="https", **kwargs) as c:
            with pytest.raises(KefConnectionError):
                await c.get_volume()
        async with KefAsyncClient(fake.host, **kwargs) as c:
            assert await c.get_volume() == 30
            assert c.is_secure is False
    finally:
        fake.stop()


async def test_async_hostname_mode(tls_speaker: FakeSpeaker, pki: PKI) -> None:
    lenient = create_ssl_context(ca_pem=pki.ca_pem, check_hostname=False)
    async with KefAsyncClient(
        "localhost", transport="https", ssl_context=lenient, https_port=tls_speaker.https_port
    ) as c:
        assert await c.get_volume() == 30


async def test_async_default_context_is_built_off_loop(speaker: FakeSpeaker) -> None:
    """No ssl_context given: the KEF CA context is built lazily (HTTPS to a plain port fails)."""
    async with KefAsyncClient(speaker.host, transport="https", https_port=speaker.http_port) as c:
        with pytest.raises(KefConnectionError):
            await c.get_volume()
