"""Transport: scheme selection, TLS, authentication, error mapping.

``_sync/transport.py`` is GENERATED from this file by ``scripts/gen_sync.py``.
Only use constructs that translate mechanically (no asyncio calls here: use the
backend's ``sleep`` / ``run_blocking`` / ``create_lock``).
"""

from __future__ import annotations

import functools
import logging
import ssl
import time
from typing import Any

from .. import _auth, _protocol, _tls, const
from ..const import TransportMode
from ..exceptions import KefApiError, KefAuthError, KefConnectionError
from .backend import AsyncBackend, HTTPResponse

_LOGGER = logging.getLogger("pykefcontrol")


def _url_host(host: str) -> str:
    """Host as written in a URL: IPv6 in brackets, zone id ``%`` escaped."""
    if ":" in host and not host.startswith("["):
        return "[" + host.replace("%", "%25") + "]"
    return host


class AsyncTransport:
    """Sends protocol requests to one speaker over HTTPS (port 4430) or HTTP (port 80).

    In ``AUTO`` mode the first request probes HTTPS and falls back to HTTP. Once
    HTTPS has worked, the transport never falls back to plain HTTP (a speaker
    does not downgrade); while on HTTP, HTTPS is re-probed every few minutes.
    Safe to use from concurrent tasks (probing and provisioning are serialized).
    """

    def __init__(
        self,
        host: str,
        backend: AsyncBackend,
        *,
        mode: TransportMode | str = TransportMode.AUTO,
        credentials: _auth.Credentials | None = None,
        verify_ssl: bool = True,
        ssl_context: ssl.SSLContext | None = None,
        timeout: float = const.DEFAULT_TIMEOUT,
        http_port: int = const.HTTP_PORT,
        https_port: int = const.HTTPS_PORT,
    ) -> None:
        self.host = host
        self.mode = TransportMode(mode)
        self.credentials = credentials or _auth.Credentials.default()
        self.timeout = timeout
        self._backend = backend
        self._verify_ssl = verify_ssl
        self._ssl_context = ssl_context
        url_host = _url_host(host)
        self._https_base = f"https://{url_host}:{https_port}"
        self._http_base = (
            f"http://{url_host}" if http_port == 80 else f"http://{url_host}:{http_port}"
        )
        self._base: str | None = None
        self._chosen_at = 0.0
        self._https_confirmed = False
        self._last_secure: bool | None = None
        self._provisioned = False
        self._closed = False
        self._lock = backend.create_lock()

    # --- state -----------------------------------------------------------------

    @property
    def secure(self) -> bool | None:
        """``True`` over HTTPS, ``False`` over HTTP, ``None`` before the first request."""
        return self._last_secure

    @property
    def base_url(self) -> str | None:
        return self._base

    @property
    def closed(self) -> bool:
        return self._closed

    def invalidate(self) -> None:
        """Forget the scheme chosen in ``AUTO`` mode: the next request probes again."""
        if self.mode is TransportMode.AUTO:
            self._base = None

    def _use(self, base: str) -> None:
        self._base = base
        self._last_secure = base == self._https_base
        self._chosen_at = time.monotonic()

    async def _get_ssl_context(self) -> ssl.SSLContext:
        if self._ssl_context is None:
            factory = functools.partial(
                _tls.default_ssl_context,
                verify=self._verify_ssl,
                check_hostname=_tls.is_ip_address(self.host.split("%", 1)[0]),
            )
            self._ssl_context = await self._backend.run_blocking(factory)
        return self._ssl_context

    def _needs_connect(self) -> bool:
        if self._base is None:
            return True
        return (
            self.mode is TransportMode.AUTO
            and self._base == self._http_base
            and time.monotonic() - self._chosen_at > const.HTTPS_REPROBE_INTERVAL
        )

    async def connect(self) -> None:
        """Choose the scheme (probing HTTPS in ``AUTO`` mode) if not done yet."""
        if self._closed:
            raise KefConnectionError("Client is closed")
        if not self._needs_connect():
            return
        async with self._lock:
            if not self._needs_connect():  # another task did it meanwhile
                return
            if self.mode is TransportMode.HTTP:
                self._use(self._http_base)
                return
            await self._get_ssl_context()
            if self.mode is TransportMode.HTTPS or self._https_confirmed:
                self._use(self._https_base)
                return
            probe = _protocol.get_data(const.PROBE_PATH)
            try:
                await self._send_raw(self._https_base, probe, timeout=const.PROBE_TIMEOUT)
            except KefConnectionError as err:
                _LOGGER.debug("%s: HTTPS unavailable (%s), using HTTP", self.host, err)
                self._use(self._http_base)
            else:
                _LOGGER.debug("%s: using HTTPS on %s", self.host, self._https_base)
                self._https_confirmed = True
                self._use(self._https_base)

    # --- requests ----------------------------------------------------------------

    async def _send_raw(
        self,
        base: str,
        request: _protocol.Request,
        *,
        timeout: float | None = None,
        authorization: str | None = None,
    ) -> HTTPResponse:
        headers: dict[str, str] = {}
        if request.body is not None:
            headers["Content-Type"] = const.JSON_CONTENT_TYPE
        if authorization is not None:
            headers["Authorization"] = authorization
        secure = base == self._https_base
        return await self._backend.send(
            request.method,
            base + request.target,
            body=request.body,
            headers=headers,
            ssl_context=await self._get_ssl_context() if secure else None,
            timeout=timeout if timeout is not None else (request.timeout or self.timeout),
        )

    async def _provision(self, *, force: bool = False) -> None:
        """Create our user on the speaker (unauthenticated ``webserver:addUser``)."""
        async with self._lock:
            if self._provisioned and not force:
                return
            request = _protocol.Request(
                "POST",
                const.ENDPOINT_SET_DATA,
                body=_protocol.dumps(_auth.add_user_payload(self.credentials)),
                path="webserver:addUser",
            )
            response = await self._send_raw(self._https_base, request)
            # Don't retry on every request if it failed: a 401 will trigger a new attempt.
            self._provisioned = True
            if not _auth.is_already_provisioned(response.status, response.body):
                _LOGGER.warning(
                    "%s: could not create user %r (HTTP %s): %s",
                    self.host,
                    self.credentials.username,
                    response.status,
                    _protocol.error_message(response.body),
                )

    def _authorization(self, request: _protocol.Request) -> str:
        return _auth.sign(self.credentials, self._https_base + request.target, request.body)

    async def request(self, request: _protocol.Request) -> Any:
        """Send ``request`` and return the decoded JSON answer.

        :raises KefConnectionError: speaker unreachable (in ``AUTO`` mode the scheme
            is probed again on the next request), or client closed.
        :raises KefAuthError: credentials rejected even after re-provisioning.
        :raises KefApiError: any other HTTP error status.
        """
        await self.connect()
        base = self._base
        if base is None:  # closed or invalidated concurrently
            raise KefConnectionError(f"{self.host}: not connected")
        sign = base == self._https_base and request.method == "POST"
        # The speaker answers 401 to an unknown user only after ~10 s: give signed
        # requests enough time to receive it (and re-provision) instead of timing out.
        timeout = request.timeout or self.timeout
        if sign:
            timeout = max(timeout, const.SIGNED_REQUEST_TIMEOUT)
        try:
            authorization = None
            if sign:
                await self._provision()
                authorization = self._authorization(request)
            response = await self._send_raw(
                base, request, timeout=timeout, authorization=authorization
            )
            if response.status == 401 and sign:
                _LOGGER.debug("%s: 401, re-provisioning user and retrying", self.host)
                await self._provision(force=True)
                response = await self._send_raw(
                    base, request, timeout=timeout, authorization=self._authorization(request)
                )
                if response.status == 401:
                    what = request.path or request.endpoint
                    raise KefAuthError(f"{self.host} rejected our credentials ({what})")
        except KefConnectionError:
            if sign:
                self._provisioned = False  # the speaker may have forgotten our user
            self.invalidate()
            raise
        if response.status >= 400:
            message = _protocol.error_message(response.body)
            raise KefApiError(response.status, message, path=request.path)
        if base == self._https_base:
            self._https_confirmed = True
        return _protocol.loads(response.body)

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)

    async def close(self) -> None:
        """Close for good: later requests raise :class:`KefConnectionError`."""
        self._closed = True
        self._base = None
        await self._backend.close()
