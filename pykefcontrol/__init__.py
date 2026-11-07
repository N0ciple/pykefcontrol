"""Control KEF W2-platform wireless speakers over the local network.

Supported: LS50 Wireless II, LS60 Wireless, LSX II, LSX II LT, XIO, LS LUXE (and,
generically, future W2 speakers). Both an asyncio client
(:class:`KefAsyncClient`, built on aiohttp) and a blocking client
(:class:`KefClient`, built on urllib3) are provided, with the same API.

Quick start::

    from pykefcontrol import KefClient

    with KefClient("192.168.1.20") as speaker:
        speaker.power_on()
        speaker.set_volume(30)
        print(speaker.get_player_state().track)
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from . import paths
from ._async.client import AsyncEventQueue, KefAsyncClient
from ._auth import Credentials
from ._sync.client import EventQueue, KefClient
from ._tls import KEF_ROOT_CA_PEM, create_ssl_context
from .capabilities import Capabilities, Feature, FirmwareVersion, ModelInfo, SpeakerModel
from .const import TransportMode
from .enums import (
    BassExtension,
    CableMode,
    EventType,
    FavouriteButtonFunction,
    MasterChannelMode,
    PlaybackState,
    PlayMode,
    Polarity,
    SoundProfile,
    Source,
    SpeakerIRCode,
    SpeakerStatus,
    SpeedTestStatus,
    StandbyMode,
    SubwooferPreset,
    VolumeDisplay,
    WakeUpSource,
)
from .eq import EqDescriptor, EqProfile, EqRange
from .exceptions import (
    KefApiError,
    KefAuthError,
    KefConnectionError,
    KefError,
    KefProtocolError,
    KefTimeoutError,
    KefUnsupportedError,
)
from .models import (
    BluetoothState,
    DeviceInfo,
    Event,
    NetworkInfo,
    NetworkInterface,
    PlayerControls,
    PlayerState,
    SpeakerState,
    Subscription,
    SubscriptionType,
    Track,
)
from .settings import Setting, Settings
from .values import ValueType

try:
    __version__ = version("pykefcontrol")
except PackageNotFoundError:  # running from a source checkout
    __version__ = "0+unknown"

__all__ = [
    "KEF_ROOT_CA_PEM",
    "AsyncEventQueue",
    "BassExtension",
    "BluetoothState",
    "CableMode",
    "Capabilities",
    "Credentials",
    "DeviceInfo",
    "EqDescriptor",
    "EqProfile",
    "EqRange",
    "Event",
    "EventQueue",
    "EventType",
    "FavouriteButtonFunction",
    "Feature",
    "FirmwareVersion",
    "KefApiError",
    "KefAsyncClient",
    "KefAuthError",
    "KefClient",
    "KefConnectionError",
    "KefError",
    "KefProtocolError",
    "KefTimeoutError",
    "KefUnsupportedError",
    "MasterChannelMode",
    "ModelInfo",
    "NetworkInfo",
    "NetworkInterface",
    "PlayMode",
    "PlaybackState",
    "PlayerControls",
    "PlayerState",
    "Polarity",
    "Setting",
    "Settings",
    "SoundProfile",
    "Source",
    "SpeakerIRCode",
    "SpeakerModel",
    "SpeakerState",
    "SpeakerStatus",
    "SpeedTestStatus",
    "StandbyMode",
    "Subscription",
    "SubscriptionType",
    "SubwooferPreset",
    "Track",
    "TransportMode",
    "ValueType",
    "VolumeDisplay",
    "WakeUpSource",
    "__version__",
    "create_ssl_context",
    "paths",
]
