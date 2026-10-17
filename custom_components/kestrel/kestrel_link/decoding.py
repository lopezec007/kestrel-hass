"""Decoding of LiNK metadata-described data records.

Metadata packets describe each field of a data record by name code, unit
code and size.  The unit code determines the wire encoding (signedness and
scaling); the size determines the integer width.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import struct
from typing import Any, Literal

from .const import BYTE_ORDER, FieldName, FieldUnit
from .types import FieldDescriptor, LinkRecord, MetadataPacket, ProtocolError

EncodingKind = Literal["int", "float", "str", "datetime", "float32", "float64"]

BT_DATETIME_SIZE = 7
_PLAUSIBLE_YEARS = range(1990, 2151)


@dataclass(frozen=True, slots=True)
class UnitEncoding:
    """How a field unit code is encoded on the wire."""

    signed: bool
    scale: float | None  # multiply the raw integer by this; None for unscaled
    kind: EncodingKind = "int"


_U = UnitEncoding(signed=False, scale=None)
_S = UnitEncoding(signed=True, scale=None)


def _scaled(signed: bool, divisor: float) -> UnitEncoding:
    return UnitEncoding(signed=signed, scale=1.0 / divisor, kind="float")


UNIT_ENCODINGS: dict[int, UnitEncoding] = {
    FieldUnit.UINT8: _U,
    FieldUnit.INT8: _S,
    FieldUnit.UINT16: _U,
    FieldUnit.INT16: _S,
    FieldUnit.UINT32: _U,
    FieldUnit.INT32: _S,
    FieldUnit.UINT64: _U,
    FieldUnit.INT64: _S,
    FieldUnit.FLOAT32: UnitEncoding(signed=True, scale=None, kind="float32"),
    FieldUnit.FLOAT64: UnitEncoding(signed=True, scale=None, kind="float64"),
    FieldUnit.ASCII_STRING: UnitEncoding(signed=False, scale=None, kind="str"),
    FieldUnit.SECONDS: _U,
    FieldUnit.GPS_TIME: _U,
    FieldUnit.PERCENT_X100_U16: _scaled(False, 100),
    FieldUnit.DEGREES_C_X100_I16: _scaled(True, 100),
    FieldUnit.MILLIBAR_X10_U16: _scaled(False, 10),
    FieldUnit.BLUETOOTH_DATE_TIME: UnitEncoding(
        signed=False, scale=None, kind="datetime"
    ),
    FieldUnit.METERS_X100_I24: _scaled(True, 100),
    FieldUnit.GRAMS_PER_KG_X100_U24: _scaled(False, 100),
    FieldUnit.KG_PER_M3_X1000_U16: _scaled(False, 1000),
    FieldUnit.NEWTONS_X10_I16: _scaled(True, 10),
    FieldUnit.ARC_DEGREES_X100_I16: _scaled(True, 100),
    FieldUnit.ARC_DEGREES_PER_SEC_X100_I16: _scaled(True, 100),
    FieldUnit.MILLISECONDS_U16: _U,
    FieldUnit.M3_PER_S_X1000_U24: _scaled(False, 1000),
    FieldUnit.JOULES_X10_U16: _scaled(False, 10),
    FieldUnit.ARC_DEGREES_I8: _S,
    FieldUnit.ARC_DEGREES_U8: _U,
    FieldUnit.WATTS_X10_U16: _scaled(False, 10),
    FieldUnit.KG_PER_M2_PER_H_X100_U16: _scaled(False, 100),
    FieldUnit.M_PER_S_X1000_U16: _scaled(False, 1000),
    FieldUnit.PERCENT_X10_U16: _scaled(False, 10),
    FieldUnit.DEGREES_DIRECTION: _U,
    FieldUnit.METERS_X10_I24: _scaled(True, 10),
    FieldUnit.W_PER_M2_X10_U16: _scaled(False, 10),
    FieldUnit.DEGREES_C_X100_I24: _scaled(True, 100),
    FieldUnit.M_PER_S_X1000_I24: _scaled(True, 1000),
    FieldUnit.DIFF_DEGREES_C_X100_I16: _scaled(True, 100),
    FieldUnit.CENTIMETERS_X10_U16: _scaled(False, 10),
    FieldUnit.METERS_X100_U24: _scaled(False, 100),
    FieldUnit.DEGREES_X1000_I24: _scaled(True, 1000),
    FieldUnit.UNITLESS_X100_I16: _scaled(True, 100),
    FieldUnit.MILLIBAR_X100_U24: _scaled(False, 100),
    FieldUnit.VOLTS_X1000_U16: _scaled(False, 1000),
    FieldUnit.MILLIAMPS_I16: _S,
    FieldUnit.UINT24: _U,
    FieldUnit.METERS_I16: _S,
    FieldUnit.MILLIMETERS_X10_U16: _scaled(False, 10),
    FieldUnit.DEGREES_C_X10_I16: _scaled(True, 10),
    FieldUnit.DEGREES_F_X10_I16: _scaled(True, 10),
}


def decode_int(raw: bytes, *, signed: bool) -> int:
    """Decode a little-endian integer of any width."""
    return int.from_bytes(raw, BYTE_ORDER, signed=signed)


def is_bad_value(raw_int: int, size: int, *, signed: bool) -> bool:
    """Return True if ``raw_int`` is the bad-value sentinel for its width.

    Unsigned sentinels are all ones (``0xFFFF``); signed sentinels are the
    most negative value plus one (``0x8001``, ``0x800001``), compared on the
    unsigned bit pattern.
    """
    if size <= 0:
        return False
    bits = 8 * size
    pattern = raw_int & ((1 << bits) - 1)
    if signed:
        return pattern == (1 << (bits - 1)) + 1
    return pattern == (1 << bits) - 1


def _plausible_datetime(
    year: int, month: int, day: int, hms: tuple[int, int, int]
) -> datetime | None:
    if year not in _PLAUSIBLE_YEARS:
        return None
    try:
        return datetime(year, month, day, *hms)
    except ValueError:
        return None


def decode_bt_datetime(raw: bytes) -> datetime | None:
    """Decode a 7-byte Bluetooth SIG Date Time value.

    Three layouts are recognised, in this order:

    1. SIG order with a little-endian year (the specification).
    2. The order real Kestrel DROP units use for their clock and log
       timestamps: second, minute, hour, day, month, year (little-endian).
    3. SIG order with a big-endian year, matching NK's worked example.

    Returns None for an all-zero or otherwise invalid value.
    """
    if len(raw) < BT_DATETIME_SIZE:
        return None
    data = bytes(raw[:BT_DATETIME_SIZE])
    sig_year_le = data[0] | (data[1] << 8)
    if (
        when := _plausible_datetime(sig_year_le, data[2], data[3], tuple(data[4:7]))  # type: ignore[arg-type]
    ) is not None:
        return when
    drop_year = data[5] | (data[6] << 8)
    if (
        when := _plausible_datetime(
            drop_year, data[4], data[3], (data[2], data[1], data[0])
        )
    ) is not None:
        return when
    sig_year_be = (data[0] << 8) | data[1]
    return _plausible_datetime(sig_year_be, data[2], data[3], tuple(data[4:7]))  # type: ignore[arg-type]


def encode_bt_datetime(dt: datetime, *, drop_layout: bool = False) -> bytes:
    """Encode a datetime as a 7-byte Date Time value.

    The SIG layout is year (LE), month, day, hour, minute, second.  Kestrel
    DROP firmware uses the reverse field order with the year still
    little-endian; pass ``drop_layout=True`` for it.
    """
    if drop_layout:
        return struct.pack(
            "<BBBBBH", dt.second, dt.minute, dt.hour, dt.day, dt.month, dt.year
        )
    return struct.pack(
        "<HBBBBB", dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second
    )


def decode_field(desc: FieldDescriptor, raw: bytes) -> Any:
    """Decode one field value according to its descriptor.

    Returns a ``str`` for ASCII fields, a ``datetime`` (or None) for Bluetooth
    Date Time, a ``float`` for scaled units, an ``int`` for raw integers, and
    None when the raw integer equals its bad-value sentinel.
    """
    encoding = UNIT_ENCODINGS.get(desc.unit, _U)
    if encoding.kind == "str":
        return bytes(raw).split(b"\x00", 1)[0].decode("ascii", errors="replace")
    if encoding.kind == "datetime":
        return decode_bt_datetime(raw)
    if encoding.kind == "float32" and len(raw) == 4:
        return struct.unpack("<f", raw)[0]
    if encoding.kind == "float64" and len(raw) == 8:
        return struct.unpack("<d", raw)[0]
    if not raw:
        return None
    value = decode_int(raw, signed=encoding.signed)
    if is_bad_value(value, len(raw), signed=encoding.signed):
        return None
    if encoding.scale is not None:
        return value * encoding.scale
    return value


class RecordLayout:
    """Layout of a data record as described by metadata descriptors."""

    def __init__(
        self, fields: tuple[FieldDescriptor, ...] | list[FieldDescriptor]
    ) -> None:
        self.fields: tuple[FieldDescriptor, ...] = tuple(fields)
        self.record_size: int = sum(f.size for f in self.fields)

    def __len__(self) -> int:
        return len(self.fields)

    def decode_record(self, raw: bytes) -> LinkRecord:
        """Decode exactly one record."""
        if len(raw) < self.record_size:
            raise ProtocolError("Record shorter than layout")
        values: dict[int, Any] = {}
        timestamp: datetime | None = None
        offset = 0
        for desc in self.fields:
            value = decode_field(desc, raw[offset : offset + desc.size])
            offset += desc.size
            if desc.name == FieldName.TIMESTAMP and isinstance(value, datetime):
                timestamp = value
            values[desc.name] = value
        return LinkRecord(timestamp=timestamp, values=values)

    def decode_records(
        self, payload: bytes, *, numbered: bool
    ) -> tuple[int | None, list[LinkRecord]]:
        """Decode a data packet payload into records.

        Args:
            payload: The data packet's data section.
            numbered: True if the payload starts with a u16 packet number
                (data log transfers), False otherwise (snapshots).

        Returns:
            ``(packet_number, records)``; trailing partial bytes are ignored.
        """
        number: int | None = None
        body = payload
        if numbered:
            if len(payload) < 2:
                raise ProtocolError("Numbered data packet lacks a packet number")
            number = payload[0] | (payload[1] << 8)
            body = payload[2:]
        records: list[LinkRecord] = []
        if self.record_size == 0:
            return number, records
        for offset in range(0, len(body) - self.record_size + 1, self.record_size):
            records.append(self.decode_record(body[offset : offset + self.record_size]))
        return number, records


class MetadataAccumulator:
    """Accumulate metadata packets into a record layout.

    A Metadata Start packet replaces everything received before; plain
    Metadata packets append their fields.
    """

    def __init__(self) -> None:
        self._fields: list[FieldDescriptor] = []
        self._started = False

    def add(self, packet: MetadataPacket) -> None:
        """Incorporate a metadata packet."""
        if packet.start:
            self._fields = list(packet.fields)
            self._started = True
        else:
            self._fields.extend(packet.fields)

    @property
    def has_metadata(self) -> bool:
        """Return True once at least one descriptor has been received."""
        return bool(self._fields)

    def layout(self) -> RecordLayout:
        """Return the layout described so far."""
        return RecordLayout(tuple(self._fields))
