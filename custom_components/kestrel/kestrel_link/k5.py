"""Kestrel 5000-family GATT characteristic parsing and encoding.

The Kestrel 5000, 5400, 5500, 5700, 7000 and 3550 share one BLE profile:
presence bitmaps in the Measurement Status characteristics and fixed-layout
20-byte measurement characteristics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from .const import MeasurementKind, NativeUnit
from .drop import (
    COMMANDS_LENGTH,
    IGNORE_I16_RAW,
    IGNORE_U8,
    IGNORE_U24,
    SETTINGS_LENGTH,
    scale,
)
from .types import KestrelSettings, Measurement
from .uuids import (
    K5_DERIVED1_SHORT,
    K5_DERIVED2_SHORT,
    K5_DERIVED3_SHORT,
    K5_DERIVED4_SHORT,
    K5_SENSOR_SHORT,
)

# Measurement Status 1 bit -> kind
STATUS1_BITS: dict[int, MeasurementKind] = {
    0: MeasurementKind.WIND_SPEED,
    1: MeasurementKind.TEMPERATURE,
    2: MeasurementKind.GLOBE_TEMPERATURE,
    3: MeasurementKind.RELATIVE_HUMIDITY,
    4: MeasurementKind.STATION_PRESSURE,
    5: MeasurementKind.MAGNETIC_DIRECTION,
    6: MeasurementKind.TRUE_DIRECTION,
    7: MeasurementKind.AIR_DENSITY,
    8: MeasurementKind.ALTITUDE,
    9: MeasurementKind.BAROMETRIC_PRESSURE,
    10: MeasurementKind.CROSSWIND,
    11: MeasurementKind.HEADWIND,
    12: MeasurementKind.DENSITY_ALTITUDE,
    13: MeasurementKind.RELATIVE_AIR_DENSITY,
    14: MeasurementKind.DEW_POINT,
    15: MeasurementKind.HEAT_INDEX,
    16: MeasurementKind.EVAPORATION_RATE,
    17: MeasurementKind.MOISTURE_CONTENT,
    18: MeasurementKind.THERMAL_WORK_LIMIT,
    19: MeasurementKind.WET_BULB_GLOBE_TEMPERATURE,
    20: MeasurementKind.NATURALLY_ASPIRATED_WET_BULB,
    21: MeasurementKind.WET_BULB_TEMPERATURE,
    22: MeasurementKind.WIND_CHILL,
    23: MeasurementKind.AIR_SPEED,
    24: MeasurementKind.AIR_FLOW,
    25: MeasurementKind.DELTA_T,
    26: MeasurementKind.HUMIDITY_RATIO,
    27: MeasurementKind.HEAT_LOAD_INDEX,
    28: MeasurementKind.PROBABILITY_OF_IGNITION,
    29: MeasurementKind.AHLU_1,
    30: MeasurementKind.AHLU_2,
    31: MeasurementKind.AHLU_3,
}

# Measurement Status 2 bit -> kind
STATUS2_BITS: dict[int, MeasurementKind] = {
    0: MeasurementKind.THI_YOUSEF,
    1: MeasurementKind.THI_NRC,
    2: MeasurementKind.VAPOR_PRESSURE_DEFICIT,
    3: MeasurementKind.HUMIDEX,
}

# Wire byte order (typed so int.from_bytes/to_bytes accept it).
LE: Final[Literal["little"]] = "little"


@dataclass(frozen=True, slots=True)
class K5Field:
    """One fixed-position value inside a Kestrel measurement characteristic."""

    kind: MeasurementKind
    offset: int
    size: int
    signed: bool
    exponent: int
    unit: NativeUnit
    bad_value: int | None = None  # raw unsigned sentinel; None -> derive

    @property
    def end(self) -> int:
        """Return the exclusive end offset."""
        return self.offset + self.size


def _bad(size: int, signed: bool) -> int:
    return (1 << (8 * size - 1)) | 1 if signed else (1 << (8 * size)) - 1


_C = NativeUnit.CELSIUS
_P = NativeUnit.PERCENT
_H = NativeUnit.HPA
_M = NativeUnit.METERS
_MS = NativeUnit.METERS_PER_SECOND
_D = NativeUnit.DEGREES
_U = NativeUnit.UNITLESS

K5_LAYOUTS: dict[int, tuple[K5Field, ...]] = {
    K5_SENSOR_SHORT: (
        K5Field(MeasurementKind.WIND_SPEED, 0, 2, False, -3, _MS),
        K5Field(MeasurementKind.TEMPERATURE, 2, 2, True, -2, _C),
        K5Field(MeasurementKind.GLOBE_TEMPERATURE, 4, 2, True, -2, _C),
        K5Field(MeasurementKind.RELATIVE_HUMIDITY, 6, 2, False, -2, _P),
        K5Field(MeasurementKind.STATION_PRESSURE, 8, 2, False, -1, _H),
        K5Field(MeasurementKind.MAGNETIC_DIRECTION, 10, 2, False, 0, _D),
        K5Field(MeasurementKind.AIR_SPEED, 12, 2, False, -3, _MS),
    ),
    K5_DERIVED1_SHORT: (
        K5Field(MeasurementKind.TRUE_DIRECTION, 0, 2, False, 0, _D),
        K5Field(MeasurementKind.AIR_DENSITY, 2, 2, False, -3, NativeUnit.KG_PER_M3),
        K5Field(MeasurementKind.ALTITUDE, 4, 3, True, -1, _M),
        K5Field(MeasurementKind.BAROMETRIC_PRESSURE, 7, 2, False, -1, _H),
        K5Field(MeasurementKind.CROSSWIND, 9, 2, False, -3, _MS),
        K5Field(MeasurementKind.HEADWIND, 11, 3, True, -3, _MS),
        K5Field(MeasurementKind.DENSITY_ALTITUDE, 14, 3, True, -1, _M),
        K5Field(MeasurementKind.RELATIVE_AIR_DENSITY, 17, 2, False, -1, _P),
    ),
    K5_DERIVED2_SHORT: (
        K5Field(MeasurementKind.DEW_POINT, 0, 2, True, -2, _C),
        K5Field(MeasurementKind.HEAT_INDEX, 2, 3, True, -2, _C),
        K5Field(
            MeasurementKind.EVAPORATION_RATE,
            5,
            2,
            False,
            -2,
            NativeUnit.KG_PER_M2_PER_HOUR,
        ),
        K5Field(
            MeasurementKind.MOISTURE_CONTENT, 7, 3, False, -2, NativeUnit.GRAMS_PER_KG
        ),
        K5Field(
            MeasurementKind.THERMAL_WORK_LIMIT,
            10,
            2,
            False,
            -1,
            NativeUnit.WATTS_PER_M2,
        ),
        K5Field(MeasurementKind.WET_BULB_GLOBE_TEMPERATURE, 12, 2, True, -2, _C),
        K5Field(MeasurementKind.NATURALLY_ASPIRATED_WET_BULB, 14, 2, True, -2, _C),
        K5Field(MeasurementKind.WET_BULB_TEMPERATURE, 16, 2, True, -2, _C),
        K5Field(MeasurementKind.WIND_CHILL, 18, 2, True, -2, _C),
    ),
    K5_DERIVED3_SHORT: (
        K5Field(MeasurementKind.AIR_FLOW, 0, 3, False, -3, NativeUnit.M3_PER_SECOND),
        K5Field(MeasurementKind.DELTA_T, 3, 2, True, -2, _C),
        K5Field(
            MeasurementKind.HUMIDITY_RATIO, 5, 3, False, -2, NativeUnit.GRAMS_PER_KG
        ),
        K5Field(MeasurementKind.VAPOR_PRESSURE_DEFICIT, 8, 2, False, -1, _H),
        K5Field(MeasurementKind.HEAT_LOAD_INDEX, 10, 2, True, -2, _U),
        K5Field(MeasurementKind.PROBABILITY_OF_IGNITION, 12, 2, False, -2, _P),
        K5Field(MeasurementKind.AHLU_1, 14, 2, False, 0, _U),
        K5Field(MeasurementKind.AHLU_2, 16, 2, False, 0, _U),
        K5Field(MeasurementKind.AHLU_3, 18, 2, False, 0, _U),
    ),
    K5_DERIVED4_SHORT: (
        K5Field(MeasurementKind.THI_YOUSEF, 0, 2, True, -2, _U),
        K5Field(MeasurementKind.THI_NRC, 2, 2, True, -2, _U),
        # The spec lists 0xFFFF as the bad value for this signed field.
        K5Field(MeasurementKind.HUMIDEX, 4, 2, True, -2, _U, bad_value=0xFFFF),
    ),
}

K5_KIND_TO_SHORT: dict[MeasurementKind, int] = {
    f.kind: short for short, fields in K5_LAYOUTS.items() for f in fields
}


def _bits(raw: bytes | bytearray | None) -> int:
    if not raw:
        return 0
    return int.from_bytes(bytes(raw), LE)


def parse_k5_status(
    status1: bytes | bytearray | None, status2: bytes | bytearray | None = None
) -> set[MeasurementKind]:
    """Return the set of measurements the device reports as present."""
    present: set[MeasurementKind] = set()
    bits1 = _bits(status1)
    bits2 = _bits(status2)
    present.update(k for bit, k in STATUS1_BITS.items() if bits1 & (1 << bit))
    present.update(k for bit, k in STATUS2_BITS.items() if bits2 & (1 << bit))
    return present


def parse_k5_field(field: K5Field, raw: bytes, *, present: bool) -> Measurement:
    """Decode one field of a Kestrel measurement characteristic."""
    chunk = raw[field.offset : field.end]
    if len(chunk) < field.size:
        return Measurement(
            field.kind,
            None,
            field.unit,
            present=present,
            enabled=present,
            valid=False,
            raw=chunk,
        )
    unsigned = int.from_bytes(chunk, LE)
    bad = (
        field.bad_value
        if field.bad_value is not None
        else _bad(field.size, field.signed)
    )
    if not present or unsigned == bad:
        return Measurement(
            field.kind,
            None,
            field.unit,
            present=present,
            enabled=present,
            valid=False,
            raw=chunk,
        )
    raw_int = int.from_bytes(chunk, LE, signed=field.signed)
    return Measurement(
        field.kind,
        scale(raw_int, field.exponent),
        field.unit,
        present=True,
        enabled=True,
        valid=True,
        raw=chunk,
    )


def parse_k5_characteristic(
    short: int, raw: bytes | bytearray | None, present: set[MeasurementKind]
) -> dict[MeasurementKind, Measurement]:
    """Decode a whole Kestrel measurement characteristic.

    Measurements not flagged in ``present`` are returned with ``present=False``
    so callers can decide not to expose them.
    """
    data = bytes(raw) if raw is not None else b""
    return {
        f.kind: parse_k5_field(f, data, present=f.kind in present)
        for f in K5_LAYOUTS[short]
    }


# --------------------------------------------------------------------------- #
# Settings and commands
# --------------------------------------------------------------------------- #

# Reference altitude on the Kestrel 5000 family uses a -1 exponent (0.1 m).
K5_ALTITUDE_EXPONENT = -1


def parse_kestrel_settings(raw: bytes | bytearray) -> KestrelSettings:
    """Decode the Kestrel 5000-family settings characteristic."""
    data = bytes(raw)
    if len(data) < 10:
        raise ValueError(f"settings payload too short: {len(data)} bytes")
    li = int.from_bytes(data[0:3], LE)
    alt_raw = int.from_bytes(data[7:9], LE)
    alt: int | None
    if alt_raw == IGNORE_I16_RAW:
        alt = None
    else:
        # Stored in 0.1 m units; the dataclass keeps whole metres.
        alt = round(int.from_bytes(data[7:9], LE, signed=True) / 10)
    return KestrelSettings(
        log_interval_s=None if li == IGNORE_U24 else li,
        wrap_log=None if data[3] == IGNORE_U8 else bool(data[3]),
        transmission_rate_s=None if data[4] == IGNORE_U8 else data[4],
        security_level=None if data[5] == IGNORE_U8 else data[5],
        setup_complete=None if data[6] == IGNORE_U8 else bool(data[6]),
        reference_altitude_m=alt,
        auto_shutdown_min=None if data[9] == IGNORE_U8 else data[9],
    )


def encode_kestrel_settings(settings: KestrelSettings) -> bytes:
    """Encode Kestrel 5000-family settings (20 bytes, None -> ignore)."""
    from .drop import validate_drop_settings  # noqa: PLC0415

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
    if settings.reference_altitude_m is None:
        buf[7:9] = IGNORE_I16_RAW.to_bytes(2, LE)
    else:
        tenths = settings.reference_altitude_m * 10
        if not -32768 <= tenths <= 32767:
            raise ValueError("reference altitude out of range for 0.1 m encoding")
        buf[7:9] = tenths.to_bytes(2, LE, signed=True)
    if settings.auto_shutdown_min is not None:
        if not 0 <= settings.auto_shutdown_min <= 0xFE:
            raise ValueError("auto shutdown must be 0-254 minutes")
        buf[9] = settings.auto_shutdown_min
    return bytes(buf)


def encode_kestrel_command(
    *,
    erase_log: bool = False,
    restore_defaults: bool = False,
    visual_identify: bool = False,
    sync_ble_data: bool = False,
    store_log_point: bool = False,
) -> bytes:
    """Encode the Kestrel 5000-family commands characteristic."""
    buf = bytearray(COMMANDS_LENGTH)
    buf[0] = 1 if erase_log else 0
    buf[2] = 1 if restore_defaults else 0
    buf[3] = 1 if visual_identify else 0
    buf[4] = 1 if sync_ble_data else 0
    buf[5] = 1 if store_log_point else 0
    return bytes(buf)


def parse_k5_events(raw: bytes | bytearray | None) -> list[int]:
    """Decode the events characteristic into a list of field name codes."""
    if not raw:
        return []
    data = bytes(raw)
    events: list[int] = []
    for i in range(0, len(data) - 1, 2):
        code = int.from_bytes(data[i : i + 2], LE)
        if code in (0, 0xFFFF):
            continue
        events.append(code)
    return events
