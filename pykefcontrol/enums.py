"""Enumerations of values used by the speaker API.

All enums are :class:`~enum.StrEnum`, so they compare equal to the raw strings
sent by the speaker (``Source.WIFI == "wifi"``).

They are *open*: an unknown value coming from a newer firmware does not raise,
it produces a pseudo-member whose ``value`` is the raw string and whose
``is_known`` is ``False``. This keeps the library working with future speakers.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Self


class KefEnum(StrEnum):
    """Base class: a StrEnum that tolerates unknown values."""

    @classmethod
    def _missing_(cls, value: object) -> Self | None:
        if not isinstance(value, str):
            return None
        member = str.__new__(cls, value)
        member._name_ = f"UNKNOWN_{value}"
        member._value_ = value
        return member

    @property
    def is_known(self) -> bool:
        """``False`` for pseudo-members created from unknown values."""
        return self._name_ in type(self).__members__

    @classmethod
    def parse(cls, value: Any) -> Self | None:
        """Convert ``value`` to a member, returning ``None`` for ``None``/non-strings."""
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(value)
        return None


class Source(KefEnum):
    """Physical source (``settings:/kef/play/physicalSource``)."""

    STANDBY = "standby"
    WIFI = "wifi"
    BLUETOOTH = "bluetooth"
    TV = "tv"
    OPTICAL = "optical"
    COAXIAL = "coaxial"
    ANALOG = "analog"
    USB = "usb"


class SpeakerStatus(KefEnum):
    """Speaker status (``settings:/kef/host/speakerStatus``)."""

    STANDBY = "standby"
    POWER_ON = "powerOn"
    NETWORK_SETUP = "networkSetup"
    FIRMWARE_UPGRADE = "firmwareUpgrade"


class PlaybackState(KefEnum):
    """Player state (``player:player/data`` → ``state``)."""

    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"
    TRANSITIONING = "transitioning"


class PlayMode(KefEnum):
    """Shuffle / repeat mode (``settings:/mediaPlayer/playMode``)."""

    NORMAL = "normal"
    REPEAT_ONE = "repeatOne"
    REPEAT_ALL = "repeatAll"
    SHUFFLE = "shuffle"
    SHUFFLE_REPEAT_ONE = "shuffleRepeatOne"
    SHUFFLE_REPEAT_ALL = "shuffleRepeatAll"

    @property
    def shuffle(self) -> bool:
        return self.value.startswith("shuffle")

    @property
    def repeat(self) -> str:
        """``"off"``, ``"one"`` or ``"all"``."""
        if self.value.endswith(("RepeatOne", "repeatOne")):
            return "one"
        if self.value.endswith(("RepeatAll", "repeatAll")):
            return "all"
        return "off"

    @classmethod
    def from_flags(cls, *, shuffle: bool, repeat: str) -> PlayMode:
        """Build a mode from a shuffle flag and a repeat mode (``off``/``one``/``all``)."""
        table = {
            (False, "off"): cls.NORMAL,
            (False, "one"): cls.REPEAT_ONE,
            (False, "all"): cls.REPEAT_ALL,
            (True, "off"): cls.SHUFFLE,
            (True, "one"): cls.SHUFFLE_REPEAT_ONE,
            (True, "all"): cls.SHUFFLE_REPEAT_ALL,
        }
        try:
            return table[(shuffle, repeat)]
        except KeyError:
            raise ValueError(f"repeat must be 'off', 'one' or 'all', not {repeat!r}") from None


class StandbyMode(KefEnum):
    """Auto-standby delay (``settings:/kef/host/standbyMode``)."""

    MINUTES_20 = "standby_20mins"
    MINUTES_30 = "standby_30mins"
    MINUTES_60 = "standby_60mins"
    NEVER = "standby_none"


class WakeUpSource(KefEnum):
    """Source that wakes the speaker up (``settings:/kef/host/wakeUpSource``)."""

    DEFAULT = "wakeup_default"
    BLUETOOTH = "bluetooth"
    TV = "tv"
    OPTICAL = "optical"
    COAXIAL = "coaxial"
    ANALOG = "analog"
    USB = "usb"


class CableMode(KefEnum):
    """Link between primary and secondary speaker (``settings:/kef/host/cableMode``)."""

    WIRED = "wired"
    WIRELESS = "wireless"


class MasterChannelMode(KefEnum):
    """Which side is the primary speaker (``settings:/kef/host/masterChannelMode``)."""

    LEFT = "left"
    RIGHT = "right"
    LEFT_RIGHT = "leftright"


class VolumeDisplay(KefEnum):
    """Volume display mode (``settings:/kef/host/volumeDisplay``)."""

    LINEAR = "linear"
    PRECISE = "precise"
    UNKNOWN = "unknown"


class SpeakerIRCode(KefEnum):
    """IR code set (``settings:/kef/host/remote/speakerIRCode``)."""

    SET_A = "ir_code_set_a"
    SET_B = "ir_code_set_b"
    UNKNOWN = "unknown"


class FavouriteButtonFunction(KefEnum):
    """Function of the remote's favourite button."""

    NEXT_SOURCE = "nextSource"
    SET_DIALOGUE_MODE = "setDialogueMode"
    SET_CABLE_MODE = "setCableMode"
    ENABLE_BLUETOOTH_PAIRING = "enableBluetoothPairing"
    SET_SUBWOOFER_OUT = "setSubwooferOut"
    SET_VOLUME = "setVolume"
    SET_DISABLE_TOP_PANEL = "setDisableTopPanel"
    SET_MAXIMUM_VOLUME = "setMaximumVolume"
    SET_USB_SOURCE = "setUsbSource"
    SET_MASTER_CHANNEL_MODE = "setMasterChannelMode"
    UNKNOWN = "unknown"


class SpeedTestStatus(KefEnum):
    """Status of the speaker's internet speed test."""

    IDLE = "idle"
    IN_PROGRESS = "inProgress"
    FINISHED = "finished"
    ERROR = "error"


class BassExtension(KefEnum):
    """EQ bass extension."""

    STANDARD = "standard"
    EXTRA = "extra"
    LESS = "less"


class Polarity(KefEnum):
    """Audio / subwoofer polarity."""

    NORMAL = "normal"
    INVERTED = "inverted"


class SubwooferPreset(KefEnum):
    """Subwoofer model preset (sets crossover and gain)."""

    CUSTOM = "custom"
    OTHER = "other"
    KC62 = "kc62"
    KF92 = "kf92"
    KUBE_8B = "kube8b"
    KUBE_10B = "kube10b"
    KUBE_12B = "kube12b"
    KUBE_15MIE = "kube15mie"
    T2 = "t2"


class SoundProfile(KefEnum):
    """Sound profile (EQ v2, mostly XIO)."""

    DEFAULT = "default"
    MUSIC = "music"
    MOVIE = "movie"
    NIGHT = "night"
    DIALOGUE = "dialogue"
    DIRECT = "direct"


class EventType(KefEnum):
    """``itemType`` / ``rowsType`` of an event from the event queue."""

    NONE = "none"
    UPDATE = "update"
    REMOVE = "remove"
    RESET = "reset"
