"""Tests for Kestrel 5000-family parsing/encoding."""

import pytest

from custom_components.kestrel.kestrel_link import k5
from custom_components.kestrel.kestrel_link.const import MeasurementKind as MK  # noqa: N817
from custom_components.kestrel.kestrel_link.types import KestrelSettings
from custom_components.kestrel.kestrel_link.uuids import (
    K5_DERIVED1_SHORT,
    K5_DERIVED2_SHORT,
    K5_DERIVED3_SHORT,
    K5_DERIVED4_SHORT,
    K5_SENSOR_SHORT,
)

ALL_STATUS1 = (0xFFFFFFFF).to_bytes(8, "little")
ALL_STATUS2 = (0x0F).to_bytes(8, "little")


def test_status_bitmaps() -> None:
    present = k5.parse_k5_status(
        (0b1010).to_bytes(8, "little"), (0b11).to_bytes(8, "little")
    )
    assert present == {MK.TEMPERATURE, MK.RELATIVE_HUMIDITY, MK.THI_YOUSEF, MK.THI_NRC}
    assert k5.parse_k5_status(None, None) == set()
    full = k5.parse_k5_status(ALL_STATUS1, ALL_STATUS2)
    assert len(full) == 36
    assert MK.AHLU_3 in full and MK.HUMIDEX in full


def test_layouts_fit_in_twenty_bytes_without_overlap() -> None:
    for fields in k5.K5_LAYOUTS.values():
        end = 0
        for f in fields:
            assert f.offset >= end
            end = f.end
        assert end <= 20


def _u(v: int, n: int) -> bytes:
    return v.to_bytes(n, "little")


def _s(v: int, n: int) -> bytes:
    return v.to_bytes(n, "little", signed=True)


def test_sensor_characteristic() -> None:
    raw = (
        _u(3500, 2)
        + _s(2347, 2)
        + _s(-1000, 2)
        + _u(5512, 2)
        + _u(10132, 2)
        + _u(270, 2)
        + _u(0xFFFF, 2)
        + bytes(6)
    )
    present = k5.parse_k5_status(ALL_STATUS1, ALL_STATUS2)
    out = k5.parse_k5_characteristic(K5_SENSOR_SHORT, raw, present)
    assert out[MK.WIND_SPEED].value == 3.5
    assert out[MK.TEMPERATURE].value == 23.47
    assert out[MK.GLOBE_TEMPERATURE].value == -10.0
    assert out[MK.RELATIVE_HUMIDITY].value == 55.12
    assert out[MK.STATION_PRESSURE].value == 1013.2
    assert out[MK.MAGNETIC_DIRECTION].value == 270.0
    assert out[MK.AIR_SPEED].value is None  # bad value
    assert out[MK.AIR_SPEED].valid is False


def test_derived1_with_int24_values() -> None:
    raw = (
        _u(90, 2)
        + _u(1225, 2)
        + _s(-123, 3)
        + _u(10201, 2)
        + _u(1500, 2)
        + _s(-2500, 3)
        + _s(0x800001 - (1 << 24), 3)
        + _u(1013, 2)
        + bytes(1)
    )
    present = k5.parse_k5_status(ALL_STATUS1, ALL_STATUS2)
    out = k5.parse_k5_characteristic(K5_DERIVED1_SHORT, raw, present)
    assert out[MK.TRUE_DIRECTION].value == 90
    assert out[MK.AIR_DENSITY].value == 1.225
    assert out[MK.ALTITUDE].value == -12.3
    assert out[MK.BAROMETRIC_PRESSURE].value == 1020.1
    assert out[MK.CROSSWIND].value == 1.5
    assert out[MK.HEADWIND].value == -2.5
    assert out[MK.DENSITY_ALTITUDE].value is None  # 0x800001 sentinel
    assert out[MK.RELATIVE_AIR_DENSITY].value == 101.3


