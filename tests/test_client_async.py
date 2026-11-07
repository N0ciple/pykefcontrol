"""Tests of the asyncio client (KefAsyncClient) against the fake speaker.

Parallel to test_client_sync.py: the test bodies are the same, with ``await``.
Every test runs over plain HTTP and over signed HTTPS.
"""

from __future__ import annotations

import ssl
from collections.abc import AsyncIterator
from typing import Any

import aiohttp
import pytest

from pykefcontrol import (
    BassExtension,
    KefApiError,
    KefAsyncClient,
    KefConnectionError,
    KefError,
    KefProtocolError,
    KefTimeoutError,
    PlaybackState,
    PlayMode,
    Settings,
    Source,
    SpeakerModel,
    SpeakerStatus,
    ValueType,
)

from .fake_speaker import FakeSpeaker, free_port, typed
from .test_eq import v1_inner, v2_inner


@pytest.fixture
def fake(auto_speaker: FakeSpeaker) -> FakeSpeaker:
    return auto_speaker


def make(
    fake: FakeSpeaker, ssl_context: ssl.SSLContext | None = None, **kwargs: Any
) -> KefAsyncClient:
    kwargs.setdefault("http_port", fake.http_port)
    kwargs.setdefault("https_port", fake.https_port)
    return KefAsyncClient(fake.host, ssl_context=ssl_context, **kwargs)


@pytest.fixture
async def client(
    fake: FakeSpeaker, ssl_context: ssl.SSLContext, transport_mode: str
) -> AsyncIterator[KefAsyncClient]:
    async with make(fake, ssl_context, transport=transport_mode) as c:
        yield c


async def test_transport_matches_mode(client: Any, transport_mode: str) -> None:
    assert client.is_secure is None
    await client.get_volume()
    assert client.is_secure is (transport_mode == "https")


async def test_get_and_set_volume(client: Any, fake: FakeSpeaker) -> None:
    assert await client.get_volume() == 30
    await client.set_volume(45)
    assert fake.store["player:volume"] == typed("i32_", 45)
    assert fake.set_data_calls() == [
        {"path": "player:volume", "role": "value", "value": typed("i32_", 45)}
    ]
    assert await client.get_volume() == 45


@pytest.mark.parametrize("bad", [101, -1])
async def test_set_volume_validation(client: Any, fake: FakeSpeaker, bad: int) -> None:
    with pytest.raises(ValueError, match="volume"):
        await client.set_volume(bad)
    assert fake.set_data_calls() == []


async def test_volume_up_down_use_speaker_step(client: Any, fake: FakeSpeaker) -> None:
    assert await client.volume_up() == 35  # volumeStep is 5
    assert await client.volume_down(10) == 25
    fake.set("player:volume", typed("i32_", 98))
    assert await client.volume_up() == 100


async def test_mute(client: Any, fake: FakeSpeaker) -> None:
    assert await client.get_mute() is False
    await client.set_mute(True)
    assert fake.store["settings:/mediaPlayer/mute"] == typed("bool_", True)
    assert fake.store["player:volume"] == typed("i32_", 30)  # volume untouched
    assert await client.get_mute() is True


async def test_set_source(client: Any, fake: FakeSpeaker) -> None:
    await client.set_source("optical")
    assert fake.store["settings:/kef/play/physicalSource"] == typed("kefPhysicalSource", "optical")
    assert await client.get_source() == Source.OPTICAL
    assert await client.is_on() is True


async def test_power_on_defaults_to_wifi_then_last_source(client: Any, fake: FakeSpeaker) -> None:
    fake.set("settings:/kef/play/physicalSource", typed("kefPhysicalSource", "standby"))
    assert await client.is_on() is False
    await client.power_on()
    assert await client.get_source() == Source.WIFI
    await client.set_source(Source.TV)
    await client.power_off()
    assert fake.store["settings:/kef/play/physicalSource"] == typed("kefPhysicalSource", "standby")
    await client.power_on()
    assert await client.get_source() == Source.TV
    await client.power_on(Source.USB)
    assert await client.get_source() == Source.USB


async def test_power_off_writes_standby(client: Any, fake: FakeSpeaker) -> None:
    await client.power_off()
    assert fake.set_data_calls() == [
        {
            "path": "settings:/kef/play/physicalSource",
            "role": "value",
            "value": typed("kefPhysicalSource", "standby"),
        }
    ]


