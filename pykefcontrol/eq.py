"""EQ / DSP profile model and (de)serialisation. Pure functions, no I/O.

The official KEF Connect app always reads and writes the *whole* profile
(GET ``kef:eqProfile[/v2]``, modify, POST it back); the individual
``settings:/kef/dsp/*`` leaves are mostly unused by the app, so this library
follows the same approach.

Two wire formats exist:

* **v2** (``kef:eqProfile/v2``, type ``kefEqProfileV2``): flat object with real
  physical values (dB, Hz).
* **v1** (``kef:eqProfile``, type ``kefEqProfile``): numeric settings are nested
  under ``dspInfo`` and are *indices* into fixed value lists, not physical values.

:class:`EqProfile` always holds physical values (balance steps, dB, Hz); the
conversion from/to v1 indices is done by :func:`parse_eq_profile` and
:func:`eq_profile_to_api`. Unknown keys sent by the speaker are kept in
``extra`` (and ``extra_dsp`` for v1's ``dspInfo``) and written back verbatim, so
fields added by newer firmware are never dropped.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from .enums import BassExtension, Polarity, SoundProfile, SubwooferPreset
from .exceptions import KefProtocolError
from .values import ValueType, decode, encode, type_of

# --------------------------------------------------------------------------- #
# Profile
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True, kw_only=True)
class EqProfile:
    """An EQ profile in physical units. Defaults are the app's "normal" profile.

    Units: ``balance`` in steps (-30..30), ``*_setting`` / ``treble`` /
    ``subwooferGain`` in dB, ``*_freq`` in Hz. ``version`` is the wire format the
    profile came from and will be written as (1 or 2).
    """

    profile_name: str = ""
    profile_id: str = ""
    expert_mode: bool = False
    balance: int = 0
    desk_mode: bool = False
    desk_mode_setting: float | None = -3.0
    wall_mode: bool = False
    wall_mode_setting: float = 0.0
    wall_mounted: bool = False
    phase_correction: bool = True
    treble: float = 0.0
    high_pass_mode: bool = False
    high_pass_freq: float = 95
    sub_out_low_pass_freq: float = 80
    subwoofer_gain: float = 0.0
    subwoofer_polarity: Polarity = Polarity.NORMAL
    subwoofer_preset: SubwooferPreset = SubwooferPreset.CUSTOM
    subwoofer_count: int = 0
    sub_stereo: bool = False
    audio_polarity: Polarity = Polarity.NORMAL
    is_kw1: bool = False
    bass_extension: BassExtension = BassExtension.STANDARD
    subwoofer_out: bool = True
    sound_profile: SoundProfile = SoundProfile.DEFAULT
    version: int = 2
    extra: Mapping[str, Any] = field(default_factory=dict)
    extra_dsp: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_default(self) -> bool:
        """``True`` for the speaker's default profile (empty id and name)."""
        return not self.profile_id and not self.profile_name

    def replace(self, **changes: Any) -> EqProfile:
        """Return a copy with ``changes`` applied."""
        return dataclasses.replace(self, **changes)


# --------------------------------------------------------------------------- #
# Ranges and validation
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class EqRange:
    """Allowed range of a numeric setting (balance steps, dB or Hz)."""

    minimum: float
    maximum: float
    step: float
    default: float | None = None


# Keyed by EqProfile field name; app fallbacks (speakers may advertise their own).
DEFAULT_RANGES: Final[Mapping[str, EqRange]] = {
    "balance": EqRange(-30, 30, 1, 0),
    "desk_mode_setting": EqRange(-10, 0, 0.5, -3.0),
    "wall_mode_setting": EqRange(-10, 0, 0.5, 0.0),
    "treble": EqRange(-3, 3, 0.25, 0.0),
    "high_pass_freq": EqRange(50, 120, 5, 95),
    "sub_out_low_pass_freq": EqRange(40, 250, 5, 80),
    "subwoofer_gain": EqRange(-10, 10, 1, 0.0),
    "subwoofer_count": EqRange(0, 2, 1, 0),
}

# Frequencies may be off-grid (subwoofer presets use 47.5, 62.5 ...).
_OFF_GRID_OK: Final = frozenset({"high_pass_freq", "sub_out_low_pass_freq"})


