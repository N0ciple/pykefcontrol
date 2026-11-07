"""Asynchronous client for KEF W2-platform speakers.

``_sync/client.py`` (:class:`~pykefcontrol.KefClient`) is GENERATED from this
file by ``scripts/gen_sync.py``: edit this file, then regenerate. Only use
constructs that translate mechanically (``await`` is simply removed): no direct
asyncio calls (use ``self._transport.sleep``), no ``asyncio.gather``.
"""

from __future__ import annotations

import logging
import ssl
import time
from collections.abc import AsyncGenerator, Iterable, Mapping
from datetime import UTC, datetime
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self

from .. import _auth, _protocol, const, eq, paths
from ..capabilities import (
    Capabilities,
    FirmwareVersion,
    SpeakerModel,
    get_capabilities,
)
from ..const import TransportMode
from ..enums import PlaybackState, PlayMode, Source, SpeakerStatus
from ..exceptions import (
    KefApiError,
    KefConnectionError,
    KefError,
    KefProtocolError,
)
from ..models import (
    BluetoothState,
    DeviceInfo,
    Event,
    NetworkInfo,
    PlayerState,
    SpeakerState,
    Subscription,
)
from ..settings import Setting, Settings
from ..values import ValueType, decode, encode
from .backend import AsyncBackend
from .transport import AsyncTransport

if TYPE_CHECKING:
    import aiohttp

_LOGGER = logging.getLogger("pykefcontrol")

#: Paths followed by :meth:`KefAsyncClient.watch` (and their state field).
WATCHED_PATHS: tuple[str, ...] = (
    paths.SPEAKER_STATUS,
    paths.PHYSICAL_SOURCE,
    paths.VOLUME,
    paths.MUTE,
    paths.PLAY_MODE,
    paths.PLAY_DATA,
    paths.DEVICE_NAME,
)


