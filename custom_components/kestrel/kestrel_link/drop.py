"""Kestrel DROP GATT characteristic parsing and encoding."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from .const import MeasurementKind, NativeUnit
from .types import DropSettings, Measurement

STATUS_PRESENT = 0x01
STATUS_ENABLED = 0x02
STATUS_VALID = 0x04

SETTINGS_LENGTH = 20
COMMANDS_LENGTH = 20
NAME_LENGTH = 20
DATETIME_LENGTH = 7

# Ignore / unsupported sentinels of the settings characteristic.
IGNORE_U24 = 0xFFFFFF
IGNORE_U8 = 0xFF
IGNORE_I16_RAW = 0x8001  # -32767 when read as signed

LOG_INTERVAL_MIN_S = 2
LOG_INTERVAL_MAX_S = 86400
TRANSMISSION_RATE_MIN_S = 2
TRANSMISSION_RATE_MAX_S = 60

# Wire byte order (typed so int.from_bytes/to_bytes accept it).
LE: Final[Literal["little"]] = "little"


@dataclass(frozen=True, slots=True)
class DropMeasurementSpec:
    """How a DROP measurement characteristic encodes its value."""

    kind: MeasurementKind
    signed: bool
    exponent: int
    unit: NativeUnit


# Characteristic short id -> spec.  Value width is taken from the payload.
DROP_MEASUREMENT_CHARS: dict[int, DropMeasurementSpec] = {
    0x0001: DropMeasurementSpec(
        MeasurementKind.TEMPERATURE, True, -2, NativeUnit.CELSIUS
    ),
    0x0002: DropMeasurementSpec(
        MeasurementKind.RELATIVE_HUMIDITY, False, -2, NativeUnit.PERCENT
    ),
    0x0003: DropMeasurementSpec(
        MeasurementKind.HEAT_INDEX, True, -2, NativeUnit.CELSIUS
    ),
    0x0004: DropMeasurementSpec(
        MeasurementKind.DEW_POINT, True, -2, NativeUnit.CELSIUS
    ),
    0x0005: DropMeasurementSpec(
        MeasurementKind.WET_BULB_TEMPERATURE, True, -2, NativeUnit.CELSIUS
    ),
    0x0006: DropMeasurementSpec(MeasurementKind.DELTA_T, True, -2, NativeUnit.CELSIUS),
    0x0007: DropMeasurementSpec(
        MeasurementKind.STATION_PRESSURE, False, -1, NativeUnit.HPA
    ),
    0x0008: DropMeasurementSpec(
        MeasurementKind.BAROMETRIC_PRESSURE, False, -1, NativeUnit.HPA
    ),
    0x0009: DropMeasurementSpec(
        MeasurementKind.PRESSURE_TREND, False, -4, NativeUnit.HPA
    ),
    # NK's DROP table lists exponent -2, but real D3 units report tenths of a
    # metre (raw 19275 at a 856 hPa site is 1927.5 m), matching the K5 layout.
    0x000A: DropMeasurementSpec(
        MeasurementKind.DENSITY_ALTITUDE, True, -1, NativeUnit.METERS
    ),
    0x000B: DropMeasurementSpec(
        MeasurementKind.HUMIDITY_RATIO, False, -2, NativeUnit.GRAMS_PER_KG
    ),
    0x000C: DropMeasurementSpec(
        MeasurementKind.MOISTURE_CONTENT, False, -2, NativeUnit.GRAMS_PER_KG
    ),
    0x000D: DropMeasurementSpec(
        MeasurementKind.RELATIVE_AIR_DENSITY, False, -2, NativeUnit.PERCENT
    ),
    0x000E: DropMeasurementSpec(MeasurementKind.THI_NRC, True, -2, NativeUnit.UNITLESS),
    0x000F: DropMeasurementSpec(
        MeasurementKind.THI_YOUSEF, True, -2, NativeUnit.UNITLESS
    ),
}

# Kind -> short id, for callers that need the reverse mapping.
DROP_KIND_TO_SHORT: dict[MeasurementKind, int] = {
    spec.kind: short for short, spec in DROP_MEASUREMENT_CHARS.items()
}


def scale(raw_int: int, exponent: int) -> float:
    """Apply a decimal exponent to a raw integer."""
    if exponent >= 0:
        return float(raw_int * 10**exponent)
    return round(raw_int / 10 ** (-exponent), -exponent)


def parse_drop_measurement(
    spec: DropMeasurementSpec, raw: bytes | bytearray | None
) -> Measurement:
    """Parse a DROP measurement characteristic (status byte + LE integer)."""
    data = bytes(raw) if raw is not None else b""
    if len(data) < 2:
        return Measurement(
            kind=spec.kind,
            value=None,
            unit=spec.unit,
            present=False,
            enabled=False,
            valid=False,
            raw=data,
        )
    status = data[0]
    present = bool(status & STATUS_PRESENT)
    enabled = bool(status & STATUS_ENABLED)
    valid = bool(status & STATUS_VALID)
    value: float | None = None
    if present and valid:
        raw_int = int.from_bytes(data[1:], LE, signed=spec.signed)
        value = scale(raw_int, spec.exponent)
    return Measurement(
        kind=spec.kind,
        value=value,
        unit=spec.unit,
        present=present,
        enabled=enabled,
        valid=valid,
        raw=data,
    )


def parse_drop_measurement_by_short(
    short: int, raw: bytes | bytearray | None
) -> Measurement:
    """Parse a measurement given its characteristic short id."""
    return parse_drop_measurement(DROP_MEASUREMENT_CHARS[short], raw)


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #


def _u8_or_none(value: int) -> int | None:
    return None if value == IGNORE_U8 else value


def parse_drop_settings(raw: bytes | bytearray) -> DropSettings:
    """Decode the 20-byte DROP settings characteristic."""
    data = bytes(raw)
    if len(data) < 9:
        raise ValueError(f"settings payload too short: {len(data)} bytes")
    log_interval = int.from_bytes(data[0:3], LE)
    wrap = _u8_or_none(data[3])
    tx = _u8_or_none(data[4])
    security = _u8_or_none(data[5])
    setup = _u8_or_none(data[6])
    alt_raw = int.from_bytes(data[7:9], LE)
    return DropSettings(
        log_interval_s=None if log_interval == IGNORE_U24 else log_interval,
        wrap_log=None if wrap is None else bool(wrap),
        transmission_rate_s=tx,
        security_level=security,
        setup_complete=None if setup is None else bool(setup),
        reference_altitude_m=(
            None
            if alt_raw == IGNORE_I16_RAW
            else int.from_bytes(data[7:9], LE, signed=True)
        ),
    )


def validate_drop_settings(settings: DropSettings) -> None:
    """Raise ValueError if a setting is outside the device's accepted range."""
    li = settings.log_interval_s
    if (
        li is not None
        and li != 0
        and not LOG_INTERVAL_MIN_S <= li <= LOG_INTERVAL_MAX_S
    ):
        raise ValueError(
            f"log interval must be 0 or {LOG_INTERVAL_MIN_S}-{LOG_INTERVAL_MAX_S} s"
        )
    tx = settings.transmission_rate_s
    if tx is not None and not TRANSMISSION_RATE_MIN_S <= tx <= TRANSMISSION_RATE_MAX_S:
        raise ValueError(
            f"transmission rate must be {TRANSMISSION_RATE_MIN_S}-{TRANSMISSION_RATE_MAX_S} s"
        )
    sec = settings.security_level
    if sec is not None and not 0 <= sec <= 2:
        raise ValueError("security level must be 0, 1 or 2")
    alt = settings.reference_altitude_m
    if alt is not None and not -32768 <= alt <= 32767:
        raise ValueError("reference altitude must fit in a signed 16-bit integer")
    if alt is not None and alt == -32767:
        # Would collide with the ignore sentinel.
        raise ValueError("reference altitude -32767 m is reserved")