def validate_eq_profile(profile: EqProfile, ranges: Mapping[str, EqRange] | None = None) -> None:
    """Raise :class:`ValueError` if a numeric setting is outside its range.

    ``ranges`` defaults to :data:`DEFAULT_RANGES`; pass
    :func:`ranges_from_descriptors` output to use the speaker's own limits.
    Values must lie on the range's step grid, except the two frequencies.
    """
    rng = DEFAULT_RANGES if ranges is None else ranges
    for name, spec in rng.items():
        if not hasattr(profile, name):
            continue
        value = getattr(profile, name)
        if value is None:
            continue
        if not spec.minimum - 1e-9 <= value <= spec.maximum + 1e-9:
            raise ValueError(f"{name}={value} out of range [{spec.minimum}, {spec.maximum}]")
        if name in _OFF_GRID_OK or spec.step <= 0:
            continue
        steps = (value - spec.minimum) / spec.step
        if abs(steps - round(steps)) > 1e-6:
            raise ValueError(f"{name}={value} is not a multiple of {spec.step} from {spec.minimum}")


# --------------------------------------------------------------------------- #
# v1 index tables
# --------------------------------------------------------------------------- #

_TREBLE_V1: Final[tuple[float, ...]] = (
    -3, -2.5, -2, -1.5, -1, -0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75, 1, 1.5, 2, 2.5, 3,
)  # fmt: skip


def _grid(minimum: float, step: float, count: int) -> tuple[float, ...]:
    return tuple(minimum + i * step for i in range(count))


# field name -> (v1 dspInfo key, value list indexed by the wire index)
_V1_TABLES: Final[Mapping[str, tuple[str, tuple[float, ...]]]] = {
    "balance": ("balance", _grid(-30, 1, 61)),
    "desk_mode_setting": ("deskModeSetting", _grid(-10, 0.5, 21)),
    "wall_mode_setting": ("wallModeSetting", _grid(-10, 0.5, 21)),
    "treble": ("trebleAmount", _TREBLE_V1),
    "high_pass_freq": ("highPassModeFreq", _grid(50, 5, 15)),
    "sub_out_low_pass_freq": ("subOutLPFreq", _grid(40, 5, 43)),
    "subwoofer_gain": ("subwooferGain", _grid(-10, 1, 21)),
}

_DEFAULTS: Final = EqProfile()

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _bool(d: Mapping[str, Any], key: str, default: bool) -> bool:
    value = d.get(key)
    return value if isinstance(value, bool) else default


def _str(d: Mapping[str, Any], key: str, default: str) -> str:
    value = d.get(key)
    return value if isinstance(value, str) else default


def _num(d: Mapping[str, Any], key: str, default: float) -> float:
    value = d.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return default
    return value


def _int(d: Mapping[str, Any], key: str, default: int) -> int:
    value = d.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return default
    return int(value)


def _enum[E: (BassExtension, Polarity, SubwooferPreset, SoundProfile)](
    cls: type[E], d: Mapping[str, Any], key: str, default: E
) -> E:
    parsed = cls.parse(d.get(key))
    return default if parsed is None else parsed


def _index_to_value(field_name: str, d: Mapping[str, Any], default: float) -> float:
    key, table = _V1_TABLES[field_name]
    idx = d.get(key)
    if isinstance(idx, bool) or not isinstance(idx, int) or not 0 <= idx < len(table):
        return default
    return table[idx]


def _value_to_index(field_name: str, value: float) -> int:
    table = _V1_TABLES[field_name][1]
    return min(range(len(table)), key=lambda i: abs(table[i] - value))


def _freq_out(value: float) -> int | float:
    return int(value) if float(value).is_integer() else float(value)


