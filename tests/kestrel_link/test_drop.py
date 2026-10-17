"""Tests for DROP characteristic parsing/encoding."""

from datetime import datetime

import pytest

from custom_components.kestrel.kestrel_link import drop
from custom_components.kestrel.kestrel_link.const import MeasurementKind, NativeUnit
from custom_components.kestrel.kestrel_link.types import DropSettings


def test_doc_example_dry_bulb() -> None:
    m = drop.parse_drop_measurement_by_short(0x0001, b"\x07\x2b\x09")
    assert m.kind is MeasurementKind.TEMPERATURE
    assert m.value == 23.47
    assert m.unit is NativeUnit.CELSIUS
    assert m.present and m.enabled and m.valid
    assert m.raw == b"\x07\x2b\x09"


def test_negative_temperature() -> None:
    raw = b"\x07" + (-1250).to_bytes(2, "little", signed=True)
    assert drop.parse_drop_measurement_by_short(0x0001, raw).value == -12.5


@pytest.mark.parametrize(
    ("short", "value_bytes", "expected", "unit"),
    [
        (0x0002, (4000).to_bytes(2, "little"), 40.0, NativeUnit.PERCENT),
        (0x0003, (2775).to_bytes(3, "little", signed=True), 27.75, NativeUnit.CELSIUS),
        (0x0003, (-50).to_bytes(3, "little", signed=True), -0.5, NativeUnit.CELSIUS),
        (0x0004, (2000).to_bytes(2, "little", signed=True), 20.0, NativeUnit.CELSIUS),
        (0x0005, (1850).to_bytes(2, "little", signed=True), 18.5, NativeUnit.CELSIUS),
        (0x0006, (325).to_bytes(2, "little", signed=True), 3.25, NativeUnit.CELSIUS),
        (0x0007, (10132).to_bytes(2, "little"), 1013.2, NativeUnit.HPA),
        (0x0008, (10201).to_bytes(2, "little"), 1020.1, NativeUnit.HPA),
        (0x0009, (12).to_bytes(2, "little"), 0.0012, NativeUnit.HPA),
        (
            0x000A,
            (-12345).to_bytes(3, "little", signed=True),
            -1234.5,
            NativeUnit.METERS,
        ),
        (0x000B, (123456).to_bytes(3, "little"), 1234.56, NativeUnit.GRAMS_PER_KG),
        (0x000C, (789).to_bytes(3, "little"), 7.89, NativeUnit.GRAMS_PER_KG),
        (0x000D, (9876).to_bytes(2, "little"), 98.76, NativeUnit.PERCENT),
        (0x000E, (7250).to_bytes(2, "little", signed=True), 72.5, NativeUnit.UNITLESS),
        (0x000F, (-100).to_bytes(2, "little", signed=True), -1.0, NativeUnit.UNITLESS),
    ],
)
def test_each_characteristic(
    short: int, value_bytes: bytes, expected: float, unit: NativeUnit
) -> None:
    m = drop.parse_drop_measurement_by_short(short, b"\x07" + value_bytes)
    assert m.value == pytest.approx(expected)
    assert m.unit is unit
    assert m.kind is drop.DROP_MEASUREMENT_CHARS[short].kind


def test_all_fifteen_characteristics_mapped() -> None:
    assert set(drop.DROP_MEASUREMENT_CHARS) == set(range(1, 16))
    assert drop.DROP_KIND_TO_SHORT[MeasurementKind.DEW_POINT] == 0x0004


@pytest.mark.parametrize(
    ("status", "present", "enabled", "valid", "has_value"),
    [
        (0x07, True, True, True, True),
        (0x03, True, True, False, False),  # invalid -> value None
        (0x05, True, False, True, True),  # disabled but valid
        (0x01, True, False, False, False),
        (0x00, False, False, False, False),
        (0x06, False, True, True, False),  # not present -> never a value
    ],
)
def test_status_bits(
    status: int, present: bool, enabled: bool, valid: bool, has_value: bool
) -> None:
    m = drop.parse_drop_measurement_by_short(0x0001, bytes([status, 0x2B, 0x09]))
    assert m.present is present
    assert m.enabled is enabled
    assert m.valid is valid
    assert (m.value is not None) is has_value


def test_short_or_empty_payload() -> None:
    for raw in (b"", b"\x07", None, bytearray()):
        m = drop.parse_drop_measurement_by_short(0x0002, raw)
        assert m.present is False
        assert m.value is None