def encode_drop_settings(settings: DropSettings) -> bytes:
    """Encode settings to the 20-byte characteristic value.

    Fields left as ``None`` are written with their "ignore" sentinel so the
    device keeps its current value.  Unused trailing bytes are written as 0xFF
    (the documented ignore value for every single-byte setting), which keeps
    the write harmless if a future firmware assigns meaning to them.
    """
    validate_drop_settings(settings)
    buf = bytearray([IGNORE_U8] * SETTINGS_LENGTH)
    li = IGNORE_U24 if settings.log_interval_s is None else settings.log_interval_s
    buf[0:3] = li.to_bytes(3, LE)
    if settings.wrap_log is not None:
        buf[3] = 1 if settings.wrap_log else 0
    if settings.transmission_rate_s is not None:
        buf[4] = settings.transmission_rate_s
    if settings.security_level is not None:
        buf[5] = settings.security_level
    if settings.setup_complete is not None:
        buf[6] = 1 if settings.setup_complete else 0
    alt = settings.reference_altitude_m
    if alt is None:
        buf[7:9] = IGNORE_I16_RAW.to_bytes(2, LE)
    else:
        buf[7:9] = alt.to_bytes(2, LE, signed=True)
    return bytes(buf)


# --------------------------------------------------------------------------- #
# Commands, name, time, button
# --------------------------------------------------------------------------- #