_V2_KNOWN: Final = frozenset(
    {
        "profileName", "profileId", "isExpertMode", "balance", "deskMode", "deskModeSetting",
        "wallMode", "wallModeSetting", "phaseCorrection", "trebleAmount", "highPassMode",
        "highPassModeFreq", "subwooferPolarity", "subOutLPFreq", "bassExtension",
        "subwooferGain", "subEnableStereo", "audioPolarity", "isKW1", "subwooferCount",
        "subwooferPreset", "subwooferOut", "soundProfile", "wallMounted",
    }
)  # fmt: skip
_V1_TOP_KNOWN: Final = frozenset({"profileName", "profileId", "isExpertMode", "dspInfo"})
_V1_DSP_KNOWN: Final = frozenset(
    {
        "balance", "deskMode", "deskModeSetting", "wallMode", "wallModeSetting",
        "phaseCorrection", "trebleAmount", "highPassMode", "highPassModeFreq",
        "subwooferPolarity", "subOutLPFreq", "bassExtension", "subwooferGain",
        "subEnableStereo", "audioPolarity", "isKW1", "subwooferCount", "subwooferPreset",
    }
)  # fmt: skip

# --------------------------------------------------------------------------- #
# Parsing / serialising
# --------------------------------------------------------------------------- #


def parse_eq_profile(raw: Any) -> EqProfile:
    """Parse a typed profile value (or its bare inner dict) into an :class:`EqProfile`.

    v1 is detected by the ``kefEqProfile`` type or a ``dspInfo`` key. Missing
    fields take the app's defaults; out-of-range v1 indices fall back to the
    default value. Raises :class:`KefProtocolError` if ``raw`` is not an object.
    """
    inner = decode(raw)
    if not isinstance(inner, dict):
        raise KefProtocolError(f"Expected EQ profile object, got {raw!r}")
    if type_of(raw) == ValueType.EQ_PROFILE or "dspInfo" in inner:
        return _parse_v1(inner)
    return _parse_v2(inner)


def _parse_v1(inner: dict[str, Any]) -> EqProfile:
    dsp = inner.get("dspInfo")
    if not isinstance(dsp, dict):
        dsp = {}
    d = _DEFAULTS
    return EqProfile(
        profile_name=_str(inner, "profileName", ""),
        profile_id=_str(inner, "profileId", ""),
        expert_mode=_bool(inner, "isExpertMode", False),
        balance=int(_index_to_value("balance", dsp, d.balance)),
        desk_mode=_bool(dsp, "deskMode", d.desk_mode),
        desk_mode_setting=_index_to_value("desk_mode_setting", dsp, -3.0),
        wall_mode=_bool(dsp, "wallMode", d.wall_mode),
        wall_mode_setting=_index_to_value("wall_mode_setting", dsp, d.wall_mode_setting),
        phase_correction=_bool(dsp, "phaseCorrection", d.phase_correction),
        treble=_index_to_value("treble", dsp, d.treble),
        high_pass_mode=_bool(dsp, "highPassMode", d.high_pass_mode),
        high_pass_freq=_index_to_value("high_pass_freq", dsp, d.high_pass_freq),
        sub_out_low_pass_freq=_index_to_value(
            "sub_out_low_pass_freq", dsp, d.sub_out_low_pass_freq
        ),
        subwoofer_gain=_index_to_value("subwoofer_gain", dsp, d.subwoofer_gain),
        subwoofer_polarity=_enum(Polarity, dsp, "subwooferPolarity", d.subwoofer_polarity),
        subwoofer_preset=_enum(SubwooferPreset, dsp, "subwooferPreset", d.subwoofer_preset),
        subwoofer_count=_int(dsp, "subwooferCount", d.subwoofer_count),
        sub_stereo=_bool(dsp, "subEnableStereo", d.sub_stereo),
        audio_polarity=_enum(Polarity, dsp, "audioPolarity", d.audio_polarity),
        is_kw1=_bool(dsp, "isKW1", d.is_kw1),
        bass_extension=_enum(BassExtension, dsp, "bassExtension", d.bass_extension),
        version=1,
        extra={k: v for k, v in inner.items() if k not in _V1_TOP_KNOWN},
        extra_dsp={k: v for k, v in dsp.items() if k not in _V1_DSP_KNOWN},
    )


