"""Discovery of KEF speakers on the local network (mDNS / DNS-SD).

KEF W2 speakers advertise the ``_kef-info._tcp`` service with TXT records
``mac``, ``model`` (product code such as ``SP4025``), ``version`` (firmware) and
``name``.

* :func:`parse_service_info` turns those records into a :class:`DiscoveredSpeaker`;
  it has no dependency and is what a Home Assistant zeroconf config flow needs.
* :func:`discover` / :func:`discover_blocking` browse the network and require the
  ``discovery`` extra (``pip install pykefcontrol[discovery]``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Final

from .capabilities import FirmwareVersion, SpeakerModel, model_info

SERVICE_TYPE: Final = "_kef-info._tcp.local."


@dataclass(frozen=True, slots=True)
class DiscoveredSpeaker:
    """A speaker found on the network."""

    host: str
    name: str | None
    model: SpeakerModel
    product_code: str | None
    mac_address: str | None
    firmware: FirmwareVersion | None
    properties: Mapping[str, str] = field(default_factory=dict, repr=False)

    @property
    def marketing_name(self) -> str:
        return model_info(self.model).marketing_name


def _text(value: bytes | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def parse_service_info(
    addresses: Iterable[str],
    properties: Mapping[bytes, bytes | None] | Mapping[str, str | None],
    *,
    name: str | None = None,
) -> DiscoveredSpeaker | None:
    """Build a :class:`DiscoveredSpeaker` from mDNS data (``None`` if no IPv4/IPv6 address).

    IPv4 addresses are preferred: the speaker's HTTPS certificate is issued for them.
    """
    props: dict[str, str] = {}
    for key, value in properties.items():
        text_key, text_value = _text(key), _text(value)
        if text_key is not None and text_value is not None:
            props[text_key] = text_value
    candidates = sorted(addresses, key=lambda a: ":" in a)  # IPv4 first
    if not candidates:
        return None
    product_code = props.get("model")
    model = SpeakerModel.from_product_code(product_code)
    if model == SpeakerModel.UNKNOWN and product_code:
        model = SpeakerModel.from_model_name(product_code)
    service_name = name.split(".", 1)[0] if name else None
    return DiscoveredSpeaker(
        host=candidates[0],
        name=props.get("name") or service_name,
        model=model,
        product_code=product_code,
        mac_address=props.get("mac"),
        firmware=FirmwareVersion.parse(props.get("version")),
        properties=props,
    )


async def discover(timeout: float = 3.0) -> list[DiscoveredSpeaker]:
    """Browse the network for ``timeout`` seconds and return the speakers found."""
    try:
        from zeroconf import ServiceStateChange, Zeroconf
        from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf
    except ImportError as err:  # pragma: no cover - depends on the extra
        raise ImportError(
            "Discovery needs zeroconf: pip install 'pykefcontrol[discovery]'"
        ) from err

    names: set[str] = set()

    def on_change(
        zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange
    ) -> None:
        if state_change is ServiceStateChange.Added:
            names.add(name)

    aiozc = AsyncZeroconf()
    try:
        browser = AsyncServiceBrowser(aiozc.zeroconf, SERVICE_TYPE, handlers=[on_change])
        await asyncio.sleep(timeout)
        await browser.async_cancel()
        found: list[DiscoveredSpeaker] = []
        for service in sorted(names):
            info = AsyncServiceInfo(SERVICE_TYPE, service)
            if not await info.async_request(aiozc.zeroconf, 3000):
                continue
            speaker = parse_service_info(info.parsed_addresses(), info.properties, name=service)
            if speaker is not None:
                found.append(speaker)
        return found
    finally:
        await aiozc.async_close()


def discover_blocking(timeout: float = 3.0) -> list[DiscoveredSpeaker]:
    """Blocking version of :func:`discover` (do not call from a running event loop)."""
    return asyncio.run(discover(timeout))