class KefAsyncClient:
    """Control one KEF speaker (LS50 Wireless II, LS60, LSX II, LSX II LT, XIO, LS LUXE...).

    The constructor does no I/O. The connection scheme is chosen on the first
    request (or by :meth:`connect`): HTTPS on port 4430 when the firmware supports
    it (with request signing), otherwise plain HTTP on port 80.

    Use it as an async context manager, or call :meth:`aclose` when done::

        async with KefAsyncClient("192.168.1.20") as speaker:
            await speaker.set_volume(30)

    :param host: IP address (recommended) or host name of the speaker.
    :param session: optional :class:`aiohttp.ClientSession` to reuse; it is never
        closed by the client.
    :param transport: ``"auto"`` (default), ``"https"`` or ``"http"``.
    :param credentials: user created on the speaker for HTTPS request signing
        (default: the same user as the official app).
    :param verify_ssl: verify the speaker certificate against the KEF root CA.
    :param ssl_context: prebuilt context (see :func:`pykefcontrol.create_ssl_context`),
        useful to avoid building it inside an event loop that forbids blocking calls.
    :param timeout: timeout of ordinary requests, in seconds.
    :param model: speaker model, if known (skips detection for :meth:`get_capabilities`).
    """

    def __init__(
        self,
        host: str,
        *,
        session: aiohttp.ClientSession | None = None,
        transport: TransportMode | str = TransportMode.AUTO,
        credentials: _auth.Credentials | None = None,
        verify_ssl: bool = True,
        ssl_context: ssl.SSLContext | None = None,
        timeout: float = const.DEFAULT_TIMEOUT,
        model: SpeakerModel | str | None = None,
        http_port: int = const.HTTP_PORT,
        https_port: int = const.HTTPS_PORT,
    ) -> None:
        backend = AsyncBackend(session)
        self._transport = AsyncTransport(
            host,
            backend,
            mode=transport,
            credentials=credentials,
            verify_ssl=verify_ssl,
            ssl_context=ssl_context,
            timeout=timeout,
            http_port=http_port,
            https_port=https_port,
        )
        self._model = SpeakerModel.from_model_name(model) if isinstance(model, str) else model
        self._firmware: FirmwareVersion | None = None
        self._detected = False
        self._last_source: Source | None = None
        self._eq_version: int | None = None
        self._eq_ranges: dict[str, eq.EqRange] | None = None
        self._eq_lock = backend.create_lock()
        self._queue_id: str | None = None
        self._subscriptions: dict[str, Subscription] = {}

    # --- lifecycle -----------------------------------------------------------------

    @property
    def host(self) -> str:
        return self._transport.host

    @property
    def is_secure(self) -> bool | None:
        """``True`` over HTTPS, ``False`` over HTTP, ``None`` before the first request."""
        return self._transport.secure

    async def connect(self) -> None:
        """Choose the transport now (optional: done lazily by the first request)."""
        await self._transport.connect()

    async def aclose(self) -> None:
        """Release network resources (an injected session is left open)."""
        await self._transport.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.host!r})"

    # --- low level API -----------------------------------------------------------

    async def get_data(self, path: str, roles: str = "value") -> Any:
        """Raw ``getData``: first element of the answer (a typed value for ``roles="value"``)."""
        data = await self._transport.request(_protocol.get_data(path, roles))
        return _protocol.parse_get_data(data, path)

    async def get_value(self, path: str) -> Any:
        """Read ``path`` and unwrap its typed value (``{"type":"i32_","i32_":3}`` → ``3``)."""
        return decode(await self.get_data(path))

    async def set_data(self, path: str, value: Any, role: str = "value") -> Any:
        """Raw ``setData`` with an already typed ``value``."""
        return await self._transport.request(_protocol.set_data(path, value, role))

    async def set_value(self, path: str, value_type: ValueType | str, value: Any) -> Any:
        """Write ``value`` to ``path`` as a typed value of ``value_type``."""
        return await self.set_data(path, encode(value_type, value))

    async def activate(self, path: str, value: Any = None) -> Any:
        """Trigger an action node (``role: activate``)."""
        return await self._transport.request(_protocol.activate(path, value))

    async def get_rows(self, path: str, start: int = 0, end: int = 19) -> dict[str, Any]:
        """List rows ``start``..``end`` (inclusive) of a container (play queue, browse tree...)."""
        data = await self._transport.request(_protocol.get_rows(path, start, end))
        return _protocol.parse_rows(data, path)

    async def get_setting[T](self, setting: Setting[T]) -> T:
        """Read a setting from the :class:`~pykefcontrol.Settings` catalogue."""
        return setting.decode(await self.get_data(setting.path))

    async def set_setting[T](self, setting: Setting[T], value: T) -> None:
        """Validate and write a setting from the :class:`~pykefcontrol.Settings` catalogue."""
        await self.set_data(setting.path, setting.encode(value))

    async def _get_optional[T](self, setting: Setting[T]) -> T | None:
        """Read a setting, returning ``None`` if the speaker does not expose it."""
        try:
            return await self.get_setting(setting)
        except (KefApiError, KefProtocolError, ValueError, TypeError):
            return None

    # --- device -------------------------------------------------------------------

    async def get_device_info(self) -> DeviceInfo:
        """Identity of the speaker: name, model, serial number, MAC, firmware."""
        model_name = await self._get_optional(Settings.MODEL_NAME)
        device_version = await self._get_optional(Settings.DEVICE_VERSION)
        release_text = await self._get_optional(Settings.RELEASE_TEXT)
        firmware_version = await self._get_optional(Settings.FIRMWARE_VERSION)
        # settings:/version ("4.1.192.0x869cad1" on LS50WII 4.1) is the reliable source;
        # settings:/kef/host/firmwareVersion holds MCU versions, sometimes unreadable.
        firmware = FirmwareVersion.parse(device_version)
        model = SpeakerModel.from_model_name(model_name)
        if model == SpeakerModel.UNKNOWN and release_text:
            # Release text looks like "LS50WII_V41192".
            model = SpeakerModel.from_model_name(release_text.split("_", 1)[0])
        if model == SpeakerModel.UNKNOWN and self._model is not None:
            model = self._model  # keep the model given to the constructor
        name = await self._get_optional(Settings.DEVICE_NAME)
        serial_number = await self._get_optional(Settings.SERIAL_NUMBER)
        mac_address = await self._get_optional(Settings.MAC_ADDRESS)
        hardware_version = await self._get_optional(Settings.HARDWARE_VERSION)
        if mac_address is None and serial_number is None and model_name is None:
            raise KefProtocolError(f"{self.host} does not look like a KEF speaker")
        self._model, self._firmware, self._detected = model, firmware, True
        return DeviceInfo(
            name=name,
            model=model,
            model_name=model_name,
            serial_number=serial_number,
            mac_address=mac_address,
            firmware=firmware,
            firmware_version=firmware_version,
            release_text=release_text,
            hardware_version=hardware_version,
        )

    async def get_capabilities(self) -> Capabilities:
        """Sources and features of this model / firmware (detected once, then cached)."""
        if not self._detected:
            await self.get_device_info()
        assert self._model is not None
        return get_capabilities(self._model, self._firmware)

    async def get_name(self) -> str:
        return await self.get_setting(Settings.DEVICE_NAME)

    async def set_name(self, name: str) -> None:
        await self.set_setting(Settings.DEVICE_NAME, name)

    async def get_mac_address(self) -> str:
        return await self.get_setting(Settings.MAC_ADDRESS)

    async def get_network_info(self) -> NetworkInfo:
        return NetworkInfo.from_api(await self.get_data(paths.NETWORK_INFO))

    # --- power & source -----------------------------------------------------------

    async def get_status(self) -> SpeakerStatus:
        """``standby``, ``powerOn``, ``networkSetup`` or ``firmwareUpgrade``."""
        return await self.get_setting(Settings.SPEAKER_STATUS)

    async def is_on(self) -> bool:
        return (await self.get_source()) != Source.STANDBY

    async def get_source(self) -> Source:
        """Current source (:attr:`Source.STANDBY` when the speaker is off)."""
        source = await self.get_setting(Settings.PHYSICAL_SOURCE)
        if source != Source.STANDBY:
            self._last_source = source
        return source

    async def set_source(self, source: Source | str) -> None:
        """Select a source; selecting a source wakes the speaker up."""
        source = Source(source)
        await self.set_setting(Settings.PHYSICAL_SOURCE, source)
        if source != Source.STANDBY:
            self._last_source = source

    async def power_on(self, source: Source | str | None = None) -> None:
        """Wake the speaker up on ``source`` (default: last known source, else Wi-Fi).

        Like the official app, this selects a real source.
        """
        await self.set_source(source or self._last_source or Source.WIFI)

    async def power_off(self) -> None:
        """Put the speaker in standby."""
        await self.set_source(Source.STANDBY)

    async def reboot(self) -> None:
        await self.activate(paths.REBOOT)

    async def factory_reset(self) -> None:
        """Reset the speaker to factory settings (it leaves the network!)."""
        await self.activate(paths.FACTORY_RESET)

    # --- volume ---------------------------------------------------------------------

    async def get_volume(self) -> int:
        """Volume, 0-100."""
        return await self.get_setting(Settings.VOLUME)

    async def set_volume(self, volume: int) -> None:
        """Set the volume (0-100)."""
        await self.set_setting(Settings.VOLUME, volume)

    async def volume_up(self, step: int | None = None) -> int:
        """Raise the volume by ``step`` (default: speaker's volume step); return the new volume."""
        return await self._step_volume(step, +1)

    async def volume_down(self, step: int | None = None) -> int:
        """Lower the volume by ``step`` (default: speaker's volume step); return the new volume."""
        return await self._step_volume(step, -1)

    async def _step_volume(self, step: int | None, direction: int) -> int:
        if step is None:
            step = await self._get_optional(Settings.VOLUME_STEP) or 1
        volume = max(0, min(100, await self.get_volume() + direction * step))
        await self.set_volume(volume)
        return volume

    async def get_mute(self) -> bool:
        return await self.get_setting(Settings.MUTE)

    async def set_mute(self, muted: bool) -> None:
        """Mute or unmute (the volume is left untouched)."""
        await self.set_setting(Settings.MUTE, muted)

    async def set_default_volume(self, volume: int, source: Source | str | None = None) -> None:
        """Set the volume applied when waking up, globally or for one ``source``.

        Uses the ``hostlink:defaultVolume/set`` action of the official app (experimental).
        """
        if isinstance(volume, bool) or not 0 <= volume <= 100:
            raise ValueError("volume must be an int between 0 and 100")
        value = {
            "kefPhysicalSource": str(Source(source)) if source is not None else None,
            "defaultVolume": volume,
        }
        await self.activate(
            paths.RESET_DEFAULT_VOLUME_LEVEL_SET, encode(ValueType.DEFAULT_VOLUME_SETTINGS, value)
        )

    # --- playback -----------------------------------------------------------------

    async def get_player_state(self) -> PlayerState:
        """Playback state, current track and allowed controls."""
        return PlayerState.from_api(await self.get_data(paths.PLAY_DATA))

    async def get_play_position(self) -> int:
        """Position in the current track, in milliseconds."""
        return int(await self.get_value(paths.PLAY_TIME))

    async def _control(self, command: str, **args: Any) -> None:
        await self.activate(paths.CONTROL, {"control": command, **args})

    async def play_pause(self) -> None:
        """Toggle play / pause (the speaker's ``pause`` command is a toggle)."""
        await self._control("pause")

    async def play(self) -> None:
        """Resume playback (no-op if already playing)."""
        if (await self.get_player_state()).state != PlaybackState.PLAYING:
            await self._control("pause")

    async def pause(self) -> None:
        """Pause playback (no-op if not playing)."""
        if (await self.get_player_state()).state == PlaybackState.PLAYING:
            await self._control("pause")

    async def stop(self) -> None:
        await self._control("stop")

    async def next_track(self) -> None:
        await self._control("next")

    async def previous_track(self) -> None:
        await self._control("previous")

    async def seek(self, position_ms: int) -> None:
        """Seek to ``position_ms`` milliseconds in the current track."""
        if position_ms < 0:
            raise ValueError("position_ms must be >= 0")
        await self._control("seekTime", time=int(position_ms))

    async def get_play_mode(self) -> PlayMode:
        return await self.get_setting(Settings.PLAY_MODE)

    async def set_play_mode(self, mode: PlayMode | str) -> None:
        """Set shuffle / repeat (see :meth:`PlayMode.from_flags`)."""
        await self.set_setting(Settings.PLAY_MODE, PlayMode(mode))

    async def play_url(
        self, url: str, *, title: str | None = None, mime_type: str = "audio/unknown"
    ) -> None:
        """Play an audio stream URL (internet radio), like the app's custom radios. Experimental."""
        roles = {
            "title": title or url,
            "type": "audio",
            "audioType": "audioBroadcast",
            "mediaData": {
                "metaData": {"serviceID": "customRadio", "live": True},
                "resources": [{"uri": url, "mimeType": mime_type}],
            },
        }
        await self._control("play", type="none", mediaRoles=roles)

    # --- bluetooth ----------------------------------------------------------------

    async def get_bluetooth_state(self) -> BluetoothState:
        return BluetoothState.from_api(await self.get_data(paths.BLUETOOTH_STATE))

    async def bluetooth_pairing(self) -> None:
        """Make the speaker discoverable for Bluetooth pairing."""
        await self.activate(paths.BLUETOOTH_EXTERNAL_DISCOVERABLE)

    async def bluetooth_disconnect(self) -> None:
        await self.activate(paths.BLUETOOTH_DISCONNECT)

    # --- EQ / DSP -------------------------------------------------------------------

    async def get_eq_version(self) -> int:
        """EQ profile format of this speaker: 2 (values) or 1 (indices, old LS50WII firmware)."""
        if self._eq_version is None:
            try:
                await self.get_data(paths.EQ_PROFILE_V2)
            except KefApiError as v2_error:
                # Only conclude "v1" if the v1 node really exists (not a transient error).
                try:
                    await self.get_data(paths.EQ_PROFILE)
                except KefError:
                    raise v2_error from None
                self._eq_version = 1
            else:
                self._eq_version = 2
        return self._eq_version

    async def get_eq_profile(self) -> eq.EqProfile:
        """Current EQ / DSP profile, in physical units whatever the speaker's format."""
        version = await self.get_eq_version()
        raw = await self.get_data(paths.EQ_PROFILE_V2 if version == 2 else paths.EQ_PROFILE)
        return eq.parse_eq_profile(raw)

    async def set_eq_profile(
        self, profile: eq.EqProfile, *, validate: bool = True, wait: bool = True
    ) -> None:
        """Write a whole EQ profile (the official app always writes the whole profile).

        The speaker applies EQ writes asynchronously (~70 ms on an LS50 Wireless II):
        a read right after the write still returns the old profile. With ``wait``
        (the default), return only once the speaker reports the new profile (or after
        :data:`~pykefcontrol.const.EQ_APPLY_TIMEOUT` seconds), so that a following
        read, or :meth:`update_eq_profile`, sees it.

        With ``validate``, values are checked against :meth:`get_eq_ranges`.
        """
        if validate:
            eq.validate_eq_profile(profile, await self.get_eq_ranges())
        version = await self.get_eq_version()
        path = paths.EQ_PROFILE_V2 if version == 2 else paths.EQ_PROFILE
        await self.set_data(path, eq.eq_profile_to_api(profile, version))
        if wait:
            await self._wait_eq_profile(profile)

    async def _wait_eq_profile(self, expected: eq.EqProfile) -> None:
        deadline = time.monotonic() + const.EQ_APPLY_TIMEOUT
        while True:
            await self._transport.sleep(const.EQ_APPLY_POLL_INTERVAL)
            if await self.get_eq_profile() == expected:
                return
            if time.monotonic() >= deadline:
                _LOGGER.debug("%s: EQ profile not confirmed by the speaker", self.host)
                return

    async def update_eq_profile(self, **changes: Any) -> eq.EqProfile:
        """Change some EQ fields (read, modify, write). Returns the new profile.

        Calls are serialized, so concurrent updates of different fields don't
        overwrite each other.

        >>> await speaker.update_eq_profile(treble=1.5, bass_extension=BassExtension.EXTRA)
        """
        async with self._eq_lock:
            profile = (await self.get_eq_profile()).replace(**changes)
            await self.set_eq_profile(profile)
            return profile

    async def reset_eq_profile(self) -> None:
        """Restore the default DSP settings."""
        version = await self.get_eq_version()
        await self.activate(paths.RESTORE_DSP_INFO_V2 if version == 2 else paths.RESTORE_DSP_INFO)

    async def get_eq_descriptors(self) -> dict[str, eq.EqDescriptor]:
        """Ranges / choices advertised by the speaker for each EQ setting (EQ v2 only)."""
        return eq.parse_eq_descriptors(await self.get_rows(paths.EQ_FORMAT, 0, 100))

    async def get_eq_ranges(self) -> dict[str, eq.EqRange]:
        """Allowed range of each numeric EQ field (cached).

        The speaker's own ranges (EQ v2 descriptors) where it advertises them, the
        app's defaults (:data:`~pykefcontrol.eq.DEFAULT_RANGES`) otherwise.
        """
        if self._eq_ranges is None:
            ranges = dict(eq.DEFAULT_RANGES)
            if await self.get_eq_version() == 2:
                try:
                    ranges.update(eq.ranges_from_descriptors(await self.get_eq_descriptors()))
                except KefError as err:
                    _LOGGER.debug("%s: no EQ descriptors (%s), using defaults", self.host, err)
                    return ranges  # not cached: retried on the next call
            self._eq_ranges = ranges
        return self._eq_ranges

    # --- state snapshot -----------------------------------------------------------

    async def get_state(self, extra_paths: Iterable[str] = ()) -> SpeakerState:
        """Read everything a media-player UI needs in one call.

        ``extra_paths`` are read too and stored, decoded, in :attr:`SpeakerState.extra`.
        """
        source = await self.get_source()
        player = await self.get_player_state()
        position, updated_at = await self._read_position(player)
        extra: dict[str, Any] = {}
        for path in extra_paths:
            try:
                extra[path] = await self.get_value(path)
            except (KefApiError, KefProtocolError):
                extra[path] = None
        status = await self.get_status()
        volume = await self.get_volume()
        muted = await self._get_optional(Settings.MUTE)
        play_mode = await self._get_optional(Settings.PLAY_MODE)
        name = await self._get_optional(Settings.DEVICE_NAME)
        return SpeakerState(
            status=status,
            source=source,
            volume=volume,
            muted=muted,
            play_mode=play_mode,
            player=player,
            position_ms=position,
            position_updated_at=updated_at,
            name=name,
            extra=extra,
        )

    async def _read_position(self, player: PlayerState) -> tuple[int | None, datetime | None]:
        if player.state not in (PlaybackState.PLAYING, PlaybackState.PAUSED):
            return None, None
        try:
            return await self.get_play_position(), datetime.now(UTC)
        except (KefApiError, KefProtocolError, TypeError, ValueError):
            return None, None

    # --- events -------------------------------------------------------------------

    def event_queue(self) -> AsyncEventQueue:
        """Create a new, empty event queue on this speaker (no I/O until used).

        Queues are independent: each consumer should use its own.
        """
        return AsyncEventQueue(self._transport)

    async def events(
        self, subscriptions: Iterable[str | Subscription], *, timeout: int = const.POLL_TIMEOUT
    ) -> AsyncGenerator[Event]:
        """Subscribe to ``subscriptions`` on a new queue and yield every event, forever.

        Low level: errors are raised (see :meth:`watch` for automatic reconnection).
        """
        queue = self.event_queue()
        await queue.subscribe(subscriptions)
        while True:
            for event in await queue.poll(timeout):
                yield event

    async def watch(
        self,
        *,
        extra_paths: Iterable[str] = (),
        track_position: bool = False,
        reconnect: bool = True,
    ) -> AsyncGenerator[SpeakerState | None]:
        """Yield a fresh :class:`SpeakerState` every time something changes on the speaker.

        This is the recommended way to follow a speaker (push updates, no polling
        interval): one long-poll request is kept open on a private event queue.

        * The first item is a full snapshot; then a new state is yielded after each
          change.
        * ``None`` is yielded when the speaker is unreachable (including when it is
          already offline at start); the client then retries with exponential
          back-off (1 s → 30 s), re-subscribes and yields a full snapshot again.
          An expired event queue is recreated silently. With ``reconnect=False``
          errors are raised instead.
        * ``extra_paths`` are followed too and exposed in :attr:`SpeakerState.extra`.
        * ``track_position=True`` also follows the play time (one event per second
          while playing). By default the position is refreshed on every player
          change, which is enough to extrapolate it (as Home Assistant does).
        * The iteration ends when the client is closed.

        ::

            async for state in speaker.watch():
                if state is None:
                    print("speaker unavailable")
                else:
                    print(state.volume, state.track)
        """
        extra = tuple(extra_paths)
        followed = WATCHED_PATHS + extra + ((paths.PLAY_TIME,) if track_position else ())
        queue = self.event_queue()
        delay = const.RECONNECT_DELAY_MIN
        available: bool | None = None  # None: nothing yielded yet
        state: SpeakerState | None = None
        while not self._transport.closed:
            try:
                if state is None:
                    queue.reset()
                    await queue.subscribe(followed)
                    state = await self.get_state(extra)
                    available = True
                    yield state
                started = time.monotonic()
                try:
                    events = await queue.poll()
                except KefApiError as err:
                    # The speaker forgot the queue: recreate it and resync, quietly.
                    _LOGGER.debug("%s: event queue lost (%s), resubscribing", self.host, err)
                    state = None
                    await self._transport.sleep(delay)
                    delay = min(delay * 2, const.RECONNECT_DELAY_MAX)
                    continue
                delay = const.RECONNECT_DELAY_MIN
                if not events:
                    if time.monotonic() - started < const.MIN_POLL_INTERVAL:
                        await self._transport.sleep(const.MIN_POLL_INTERVAL)  # don't spin
                    continue
                try:
                    new_state = await self._apply_events(
                        state, _protocol.latest_per_path(events), extra
                    )
                except KefConnectionError:
                    raise
                except Exception as err:  # unexpected data: resync from scratch
                    _LOGGER.debug("%s: could not apply events (%r), resyncing", self.host, err)
                    new_state = await self.get_state(extra)
                if new_state != state:
                    state = new_state
                    yield state
            except KefError as err:
                if self._transport.closed:
                    return  # aclose() interrupted a request: just stop
                if not reconnect:
                    raise
                state = None
                if available is not False:
                    _LOGGER.warning("%s: speaker unavailable (%s), retrying", self.host, err)
                    available = False
                    yield None
                else:
                    _LOGGER.debug("%s: still unavailable (%s), retry in %ss", self.host, err, delay)
                self._transport.invalidate()
                await self._transport.sleep(delay)
                delay = min(delay * 2, const.RECONNECT_DELAY_MAX)

    async def _apply_events(
        self, state: SpeakerState, events: Iterable[Event], extra_paths: tuple[str, ...]
    ) -> SpeakerState:
        changes: dict[str, Any] = {}
        extra: dict[str, Any] | None = None
        refresh_position = False
        for event in events:
            value = event.value if event.has_value else None
            path = event.path
            if path == paths.PLAY_DATA:
                if event.has_value and isinstance(value, Mapping):
                    player = PlayerState.from_api(value)
                else:
                    player = await self.get_player_state()
                changes["player"] = player
                refresh_position = True
            elif path == paths.PLAY_TIME:
                if isinstance(value, int | float) and not isinstance(value, bool):
                    changes["position_ms"] = int(value)
                    changes["position_updated_at"] = datetime.now(UTC)
            elif path in _EVENT_SETTINGS:
                setting = _EVENT_SETTINGS[path]
                field_name = _EVENT_FIELDS[path]
                if not event.has_value:
                    changes[field_name] = await self._get_optional(setting)
                else:
                    try:
                        changes[field_name] = setting.decode(event.raw.get("itemValue"))
                    except (KefProtocolError, ValueError, TypeError):
                        changes[field_name] = None
                if path == paths.PHYSICAL_SOURCE:
                    source = changes[field_name]
                    if isinstance(source, Source) and source != Source.STANDBY:
                        self._last_source = source
            elif path in extra_paths:
                if extra is None:
                    extra = dict(state.extra)
                extra[path] = value if event.has_value else await self._get_value_or_none(path)
        if refresh_position:
            player = changes["player"]
            changes["position_ms"], changes["position_updated_at"] = await self._read_position(
                player
            )
        if extra is not None:
            changes["extra"] = extra
        return state.replace(**changes) if changes else state

    async def _get_value_or_none(self, path: str) -> Any:
        try:
            return await self.get_value(path)
        except (KefApiError, KefProtocolError):
            return None


