"""Tests for pykefcontrol.models (pure parsers) and KefEnum."""

from __future__ import annotations

from typing import Any

from pykefcontrol import (
    EventType,
    NetworkInfo,
    PlaybackState,
    PlayerState,
    PlayMode,
    Source,
    SpeakerState,
    SpeakerStatus,
    Track,
)
from pykefcontrol.models import BluetoothState, Event, PlayerControls, Subscription


def test_event_with_value() -> None:
    raw = {"path": "player:volume", "itemType": "update", "itemValue": {"type": "i32_", "i32_": 7}}
    ev = Event.from_api(raw)
    assert (ev.path, ev.type, ev.value, ev.has_value) == (
        "player:volume",
        EventType.UPDATE,
        7,
        True,
    )
    assert ev.raw is raw


def test_event_without_value() -> None:
    ev = Event.from_api({"path": "x", "itemType": "update"})
    assert ev.value is None
    assert ev.has_value is False


def test_event_with_null_value_still_has_value() -> None:
    ev = Event.from_api({"path": "x", "itemType": "update", "itemValue": None})
    assert ev.has_value is True
    assert ev.value is None


def test_rows_event() -> None:
    ev = Event.from_api({"path": "playlists:pq/getitems", "rowsType": "reset", "rowsVersion": 5})
    assert ev.type == EventType.RESET
    assert not ev.has_value


def test_event_defaults_to_update_and_tolerates_unknown_type() -> None:
    assert Event.from_api({"path": "x"}).type == EventType.UPDATE
    unknown = Event.from_api({"path": "x", "itemType": "frobnicate"}).type
    assert unknown == "frobnicate"
    assert not unknown.is_known


def test_subscription_to_api() -> None:
    assert Subscription("a").to_api() == {"path": "a", "type": "itemWithValue"}


def test_kef_enum_unknown_value() -> None:
    phono = Source("phono")
    assert phono == "phono"
    assert phono.value == "phono"
    assert phono.is_known is False
    assert Source("wifi") is Source.WIFI
    assert Source.WIFI.is_known
    assert Source.parse(None) is None
    assert Source.parse(3) is None
    assert Source.parse("phono") == "phono"


def player_raw(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "state": "playing",
        "status": {"duration": 1000},
        "controls": {
            "pause": True,
            "next_": True,
            "previous": False,
            "seekTime": True,
            "playMode": {"shuffle": True, "repeatOne": False, "normal": True},
        },
        "trackRoles": {
            "title": "Song",
            "icon": "http://cover",
            "mediaData": {
                "metaData": {"artist": "A", "album": "B", "serviceID": "spotify", "live": False},
                "resources": [
                    {
                        "duration": 215000,
                        "codec": "flac",
                        "sampleFrequency": 96000,
                        "bitsPerSample": 24,
                        "nrAudioChannels": 2,
                        "bitRate": 1000,
                    }
                ],
            },
        },
    }
    data.update(overrides)
    return data


def test_player_state_full() -> None:
    state = PlayerState.from_api(player_raw())
    assert state.state == PlaybackState.PLAYING
    assert state.is_playing
    track = state.track
    assert track is not None
    assert (track.title, track.artist, track.album) == ("Song", "A", "B")
    assert track.album_artist == "A"  # falls back on the artist
    assert track.cover_url == "http://cover"
    assert track.service_id == "spotify"
    assert track.duration_ms == 215000 == state.duration_ms
    assert (track.codec, track.sample_rate, track.bits_per_sample) == ("flac", 96000, 24)
    assert (track.channels, track.bit_rate, track.live) == (2, 1000, False)
    assert state.controls.pause and state.controls.next and not state.controls.previous
    assert state.controls.seek
    assert state.controls.play_modes == {PlayMode.SHUFFLE, PlayMode.NORMAL}


def test_player_state_typed_wrapper_and_garbage() -> None:
    wrapped = {"type": "playerData", "playerData": player_raw(state="paused")}
    assert PlayerState.from_api(wrapped).state == PlaybackState.PAUSED
    empty = PlayerState.from_api("junk")
    assert empty.state == PlaybackState.STOPPED
    assert empty.track is None
    assert not empty.is_playing
    assert empty.duration_ms is None


def test_track_falls_back_on_media_roles() -> None:
    data = {
        "state": "playing",
        "status": {"duration": 5000},
        "mediaRoles": {
            "title": "Radio X",
            "icon": "http://logo",
            "mediaData": {"metaData": {"artist": "Station", "serviceID": "radio", "live": True}},
        },
    }
    track = Track.from_player_data(data)
    assert track is not None
    assert (track.title, track.artist, track.cover_url) == ("Radio X", "Station", "http://logo")
    assert track.service_id == "radio"
    assert track.live is True
    assert track.duration_ms == 5000  # status.duration when no resource duration
    assert Track.from_player_data({"state": "stopped"}) is None