def encode_drop_command(
    *, erase_log: bool = False, blink_led: bool = False, restore_defaults: bool = False
) -> bytes:
    """Encode the 20-byte DROP commands characteristic."""
    buf = bytearray(COMMANDS_LENGTH)
    buf[0] = 1 if erase_log else 0
    buf[1] = 1 if blink_led else 0
    buf[2] = 1 if restore_defaults else 0
    return bytes(buf)


def parse_drop_button(raw: bytes | bytearray | None) -> int | None:
    """Decode the button-pressed notification (single byte)."""
    if not raw:
        return None
    return int(raw[0])


def parse_ascii(raw: bytes | bytearray | None) -> str | None:
    """Decode a NUL/0xFF-padded ASCII characteristic."""
    if raw is None:
        return None
    text = bytes(raw).split(b"\x00", 1)[0].rstrip(b"\xff")
    try:
        return text.decode("ascii").strip() or None
    except UnicodeDecodeError:
        return text.decode("latin-1", errors="replace").strip() or None


def encode_name(name: str, length: int = NAME_LENGTH) -> bytes:
    """Encode a device name as NUL-padded ASCII of fixed length."""
    data = name.encode("ascii", errors="replace")[:length]
    return data.ljust(length, b"\x00")


def _build_datetime(
    year: int, month: int, day: int, hms: tuple[int, int, int]
) -> datetime | None:
    if year < 2000 or year > 2150 or month == 0 or day == 0:
        return None
    try:
        return datetime(year, month, day, *hms)
    except ValueError:
        return None


def decode_sig_datetime(raw: bytes | bytearray | None) -> datetime | None:
    """Decode the 7-byte Date/Time characteristic.

    The specification references the SIG Date Time layout (year u16 LE,
    month, day, hour, minute, second).  Real DROP D3 units (BLE profile 1.25)
    transmit the fields in the opposite order -- second, minute, hour, day,
    month, year u16 LE.  Both layouts are accepted; the one yielding a
    plausible date wins, with the DROP layout tried first.
    """
    if raw is None or len(raw) < DATETIME_LENGTH:
        return None
    data = bytes(raw[:DATETIME_LENGTH])
    # DROP order.
    second, minute, hour, day, month = data[0:5]
    year = int.from_bytes(data[5:7], LE)
    if (when := _build_datetime(year, month, day, (hour, minute, second))) is not None:
        return when
    # SIG order.
    year = int.from_bytes(data[0:2], LE)
    month, day, hour, minute, second = data[2:7]
    return _build_datetime(year, month, day, (hour, minute, second))


def encode_sig_datetime(when: datetime, *, drop_layout: bool = True) -> bytes:
    """Encode a datetime (device-local, tz ignored) for the Date/Time characteristic.

    ``drop_layout`` selects the field order real DROP units use (see
    :func:`decode_sig_datetime`); pass False for the SIG order.
    """
    if drop_layout:
        return bytes(
            [when.second, when.minute, when.hour, when.day, when.month]
        ) + when.year.to_bytes(2, LE)
    return when.year.to_bytes(2, LE) + bytes(
        [when.month, when.day, when.hour, when.minute, when.second]
    )