def _parse_v2(inner: dict[str, Any]) -> EqProfile:
    d = _DEFAULTS
    count = _int(inner, "subwooferCount", d.subwoofer_count)
    sub_out = _bool(inner, "subwooferOut", True)
    if inner.get("subwooferOutHotfix") is True and count <= 0:
        sub_out = False
    if "deskModeSetting" not in inner:
        desk: float | None = d.desk_mode_setting
    elif inner["deskModeSetting"] is None:
        desk = None
    else:
        desk = _num(inner, "deskModeSetting", -3.0)
    return EqProfile(
        profile_name=_str(inner, "profileName", ""),
        profile_id=_str(inner, "profileId", ""),
        expert_mode=_bool(inner, "isExpertMode", False),
        balance=int(_num(inner, "balance", d.balance)),
        desk_mode=_bool(inner, "deskMode", d.desk_mode),
        desk_mode_setting=desk,
        wall_mode=_bool(inner, "wallMode", d.wall_mode),
        wall_mode_setting=_num(inner, "wallModeSetting", d.wall_mode_setting),
        wall_mounted=_bool(inner, "wallMounted", False),
        phase_correction=_bool(inner, "phaseCorrection", d.phase_correction),
        treble=_num(inner, "trebleAmount", d.treble),
        high_pass_mode=_bool(inner, "highPassMode", d.high_pass_mode),
        high_pass_freq=_num(inner, "highPassModeFreq", d.high_pass_freq),
        sub_out_low_pass_freq=_num(inner, "subOutLPFreq", d.sub_out_low_pass_freq),
        subwoofer_gain=_num(inner, "subwooferGain", d.subwoofer_gain),
        subwoofer_polarity=_enum(Polarity, inner, "subwooferPolarity", d.subwoofer_polarity),
        subwoofer_preset=_enum(SubwooferPreset, inner, "subwooferPreset", d.subwoofer_preset),
        subwoofer_count=count,
        sub_stereo=_bool(inner, "subEnableStereo", d.sub_stereo),
        audio_polarity=_enum(Polarity, inner, "audioPolarity", d.audio_polarity),
        is_kw1=_bool(inner, "isKW1", d.is_kw1),
        bass_extension=_enum(BassExtension, inner, "bassExtension", d.bass_extension),
        subwoofer_out=sub_out,
        sound_profile=_enum(SoundProfile, inner, "soundProfile", d.sound_profile),
        version=2,
        extra={k: v for k, v in inner.items() if k not in _V2_KNOWN},
    )


def eq_profile_to_api(profile: EqProfile, version: int | None = None) -> dict[str, Any]:
    """Return the typed value to send with ``setData`` for ``profile``.

    ``version`` (1 or 2) defaults to ``profile.version``. v1 converts physical
    values to the nearest index (clamped) and cannot carry ``wall_mounted``,
    ``subwoofer_out`` or ``sound_profile``. ``extra`` is merged back only when
    writing the same version the profile was read as. v2 sends
    ``subwooferOutHotfix`` and ``isCalibrated`` as ``null`` like the app, unless
    the speaker sent them.
    """
    ver = profile.version if version is None else version
    if ver not in (1, 2):
        raise ValueError(f"EQ profile version must be 1 or 2, not {ver!r}")
    keep_extra = ver == profile.version
    if ver == 1:
        return _to_v1(profile, keep_extra)
    return _to_v2(profile, keep_extra)


def _to_v2(p: EqProfile, keep_extra: bool) -> dict[str, Any]:
    body: dict[str, Any] = {
        "subwooferOutHotfix": None,
        "isCalibrated": None,
    }
    if keep_extra:
        body.update(p.extra)
    body.update(
        {
            "profileName": p.profile_name,
            "profileId": p.profile_id,
            "isExpertMode": p.expert_mode,
            "balance": int(p.balance),
            "deskMode": p.desk_mode,
            "deskModeSetting": p.desk_mode_setting,
            "wallMode": p.wall_mode,
            "wallModeSetting": float(p.wall_mode_setting),
            "phaseCorrection": p.phase_correction,
            "trebleAmount": float(p.treble),
            "highPassMode": p.high_pass_mode,
            "highPassModeFreq": _freq_out(p.high_pass_freq),
            "subwooferPolarity": str(p.subwoofer_polarity),
            "subOutLPFreq": _freq_out(p.sub_out_low_pass_freq),
            "bassExtension": str(p.bass_extension),
            "subwooferGain": float(p.subwoofer_gain),
            "subEnableStereo": p.sub_stereo,
            "audioPolarity": str(p.audio_polarity),
            "isKW1": p.is_kw1,
            "subwooferCount": int(p.subwoofer_count),
            "subwooferPreset": str(p.subwoofer_preset),
            "subwooferOut": p.subwoofer_out,
            "soundProfile": str(p.sound_profile),
            "wallMounted": p.wall_mounted,
        }
    )
    return encode(ValueType.EQ_PROFILE_V2, body)