def test_derived2_and_3_and_4() -> None:
    present = k5.parse_k5_status(ALL_STATUS1, ALL_STATUS2)
    raw2 = (
        _s(1200, 2)
        + _s(2775, 3)
        + _u(150, 2)
        + _u(0xFFFFFF, 3)
        + _u(2500, 2)
        + _s(2100, 2)
        + _s(1900, 2)
        + _s(1800, 2)
        + _s(-1500, 2)
    )
    out = k5.parse_k5_characteristic(K5_DERIVED2_SHORT, raw2, present)
    assert out[MK.DEW_POINT].value == 12.0
    assert out[MK.HEAT_INDEX].value == 27.75
    assert out[MK.EVAPORATION_RATE].value == 1.5
    assert out[MK.MOISTURE_CONTENT].value is None
    assert out[MK.THERMAL_WORK_LIMIT].value == 250.0
    assert out[MK.WET_BULB_GLOBE_TEMPERATURE].value == 21.0
    assert out[MK.NATURALLY_ASPIRATED_WET_BULB].value == 19.0
    assert out[MK.WET_BULB_TEMPERATURE].value == 18.0
    assert out[MK.WIND_CHILL].value == -15.0

    raw3 = (
        _u(1234, 3)
        + _s(325, 2)
        + _u(789, 3)
        + _u(123, 2)
        + _s(7000, 2)
        + _u(4000, 2)
        + _u(10, 2)
        + _u(20, 2)
        + _u(0xFFFF, 2)
    )
    out = k5.parse_k5_characteristic(K5_DERIVED3_SHORT, raw3, present)
    assert out[MK.AIR_FLOW].value == 1.234
    assert out[MK.DELTA_T].value == 3.25
    assert out[MK.HUMIDITY_RATIO].value == 7.89
    assert out[MK.VAPOR_PRESSURE_DEFICIT].value == 12.3
    assert out[MK.HEAT_LOAD_INDEX].value == 70.0
    assert out[MK.PROBABILITY_OF_IGNITION].value == 40.0
    assert out[MK.AHLU_1].value == 10 and out[MK.AHLU_2].value == 20
    assert out[MK.AHLU_3].value is None

    raw4 = _s(7250, 2) + _s(6800, 2) + _u(0xFFFF, 2) + bytes(14)
    out = k5.parse_k5_characteristic(K5_DERIVED4_SHORT, raw4, present)
    assert out[MK.THI_YOUSEF].value == 72.5
    assert out[MK.THI_NRC].value == 68.0
    assert out[MK.HUMIDEX].value is None


def test_not_present_measurements_have_no_value() -> None:
    raw = _u(3500, 2) + _s(2347, 2) + bytes(16)
    out = k5.parse_k5_characteristic(K5_SENSOR_SHORT, raw, {MK.TEMPERATURE})
    assert out[MK.WIND_SPEED].present is False
    assert out[MK.WIND_SPEED].value is None
    assert out[MK.TEMPERATURE].value == 23.47
    out = k5.parse_k5_characteristic(K5_SENSOR_SHORT, None, {MK.TEMPERATURE})
    assert out[MK.TEMPERATURE].value is None and out[MK.TEMPERATURE].present


def test_kestrel_settings_round_trip() -> None:
    s = KestrelSettings(
        log_interval_s=60,
        wrap_log=False,
        transmission_rate_s=10,
        security_level=1,
        setup_complete=True,
        reference_altitude_m=250,
        auto_shutdown_min=30,
    )
    raw = k5.encode_kestrel_settings(s)
    assert len(raw) == 20
    assert raw[7:9] == (2500).to_bytes(2, "little", signed=True)  # 0.1 m units
    assert raw[9] == 30
    assert k5.parse_kestrel_settings(raw) == s
    empty = k5.encode_kestrel_settings(KestrelSettings())
    assert empty[:10] == b"\xff\xff\xff\xff\xff\xff\xff\x01\x80\xff"
    assert k5.parse_kestrel_settings(empty).is_empty()
    with pytest.raises(ValueError):
        k5.encode_kestrel_settings(KestrelSettings(reference_altitude_m=5000))
    with pytest.raises(ValueError):
        k5.encode_kestrel_settings(KestrelSettings(auto_shutdown_min=255))
    with pytest.raises(ValueError):
        k5.parse_kestrel_settings(b"\x00" * 9)


def test_kestrel_command_encoding() -> None:
    assert k5.encode_kestrel_command() == bytes(20)
    assert k5.encode_kestrel_command(visual_identify=True)[3] == 1
    assert k5.encode_kestrel_command(store_log_point=True)[5] == 1
    assert k5.encode_kestrel_command(sync_ble_data=True)[4] == 1
    assert (
        k5.encode_kestrel_command(erase_log=True, restore_defaults=True)[:3]
        == b"\x01\x00\x01"
    )


def test_events() -> None:
    assert k5.parse_k5_events(b"\x7e\x00\xff\xff\x00\x00") == [126]
    assert k5.parse_k5_events(None) == []