async def test_play_pause_are_idempotent(client: Any, fake: FakeSpeaker) -> None:
    await client.play()  # already playing
    assert fake.controls == []
    await client.pause()
    assert fake.controls == [{"control": "pause"}]
    got = await client.get_player_state()
    assert got.state == PlaybackState.PAUSED
    await client.pause()  # already paused
    assert len(fake.controls) == 1
    await client.play()
    assert len(fake.controls) == 2
    got = await client.get_player_state()
    assert got.state == PlaybackState.PLAYING


async def test_play_pause_toggles(client: Any, fake: FakeSpeaker) -> None:
    await client.play_pause()
    await client.play_pause()
    assert fake.controls == [{"control": "pause"}, {"control": "pause"}]
    got = await client.get_player_state()
    assert got.is_playing


async def test_transport_controls(client: Any, fake: FakeSpeaker) -> None:
    await client.stop()
    await client.next_track()
    await client.previous_track()
    await client.seek(12345)
    assert fake.controls == [
        {"control": "stop"},
        {"control": "next"},
        {"control": "previous"},
        {"control": "seekTime", "time": 12345},
    ]
    assert fake.activations[-1] == ("player:player/control", {"control": "seekTime", "time": 12345})
    with pytest.raises(ValueError, match="position_ms"):
        await client.seek(-1)


async def test_get_player_state_and_position(client: Any) -> None:
    state = await client.get_player_state()
    assert state.is_playing
    assert state.track is not None and state.track.title == "Song"
    assert await client.get_play_position() == 42000


async def test_play_mode(client: Any, fake: FakeSpeaker) -> None:
    await client.set_play_mode(PlayMode.SHUFFLE)
    assert fake.store["settings:/mediaPlayer/playMode"] == typed("playerPlayMode", "shuffle")
    assert await client.get_play_mode() == PlayMode.SHUFFLE


async def test_device_info_and_capabilities(client: Any) -> None:
    info = await client.get_device_info()
    assert info.model == SpeakerModel.LS50_WIRELESS_II
    assert info.model_name == "LS50WII"
    assert info.name == "Living room"
    assert info.serial_number == "SN123"
    assert info.mac_address == "AA:BB:CC:DD:EE:FF"
    assert info.firmware is not None and (info.firmware.major, info.firmware.minor) == (4, 2)
    caps = await client.get_capabilities()
    assert caps.model == SpeakerModel.LS50_WIRELESS_II
    assert Source.WIFI in caps.sources
    assert await client.get_name() == "Living room"
    assert await client.get_mac_address() == "AA:BB:CC:DD:EE:FF"


async def test_device_info_with_product_code_model_name(client: Any, fake: FakeSpeaker) -> None:
    fake.set("settings:/kef/host/modelName", typed("string_", "SP4025"))
    info = await client.get_device_info()
    assert info.model_name == "SP4025"
    assert info.model == SpeakerModel.LS50_WIRELESS_II  # from the release text
    assert info.firmware is not None and str(info.firmware).startswith("4.2.1")
    assert info.firmware_version is not None  # raw (garbled) host value is kept as is


async def test_device_info_firmware_from_version_only(client: Any, fake: FakeSpeaker) -> None:
    del fake.store["settings:/version"]
    info = await client.get_device_info()
    assert info.firmware is None


async def test_device_info_rejects_non_kef_device(client: Any, fake: FakeSpeaker) -> None:
    for path in (
        "settings:/kef/host/modelName",
        "settings:/kef/host/serialNumber",
        "settings:/system/primaryMacAddress",
    ):
        del fake.store[path]
    with pytest.raises(KefProtocolError, match="KEF"):
        await client.get_device_info()


async def test_device_info_keeps_constructor_model(fake: FakeSpeaker) -> None:
    del fake.store["settings:/kef/host/modelName"]
    del fake.store["settings:/releasetext"]
    async with make(fake, transport="http", model="xio") as c:
        info = await c.get_device_info()
        assert info.model == SpeakerModel.XIO


async def test_capabilities_detects_model_lazily(client: Any, fake: FakeSpeaker) -> None:
    fake.set("settings:/kef/host/modelName", typed("string_", "LSXII"))
    got = await client.get_capabilities()
    assert got.model == SpeakerModel.LSX_II