def _to_v1(p: EqProfile, keep_extra: bool) -> dict[str, Any]:
    def idx(name: str, value: float | None) -> int:
        if value is None:
            value = DEFAULT_RANGES[name].default or 0.0
        return _value_to_index(name, value)

    dsp: dict[str, Any] = dict(p.extra_dsp) if keep_extra else {}
    dsp.update(
        {
            "balance": idx("balance", p.balance),
            "deskMode": p.desk_mode,
            "deskModeSetting": idx("desk_mode_setting", p.desk_mode_setting),
            "wallMode": p.wall_mode,
            "wallModeSetting": idx("wall_mode_setting", p.wall_mode_setting),
            "phaseCorrection": p.phase_correction,
            "trebleAmount": idx("treble", p.treble),
            "highPassMode": p.high_pass_mode,
            "highPassModeFreq": idx("high_pass_freq", p.high_pass_freq),
            "subwooferPolarity": str(p.subwoofer_polarity),
            "subOutLPFreq": idx("sub_out_low_pass_freq", p.sub_out_low_pass_freq),
            "bassExtension": str(p.bass_extension),
            "subwooferGain": idx("subwoofer_gain", p.subwoofer_gain),
            "subEnableStereo": p.sub_stereo,
            "audioPolarity": str(p.audio_polarity),
            "isKW1": p.is_kw1,
            "subwooferCount": int(p.subwoofer_count),
            "subwooferPreset": str(p.subwoofer_preset),
        }
    )
    body: dict[str, Any] = dict(p.extra) if keep_extra else {}
    body.update(
        {
            "profileName": p.profile_name,
            "profileId": p.profile_id,
            "isExpertMode": p.expert_mode,
            "dspInfo": dsp,
        }
    )
    return encode(ValueType.EQ_PROFILE, body)


# --------------------------------------------------------------------------- #
# Descriptors (kef:dsp/editValue)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class EqDescriptor:
    """One row of ``kef:dsp/editValue``: what the speaker allows for a setting.

    ``format`` is ``"range"``, ``"boolean"`` or ``"stringList"``; ``range`` is set
    for ranges and ``choices`` for string lists.
    """

    name: str
    format: str
    default: Any
    range: EqRange | None
    choices: tuple[str, ...]


def _opt_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def parse_eq_descriptors(rows_response: Any) -> dict[str, EqDescriptor]:
    """Parse a ``getRows`` response for ``kef:dsp/editValue``, keyed by API name."""
    rows = rows_response.get("rows") if isinstance(rows_response, dict) else rows_response
    if not isinstance(rows, list):
        raise KefProtocolError(f"Expected EQ descriptor rows, got {rows_response!r}")
    result: dict[str, EqDescriptor] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            continue
        desc = row.get("descriptor")
        desc = desc if isinstance(desc, dict) else {}
        fmt = desc.get("format")
        default = decode(row.get("defaultValue"))
        rng: EqRange | None = None
        raw_range = desc.get("range")
        if isinstance(raw_range, dict):
            lo, hi, step = (_opt_float(raw_range.get(k)) for k in ("min", "max", "step"))
            if lo is not None and hi is not None:
                rng = EqRange(lo, hi, step if step is not None else 1.0, _opt_float(default))
        raw_list = desc.get("stringList")
        choices = (
            tuple(s for s in raw_list if isinstance(s, str)) if isinstance(raw_list, list) else ()
        )
        name = row["name"]
        result[name] = EqDescriptor(
            name=name,
            format=fmt if isinstance(fmt, str) else "",
            default=default,
            range=rng,
            choices=choices,
        )
    return result


_API_TO_FIELD: Final[Mapping[str, str]] = {
    "balance": "balance",
    "deskModeSetting": "desk_mode_setting",
    "wallModeSetting": "wall_mode_setting",
    "trebleAmount": "treble",
    "highPassModeFreq": "high_pass_freq",
    "subOutLPFreq": "sub_out_low_pass_freq",
    "subwooferGain": "subwoofer_gain",
    "subwooferCount": "subwoofer_count",
}