class AsyncEventQueue:
    """An event queue on the speaker: subscribe to paths, then long-poll for changes.

    Create it with :meth:`KefAsyncClient.event_queue`. A queue belongs to one
    consumer; create one per consumer. The speaker does not replay current values:
    read the state after subscribing.

    ::

        queue = speaker.event_queue()
        await queue.subscribe([paths.VOLUME, paths.MUTE])
        while True:
            for event in await queue.poll():
                print(event.path, event.value)
    """

    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport
        self._queue_id: str | None = None
        self._subscriptions: dict[str, Subscription] = {}

    @property
    def queue_id(self) -> str | None:
        """Id of the queue on the speaker (``None`` before the first subscription)."""
        return self._queue_id

    @property
    def subscriptions(self) -> tuple[Subscription, ...]:
        return tuple(self._subscriptions.values())

    def reset(self) -> None:
        """Forget the queue (the next :meth:`subscribe` creates a new one)."""
        self._queue_id = None
        self._subscriptions = {}

    async def subscribe(
        self,
        subscriptions: Iterable[str | Subscription],
        *,
        unsubscribe: Iterable[str | Subscription] = (),
    ) -> bool:
        """Add (and remove) paths, creating the queue if needed.

        Returns ``True`` if a *new* queue was created: events may have been missed,
        so callers should re-read the state.
        """
        add = [s if isinstance(s, Subscription) else Subscription(s) for s in subscriptions]
        remove = [s if isinstance(s, Subscription) else Subscription(s) for s in unsubscribe]
        request = _protocol.modify_queue(add, remove, self._queue_id)
        queue_id = _protocol.parse_queue_id(await self._transport.request(request))
        created = queue_id != self._queue_id
        if created and self._queue_id is not None:
            # The speaker replaced the queue: re-send every subscription.
            remaining = {**self._subscriptions, **{s.path: s for s in add}}
            for sub in remove:
                remaining.pop(sub.path, None)
            self.reset()
            await self.subscribe(remaining.values())
            return True
        self._queue_id = queue_id
        for sub in add:
            self._subscriptions[sub.path] = sub
        for sub in remove:
            self._subscriptions.pop(sub.path, None)
        return created

    async def poll(self, timeout: int = const.POLL_TIMEOUT) -> list[Event]:
        """Wait up to ``timeout`` seconds for events (``[]`` on timeout), in arrival order.

        :raises KefApiError: the speaker does not know the queue (expired): subscribe again.
        """
        if self._queue_id is None:
            raise KefError("Not subscribed: call subscribe() first")
        try:
            data = await self._transport.request(_protocol.poll_queue(self._queue_id, timeout))
        except (KefApiError, KefConnectionError):
            self._queue_id = None  # the queue is probably gone; resubscribe
            raise
        return _protocol.parse_events(data)


_EVENT_SETTINGS: dict[str, Setting[Any]] = {
    paths.SPEAKER_STATUS: Settings.SPEAKER_STATUS,
    paths.PHYSICAL_SOURCE: Settings.PHYSICAL_SOURCE,
    paths.VOLUME: Settings.VOLUME,
    paths.MUTE: Settings.MUTE,
    paths.PLAY_MODE: Settings.PLAY_MODE,
    paths.DEVICE_NAME: Settings.DEVICE_NAME,
}
_EVENT_FIELDS: dict[str, str] = {
    paths.SPEAKER_STATUS: "status",
    paths.PHYSICAL_SOURCE: "source",
    paths.VOLUME: "volume",
    paths.MUTE: "muted",
    paths.PLAY_MODE: "play_mode",
    paths.DEVICE_NAME: "name",
}