def test_track_prefers_track_roles_over_media_roles() -> None:
    data = {"trackRoles": {"title": "T"}, "mediaRoles": {"title": "M", "icon": "i"}}
    track = Track.from_player_data(data)
    assert track is not None
    assert (track.title, track.cover_url) == ("T", "i")


def test_track_resources_first_then_active_resource() -> None:
    data = {
        "trackRoles": {
            "title": "T",
            "mediaData": {
                "resources": [{"codec": "aac", "sampleFrequency": 48000, "nrAudioChannels": 6}],
                "activeResource": {"codec": "mp3", "sampleFrequency": 1, "streamChannels": 1},
            },
        }
    }
    track = Track.from_player_data(data)
    assert track is not None
    assert (track.codec, track.sample_rate, track.channels) == ("aac", 48000, 6)

    legacy = {
        "trackRoles": {
            "title": "T",
            "mediaData": {
                "activeResource": {"codec": "mp3", "streamSampleRate": 44100, "streamChannels": 2}
            },
        }
    }
    track = Track.from_player_data(legacy)
    assert track is not None
    assert (track.codec, track.sample_rate, track.channels) == ("mp3", 44100, 2)


def test_controls_next_key_variants() -> None:
    assert PlayerControls.from_api({"next_": True}).next is True
    assert PlayerControls.from_api({"next": True}).next is True
    assert PlayerControls.from_api({"next_": False, "next": True}).next is False
    assert PlayerControls.from_api(None) == PlayerControls()


def test_network_info() -> None:
    raw = {
        "type": "networkInfo",
        "networkInfo": {
            "state": "online",
            "wired": {"name": "eth0", "state": "down", "addresses": []},
            "wireless": {
                "name": "wlan0",
                "state": "up",
                "mac": "aa:bb",
                "ssid": "home",
                "frequency": 5180,
                "channel": 36,
                "signalLevel": -50,
                "addresses": [
                    {"ip": "192.168.1.9", "protocol": "ipv4", "prefix": 24, "dhcp": True},
                    {"protocol": "ipv6"},
                ],
            },
        },
    }
    info = NetworkInfo.from_api(raw)
    assert info.state == "online"
    assert info.wired is not None and info.wired.addresses == ()
    assert info.active is info.wireless
    assert info.ip_address == "192.168.1.9"
    wifi = info.wireless
    assert wifi is not None
    assert (wifi.ssid, wifi.frequency, wifi.channel, wifi.signal_level) == ("home", 5180, 36, -50)
    assert len(wifi.addresses) == 1
    assert wifi.addresses[0].dhcp is True


def test_network_info_prefers_wired_and_handles_garbage() -> None:
    up = {"state": "up", "addresses": [{"ip": "10.0.0.2"}]}
    info = NetworkInfo.from_api({"state": "online", "wired": up, "wireless": up})
    assert info.active is info.wired
    empty = NetworkInfo.from_api("junk")
    assert empty.state is None and empty.active is None and empty.ip_address is None


def test_bluetooth_state() -> None:
    bt = BluetoothState.from_api({"connected": True, "pairingCode": ""})
    assert bt.connected and bt.pairing_code is None
    assert BluetoothState.from_api(3) == BluetoothState()


def test_speaker_state_is_on() -> None:
    assert not SpeakerState().is_on  # nothing known
    assert SpeakerState(status=SpeakerStatus.POWER_ON).is_on
    assert SpeakerState(source=Source.WIFI).is_on
    assert not SpeakerState(status=SpeakerStatus.STANDBY, source=Source.WIFI).is_on
    assert not SpeakerState(status=SpeakerStatus.POWER_ON, source=Source.STANDBY).is_on


def test_speaker_state_helpers() -> None:
    player = PlayerState.from_api(player_raw())
    state = SpeakerState(player=player, volume=3)
    assert state.playback_state == PlaybackState.PLAYING
    assert state.track is player.track
    assert state.replace(volume=4).volume == 4
    assert state.volume == 3
    assert SpeakerState().playback_state is None and SpeakerState().track is None


def test_parsers_are_total() -> None:
    assert PlayerState.from_api({"trackRoles": ["x"]}).track is None
    assert PlayerState.from_api({"mediaRoles": {"mediaData": {"resources": "x"}}}).track is not None
    assert PlayerControls.from_api({"playMode": ["x"]}).play_modes == frozenset()
    info = NetworkInfo.from_api({"wired": {"addresses": "nope"}, "wireless": {"addresses": 3}})
    assert info.wired is not None and info.wired.addresses == ()
    assert info.ip_address is None
    assert NetworkInfo.from_api({"wired": 3, "wireless": []}).wired is None
    assert BluetoothState.from_api({"connected": "yes"}).connected is True
