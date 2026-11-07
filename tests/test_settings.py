from __future__ import annotations

from typing import Any

import pytest

from pykefcontrol import paths
from pykefcontrol.enums import Source, StandbyMode
from pykefcontrol.settings import ALL_SETTINGS, Settings, setting_by_path


def test_every_path_in_paths_module() -> None:
    known = {v for k, v in vars(paths).items() if k.isupper() and isinstance(v, str)}
    assert ALL_SETTINGS
    for setting in ALL_SETTINGS:
        assert setting.path in known, setting.path


def test_catalogue_matches_class() -> None:
    assert Settings.VOLUME in ALL_SETTINGS
    assert setting_by_path("player:volume") is Settings.VOLUME
    assert setting_by_path("nope:") is None


def test_bool_roundtrip() -> None:
    wire = Settings.STARTUP_TONE.encode(True)
    assert wire == {"type": "bool_", "bool_": True}
    assert Settings.STARTUP_TONE.decode(wire) is True


def test_bool_rejects_int() -> None:
    with pytest.raises(TypeError):
        Settings.MUTE.encode(1)  # type: ignore[arg-type]


def test_int_range() -> None:
    assert Settings.MAXIMUM_VOLUME.encode(80) == {"type": "i32_", "i32_": 80}
    with pytest.raises(ValueError, match="maximum"):
        Settings.MAXIMUM_VOLUME.encode(101)
    with pytest.raises(ValueError, match="minimum"):
        Settings.VOLUME.encode(-1)
    with pytest.raises(TypeError):
        Settings.VOLUME.encode(True)


def test_float_accepts_int() -> None:
    assert Settings.WIRELESS_REAR_GAIN.encode(2) == {"type": "double_", "double_": 2.0}
    with pytest.raises(ValueError, match="maximum"):
        Settings.WIRELESS_REAR_GAIN.encode(10.5)


def test_enum() -> None:
    wire = Settings.PHYSICAL_SOURCE.encode(Source.WIFI)
    assert wire == {"type": "kefPhysicalSource", "kefPhysicalSource": "wifi"}
    raw: dict[str, Any] = {"type": "kefPhysicalSource", "kefPhysicalSource": "optical"}
    assert Settings.PHYSICAL_SOURCE.decode(raw) is Source.OPTICAL
    assert Settings.STANDBY_MODE.encode("standby_60mins")["kefStandbyMode"] == "standby_60mins"
    assert (
        Settings.STANDBY_MODE.decode({"type": "kefStandbyMode", "kefStandbyMode": "standby_none"})
        is StandbyMode.NEVER
    )


def test_unknown_enum_value_tolerated() -> None:
    raw = {"type": "kefPhysicalSource", "kefPhysicalSource": "phono"}
    assert Settings.PHYSICAL_SOURCE.decode(raw) == "phono"


def test_read_only() -> None:
    for setting in (Settings.MODEL_NAME, Settings.SPEAKER_STATUS, Settings.DEFAULT_VOLUME_WIFI):
        assert not setting.writable
        with pytest.raises(ValueError, match="read-only"):
            setting.encode("x")  # type: ignore[arg-type]


def test_str_and_decode_plain() -> None:
    assert Settings.DEVICE_NAME.encode("Living") == {"type": "string_", "string_": "Living"}
    assert Settings.MODEL_NAME.decode({"type": "string_", "string_": "LS50WII"}) == "LS50WII"


def test_decode_type_mismatch_raises_protocol_error() -> None:
    import pytest

    from pykefcontrol import KefProtocolError, Settings

    for bad in (
        {"type": "bool_", "bool_": True},
        {"type": "string_", "string_": "x"},
        {"type": "i32_"},
    ):
        with pytest.raises(KefProtocolError):
            Settings.VOLUME.decode(bad)
    with pytest.raises(KefProtocolError):
        Settings.MUTE.decode({"type": "i32_", "i32_": 1})
    assert Settings.VOLUME.decode({"type": "i32_", "i32_": 5}) == 5


def test_encode_rejects_unknown_enum_value() -> None:
    import pytest

    from pykefcontrol import Settings

    with pytest.raises(ValueError, match="wfi"):
        Settings.PHYSICAL_SOURCE.encode("wfi")  # type: ignore[arg-type]