def ranges_from_descriptors(descriptors: Mapping[str, EqDescriptor]) -> dict[str, EqRange]:
    """Map descriptors with a range to ``{EqProfile field name: EqRange}``."""
    return {
        _API_TO_FIELD[name]: desc.range
        for name, desc in descriptors.items()
        if name in _API_TO_FIELD and desc.range is not None
    }


# --------------------------------------------------------------------------- #
# Subwoofer presets (app logic, eq_dsp.md section 5)
# --------------------------------------------------------------------------- #

_LS60 = "ls60w"
_LUXE = "luxe"
_LSX = "lsx"
_LS50 = "ls50w2"

_MODEL_FAMILY: Final[Mapping[str, str]] = {
    "ls60w": _LS60,
    "luxe": _LUXE,
    "lsxii": _LSX,
    "lsx2": _LSX,
    "lsxiilt": _LSX,
    "lsx2lt": _LSX,
    "xio": _LSX,
    "ls50wii": _LS50,
    "ls50w2": _LS50,
}

_Freqs = tuple[float, float]
_KW1_T2: Final[tuple[_Freqs, _Freqs]] = ((95, 80), (67.5, 62.5))  # (kw1, not kw1)

# family -> preset -> (high-pass, low-pass); absent == default 95 / 80
_FREQS: Final[Mapping[str, Mapping[SubwooferPreset, _Freqs]]] = {
    _LS60: {
        SubwooferPreset.OTHER: (65, 55),
        SubwooferPreset.KC62: (65, 47.5),
        SubwooferPreset.KF92: (72.5, 50),
        SubwooferPreset.KUBE_10B: (60, 52.5),
        SubwooferPreset.KUBE_12B: (60, 52.5),
        SubwooferPreset.KUBE_15MIE: (60, 52.5),
    },
    _LUXE: {
        SubwooferPreset.OTHER: (65, 55),
        SubwooferPreset.KC62: (65, 57.5),
        SubwooferPreset.KF92: (65, 57.5),
        SubwooferPreset.KUBE_8B: (65, 60),
        SubwooferPreset.KUBE_10B: (65, 57.5),
        SubwooferPreset.KUBE_12B: (65, 57.5),
        SubwooferPreset.KUBE_15MIE: (65, 57.5),
    },
    _LSX: {
        SubwooferPreset.OTHER: (65, 55),
        SubwooferPreset.KC62: (67.5, 47.5),
        SubwooferPreset.KF92: (67.5, 55),
        SubwooferPreset.KUBE_8B: (67.5, 62.5),
        SubwooferPreset.KUBE_10B: (67.5, 55),
        SubwooferPreset.KUBE_12B: (65, 52.5),
        SubwooferPreset.KUBE_15MIE: (65, 57.5),
    },
    _LS50: {
        SubwooferPreset.OTHER: (65, 55),
        SubwooferPreset.KC62: (70, 45),
        SubwooferPreset.KF92: (70, 50),
        SubwooferPreset.KUBE_8B: (70, 60),
        SubwooferPreset.KUBE_10B: (70, 55),
        SubwooferPreset.KUBE_12B: (70, 55),
        SubwooferPreset.KUBE_15MIE: (60, 55),
        SubwooferPreset.T2: (70, 65),
    },
}

_Gain = tuple[int, int]  # (one subwoofer, two subwoofers)
_P = SubwooferPreset

