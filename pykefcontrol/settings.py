"""Declarative registry of speaker settings.

Rather than one hand-written method per setting, each setting is described once
by a :class:`Setting` (path, value type, Python type, validation), and the
clients expose two generic, fully typed methods::

    volume_limit = await speaker.get_setting(Settings.MAXIMUM_VOLUME)   # -> int
    await speaker.set_setting(Settings.STARTUP_TONE, False)

The catalogue lives in :class:`Settings`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from . import paths
from .enums import (
    CableMode,
    FavouriteButtonFunction,
    KefEnum,
    MasterChannelMode,
    PlayMode,
    Source,
    SpeakerIRCode,
    SpeakerStatus,
    StandbyMode,
    VolumeDisplay,
    WakeUpSource,
)
from .exceptions import KefProtocolError
from .values import ValueType, decode, encode


@dataclass(frozen=True, slots=True)
class Setting[T]:
    """Description of one setting exposed by the speaker.

    :param path: API path (``settings:/...``).
    :param value_type: typed-value discriminator used on the wire.
    :param py_type: Python type of the decoded value (``bool``, ``int``, ``float``,
        ``str`` or a :class:`~pykefcontrol.enums.KefEnum` subclass).
    :param writable: ``False`` for read-only settings.
    :param minimum/maximum: inclusive bounds for numeric settings.
    :param description: short human description (used by the CLI / docs).
    """

    path: str
    value_type: ValueType
    py_type: type[T]
    writable: bool = True
    minimum: float | None = None
    maximum: float | None = None
    description: str = field(default="", compare=False)

    def decode(self, raw: Any) -> T:
        """Convert a typed value received from the speaker to ``py_type``.

        :raises KefProtocolError: the payload does not have the expected type.
        """
        payload = decode(raw)
        py_type: Any = self.py_type
        if issubclass(py_type, KefEnum):
            if isinstance(payload, str):
                return py_type(payload)  # type: ignore[no-any-return]
        elif py_type is bool:
            if isinstance(payload, bool):
                return payload  # type: ignore[return-value]
        elif py_type is int:
            if isinstance(payload, int) and not isinstance(payload, bool):
                return payload  # type: ignore[return-value]
            if isinstance(payload, float) and payload.is_integer():
                return int(payload)  # type: ignore[return-value]
        elif py_type is float:
            if isinstance(payload, int | float) and not isinstance(payload, bool):
                return float(payload)  # type: ignore[return-value]
        elif isinstance(payload, py_type):
            return payload  # type: ignore[no-any-return]
        raise KefProtocolError(f"{self.path}: expected {py_type.__name__}, got {raw!r}")

    def encode(self, value: T) -> dict[str, Any]:
        """Validate ``value`` and wrap it as a typed value for the speaker."""
        if not self.writable:
            raise ValueError(f"Setting {self.path} is read-only")
        py_type: Any = self.py_type
        if issubclass(py_type, KefEnum):
            member: KefEnum = py_type(value)
            if not member.is_known:  # enums are open for reading only: catch typos
                allowed = ", ".join(m.value for m in py_type)
                msg = f"{self.path}: unknown value {member.value!r} (allowed: {allowed})"
                raise ValueError(msg)
            value = member  # type: ignore[assignment]
        elif py_type is bool:
            if not isinstance(value, bool):
                raise TypeError(f"{self.path} expects a bool, got {value!r}")
        elif py_type is int:
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{self.path} expects an int, got {value!r}")
        elif py_type is float:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise TypeError(f"{self.path} expects a number, got {value!r}")
            value = float(value)  # type: ignore[assignment]
        elif py_type is str and not isinstance(value, str):
            raise TypeError(f"{self.path} expects a str, got {value!r}")
        if isinstance(value, int | float) and not isinstance(value, bool):
            if self.minimum is not None and value < self.minimum:
                raise ValueError(f"{self.path}: {value} < minimum {self.minimum}")
            if self.maximum is not None and value > self.maximum:
                raise ValueError(f"{self.path}: {value} > maximum {self.maximum}")
        return encode(self.value_type, value)


class Settings:
    """Catalogue of known settings (namespace, not meant to be instantiated)."""

    # --- identity (read-only) ---
    MODEL_NAME: Final = Setting(
        paths.MODEL_NAME,
        ValueType.STRING,
        str,
        writable=False,
        description="Model id (for example LS50WII)",
    )
    SERIAL_NUMBER: Final = Setting(
        paths.SERIAL_NUMBER, ValueType.STRING, str, writable=False, description="Serial number"
    )
    FIRMWARE_VERSION: Final = Setting(
        paths.FIRMWARE_VERSION,
        ValueType.STRING,
        str,
        writable=False,
        description="Firmware version reported by the host",
    )
    HARDWARE_VERSION: Final = Setting(
        paths.HARDWARE_VERSION,
        ValueType.STRING,
        str,
        writable=False,
        description="Hardware version",
    )
    RELEASE_TEXT: Final = Setting(
        paths.FIRMWARE_TEXT,
        ValueType.STRING,
        str,
        writable=False,
        description="Firmware release text",
    )
    DEVICE_VERSION: Final = Setting(
        paths.DEVICE_VERSION,
        ValueType.STRING,
        str,
        writable=False,
        description="Device software version",
    )
    MAC_ADDRESS: Final = Setting(
        paths.PRIMARY_MAC_ADDRESS,
        ValueType.STRING,
        str,
        writable=False,
        description="Primary MAC address",
    )
    MEMBER_ID: Final = Setting(
        paths.MEMBER_ID,
        ValueType.STRING,
        str,
        writable=False,
        description="Unique member id of the speaker",
    )
    KEF_ID: Final = Setting(
        paths.KEF_ID, ValueType.STRING, str, writable=False, description="KEF account id"
    )
    DEVICE_NAME: Final = Setting(
        paths.DEVICE_NAME, ValueType.STRING, str, description="Friendly name of the speaker"
    )

    # --- status and playback ---
    SPEAKER_STATUS: Final = Setting(
        paths.SPEAKER_STATUS,
        ValueType.SPEAKER_STATUS,
        SpeakerStatus,
        writable=False,
        description="Power status of the speaker",
    )
    PHYSICAL_SOURCE: Final = Setting(
        paths.PHYSICAL_SOURCE,
        ValueType.PHYSICAL_SOURCE,
        Source,
        description="Selected physical source (standby = off)",
    )
    VOLUME: Final = Setting(
        paths.VOLUME, ValueType.I32, int, minimum=0, maximum=100, description="Current volume"
    )
    MUTE: Final = Setting(paths.MUTE, ValueType.BOOL, bool, description="Mute")
    PLAY_MODE: Final = Setting(
        paths.PLAY_MODE, ValueType.PLAY_MODE, PlayMode, description="Shuffle and repeat mode"
    )

    # --- volume ---
    MAXIMUM_VOLUME: Final = Setting(
        paths.MAXIMUM_VOLUME,
        ValueType.I32,
        int,
        minimum=0,
        maximum=100,
        description="Maximum volume",
    )
    VOLUME_LIMIT: Final = Setting(
        paths.VOLUME_LIMIT, ValueType.BOOL, bool, description="Enable the maximum volume limit"
    )
    VOLUME_STEP: Final = Setting(
        paths.VOLUME_STEP, ValueType.I16, int, minimum=1, description="Volume step size"
    )
    VOLUME_DISPLAY: Final = Setting(
        paths.VOLUME_DISPLAY,
        ValueType.VOLUME_DISPLAY,
        VolumeDisplay,
        description="Volume display mode",
    )
    STANDBY_DEFAULT_VOLUME: Final = Setting(
        paths.RESET_STANDBY_VOLUME,
        ValueType.BOOL,
        bool,
        description="Reset volume when entering standby",
    )
    ADVANCED_STANDBY_DEFAULT_VOLUME: Final = Setting(
        paths.ADVANCED_STANDBY_DEFAULT_VOL,
        ValueType.BOOL,
        bool,
        description="Per-source reset of the volume on standby",
    )
    DEFAULT_VOLUME_GLOBAL: Final = Setting(
        paths.RESET_DEFAULT_VOLUME_LEVEL_GET,
        ValueType.I32,
        int,
        writable=False,
        description="Global default volume (set via action)",
    )
    DEFAULT_VOLUME_WIFI: Final = Setting(
        paths.DEFAULT_VOLUME_WIFI,
        ValueType.I32,
        int,
        writable=False,
        description="Default volume for Wi-Fi (set via action)",
    )
    DEFAULT_VOLUME_BLUETOOTH: Final = Setting(
        paths.DEFAULT_VOLUME_BLUETOOTH,
        ValueType.I32,
        int,
        writable=False,
        description="Default volume for Bluetooth (set via action)",
    )
    DEFAULT_VOLUME_TV: Final = Setting(
        paths.DEFAULT_VOLUME_TV,
        ValueType.I32,
        int,
        writable=False,
        description="Default volume for TV (set via action)",
    )
    DEFAULT_VOLUME_OPTICAL: Final = Setting(
        paths.DEFAULT_VOLUME_OPTICAL,
        ValueType.I32,
        int,
        writable=False,
        description="Default volume for optical (set via action)",
    )
    DEFAULT_VOLUME_COAXIAL: Final = Setting(
        paths.DEFAULT_VOLUME_COAXIAL,
        ValueType.I32,
        int,
        writable=False,
        description="Default volume for coaxial (set via action)",
    )
    DEFAULT_VOLUME_ANALOG: Final = Setting(
        paths.DEFAULT_VOLUME_ANALOGUE,
        ValueType.I32,
        int,
        writable=False,
        description="Default volume for analog (set via action)",
    )
    DEFAULT_VOLUME_USB: Final = Setting(
        paths.DEFAULT_VOLUME_USB,
        ValueType.I32,
        int,
        writable=False,
        description="Default volume for USB (set via action)",
    )

    # --- power ---
    STANDBY_MODE: Final = Setting(
        paths.STANDBY_MODE, ValueType.STANDBY_MODE, StandbyMode, description="Auto-standby delay"
    )
    WAKE_UP_SOURCE: Final = Setting(
        paths.WAKE_UP_SOURCE,
        ValueType.WAKE_UP_SOURCE,
        WakeUpSource,
        description="Source that wakes the speaker up",
    )
    AUTO_SWITCH_TO_TV: Final = Setting(
        paths.AUTO_SWITCH_TO_TV,
        ValueType.BOOL,
        bool,
        description="Switch to TV (HDMI ARC) automatically",
    )
    STARTUP_TONE: Final = Setting(
        paths.STARTUP_TONE, ValueType.BOOL, bool, description="Play a tone at startup"
    )

    # --- LEDs and panels ---
    DISABLE_FRONT_LED: Final = Setting(
        paths.DISABLE_FRONT_LED, ValueType.BOOL, bool, description="Turn the front LED off"
    )
    DISABLE_FRONT_STANDBY_LED: Final = Setting(
        paths.DISABLE_FRONT_STANDBY_LED,
        ValueType.BOOL,
        bool,
        description="Turn the front standby LED off",
    )
    TOP_PANEL_LED: Final = Setting(
        paths.ENABLE_TOP_PANEL_LED, ValueType.BOOL, bool, description="Top panel LED enabled"
    )
    TOP_PANEL_STANDBY_LED: Final = Setting(
        paths.ENABLE_TOP_PANEL_STANDBY_LED,
        ValueType.BOOL,
        bool,
        description="Top panel standby LED enabled",
    )
    DISABLE_TOP_PANEL: Final = Setting(
        paths.FRONT_PANEL_DISABLED, ValueType.BOOL, bool, description="Lock the top panel"
    )
    USB_CHARGING: Final = Setting(
        paths.USB_CHARGING, ValueType.BOOL, bool, description="USB charging"
    )

    # --- speaker layout ---
    CABLE_MODE: Final = Setting(
        paths.CABLE_MODE,
        ValueType.CABLE_MODE,
        CableMode,
        description="Wired or wireless link between speakers",
    )
    MASTER_CHANNEL_MODE: Final = Setting(
        paths.MASTER_CHANNEL_MODE,
        ValueType.MASTER_CHANNEL_MODE,
        MasterChannelMode,
        description="Which side is the primary speaker",
    )
    SUBWOOFER_FORCE_ON: Final = Setting(
        paths.SUBWOOFER_FORCE_ON, ValueType.BOOL, bool, description="Keep the subwoofer awake"
    )
    SUBWOOFER_FORCE_ON_KW1: Final = Setting(
        paths.SUBWOOFER_FORCE_ON_KW1,
        ValueType.BOOL,
        bool,
        description="Keep the KW1 subwoofer adapter awake",
    )
    AUTO_DETECT_PLACEMENT: Final = Setting(
        paths.AUTO_DETECT_PLACEMENT,
        ValueType.BOOL,
        bool,
        description="Detect placement automatically",
    )

    # --- remote control ---
    REMOTE_IR: Final = Setting(
        paths.REMOTE_IR, ValueType.BOOL, bool, description="IR remote enabled"
    )
    SPEAKER_IR_CODE: Final = Setting(
        paths.SPEAKER_IR_CODE,
        ValueType.SPEAKER_IR_CODE,
        SpeakerIRCode,
        description="IR code set of the speaker",
    )
    REMOTE_IR_CODE: Final = Setting(
        paths.REMOTE_IR_CODE,
        ValueType.SPEAKER_IR_CODE,
        SpeakerIRCode,
        description="IR code set of the remote",
    )
    FAVOURITE_BUTTON: Final = Setting(
        paths.FAVOURITE_BUTTON_FUNCTION,
        ValueType.FAVOURITE_BUTTON,
        FavouriteButtonFunction,
        description="Function of the favourite button",
    )
    EQ_BUTTON_1: Final = Setting(
        paths.EQ_BUTTON1, ValueType.STRING, str, description="EQ profile of remote EQ button 1"
    )
    EQ_BUTTON_2: Final = Setting(
        paths.EQ_BUTTON2, ValueType.STRING, str, description="EQ profile of remote EQ button 2"
    )
    USER_FIXED_VOLUME: Final = Setting(
        paths.USER_FIXED_VOLUME,
        ValueType.I32,
        int,
        minimum=0,
        maximum=100,
        description="Volume used by the favourite button",
    )

    # --- scheduled reboot ---
    SCHEDULED_REBOOT_ENABLED: Final = Setting(
        paths.SCHEDULED_REBOOT_ENABLED, ValueType.BOOL, bool, description="Scheduled reboot enabled"
    )
    SCHEDULED_REBOOT_DAY_OF_WEEK: Final = Setting(
        paths.SCHEDULED_REBOOT_DAY_OF_WEEK,
        ValueType.I32,
        int,
        description="Scheduled reboot day of the week",
    )
    SCHEDULED_REBOOT_TIME: Final = Setting(
        paths.SCHEDULED_REBOOT_TIME,
        ValueType.STRING,
        str,
        description="Scheduled reboot time of day",
    )

    # --- languages and analytics ---
    SPEAKER_LANGUAGE: Final = Setting(
        paths.SPEAKER_LANGUAGE, ValueType.STRING, str, description="Speaker UI language"
    )
    AIRABLE_LANGUAGE: Final = Setting(
        paths.AIRABLE_LANGUAGE,
        ValueType.STRING,
        str,
        description="Internet radio / podcast language",
    )
    DISABLE_ANALYTICS: Final = Setting(
        paths.DISABLE_ANALYTICS, ValueType.BOOL, bool, description="Disable speaker analytics"
    )
    DISABLE_APP_ANALYTICS: Final = Setting(
        paths.DISABLE_APP_ANALYTICS, ValueType.BOOL, bool, description="Disable app analytics"
    )

    # --- DSP leaves ---
    SUBWOOFER_OUT_V2: Final = Setting(
        paths.SUBWOOFER_OUT, ValueType.BOOL, bool, description="Subwoofer output enabled"
    )
    DIALOGUE_MODE: Final = Setting(
        paths.DIALOGUE_MODE, ValueType.BOOL, bool, description="Dialogue enhancement"
    )
    PREFER_VIRTUAL_X: Final = Setting(
        paths.PREFER_VIRTUAL_X_VIRTUALISER,
        ValueType.BOOL,
        bool,
        description="Prefer the Virtual X virtualiser",
    )
    SUBWOOFER_GAIN_V2: Final = Setting(
        paths.SUBWOOFER_GAIN_V2,
        ValueType.I32,
        int,
        minimum=-10,
        maximum=10,
        description="Subwoofer gain in dB",
    )
    WIRELESS_REAR_GAIN: Final = Setting(
        paths.WIRELESS_REAR_GAIN,
        ValueType.DOUBLE,
        float,
        minimum=-10,
        maximum=10,
        description="Wireless rear gain in dB",
    )


def _collect() -> tuple[Setting[Any], ...]:
    return tuple(v for v in vars(Settings).values() if isinstance(v, Setting))


ALL_SETTINGS: Final[tuple[Setting[Any], ...]] = _collect()

_BY_PATH: Final[dict[str, Setting[Any]]] = {}
for _setting in ALL_SETTINGS:
    _BY_PATH.setdefault(_setting.path, _setting)


def setting_by_path(path: str) -> Setting[Any] | None:
    """Return the catalogue entry for ``path``, or ``None`` if unknown."""
    return _BY_PATH.get(path)
