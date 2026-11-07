"""urllib3 HTTP backend (hand-written; the async counterpart is ``_async/backend.py``)."""

from __future__ import annotations

import ssl
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypeVar

import urllib3
from urllib3.exceptions import HTTPError, NewConnectionError
from urllib3.exceptions import TimeoutError as Urllib3Timeout

from ..exceptions import KefConnectionError, KefTimeoutError

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class HTTPResponse:
    status: int
    body: bytes


class SyncBackend:
    """Sends raw HTTP requests with urllib3 (one pool manager per TLS context).

    :param session: optional :class:`urllib3.PoolManager` used for plain HTTP; it
        is never closed by the library. HTTPS always uses private pools bound to
        the KEF TLS context.
    """

    def __init__(self, session: urllib3.PoolManager | None = None) -> None:
        self._owns_plain = session is None
        self._plain = session if session is not None else urllib3.PoolManager(num_pools=4)
        self._secure: dict[int, urllib3.PoolManager] = {}
        self._pool_lock = threading.Lock()

    def _pool(self, url: str, ssl_context: ssl.SSLContext | None) -> urllib3.PoolManager:
        if not url.startswith("https://") or ssl_context is None:
            return self._plain
        with self._pool_lock:
            return self._secure_pool(ssl_context)

    def _secure_pool(self, ssl_context: ssl.SSLContext) -> urllib3.PoolManager:
        pool = self._secure.get(id(ssl_context))
        if pool is None:
            kwargs: dict[str, object] = {"ssl_context": ssl_context}
            if not ssl_context.check_hostname:
                # urllib3 would otherwise match the hostname itself; speaker
                # certificates only carry IP addresses (chain is still verified).
                kwargs["assert_hostname"] = False
            pool = urllib3.PoolManager(num_pools=4, **kwargs)  # type: ignore[arg-type]
            self._secure[id(ssl_context)] = pool
        return pool

    def send(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None,
        headers: Mapping[str, str],
        ssl_context: ssl.SSLContext | None,
        timeout: float,
    ) -> HTTPResponse:
        try:
            response = self._pool(url, ssl_context).request(
                method,
                url,
                body=body,
                headers=dict(headers),
                timeout=urllib3.Timeout(total=timeout),
                retries=False,
                redirect=False,
                preload_content=True,
            )
        except NewConnectionError as err:  # subclass of a timeout error in urllib3
            raise KefConnectionError(f"Connection failed: {err}") from err
        except Urllib3Timeout as err:
            raise KefTimeoutError(f"Timeout after {timeout}s: {method} {url}") from err
        except (HTTPError, OSError) as err:
            raise KefConnectionError(f"{type(err).__name__}: {err}") from err
        return HTTPResponse(response.status, response.data)

    def run_blocking(self, func: Callable[[], T]) -> T:
        return func()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def create_lock(self) -> threading.Lock:
        return threading.Lock()

    def close(self) -> None:
        if self._owns_plain:
            self._plain.clear()
        for pool in self._secure.values():
            pool.clear()
        self._secure.clear()
