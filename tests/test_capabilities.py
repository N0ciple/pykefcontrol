from __future__ import annotations

import pytest

from pykefcontrol.capabilities import (
    MODELS,
    Feature,
    FirmwareVersion,
    SpeakerModel,
    get_capabilities,
    model_info,
)
from pykefcontrol.enums import Source


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("LS50WII", SpeakerModel.LS50_WIRELESS_II),
        ("ls50w2", SpeakerModel.LS50_WIRELESS_II),
        ("LS50W2", SpeakerModel.LS50_WIRELESS_II),
        ("LS50 Wireless II", SpeakerModel.LS50_WIRELESS_II),
        ("LS60", SpeakerModel.LS60_WIRELESS),
        ("LS60W", SpeakerModel.LS60_WIRELESS),
        ("LSX2", SpeakerModel.LSX_II),
        ("LSX II", SpeakerModel.LSX_II),
        ("LSX2LT", SpeakerModel.LSX_II_LT),
        ("LSXIILT", SpeakerModel.LSX_II_LT),
        ("XIO", SpeakerModel.XIO),
        ("xio", SpeakerModel.XIO),
        ("LUXE", SpeakerModel.LS_LUXE),
        ("LS LUXE", SpeakerModel.LS_LUXE),
        # LS50 Wireless II firmware 4.1 reports the product code as modelName
        ("SP4025", SpeakerModel.LS50_WIRELESS_II),
        ("sp4017", SpeakerModel.LS60_WIRELESS),
        (None, SpeakerModel.UNKNOWN),
        ("", SpeakerModel.UNKNOWN),
    ],
)
def test_from_model_name(name: str | None, expected: SpeakerModel) -> None:
    assert SpeakerModel.from_model_name(name) is expected


def test_from_model_name_unknown_pseudo_member() -> None:
    model = SpeakerModel.from_model_name("FutureSpeaker")
    assert model == "FutureSpeaker"
    assert not model.is_known


def test_from_product_code() -> None:
    assert SpeakerModel.from_product_code("SP4025") is SpeakerModel.LS50_WIRELESS_II
    assert SpeakerModel.from_product_code("SP4017") is SpeakerModel.LS60_WIRELESS
    assert SpeakerModel.from_product_code("SP4041") is SpeakerModel.LSX_II
    assert SpeakerModel.from_product_code("SP4077") is SpeakerModel.LSX_II_LT
    assert SpeakerModel.from_product_code("SP4083") is SpeakerModel.XIO
    assert SpeakerModel.from_product_code("SP4042") is SpeakerModel.LS_LUXE
    assert SpeakerModel.from_product_code("SP9999") is SpeakerModel.UNKNOWN
    assert SpeakerModel.from_product_code(None) is SpeakerModel.UNKNOWN


def test_firmware_parse() -> None:
    v = FirmwareVersion.parse("2.6.12.4")
    assert v == FirmwareVersion(2, 6, 12, 4)
    assert str(v) == "2.6.12.4"
    assert FirmwareVersion.parse("V2.6.12") == FirmwareVersion(2, 6, 12)
    assert FirmwareVersion.parse("LS50WII_V2.7") == FirmwareVersion(2, 7)
    assert FirmwareVersion.parse("V27100") is None
    assert FirmwareVersion.parse("") is None
    assert FirmwareVersion.parse(None) is None


def test_firmware_compare() -> None:
    assert FirmwareVersion(2, 10) > FirmwareVersion(2, 9, 99)
    assert FirmwareVersion(4, 0, 0) >= FirmwareVersion(4)
    assert FirmwareVersion.parse("4.0.0") == FirmwareVersion.parse("V4.0.0")
    assert FirmwareVersion(1, 2, 3, 4) < FirmwareVersion(1, 2, 3, 5)


def test_supports_unknown_model() -> None:
    caps = get_capabilities(SpeakerModel.UNKNOWN, FirmwareVersion(0, 0, 1))
    assert all(caps.supports(f) for f in Feature)
    assert get_capabilities(SpeakerModel.from_model_name("Future"), None).supports(Feature.KW2)


def test_supports_absent_feature() -> None:
    caps = get_capabilities(SpeakerModel.LS50_WIRELESS_II, None)
    assert not caps.supports(Feature.USB_CHARGING)
    assert caps.supports(Feature.SECURED_API)  # firmware unknown but feature exists


def test_secured_api_ls50wii() -> None:
    old = get_capabilities(SpeakerModel.LS50_WIRELESS_II, FirmwareVersion(3, 9))
    new = get_capabilities(SpeakerModel.LS50_WIRELESS_II, FirmwareVersion(4, 0, 0))
    assert not old.supports(Feature.SECURED_API)
    assert new.supports(Feature.SECURED_API)


def test_luxe_any() -> None:
    caps = get_capabilities(SpeakerModel.LS_LUXE, FirmwareVersion(0, 0, 1))
    assert caps.supports(Feature.SECURED_API)
    assert not caps.supports(Feature.HUAWEI_HIPLAY)
    assert not caps.supports(Feature.USB_CHARGING)


def test_sources() -> None:
    assert model_info(SpeakerModel.LS50_WIRELESS_II).sources == (
        Source.WIFI,
        Source.BLUETOOTH,
        Source.TV,
        Source.OPTICAL,
        Source.COAXIAL,
        Source.ANALOG,
    )
    assert Source.USB in model_info(SpeakerModel.LSX_II).sources
    assert Source.ANALOG not in model_info(SpeakerModel.LSX_II_LT).sources
    assert model_info(SpeakerModel.XIO).sources == (
        Source.WIFI,
        Source.BLUETOOTH,
        Source.TV,
        Source.OPTICAL,
    )
    assert len(model_info(SpeakerModel.UNKNOWN).sources) == 7
    assert Source.STANDBY not in model_info(SpeakerModel.UNKNOWN).sources
    assert get_capabilities(SpeakerModel.XIO, None).sources == model_info(SpeakerModel.XIO).sources


def test_models_table() -> None:
    assert len(MODELS) == 6
    assert MODELS[SpeakerModel.LS50_WIRELESS_II].eq_v2_from == FirmwareVersion(2, 5, 74)
    assert MODELS[SpeakerModel.XIO].eq_v2_from is None
    assert MODELS[SpeakerModel.XIO].product_code == "SP4083"
    assert not model_info(SpeakerModel.UNKNOWN).feature_min_firmware
