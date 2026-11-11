"""Typed data structures returned by the clients, and their (pure) parsers."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .capabilities import FirmwareVersion, SpeakerModel
from .enums import EventType, KefEnum, PlaybackState, PlayMode, Source, SpeakerStatus
from .values import decode


class SubscriptionType(KefEnum):
    """What the event queue sends for a subscribed path."""

    ITEM = "item"  #: only "this path changed" (you must fetch the value)
    ITEM_WITH_VALUE = "itemWithValue"  #: the new value is included
    ITEM_WITH_ROLES = "itemWithRoles"
    ROWS = "rows"  #: row-level changes of a container (play queue...)
    ROWS_WITH_ROLES = "rowsWithRoles"


@dataclass(frozen=True, slots=True)
class Subscription:
    """A path to subscribe to on the event queue."""

    path: str
    type: SubscriptionType = SubscriptionType.ITEM_WITH_VALUE

    def to_api(self) -> dict[str, str]:
        return {"path": self.path, "type": str(self.type)}


@dataclass(frozen=True, slots=True)
class Event:
    """One event received from the speaker's event queue.

    :ivar path: API path that changed.
    :ivar type: ``update``, ``remove``... (``itemType`` or ``rowsType``).
    :ivar value: decoded new value (``None`` when not sent: ``item`` subscriptions,
        removals, row events).
    :ivar has_value: whether the event carried a value (``value`` may legitimately be ``None``).
    :ivar raw: the event as sent by the speaker.
    """

    path: str
    type: EventType
    value: Any = None
    has_value: bool = False
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_api(cls, raw: Mapping[str, Any]) -> Event:
        kind = raw.get("itemType") or raw.get("rowsType") or "update"
        has_value = "itemValue" in raw
        return cls(
            path=str(raw.get("path", "")),
            type=EventType(str(kind)),
            value=decode(raw["itemValue"]) if has_value else None,
            has_value=has_value,
            raw=raw,
        )


# --- player ------------------------------------------------------------------


def _dig(obj: Any, *keys: str | int) -> Any:
    for key in keys:
        if isinstance(key, int):
            if not isinstance(obj, list) or len(obj) <= key:
                return None
            obj = obj[key]
        else:
            if not isinstance(obj, Mapping):
                return None
            obj = obj.get(key)
    return obj


def _map(value: Any) -> Mapping[str, Any]:
    """``value`` if it is a mapping, else an empty one (parsers must never raise)."""
    return value if isinstance(value, Mapping) else {}


def _str(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


@dataclass(frozen=True, slots=True)
class Track:
    """What is currently playing.

    Metadata comes from ``trackRoles`` with a fallback on ``mediaRoles`` (radio
    station, playlist...), like the official app. Audio format information comes
    from the first media resource.
    """

    title: str | None = None
    artist: str | None = None
    album: str | None = None
    album_artist: str | None = None
    cover_url: str | None = None
    service_id: str | None = None
    duration_ms: int | None = None
    live: bool = False
    codec: str | None = None
    sample_rate: int | None = None
    bits_per_sample: int | None = None
    channels: int | None = None
    bit_rate: int | None = None

    @classmethod
    def from_player_data(cls, data: Mapping[str, Any]) -> Track | None:
        track = _map(data.get("trackRoles"))
        media = _map(data.get("mediaRoles"))
        if not track and not media:
            return None
        meta_t = _map(_dig(track, "mediaData", "metaData"))
        meta_m = _map(_dig(media, "mediaData", "metaData"))
        resource = _map(_dig(track, "mediaData", "resources", 0))
        active = _map(_dig(track, "mediaData", "activeResource"))  # older firmware keys
        artist = _str(_first(meta_t.get("artist"), meta_m.get("artist")))
        return cls(
            title=_str(_first(track.get("title"), media.get("title"))),
            artist=artist,
            album=_str(_first(meta_t.get("album"), meta_m.get("album"))),
            album_artist=_str(_first(meta_t.get("albumArtist"), meta_m.get("albumArtist"), artist)),
            cover_url=_str(_first(track.get("icon"), media.get("icon"))),
            service_id=_str(_first(meta_t.get("serviceID"), meta_m.get("serviceID"))),
            duration_ms=_int(_first(resource.get("duration"), _dig(data, "status", "duration"))),
            live=bool(_first(meta_t.get("live"), meta_m.get("live"))),
            codec=_str(_first(resource.get("codec"), active.get("codec"))),
            sample_rate=_int(
                _first(
                    resource.get("sampleFrequency"),
                    active.get("sampleFrequency"),
                    active.get("streamSampleRate"),
                )
            ),
            bits_per_sample=_int(resource.get("bitsPerSample")),
            channels=_int(
                _first(
                    resource.get("nrAudioChannels"),
                    active.get("nrAudioChannels"),
                    active.get("streamChannels"),
                )
            ),
            bit_rate=_int(resource.get("bitRate")),
        )


@dataclass(frozen=True, slots=True)
class PlayerControls:
    """Commands currently allowed by the player (``player:player/data`` → ``controls``)."""

    pause: bool = False
    next: bool = False
    previous: bool = False
    seek: bool = False
    play_modes: frozenset[PlayMode] = frozenset()

    @classmethod
    def from_api(cls, raw: Any) -> PlayerControls:
        if not isinstance(raw, Mapping):
            return cls()
        modes = _map(raw.get("playMode"))
        return cls(
            pause=bool(raw.get("pause")),
            next=bool(raw.get("next_", raw.get("next"))),
            previous=bool(raw.get("previous")),
            seek=bool(raw.get("seekTime")),
            play_modes=frozenset(
                PlayMode(name) for name, allowed in modes.items() if allowed is True
            ),
        )


@dataclass(frozen=True, slots=True)
class PlayerState:
    """State of the media player (``player:player/data``)."""

    state: PlaybackState = PlaybackState.STOPPED
    track: Track | None = None
    controls: PlayerControls = PlayerControls()
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def is_playing(self) -> bool:
        return self.state == PlaybackState.PLAYING

    @property
    def duration_ms(self) -> int | None:
        return self.track.duration_ms if self.track else None

    @classmethod
    def from_api(cls, raw: Any) -> PlayerState:
        data = decode(raw)
        if not isinstance(data, Mapping):
            return cls()
        state = PlaybackState.parse(data.get("state")) or PlaybackState.STOPPED
        return cls(
            state=state,
            track=Track.from_player_data(data),
            controls=PlayerControls.from_api(data.get("controls")),
            raw=data,
        )


# --- device ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """Identity of the speaker."""

    name: str | None
    model: SpeakerModel
    model_name: str | None  #: raw ``settings:/kef/host/modelName``
    serial_number: str | None
    mac_address: str | None
    firmware: FirmwareVersion | None  #: parsed firmware version, when recognisable
    firmware_version: str | None  #: raw ``settings:/kef/host/firmwareVersion``, None if unreadable
    release_text: str | None  #: raw ``settings:/releasetext``
    hardware_version: str | None  #: None when the speaker reports ``0.0.0``


@dataclass(frozen=True, slots=True)
class NetworkAddress:
    ip: str
    protocol: str | None = None
    prefix: int | None = None
    dhcp: bool | None = None


@dataclass(frozen=True, slots=True)
class NetworkInterface:
    """A wired or wireless interface of the speaker."""

    name: str | None
    state: str | None
    mac: str | None
    addresses: tuple[NetworkAddress, ...] = ()
    ssid: str | None = None
    bssid: str | None = None
    frequency: int | None = None
    channel: int | None = None
    signal_level: int | None = None  #: dBm

    @classmethod
    def from_api(cls, raw: Any) -> NetworkInterface | None:
        if not isinstance(raw, Mapping):
            return None
        raw_addresses = raw.get("addresses")
        addresses = tuple(
            NetworkAddress(
                ip=str(a.get("ip")),
                protocol=_str(a.get("protocol")),
                prefix=_int(a.get("prefix")),
                dhcp=a.get("dhcp") if isinstance(a.get("dhcp"), bool) else None,
            )
            for a in (raw_addresses if isinstance(raw_addresses, list) else ())
            if isinstance(a, Mapping) and a.get("ip")
        )
        return cls(
            name=raw.get("name"),
            state=raw.get("state"),
            mac=raw.get("mac"),
            addresses=addresses,
            ssid=raw.get("ssid"),
            bssid=raw.get("bssid"),
            frequency=_int(raw.get("frequency")),
            channel=_int(raw.get("channel")),
            signal_level=_int(raw.get("signalLevel")),
        )


@dataclass(frozen=True, slots=True)
class NetworkInfo:
    """Network status of the speaker (``network:info``)."""

    state: str | None
    wired: NetworkInterface | None
    wireless: NetworkInterface | None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def active(self) -> NetworkInterface | None:
        """The interface that is up (wired preferred)."""
        for iface in (self.wired, self.wireless):
            if iface is not None and iface.state == "up" and iface.addresses:
                return iface
        return None

    @property
    def ip_address(self) -> str | None:
        iface = self.active
        return iface.addresses[0].ip if iface else None

    @classmethod
    def from_api(cls, raw: Any) -> NetworkInfo:
        data = decode(raw)
        if not isinstance(data, Mapping):
            data = {}
        return cls(
            state=data.get("state"),
            wired=NetworkInterface.from_api(data.get("wired")),
            wireless=NetworkInterface.from_api(data.get("wireless")),
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class BluetoothState:
    """Bluetooth status (``bluetooth:state``)."""

    connected: bool = False
    discoverable: bool = False
    pairable: bool = False
    discovering: bool = False
    pairing_code: str | None = None

    @classmethod
    def from_api(cls, raw: Any) -> BluetoothState:
        data = decode(raw)
        if not isinstance(data, Mapping):
            return cls()
        return cls(
            connected=bool(data.get("connected")),
            discoverable=bool(data.get("discoverable")),
            pairable=bool(data.get("pairable")),
            discovering=bool(data.get("discovering")),
            pairing_code=_str(data.get("pairingCode")),
        )


# --- aggregated state ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SpeakerState:
    """Snapshot of everything a media-player UI needs, kept up to date by ``watch()``.

    ``position_ms`` is the playback position at ``position_updated_at`` (UTC);
    while playing, the current position is ``position_ms + elapsed`` (this is
    exactly what Home Assistant's ``media_position`` / ``media_position_updated_at``
    expect).

    A field is ``None`` when the value is unknown: not exposed by this speaker /
    firmware, or not applicable (no position when stopped). ``watch()`` yields
    ``None`` *instead of a state* when the speaker becomes unreachable.
    """

    status: SpeakerStatus | None = None
    source: Source | None = None
    volume: int | None = None
    muted: bool | None = None
    play_mode: PlayMode | None = None
    player: PlayerState | None = None
    position_ms: int | None = None
    position_updated_at: datetime | None = None
    name: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_on(self) -> bool:
        """``False`` when the speaker is in standby (like the official app)."""
        if self.status == SpeakerStatus.STANDBY or self.source == Source.STANDBY:
            return False
        return self.status is not None or self.source is not None

    @property
    def playback_state(self) -> PlaybackState | None:
        return self.player.state if self.player else None

    @property
    def track(self) -> Track | None:
        return self.player.track if self.player else None

    def replace(self, **changes: Any) -> SpeakerState:
        return dataclasses.replace(self, **changes)
