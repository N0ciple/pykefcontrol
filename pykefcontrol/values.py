"""Typed values of the KEF (StreamUnlimited) API.

The speaker wraps every value in a small object carrying its type name, and the
payload under a key equal to that type name::

    {"type": "i32_", "i32_": 42}
    {"type": "kefPhysicalSource", "kefPhysicalSource": "wifi"}
    {"type": "kefEqProfileV2", "kefEqProfileV2": {...}}

This module only knows how to wrap and unwrap them. It does no I/O.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from .exceptions import KefProtocolError


class ValueType(StrEnum):
    """Type names used by the speaker API (``"type"`` discriminator)."""

    BOOL = "bool_"
    I16 = "i16_"
    I32 = "i32_"
    I64 = "i64_"
    DOUBLE = "double_"
    STRING = "string_"

    PHYSICAL_SOURCE = "kefPhysicalSource"
    SPEAKER_STATUS = "kefSpeakerStatus"
    STANDBY_MODE = "kefStandbyMode"
    WAKE_UP_SOURCE = "kefWakeUpSource"
    CABLE_MODE = "kefCableMode"
    MASTER_CHANNEL_MODE = "kefMasterChannelMode"
    VOLUME_DISPLAY = "kefVolumeDisplay"
    PLAY_MODE = "playerPlayMode"
    SPEAKER_IR_CODE = "kefSpeakerIRCode"
    FAVOURITE_BUTTON = "kefFavouriteButtonFunction"
    DEFAULT_VOLUME_SETTINGS = "kefDefaultVolumeSettings"
    SPEED_TEST_STATUS = "kefSpeedTestStatus"
    NETWORK_STABILITY = "networkStability"
    NETWORK_INFO = "networkInfo"
    BLUETOOTH_STATE = "bluetoothState"
    FIRMWARE_UPGRADE_INFO = "kefFirmwareUpgradeInfo"
    FIRMWARE_UPDATE_STATUS = "firmwareUpdateStatus"
    EQ_PROFILE = "kefEqProfile"
    EQ_PROFILE_V2 = "kefEqProfileV2"
    BASS_EXTENSION = "kefBassExtension"
    SUBWOOFER_POLARITY = "kefSubwooferPolarity"
    SUBWOOFER_PRESET = "kefSubwooferPreset"
    SOUND_PROFILE = "kefSoundProfile"
    ALERTS_LIST = "alertsList"


def encode(value_type: ValueType | str, value: Any) -> dict[str, Any]:
    """Wrap ``value`` in a typed-value object.

    >>> encode(ValueType.I32, 42)
    {'type': 'i32_', 'i32_': 42}
    """
    name = str(value_type)
    if isinstance(value, StrEnum):
        value = str(value)
    return {"type": name, name: value}


def decode(obj: Any) -> Any:
    """Unwrap a typed-value object and return its payload.

    Objects without a ``type`` key (or whose payload key is missing) are returned
    unchanged, so callers can always pass whatever the speaker sent.
    """
    if isinstance(obj, dict):
        type_name = obj.get("type")
        if isinstance(type_name, str) and type_name in obj:
            return obj[type_name]
    return obj


def type_of(obj: Any) -> str | None:
    """Return the ``type`` discriminator of a typed value, if any."""
    if isinstance(obj, dict):
        type_name = obj.get("type")
        if isinstance(type_name, str):
            return type_name
    return None


def decode_as(obj: Any, expected: type[Any]) -> Any:
    """Unwrap a typed value and check the payload's Python type.

    ``int`` accepts ``bool``-free integers, ``float`` accepts ints too.
    """
    payload = decode(obj)
    if expected is float and isinstance(payload, int) and not isinstance(payload, bool):
        return float(payload)
    if expected is int and isinstance(payload, bool):
        raise KefProtocolError(f"Expected int, got bool: {obj!r}")
    if not isinstance(payload, expected):
        raise KefProtocolError(f"Expected {expected.__name__}, got {obj!r}")
    return payload