def test_settings_round_trip() -> None:
    s = DropSettings(
        log_interval_s=600,
        wrap_log=True,
        transmission_rate_s=5,
        security_level=0,
        setup_complete=True,
        reference_altitude_m=-120,
    )
    raw = drop.encode_drop_settings(s)
    assert len(raw) == 20
    assert raw[0:3] == (600).to_bytes(3, "little")
    assert raw[3] == 1
    assert raw[4] == 5
    assert raw[7:9] == (-120).to_bytes(2, "little", signed=True)
    assert raw[9:] == b"\xff" * 11
    assert drop.parse_drop_settings(raw) == s


def test_settings_sentinels() -> None:
    raw = b"\xff\xff\xff" + b"\xff" * 4 + b"\x01\x80" + b"\x00" * 11
    s = drop.parse_drop_settings(raw)
    assert s.is_empty()
    assert drop.encode_drop_settings(DropSettings())[:9] == raw[:9]


def test_settings_partial_write_only_sets_given_fields() -> None:
    raw = drop.encode_drop_settings(DropSettings(wrap_log=False))
    assert raw[0:3] == b"\xff\xff\xff"
    assert raw[3] == 0
    assert raw[4] == 0xFF
    assert raw[7:9] == b"\x01\x80"


def test_settings_disable_logging() -> None:
    raw = drop.encode_drop_settings(DropSettings(log_interval_s=0))
    assert raw[0:3] == b"\x00\x00\x00"
    assert drop.parse_drop_settings(raw).log_interval_s == 0


@pytest.mark.parametrize(
    "settings",
    [
        DropSettings(log_interval_s=1),
        DropSettings(log_interval_s=86401),
        DropSettings(transmission_rate_s=1),
        DropSettings(transmission_rate_s=61),
        DropSettings(security_level=3),
        DropSettings(reference_altitude_m=40000),
        DropSettings(reference_altitude_m=-32767),
    ],
)
def test_settings_validation(settings: DropSettings) -> None:
    with pytest.raises(ValueError):
        drop.encode_drop_settings(settings)


def test_settings_too_short() -> None:
    with pytest.raises(ValueError):
        drop.parse_drop_settings(b"\x00" * 5)


def test_command_encoding() -> None:
    assert drop.encode_drop_command() == bytes(20)
    assert drop.encode_drop_command(blink_led=True) == b"\x00\x01" + bytes(18)
    assert drop.encode_drop_command(erase_log=True)[0] == 1
    assert drop.encode_drop_command(restore_defaults=True)[2] == 1


def test_button_and_ascii() -> None:
    assert drop.parse_drop_button(b"\x01") == 1
    assert drop.parse_drop_button(b"") is None
    assert drop.parse_ascii(b"D3 - 1234\x00\x00\x00") == "D3 - 1234"
    assert drop.parse_ascii(b"\x00" * 20) is None
    assert drop.parse_ascii(b"abc" + b"\xff" * 5) == "abc"
    assert drop.parse_ascii(None) is None
    assert drop.encode_name("Garden") == b"Garden" + b"\x00" * 14
    assert len(drop.encode_name("x" * 40)) == 20


def test_sig_datetime_round_trip() -> None:
    when = datetime(2013, 1, 1, 0, 0, 1)
    raw = drop.encode_sig_datetime(when)
    assert raw == b"\x01\x00\x00\x01\x01\xdd\x07"
    assert drop.decode_sig_datetime(raw) == when
    assert drop.encode_sig_datetime(when, drop_layout=False) == (
        b"\xdd\x07\x01\x01\x00\x00\x01"
    )
    assert drop.decode_sig_datetime(b"\x00" * 7) is None
    assert drop.decode_sig_datetime(b"\xdd\x07\x13\x01\x00\x00\x00") is None
    # SIG order is still accepted.
    assert (
        drop.decode_sig_datetime(drop.encode_sig_datetime(when, drop_layout=False))
        == when
    )


def test_sig_datetime_real_drop_layout() -> None:
    """Capture from a DROP D3 (BLE profile 1.25): sec, min, hour, day, month, year BE."""
    raw = bytes.fromhex("351f0e0c0aea07")
    assert drop.decode_sig_datetime(raw) == datetime(2026, 10, 12, 14, 31, 53)
    assert drop.encode_sig_datetime(datetime(2026, 10, 12, 14, 31, 53)) == raw


def test_density_altitude_uses_tenths_of_metre() -> None:
    """Capture from a DROP D3 at a 856 hPa site: raw 0x4b4b -> 1927.5 m."""
    m = drop.parse_drop_measurement_by_short(0x000A, bytes.fromhex("074b4b00"))
    assert m.value == 1927.5
    assert m.present and m.valid
    assert drop.decode_sig_datetime(b"\x01") is None
