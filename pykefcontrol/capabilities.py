"""Speaker models, firmware versions and feature gating.

The tables come from the decompiled official KEF Connect app (``eq/a.java`` feature
gating and ``si/g.java`` source availability).

Only models with an HTTP API are listed. The Coda W and the Muo are Bluetooth-only
(no HTTP API) and are intentionally not part of this module.

The library never refuses a call on its own because of these tables. They are meant
to let callers (and the client's feature checks) know what a given speaker is
expected to support, and unknown models are treated generically: the speaker decides.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Self

from .enums import KefEnum, Source


class SpeakerModel(KefEnum):
    """Speaker model, as reported by ``settings:/kef/host/modelName``."""

    LS50_WIRELESS_II = "LS50WII"
    LS60_WIRELESS = "LS60W"
    LSX_II = "LSXII"
    LSX_II_LT = "LSXIILT"
    XIO = "xio"
    LS_LUXE = "luxe"
    UNKNOWN = "unknown"

    @classmethod
    def from_model_name(cls, name: str | None) -> SpeakerModel:
        """Map a model name (id, product code, legacy alias or marketing name) to a model.

        ``settings:/kef/host/modelName`` holds either the id (``LS50WII``) or, on
        recent firmware, the product code (``SP4025``): both are accepted.
        Matching is case-insensitive and ignores spaces, dashes and underscores.
        ``None`` and empty strings give :attr:`UNKNOWN`; an unrecognised name gives
        a pseudo-member carrying the raw string (see :class:`KefEnum`).
        """
        if name is None or not name.strip():
            return cls.UNKNOWN
        found = _NAME_ALIASES.get(_normalise(name)) or _PRODUCT_CODES.get(name.strip().upper())
        if found is not None:
            return found
        return cls(name.strip())

    @classmethod
    def from_product_code(cls, code: str | None) -> SpeakerModel:
        """Map a product code (``SP4025``, as sent in the mDNS ``model`` TXT) to a model."""
        if code is None:
            return cls.UNKNOWN
        return _PRODUCT_CODES.get(code.strip().upper(), cls.UNKNOWN)


def _normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


_NAME_ALIASES: Final[dict[str, SpeakerModel]] = {
    "ls50wii": SpeakerModel.LS50_WIRELESS_II,
    "ls50w2": SpeakerModel.LS50_WIRELESS_II,
    "ls50wirelessii": SpeakerModel.LS50_WIRELESS_II,
    "ls60w": SpeakerModel.LS60_WIRELESS,
    "ls60": SpeakerModel.LS60_WIRELESS,
    "ls60wireless": SpeakerModel.LS60_WIRELESS,
    "lsxii": SpeakerModel.LSX_II,
    "lsx2": SpeakerModel.LSX_II,
    "lsxiilt": SpeakerModel.LSX_II_LT,
    "lsx2lt": SpeakerModel.LSX_II_LT,
    "xio": SpeakerModel.XIO,
    "luxe": SpeakerModel.LS_LUXE,
    "lsluxe": SpeakerModel.LS_LUXE,
    "unknown": SpeakerModel.UNKNOWN,
}

_PRODUCT_CODES: Final[dict[str, SpeakerModel]] = {
    "SP4025": SpeakerModel.LS50_WIRELESS_II,
    "SP4017": SpeakerModel.LS60_WIRELESS,
    "SP4041": SpeakerModel.LSX_II,
    "SP4077": SpeakerModel.LSX_II_LT,
    "SP4083": SpeakerModel.XIO,
    "SP4042": SpeakerModel.LS_LUXE,
}


_VERSION_RE: Final = re.compile(r"\d+(?:\.\d+){1,3}")


@dataclass(frozen=True, slots=True, order=True)
class FirmwareVersion:
    """Dotted firmware version (``major.minor.patch.build``), ordered numerically."""

    major: int = 0
    minor: int = 0
    patch: int = 0
    build: int = 0
    raw: str = field(default="", compare=False)

    @classmethod
    def parse(cls, text: str | None) -> Self | None:
        """Extract the first dotted version (2 to 4 numeric parts) from ``text``.

        ``"2.6.12.4"`` and ``"V2.6.12"`` work. Anything without a dotted group, such
        as a bare digit run (``"V27100"``), gives ``None`` rather than a guess.
        """
        if not text:
            return None
        match = _VERSION_RE.search(text)
        if match is None:
            return None
        parts = [int(p) for p in match.group().split(".")]
        parts += [0] * (4 - len(parts))
        return cls(parts[0], parts[1], parts[2], parts[3], raw=text)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}.{self.build}"


class Feature(KefEnum):
    """Features gated by model and firmware."""

    SUBWOOFER_FORCE_ON = "subwoofer_force_on"
    SUBWOOFER_FORCE_ON_KW1 = "subwoofer_force_on_kw1"
    EQ_PROFILE = "eq_profile"
    STARTUP_TONE = "startup_tone"
    USB_CHARGING = "usb_charging"
    STANDBY_FRONT_LED = "standby_front_led"
    TOP_PANEL_LOCK = "top_panel_lock"
    TOP_PANEL_LED = "top_panel_led"
    CABLE_MODE = "cable_mode"
    AUTO_SWITCH_TV = "auto_switch_tv"
    DEFAULT_VOLUME = "default_volume"
    INDIVIDUAL_EQ_PROFILE = "individual_eq_profile"
    ADVANCED_REMOTE_CONTROL = "advanced_remote_control"
    GOOGLE_CAST_20 = "google_cast_20"
    SWUPDATE_18000 = "swupdate_18000"
    SECURED_API = "secured_api"
    SLEEP_TIMER = "sleep_timer"
    ALARM = "alarm"
    SCHEDULED_REBOOT = "scheduled_reboot"
    SURROUND_MODE = "surround_mode"
    HUAWEI_HIPLAY = "huawei_hiplay"
    AUTO_DETECT_PLACEMENT = "auto_detect_placement"
    IPT_CALIBRATION = "ipt_calibration"
    PREFERRED_VIRTUALISER = "preferred_virtualiser"
    KW2 = "kw2"
    MULTICHANNEL = "multichannel"


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """Static description of a speaker model."""

    model: SpeakerModel
    product_code: str | None
    marketing_name: str
    sources: tuple[Source, ...]
    eq_v2_from: FirmwareVersion | None
    feature_min_firmware: Mapping[Feature, FirmwareVersion]


def _v(text: str) -> FirmwareVersion:
    parsed = FirmwareVersion.parse(text)
    assert parsed is not None
    return parsed


_ANY: Final = FirmwareVersion(0, 0, 0, 0, raw="0.0.0")

_ALL_SOURCES: Final = (
    Source.WIFI,
    Source.BLUETOOTH,
    Source.TV,
    Source.OPTICAL,
    Source.COAXIAL,
    Source.USB,
    Source.ANALOG,
)

# Column order: LS50WII, LS60W, LSXII, LSXIILT, XIO, LUXE ("-" = feature absent).
_COLUMNS: Final = (
    SpeakerModel.LS50_WIRELESS_II,
    SpeakerModel.LS60_WIRELESS,
    SpeakerModel.LSX_II,
    SpeakerModel.LSX_II_LT,
    SpeakerModel.XIO,
    SpeakerModel.LS_LUXE,
)

_GATING: Final[dict[Feature, tuple[str, ...]]] = {
    Feature.SUBWOOFER_FORCE_ON: ("2.4.70", "1.1.34", "1.1.33", "1.0.0", "1.0.0", "any"),
    Feature.SUBWOOFER_FORCE_ON_KW1: ("-", "1.2.43", "1.2.46", "0.0.3", "1.0.0", "any"),
    Feature.EQ_PROFILE: ("1.5.0", "1.0.0", "1.0.0", "1.0.0", "1.0.0", "any"),
    Feature.STARTUP_TONE: ("1.5.0", "1.0.0", "1.0.0", "1.0.0", "1.0.0", "any"),
    Feature.USB_CHARGING: ("-", "-", "1.0.0", "1.0.0", "-", "-"),
    Feature.STANDBY_FRONT_LED: ("-", "1.0.0", "1.0.0", "1.0.0", "-", "any"),
    Feature.TOP_PANEL_LOCK: ("1.0.0", "-", "-", "-", "1.0.0", "-"),
    Feature.TOP_PANEL_LED: ("-", "-", "-", "-", "1.0.0", "-"),
    Feature.CABLE_MODE: ("1.0.0", "1.0.0", "1.0.0", "-", "-", "any"),
    Feature.AUTO_SWITCH_TV: ("3.0.100", "2.0.65", "2.0.64", "1.0.0", "1.0.0", "any"),
    Feature.DEFAULT_VOLUME: ("2.7.101", "2.0.65", "2.0.64", "1.0.0", "1.0.0", "any"),
    Feature.INDIVIDUAL_EQ_PROFILE: ("3.2.0", "2.1.0", "2.1.0", "1.2.0", "1.0.0", "any"),
    Feature.ADVANCED_REMOTE_CONTROL: ("3.5.143", "2.4.102", "2.4.101", "1.5.61", "1.0.0", "any"),
    Feature.GOOGLE_CAST_20: ("3.3.0", "2.2.0", "2.2.0", "1.0.0", "1.0.0", "any"),
    Feature.SWUPDATE_18000: ("2.5.74", "-", "1.4.0", "1.0.0", "1.0.0", "any"),
    Feature.SECURED_API: ("4.0.0", "3.0.0", "3.0.0", "2.0.0", "1.3.130", "any"),
    Feature.SLEEP_TIMER: ("4.0.0", "3.0.0", "3.0.0", "2.0.0", "1.0.0", "any"),
    Feature.ALARM: ("4.0.0", "3.0.0", "3.0.0", "2.0.0", "1.0.0", "any"),
    Feature.SCHEDULED_REBOOT: ("4.0.0", "3.0.0", "3.0.0", "2.0.0", "1.3.122", "any"),
    Feature.SURROUND_MODE: ("-", "-", "3.0.139", "2.2.90", "-", "-"),
    Feature.HUAWEI_HIPLAY: ("4.0.0", "3.0.0", "3.0.0", "2.0.0", "1.3.130", "1.0.33"),
    Feature.AUTO_DETECT_PLACEMENT: ("-", "-", "-", "-", "1.1.80", "-"),
    Feature.IPT_CALIBRATION: ("-", "-", "-", "-", "1.1.80", "-"),
    Feature.PREFERRED_VIRTUALISER: ("-", "-", "-", "-", "1.0.0", "-"),
    Feature.KW2: ("-", "-", "-", "-", "1.1.80", "-"),
    Feature.MULTICHANNEL: ("-", "-", "-", "-", "1.4.152", "-"),
}


def _feature_table(model: SpeakerModel) -> Mapping[Feature, FirmwareVersion]:
    column = _COLUMNS.index(model)
    table: dict[Feature, FirmwareVersion] = {}
    for feature, cells in _GATING.items():
        cell = cells[column]
        if cell == "-":
            continue
        table[feature] = _ANY if cell == "any" else _v(cell)
    return MappingProxyType(table)


def _info(
    model: SpeakerModel,
    code: str,
    name: str,
    sources: tuple[Source, ...],
    eq_v2_from: FirmwareVersion | None = None,
) -> ModelInfo:
    return ModelInfo(model, code, name, sources, eq_v2_from, _feature_table(model))


_S = Source
_LS_SOURCES: Final = (_S.WIFI, _S.BLUETOOTH, _S.TV, _S.OPTICAL, _S.COAXIAL, _S.ANALOG)

MODELS: Final[Mapping[SpeakerModel, ModelInfo]] = MappingProxyType(
    {
        SpeakerModel.LS50_WIRELESS_II: _info(
            SpeakerModel.LS50_WIRELESS_II, "SP4025", "LS50 Wireless II", _LS_SOURCES, _v("2.5.74")
        ),
        SpeakerModel.LS60_WIRELESS: _info(
            SpeakerModel.LS60_WIRELESS, "SP4017", "LS60 Wireless", _LS_SOURCES
        ),
        SpeakerModel.LSX_II: _info(
            SpeakerModel.LSX_II,
            "SP4041",
            "LSX II",
            (_S.WIFI, _S.BLUETOOTH, _S.TV, _S.OPTICAL, _S.USB, _S.ANALOG),
        ),
        SpeakerModel.LSX_II_LT: _info(
            SpeakerModel.LSX_II_LT,
            "SP4077",
            "LSX II LT",
            (_S.WIFI, _S.BLUETOOTH, _S.TV, _S.OPTICAL, _S.USB),
        ),
        SpeakerModel.XIO: _info(
            SpeakerModel.XIO, "SP4083", "XIO", (_S.WIFI, _S.BLUETOOTH, _S.TV, _S.OPTICAL)
        ),
        SpeakerModel.LS_LUXE: _info(SpeakerModel.LS_LUXE, "SP4042", "LS LUXE", _LS_SOURCES),
    }
)


def model_info(model: SpeakerModel) -> ModelInfo:
    """Return the :class:`ModelInfo` of ``model``, or a generic one for unknown models.

    The generic description lists all seven selectable sources and no gated feature.
    """
    known = MODELS.get(model)
    if known is not None:
        return known
    return ModelInfo(
        model=model,
        product_code=None,
        marketing_name=str(model) if model != SpeakerModel.UNKNOWN else "Unknown",
        sources=_ALL_SOURCES,
        eq_v2_from=None,
        feature_min_firmware=MappingProxyType({}),
    )


@dataclass(frozen=True, slots=True)
class Capabilities:
    """What a given speaker (model plus firmware) is expected to support."""

    model: SpeakerModel
    firmware: FirmwareVersion | None
    sources: tuple[Source, ...]

    def supports(self, feature: Feature) -> bool:
        """Tell whether ``feature`` is expected to be available.

        * Unknown model: ``True`` (generic, let the speaker decide).
        * Known model without the feature in its table: ``False``.
        * Unknown firmware: ``True`` if the feature exists for the model.
        * Otherwise: firmware >= the feature's minimum firmware.
        """
        info = MODELS.get(self.model)
        if info is None:
            return True
        minimum = info.feature_min_firmware.get(feature)
        if minimum is None:
            return False
        if self.firmware is None:
            return True
        return self.firmware >= minimum


def get_capabilities(model: SpeakerModel, firmware: FirmwareVersion | None) -> Capabilities:
    """Build the :class:`Capabilities` of a speaker."""
    return Capabilities(model=model, firmware=firmware, sources=model_info(model).sources)
