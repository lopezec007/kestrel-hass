"""Tests for LiNK record decoding."""

from __future__ import annotations

from datetime import datetime

import pytest

from custom_components.kestrel.kestrel_link.const import (
    FieldName,
    FieldUnit,
    MeasurementKind,
)
from custom_components.kestrel.kestrel_link.decoding import (
    UNIT_ENCODINGS,
    MetadataAccumulator,
    RecordLayout,
    decode_bt_datetime,
    decode_field,
    decode_int,
    encode_bt_datetime,
    is_bad_value,
)
from custom_components.kestrel.kestrel_link.packets import decode_packet
from custom_components.kestrel.kestrel_link.types import (
    DataPacket,
    FieldDescriptor,
    MetadataPacket,
    ProtocolError,
)

DOC_FIELDS = (
    FieldDescriptor(FieldName.TIMESTAMP, FieldUnit.BLUETOOTH_DATE_TIME, 7),
    FieldDescriptor(FieldName.DRY_BULB_TEMP, FieldUnit.DEGREES_C_X100_I16, 2),
    FieldDescriptor(FieldName.RELATIVE_HUMIDITY, FieldUnit.PERCENT_X100_U16, 2),
    FieldDescriptor(FieldName.HEAT_INDEX, FieldUnit.DEGREES_C_X100_I16, 2),
    FieldDescriptor(FieldName.DEW_POINT, FieldUnit.DEGREES_C_X100_I16, 2),
)
DOC_RECORD = bytes.fromhex("07DD01010000019209A00FD70AD007")
DOC_SNAPSHOT_PACKET = bytes.fromhex("03000F00") + DOC_RECORD
DOC_LOG_PACKET = bytes.fromhex("03007A00") + b"\x00\x00" + DOC_RECORD * 8


def test_decode_int() -> None:
    assert decode_int(b"\x92\x09", signed=True) == 2450
    assert decode_int(b"\xff\xff", signed=True) == -1
    assert decode_int(b"\xff\xff", signed=False) == 0xFFFF
    assert decode_int(b"\x01\x00\x80", signed=True) == -0x7FFFFF


@pytest.mark.parametrize(
    ("raw_int", "size", "signed", "expected"),
    [
        (0xFFFF, 2, False, True),
        (0xFFFE, 2, False, False),
        (0x8001, 2, True, True),
        (-0x7FFF, 2, True, True),
        (0x8000, 2, True, False),
        (0x800001, 3, True, True),
        (0xFFFFFF, 3, False, True),
        (0xFFFFFF, 3, True, False),
        (0xFF, 1, False, True),
        (0x81, 1, True, True),
        (0, 0, False, False),
    ],
)
def test_is_bad_value(raw_int: int, size: int, signed: bool, expected: bool) -> None:
    assert is_bad_value(raw_int, size, signed=signed) is expected


def test_bt_datetime_little_endian() -> None:
    raw = encode_bt_datetime(datetime(2026, 10, 17, 14, 33, 10))
    assert raw == bytes.fromhex("EA070A110E210A")
    assert decode_bt_datetime(raw) == datetime(2026, 10, 17, 14, 33, 10)


def test_bt_datetime_big_endian_fallback() -> None:
    assert decode_bt_datetime(bytes.fromhex("07DD0101000001")) == datetime(
        2013, 1, 1, 0, 0, 1
    )


def test_bt_datetime_invalid() -> None:
    assert decode_bt_datetime(b"\x00" * 7) is None
    assert decode_bt_datetime(bytes.fromhex("EA070D01000000")) is None  # month 13
    assert decode_bt_datetime(b"\x01\x02") is None


def test_unit_encodings_cover_wire_codes() -> None:
    expected = {
        0,
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        25,
        26,
        27,
        28,
        31,
        36,
        37,
        38,
        39,
        40,
        41,
        42,
        43,
        44,
        45,
        46,
        47,
        48,
        53,
        56,
        57,
        59,
        60,
        61,
        62,
        63,
        64,
        65,
        66,
        68,
        69,
        83,
        84,
        85,
        93,
        94,
        126,
        129,
        130,
    }
    assert expected <= set(UNIT_ENCODINGS)
    assert FieldUnit.METERS_NP not in UNIT_ENCODINGS


@pytest.mark.parametrize(
    ("unit", "raw", "expected"),
    [
        (FieldUnit.DEGREES_C_X100_I16, b"\x92\x09", 24.5),
        (FieldUnit.DEGREES_C_X100_I16, b"\x6e\xf6", -24.5),
        (FieldUnit.PERCENT_X100_U16, b"\xa0\x0f", 40.0),
        (FieldUnit.MILLIBAR_X10_U16, b"\x94\x27", 1013.2),
        (FieldUnit.METERS_X100_I24, b"\x18\xfc\xff", -10.0),
        (FieldUnit.UINT16, b"\x34\x12", 0x1234),
        (FieldUnit.INT8, b"\xfe", -2),
        (FieldUnit.DEGREES_DIRECTION, b"\x68\x01", 360),
        (FieldUnit.METERS_NP, b"\x05\x00", 5),  # display-only code -> raw unsigned
        (FieldUnit.ASCII_STRING, b"ABC\x00\x00", "ABC"),
        (FieldUnit.FLOAT32, bytes.fromhex("0000C03F"), 1.5),
        (FieldUnit.FLOAT64, bytes.fromhex("000000000000F83F"), 1.5),
    ],
)
def test_decode_field_values(unit: FieldUnit, raw: bytes, expected) -> None:
    value = decode_field(FieldDescriptor(FieldName.NONE, unit, len(raw)), raw)
    assert (
        value == pytest.approx(expected)
        if isinstance(expected, float)
        else value == expected
    )


