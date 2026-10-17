"""Measurements derived in software from what a device reports.

Some Kestrel models do not compute every value themselves: a DROP D3 reports
station pressure but no barometric (sea-level) pressure, which the Kestrel app
derives on the phone from the reference altitude. This module performs the
same derivations so Home Assistant can expose them as ordinary sensors.
"""

from __future__ import annotations

from .const import MeasurementKind, NativeUnit
from .types import DeviceState, Measurement

# Temperature lapse rate (K/m), standard atmosphere.
_LAPSE_RATE = 0.0065
# g * M / (R * L) for the hypsometric formula.
_EXPONENT = 5.257
_KELVIN = 273.15


def sea_level_pressure(station_hpa: float, altitude_m: float, temp_c: float) -> float:
    """Reduce a station pressure to sea level (hypsometric formula).

    Args:
        station_hpa: Measured (station) pressure in hPa.
        altitude_m: Height of the station above sea level in metres.
        temp_c: Air temperature at the station in °C.

    Returns:
        Equivalent sea-level (barometric) pressure in hPa.
    """
    column = _LAPSE_RATE * altitude_m
    factor = 1.0 - column / (temp_c + column + _KELVIN)
    return station_hpa * factor ** (-_EXPONENT)


def add_derived_measurements(state: DeviceState) -> None:
    """Fill in measurements the device lacks but that can be computed.

    Currently derives barometric pressure when the device reports station
    pressure and temperature, a reference altitude is known, and the device
    itself does not provide barometric pressure.
    """
    baro = state.measurements.get(MeasurementKind.BAROMETRIC_PRESSURE)
    if baro is not None and baro.present:
        return
    station = state.measurements.get(MeasurementKind.STATION_PRESSURE)
    temperature = state.measurements.get(MeasurementKind.TEMPERATURE)
    altitude = (
        state.settings.reference_altitude_m if state.settings is not None else None
    )
    if station is None or not station.present or altitude is None:
        return
    if temperature is None or not temperature.present:
        return
    value: float | None = None
    valid = station.value is not None and temperature.value is not None
    if station.value is not None and temperature.value is not None:
        value = round(sea_level_pressure(station.value, altitude, temperature.value), 1)
    state.measurements[MeasurementKind.BAROMETRIC_PRESSURE] = Measurement(
        kind=MeasurementKind.BAROMETRIC_PRESSURE,
        value=value,
        unit=NativeUnit.HPA,
        present=True,
        enabled=True,
        valid=valid,
        raw=b"",
        derived=True,
    )