# family -> preset -> is_kw1 -> (gain with 1 sub, gain with 2 subs)
_GAINS: Final[Mapping[str, Mapping[SubwooferPreset, Mapping[bool, _Gain]]]] = {
    _LS50: {
        _P.OTHER: {True: (0, -6), False: (0, -6)},
        _P.KC62: {True: (5, -1), False: (0, -6)},
        _P.KF92: {True: (4, -2), False: (-1, -7)},
        _P.KUBE_8B: {True: (2, -3), False: (3, -3)},
        _P.KUBE_10B: {True: (-1, -7), False: (0, -6)},
        _P.KUBE_12B: {True: (0, -6), False: (1, -5)},
        _P.KUBE_15MIE: {True: (2, -4), False: (3, -3)},
        _P.T2: {True: (0, -6), False: (0, -6)},
    },
    _LS60: {
        _P.OTHER: {True: (0, -6), False: (0, -6)},
        _P.KC62: {True: (4, -2), False: (-1, -7)},
        _P.KF92: {True: (2, -4), False: (-3, -9)},
        _P.KUBE_10B: {True: (-1, -7), False: (0, -6)},
        _P.KUBE_12B: {True: (-2, -8), False: (-1, -7)},
        _P.KUBE_15MIE: {True: (2, -4), False: (3, -3)},
    },
    _LSX: {
        _P.OTHER: {True: (0, -6), False: (0, -6)},
        _P.KC62: {True: (4, -2), False: (-1, -7)},
        _P.KF92: {True: (2, -4), False: (-3, -9)},
        _P.KUBE_8B: {True: (2, -4), False: (3, -3)},
        _P.KUBE_10B: {True: (0, -6), False: (1, -5)},
        _P.KUBE_12B: {True: (-2, -8), False: (-1, -7)},
        _P.KUBE_15MIE: {True: (-1, -7), False: (0, -6)},
        _P.T2: {False: (-1, -7)},
    },
    _LUXE: {
        _P.OTHER: {True: (0, -6), False: (0, -6)},
        _P.KC62: {True: (3, -3), False: (-2, -8)},
        _P.KF92: {True: (0, -6), False: (-5, -10)},
        _P.KUBE_8B: {True: (1, -5), False: (2, -4)},
        _P.KUBE_10B: {True: (0, -6), False: (1, -5)},
        _P.KUBE_12B: {True: (-3, -9), False: (-2, -7)},
        _P.KUBE_15MIE: {True: (2, -4), False: (3, -3)},
        _P.T2: {False: (1, -5)},
    },
}


def _preset_freqs(family: str | None, preset: SubwooferPreset, is_kw1: bool) -> _Freqs:
    if family is None:
        return (95, 80)
    if preset == SubwooferPreset.T2 and family in (_LSX, _LUXE):
        return _KW1_T2[0] if is_kw1 else _KW1_T2[1]
    return _FREQS[family].get(preset, (95, 80))


def _preset_gain(family: str | None, preset: SubwooferPreset, is_kw1: bool, count: int) -> float:
    if family is None or count not in (1, 2):
        return 0.0
    gains = _GAINS[family].get(preset, {}).get(is_kw1)
    return 0.0 if gains is None else float(gains[count - 1])


def apply_subwoofer_preset(
    profile: EqProfile, preset: SubwooferPreset, speaker_model: str
) -> EqProfile:
    """Return ``profile`` with a subwoofer ``preset`` applied, like the app does.

    ``speaker_model`` is the model id (``"LS50WII"``, ``"LS60W"``, ``"LSXII"``,
    ``"LSXIILT"``, ``"xio"``, ``"luxe"``; case-insensitive). ``custom`` only sets
    the preset (and ``subwoofer_out`` = count != 0). Other presets set the
    high-pass mode (expert mode or any sub), high-pass / low-pass frequencies (Hz)
    and gain (dB) from the app's tables; unknown models get 95 Hz / 80 Hz / 0 dB.
    For ``t2`` and ``other`` on known speakers the ``is_kw1`` flag is reset
    afterwards (tables are looked up with the previous flag).
    """
    out = profile.subwoofer_count != 0
    if preset == SubwooferPreset.CUSTOM:
        return profile.replace(subwoofer_preset=preset, subwoofer_out=out)
    family = _MODEL_FAMILY.get(speaker_model.strip().lower())
    high, low = _preset_freqs(family, preset, profile.is_kw1)
    gain = _preset_gain(family, preset, profile.is_kw1, profile.subwoofer_count)
    is_kw1 = profile.is_kw1
    if family is not None and preset in (SubwooferPreset.T2, SubwooferPreset.OTHER):
        is_kw1 = False
    return profile.replace(
        high_pass_mode=profile.expert_mode or profile.subwoofer_count != 0,
        high_pass_freq=high,
        sub_out_low_pass_freq=low,
        subwoofer_gain=gain,
        subwoofer_preset=preset,
        subwoofer_out=out,
        is_kw1=is_kw1,
    )
