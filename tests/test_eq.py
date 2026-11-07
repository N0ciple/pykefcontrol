"""Tests for pykefcontrol.eq."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from pykefcontrol.enums import BassExtension, Polarity, SubwooferPreset
from pykefcontrol.eq import (
    DEFAULT_RANGES,
    EqProfile,
    EqRange,
    apply_subwoofer_preset,
    eq_profile_to_api,
    parse_eq_descriptors,
    parse_eq_profile,
    ranges_from_descriptors,
    validate_eq_profile,
)
from pykefcontrol.exceptions import KefProtocolError


def v2_inner() -> dict[str, Any]:
    return {
        "profileName": "Night",
        "profileId": "abc",
        "isExpertMode": True,
        "balance": -4,
        "deskMode": True,
        "deskModeSetting": -2.5,
        "wallMode": False,
        "wallModeSetting": -1.0,
        "phaseCorrection": True,
        "trebleAmount": 0.75,
        "highPassMode": True,
        "highPassModeFreq": 72.5,
        "subwooferPolarity": "inverted",
        "subOutLPFreq": 62.5,
        "bassExtension": "extra",
        "subwooferGain": 3.0,
        "subEnableStereo": False,
        "audioPolarity": "normal",
        "isKW1": False,
        "subwooferCount": 1,
        "subwooferPreset": "kc62",
        "subwooferOut": True,
        "subwooferOutHotfix": None,
        "soundProfile": "music",
        "wallMounted": True,
        "isCalibrated": None,
        "futureField": {"a": 1},
    }


def v1_inner() -> dict[str, Any]:
    return {
        "profileName": "",
        "profileId": "",
        "isExpertMode": False,
        "newTop": 5,
        "dspInfo": {
            "balance": 30,
            "deskMode": False,
            "deskModeSetting": 14,
            "wallMode": False,
            "wallModeSetting": 20,
            "phaseCorrection": True,
            "trebleAmount": 8,
            "highPassMode": False,
            "highPassModeFreq": 9,
            "subwooferPolarity": "normal",
            "subOutLPFreq": 8,
            "bassExtension": "standard",
            "subwooferGain": 10,
            "subEnableStereo": False,
            "audioPolarity": "normal",
            "isKW1": False,
            "subwooferCount": 0,
            "subwooferPreset": "custom",
            "newDsp": "x",
        },
    }


def test_v2_round_trip() -> None:
    raw = {"type": "kefEqProfileV2", "kefEqProfileV2": v2_inner()}
    profile = parse_eq_profile(raw)
    assert profile.version == 2
    assert profile.treble == 0.75
    assert profile.high_pass_freq == 72.5
    assert profile.subwoofer_polarity == Polarity.INVERTED
    assert profile.bass_extension == BassExtension.EXTRA
    assert profile.extra == {
        "subwooferOutHotfix": None,
        "isCalibrated": None,
        "futureField": {"a": 1},
    }
    assert eq_profile_to_api(profile) == raw


def test_v2_writes_null_hotfix_when_absent() -> None:
    inner = v2_inner()
    del inner["subwooferOutHotfix"], inner["isCalibrated"]
    out = eq_profile_to_api(parse_eq_profile(inner))["kefEqProfileV2"]
    assert out["subwooferOutHotfix"] is None
    assert out["isCalibrated"] is None


def test_hotfix_rule() -> None:
    inner = v2_inner()
    inner.update(subwooferOutHotfix=True, subwooferCount=0, subwooferOut=True)
    assert parse_eq_profile(inner).subwoofer_out is False
    inner["subwooferCount"] = 1
    assert parse_eq_profile(inner).subwoofer_out is True
    del inner["subwooferOut"]
    inner.update(subwooferOutHotfix=None, subwooferCount=0)
    assert parse_eq_profile(inner).subwoofer_out is True


def test_missing_fields_use_defaults() -> None:
    p = parse_eq_profile({"profileName": "", "profileId": "", "balance": None})
    assert p == EqProfile(version=2)
    assert p.is_default
    assert p.replace(profile_id="x").is_default is False
    assert parse_eq_profile({"deskModeSetting": None}).desk_mode_setting is None


def test_not_a_dict() -> None:
    with pytest.raises(KefProtocolError):
        parse_eq_profile([1, 2])
    with pytest.raises(KefProtocolError):
        parse_eq_profile(None)


def test_v1_parse_defaults() -> None:
    p = parse_eq_profile({"type": "kefEqProfile", "kefEqProfile": v1_inner()})
    assert p.version == 1
    assert p.balance == 0
    assert p.treble == 0.0
    assert p.desk_mode_setting == -3.0
    assert p.wall_mode_setting == 0.0
    assert p.high_pass_freq == 95
    assert p.sub_out_low_pass_freq == 80
    assert p.subwoofer_gain == 0.0
    assert p.subwoofer_out is True
    assert p.extra == {"newTop": 5}
    assert p.extra_dsp == {"newDsp": "x"}


def test_v1_round_trip_and_bare_dict() -> None:
    inner = v1_inner()
    p = parse_eq_profile(inner)  # bare dict, detected by dspInfo
    assert p.version == 1
    assert eq_profile_to_api(p) == {"type": "kefEqProfile", "kefEqProfile": inner}


def test_v1_treble_non_uniform() -> None:
    inner = v1_inner()
    inner["dspInfo"]["trebleAmount"] = 12
    p = parse_eq_profile(inner)
    assert p.treble == 1.0
    assert eq_profile_to_api(p)["kefEqProfile"]["dspInfo"]["trebleAmount"] == 12
    assert eq_profile_to_api(p.replace(treble=1.5))["kefEqProfile"]["dspInfo"]["trebleAmount"] == 13


def test_v1_out_of_range_index_uses_default() -> None:
    inner = v1_inner()
    inner["dspInfo"].update(trebleAmount=99, balance=-1, subwooferGain="x")
    p = parse_eq_profile(inner)
    assert (p.treble, p.balance, p.subwoofer_gain) == (0.0, 0, 0.0)


def test_v1_write_clamps_and_rounds() -> None:
    p = EqProfile(balance=30, subwoofer_gain=0.0, high_pass_freq=72.5, treble=9, version=1)
    dsp = eq_profile_to_api(p)["kefEqProfile"]["dspInfo"]
    assert dsp["balance"] == 60
    assert dsp["trebleAmount"] == 16
    assert dsp["highPassModeFreq"] in (4, 5)


def test_version_conversion_drops_extra() -> None:
    p = parse_eq_profile(v2_inner())
    v1 = eq_profile_to_api(p, version=1)["kefEqProfile"]
    assert "futureField" not in v1
    assert v1["dspInfo"]["trebleAmount"] == 11
    with pytest.raises(ValueError):
        eq_profile_to_api(p, version=3)


def test_validation() -> None:
    validate_eq_profile(EqProfile())
    validate_eq_profile(EqProfile(high_pass_freq=72.5, sub_out_low_pass_freq=47.5))
    for bad in (
        EqProfile(balance=31),
        EqProfile(treble=3.25),
        EqProfile(treble=0.1),
        EqProfile(subwoofer_count=3),
        EqProfile(desk_mode_setting=0.5),
        EqProfile(high_pass_freq=130),
    ):
        with pytest.raises(ValueError):
            validate_eq_profile(bad)
    validate_eq_profile(EqProfile(desk_mode_setting=None))
    custom = {"balance": EqRange(-10, 10, 1)}
    with pytest.raises(ValueError):
        validate_eq_profile(EqProfile(balance=20), custom)
    assert set(DEFAULT_RANGES) >= {"balance", "treble", "subwoofer_count"}


ROWS = {
    "rows": [
        {
            "name": "deskModeSetting",
            "defaultValue": {"type": "double_", "double_": -3.0},
            "descriptor": {"format": "range", "range": {"min": -10.0, "max": 0.0, "step": 0.5}},
        },
        {
            "name": "subwooferCount",
            "defaultValue": {"type": "i32_", "i32_": 0},
            "descriptor": {"format": "range", "range": {"min": 0, "max": 2, "step": 1}},
        },
        {
            "name": "deskMode",
            "defaultValue": {"type": "bool_", "bool_": False},
            "descriptor": {"format": "boolean"},
        },
        {
            "name": "bassExtension",
            "defaultValue": {"type": "string_", "string_": "standard"},
            "descriptor": {"format": "stringList", "stringList": ["standard", "extra", "less"]},
        },
        {
            "name": "trebleAmount",
            "descriptor": {"format": "range", "range": {"min": -2, "max": 2, "step": 0.5}},
        },
    ],
    "rowsCount": 5,
}


def test_descriptors() -> None:
    d = parse_eq_descriptors(copy.deepcopy(ROWS))
    assert set(d) == {
        "deskModeSetting",
        "subwooferCount",
        "deskMode",
        "bassExtension",
        "trebleAmount",
    }
    assert d["deskModeSetting"].range == EqRange(-10, 0, 0.5, -3.0)
    assert d["deskModeSetting"].default == -3.0
    assert d["deskMode"].format == "boolean"
    assert d["deskMode"].range is None
    assert d["bassExtension"].choices == ("standard", "extra", "less")
    ranges = ranges_from_descriptors(d)
    assert set(ranges) == {"desk_mode_setting", "subwoofer_count", "treble"}
    assert ranges["treble"].maximum == 2
    with pytest.raises(KefProtocolError):
        parse_eq_descriptors({"nope": 1})


def test_presets() -> None:
    base = EqProfile(subwoofer_count=1)
    p = apply_subwoofer_preset(base, SubwooferPreset.KC62, "LS50WII")
    assert (p.high_pass_freq, p.sub_out_low_pass_freq, p.subwoofer_gain) == (70, 45, 0)
    assert p.high_pass_mode and p.subwoofer_out and p.subwoofer_preset == SubwooferPreset.KC62

    p = apply_subwoofer_preset(EqProfile(subwoofer_count=2), SubwooferPreset.KF92, "ls60w")
    assert p.subwoofer_gain == -9
    assert (p.high_pass_freq, p.sub_out_low_pass_freq) == (72.5, 50)

    p = apply_subwoofer_preset(base.replace(is_kw1=True), SubwooferPreset.KC62, "LSXII")
    assert p.subwoofer_gain == 4

    p = apply_subwoofer_preset(base, SubwooferPreset.KC62, "unknown")
    assert (p.high_pass_freq, p.sub_out_low_pass_freq, p.subwoofer_gain) == (95, 80, 0)

    p = apply_subwoofer_preset(EqProfile(subwoofer_count=0), SubwooferPreset.KC62, "xio")
    assert not p.high_pass_mode and not p.subwoofer_out and p.subwoofer_gain == 0


def test_preset_custom_and_kw1_reset() -> None:
    p = EqProfile(subwoofer_count=1, high_pass_freq=70, is_kw1=True, subwoofer_out=False)
    c = apply_subwoofer_preset(p, SubwooferPreset.CUSTOM, "luxe")
    assert c.high_pass_freq == 70 and c.subwoofer_out and c.is_kw1
    t2 = apply_subwoofer_preset(p, SubwooferPreset.T2, "luxe")
    assert (t2.high_pass_freq, t2.sub_out_low_pass_freq) == (95, 80)
    assert t2.is_kw1 is False
    t2 = apply_subwoofer_preset(p.replace(is_kw1=False), SubwooferPreset.T2, "LSXIILT")
    assert (t2.high_pass_freq, t2.sub_out_low_pass_freq, t2.subwoofer_gain) == (67.5, 62.5, -1)