async def test_eq_version_1_needs_the_v1_node(client: Any, fake: FakeSpeaker) -> None:
    fake.store["kef:eqProfile"] = typed("kefEqProfile", v1_inner())
    assert await client.get_eq_version() == 1  # v2 node missing, v1 readable
    fake.store["kef:eqProfile/v2"] = typed("kefEqProfileV2", v2_inner())
    assert await client.get_eq_version() == 1  # cached


async def test_eq_version_error_is_not_cached(client: Any, fake: FakeSpeaker) -> None:
    with pytest.raises(KefApiError) as info:  # neither node exists: no conclusion
        await client.get_eq_version()
    assert "does not exist" in str(info.value)
    fake.overrides["kef:eqProfile/v2"] = (503, b"busy")  # transient error, v1 absent
    with pytest.raises(KefApiError) as info:
        await client.get_eq_version()
    assert info.value.status == 503
    del fake.overrides["kef:eqProfile/v2"]
    fake.store["kef:eqProfile/v2"] = typed("kefEqProfileV2", v2_inner())
    assert await client.get_eq_version() == 2


async def test_eq_version_2_and_update_roundtrip(client: Any, fake: FakeSpeaker) -> None:
    fake.store["kef:eqProfile/v2"] = typed("kefEqProfileV2", v2_inner())
    assert await client.get_eq_version() == 2
    profile = await client.update_eq_profile(treble=1.5, bass_extension=BassExtension.LESS)
    assert profile.treble == 1.5
    written = fake.set_data_calls()
    assert [c["path"] for c in written] == ["kef:eqProfile/v2"]  # whole profile, one write
    sent = written[0]["value"]["kefEqProfileV2"]
    assert sent["trebleAmount"] == 1.5
    assert sent["bassExtension"] == "less"
    assert sent["profileName"] == "Night"  # untouched fields are written back
    assert sent["balance"] == -4
    got = await client.get_eq_profile()
    assert got.treble == 1.5


async def test_eq_v1_profile(client: Any, fake: FakeSpeaker) -> None:
    fake.store["kef:eqProfile"] = typed("kefEqProfile", v1_inner())
    assert await client.get_eq_version() == 1
    got = await client.get_eq_profile()
    assert got.version == 1
    await client.reset_eq_profile()
    assert fake.activations[-1][0] == "kef:restoreDspSettings"


async def test_eq_descriptors_use_get_rows(client: Any, fake: FakeSpeaker) -> None:
    fake.rows["kef:dsp/editValue"] = []
    assert await client.get_eq_descriptors() == {}
    (req,) = fake.requests_to("/api/getRows")
    assert req.query == {"path": "kef:dsp/editValue", "roles": "@all", "from": "0", "to": "100"}


async def test_get_rows(client: Any, fake: FakeSpeaker) -> None:
    fake.rows["browse:"] = [{"title": str(i)} for i in range(5)]
    data = await client.get_rows("browse:", 1, 2)
    assert data["rows"] == [{"title": "1"}, {"title": "2"}]
    assert data["rowsCount"] == 5


async def test_get_state_snapshot(client: Any, fake: FakeSpeaker) -> None:
    fake.store["custom:path"] = typed("string_", "hello")
    state = await client.get_state(extra_paths=["custom:path", "missing:path"])
    assert state.status == SpeakerStatus.POWER_ON
    assert state.source == Source.WIFI
    assert state.volume == 30
    assert state.muted is False
    assert state.play_mode == PlayMode.NORMAL
    assert state.name == "Living room"
    assert state.playback_state == PlaybackState.PLAYING
    assert state.position_ms == 42000
    assert state.position_updated_at is not None
    assert state.extra == {"custom:path": "hello", "missing:path": None}
    assert state.is_on


async def test_get_state_no_position_when_stopped(client: Any, fake: FakeSpeaker) -> None:
    fake.set("player:player/data", {"state": "stopped"})
    state = await client.get_state()
    assert state.position_ms is None and state.position_updated_at is None


async def test_get_setting_set_setting(client: Any, fake: FakeSpeaker) -> None:
    assert await client.get_setting(Settings.MAXIMUM_VOLUME) == 80
    await client.set_setting(Settings.MAXIMUM_VOLUME, 60)
    assert fake.store["settings:/kef/host/maximumVolume"] == typed("i32_", 60)
    await client.set_setting(Settings.DEVICE_NAME, "Kitchen")
    assert await client.get_setting(Settings.DEVICE_NAME) == "Kitchen"
    with pytest.raises(ValueError, match="read-only"):
        await client.set_setting(Settings.MODEL_NAME, "x")
    with pytest.raises(TypeError):
        await client.set_setting(Settings.MUTE, 1)