@pytest.mark.parametrize(
    ("unit", "raw"),
    [
        (FieldUnit.DEGREES_C_X100_I16, b"\x01\x80"),
        (FieldUnit.PERCENT_X100_U16, b"\xff\xff"),
        (FieldUnit.DEGREES_C_X100_I24, b"\x01\x00\x80"),
        (FieldUnit.GRAMS_PER_KG_X100_U24, b"\xff\xff\xff"),
        (FieldUnit.UINT8, b""),
    ],
)
def test_decode_field_bad_values(unit: FieldUnit, raw: bytes) -> None:
    assert decode_field(FieldDescriptor(FieldName.NONE, unit, len(raw)), raw) is None


def test_decode_field_datetime() -> None:
    desc = FieldDescriptor(FieldName.TIMESTAMP, FieldUnit.BLUETOOTH_DATE_TIME, 7)
    assert decode_field(desc, bytes.fromhex("EA070A110E210A")) == datetime(
        2026, 10, 17, 14, 33, 10
    )


def test_doc_snapshot_record() -> None:
    packet = decode_packet(DOC_SNAPSHOT_PACKET)
    assert isinstance(packet, DataPacket)
    layout = RecordLayout(DOC_FIELDS)
    assert layout.record_size == 15
    number, records = layout.decode_records(packet.payload, numbered=False)
    assert number is None
    assert len(records) == 1
    rec = records[0]
    assert rec.timestamp == datetime(2013, 1, 1, 0, 0, 1)
    assert rec.get(FieldName.DRY_BULB_TEMP) == pytest.approx(24.5)
    assert rec.get(FieldName.RELATIVE_HUMIDITY) == pytest.approx(40.0)
    assert rec.get(FieldName.HEAT_INDEX) == pytest.approx(27.75)
    assert rec.get(FieldName.DEW_POINT) == pytest.approx(20.0)
    assert rec.get(FieldName.TIMESTAMP) == rec.timestamp


def test_doc_log_packet_eight_records() -> None:
    packet = decode_packet(DOC_LOG_PACKET)
    layout = RecordLayout(DOC_FIELDS)
    number, records = layout.decode_records(packet.payload, numbered=True)
    assert number == 0
    assert len(records) == 8
    assert all(r.get(FieldName.DEW_POINT) == pytest.approx(20.0) for r in records)


def test_trailing_partial_bytes_ignored() -> None:
    layout = RecordLayout(DOC_FIELDS)
    _, records = layout.decode_records(DOC_RECORD * 2 + DOC_RECORD[:5], numbered=False)
    assert len(records) == 2


def test_numbered_requires_number() -> None:
    layout = RecordLayout(DOC_FIELDS)
    with pytest.raises(ProtocolError):
        layout.decode_records(b"\x01", numbered=True)


def test_decode_record_short_raises() -> None:
    with pytest.raises(ProtocolError):
        RecordLayout(DOC_FIELDS).decode_record(b"\x00")


def test_empty_layout() -> None:
    layout = RecordLayout(())
    assert layout.record_size == 0
    assert layout.decode_records(b"\x00\x00abc", numbered=True) == (0, [])


def test_record_measurements_mapping() -> None:
    layout = RecordLayout(DOC_FIELDS)
    _, records = layout.decode_records(DOC_RECORD, numbered=False)
    measurements = records[0].measurements()
    assert measurements == {
        MeasurementKind.TEMPERATURE: pytest.approx(24.5),
        MeasurementKind.RELATIVE_HUMIDITY: pytest.approx(40.0),
        MeasurementKind.HEAT_INDEX: pytest.approx(27.75),
        MeasurementKind.DEW_POINT: pytest.approx(20.0),
    }


def test_record_measurements_bad_value_is_none() -> None:
    bad = DOC_RECORD[:7] + b"\x01\x80" + DOC_RECORD[9:]
    _, records = RecordLayout(DOC_FIELDS).decode_records(bad, numbered=False)
    assert records[0].measurements()[MeasurementKind.TEMPERATURE] is None


def test_metadata_accumulator() -> None:
    acc = MetadataAccumulator()
    assert not acc.has_metadata
    acc.add(MetadataPacket(DOC_FIELDS[:2], start=True))
    acc.add(MetadataPacket(DOC_FIELDS[2:], start=False, packet_number=0))
    assert acc.has_metadata
    assert acc.layout().fields == DOC_FIELDS
    # A new start packet resets the accumulated layout.
    acc.add(MetadataPacket(DOC_FIELDS[:1], start=True))
    assert acc.layout().fields == DOC_FIELDS[:1]
    assert acc.layout().record_size == 7


def test_decode_bt_datetime_drop_layout() -> None:
    """Real DROP D3 clock bytes: second, minute, hour, day, month, year LE."""
    assert decode_bt_datetime(bytes.fromhex("351f0e0c0aea07")) == datetime(
        2026, 10, 12, 14, 31, 53
    )
    assert decode_bt_datetime(bytes.fromhex("30090a110aea07")) == datetime(
        2026, 10, 17, 10, 9, 48
    )


def test_encode_bt_datetime_drop_layout_round_trips() -> None:
    when = datetime(2026, 10, 17, 13, 5, 14)
    raw = encode_bt_datetime(when, drop_layout=True)
    assert raw == bytes.fromhex("0e050d110aea07")
    assert decode_bt_datetime(raw) == when
    assert decode_bt_datetime(encode_bt_datetime(when)) == when
