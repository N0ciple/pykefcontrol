"""aiohttp HTTP backend (hand-written; the sync counterpart is ``_sync/backend.py``)."""

from __future__ import annotations

import asyncio
import ssl
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypeVar

import aiohttp
from yarl import URL

from ..exceptions import KefConnectionError, KefTimeoutError

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class HTTPResponse:
    status: int
    body: bytes


class AsyncBackend:
    """Sends raw HTTP requests with aiohttp.

    :param session: an existing :class:`aiohttp.ClientSession` (for example Home
        Assistant's shared session). It is never closed by the library. When
        omitted, a private session is created lazily and closed by :meth:`close`.
    """

    def __init__(self, session: aiohttp.ClientSession | None = None) -> None:
        self._session = session
        self._owns_session = session is None
        self._closed = False

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._closed:
            raise KefConnectionError("Client is closed")
        if self._session is None or (self._owns_session and self._session.closed):
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def send(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None,
        headers: Mapping[str, str],
        ssl_context: ssl.SSLContext | None,
        timeout: float,
    ) -> HTTPResponse:
        session = await self._get_session()
        try:
            async with session.request(
                method,
                URL(url, encoded=True),
                data=body,
                headers=dict(headers),
                ssl=ssl_context if ssl_context is not None else True,
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=False,
            ) as response:
                return HTTPResponse(response.status, await response.read())
        except TimeoutError as err:
            raise KefTimeoutError(f"Timeout after {timeout}s: {method} {url}") from err
        except aiohttp.ClientError as err:
            raise KefConnectionError(f"{type(err).__name__}: {err}") from err
        except RuntimeError as err:  # "Session is closed" (e.g. an injected session)
            if session.closed:
                raise KefConnectionError(f"HTTP session closed: {err}") from err
            raise
        except OSError as err:  # e.g. ssl.SSLError raised outside aiohttp's wrappers
            raise KefConnectionError(f"{type(err).__name__}: {err}") from err

    async def run_blocking(self, func: Callable[[], T]) -> T:
        """Run blocking ``func`` (e.g. loading certificates) in the default executor."""
        return await asyncio.get_running_loop().run_in_executor(None, func)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    def create_lock(self) -> asyncio.Lock:
        return asyncio.Lock()

    async def close(self) -> None:
        self._closed = True
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None