async def test_set_source_unknown_value_fails_before_any_request(
    client: Any, fake: FakeSpeaker
) -> None:
    with pytest.raises(ValueError, match="wfi"):
        await client.set_source("wfi")
    assert fake.requests == []


@pytest.mark.parametrize(
    "bad",
    [typed("string_", "loud"), typed("bool_", True), {"type": "i32_"}],
)
async def test_get_setting_type_mismatch_is_protocol_error(
    client: Any, fake: FakeSpeaker, bad: Any
) -> None:
    fake.store["player:volume"] = bad
    with pytest.raises(KefProtocolError):
        await client.get_volume()


async def test_set_name_and_activate(client: Any, fake: FakeSpeaker) -> None:
    await client.set_name("Den")
    assert fake.store["settings:/deviceName"] == typed("string_", "Den")
    await client.reboot()
    assert fake.activations[-1] == ("powermanager:goReboot", {})


async def test_low_level_api(client: Any, fake: FakeSpeaker) -> None:
    assert await client.get_value("player:volume") == 30
    assert await client.get_data("player:volume") == typed("i32_", 30)
    await client.set_value("player:volume", ValueType.I32, 12)
    assert fake.store["player:volume"] == typed("i32_", 12)
    await client.set_data("player:volume", typed("i32_", 13))
    assert fake.store["player:volume"] == typed("i32_", 13)


async def test_api_error_maps_to_kef_api_error(client: Any) -> None:
    with pytest.raises(KefApiError) as info:
        await client.get_value("nope:nope")
    assert info.value.status == 500
    assert info.value.path == "nope:nope"
    assert info.value.message == (
        "Node at path 'nope:nope' does not exist (CMAbstractWorker::invalidPath)"
    )


async def test_post_error_status(client: Any, fake: FakeSpeaker) -> None:
    fake.overrides["x:y"] = (503, b"busy")
    with pytest.raises(KefApiError) as info:
        await client.activate("x:y", {"control": "pause"})
    assert (info.value.status, info.value.message) == (503, "busy")


async def test_invalid_json_is_protocol_error(client: Any, fake: FakeSpeaker) -> None:
    fake.overrides["x:y"] = (200, b"<html>")
    with pytest.raises(KefProtocolError):
        await client.get_data("x:y")


async def test_connection_refused(fake: FakeSpeaker) -> None:
    async with make(fake, transport="http", http_port=free_port()) as c:
        with pytest.raises(KefConnectionError) as info:
            await c.get_volume()
        assert not isinstance(info.value, KefTimeoutError)


async def test_dropped_connection(fake: FakeSpeaker) -> None:
    fake.drop_connections = True
    async with make(fake, transport="http") as c:
        with pytest.raises(KefConnectionError):
            await c.get_volume()


async def test_timeout(fake: FakeSpeaker) -> None:
    fake.response_delay = 1.0
    async with make(fake, transport="http", timeout=0.2) as c:
        with pytest.raises(KefTimeoutError):
            await c.get_volume()


async def test_event_queue_basics(client: Any, fake: FakeSpeaker) -> None:
    queue = client.event_queue()
    assert fake.requests == []  # creating a queue does no I/O
    with pytest.raises(KefError, match="Not subscribed"):
        await queue.poll(0)
    assert await queue.subscribe(["player:volume"]) is True
    assert queue.queue_id in fake.queues
    assert [s.path for s in queue.subscriptions] == ["player:volume"]
    fake.set("player:volume", typed("i32_", 3))
    fake.set("player:volume", typed("i32_", 4))
    assert [e.value for e in await queue.poll(1)] == [3, 4]  # all events, in order
    queue.reset()
    assert queue.queue_id is None and queue.subscriptions == ()


async def test_context_manager_closes_owned_session(fake: FakeSpeaker) -> None:
    c = make(fake, transport="http")
    async with c:
        await c.get_volume()
        session = c._transport._backend._session
        assert session is not None and not session.closed
    assert session.closed


async def test_injected_session_is_not_closed(fake: FakeSpeaker) -> None:
    async with aiohttp.ClientSession() as session:
        async with KefAsyncClient(
            fake.host, transport="http", http_port=fake.http_port, session=session
        ) as c:
            assert await c.get_volume() == 30
        assert not session.closed
        await c.aclose()  # closing twice is harmless
        assert not session.closed
