"""Tests for software-derived measurements."""

from __future__ import annotations

import pytest

from custom_components.kestrel.kestrel_link.const import (
    DeviceFamily,
    MeasurementKind,
    NativeUnit,
)
from custom_components.kestrel.kestrel_link.derived import (
    add_derived_measurements,
    sea_level_pressure,
)
from custom_components.kestrel.kestrel_link.types import (
    DeviceState,
    DropSettings,
    Measurement,
)


def _m(
    kind: MeasurementKind, value: float | None, unit: NativeUnit, present: bool = True
) -> Measurement:
    return Measurement(
        kind=kind, value=value, unit=unit, present=present, valid=value is not None
    )


def test_sea_level_pressure_matches_hypsometric_formula() -> None:
    # Capture from a DROP D3 at the 1525 m test site.
    assert sea_level_pressure(852.3, 1525, 20.81) == pytest.approx(1014.5, abs=0.5)
    # At sea level the reduction is the identity.
    assert sea_level_pressure(1013.25, 0, 15.0) == pytest.approx(1013.25)


def test_barometric_pressure_is_derived_when_device_lacks_it() -> None:
    state = DeviceState(address="AA", family=DeviceFamily.DROP)
    state.measurements = {
        MeasurementKind.STATION_PRESSURE: _m(
            MeasurementKind.STATION_PRESSURE, 852.3, NativeUnit.HPA
        ),
        MeasurementKind.TEMPERATURE: _m(
            MeasurementKind.TEMPERATURE, 20.81, NativeUnit.CELSIUS
        ),
        MeasurementKind.BAROMETRIC_PRESSURE: _m(
            MeasurementKind.BAROMETRIC_PRESSURE, None, NativeUnit.HPA, present=False
        ),
    }
    state.settings = DropSettings(reference_altitude_m=1525)
    add_derived_measurements(state)
    baro = state.measurements[MeasurementKind.BAROMETRIC_PRESSURE]
    assert baro.present and baro.derived and baro.valid
    assert baro.value == pytest.approx(1014.5, abs=0.5)


def test_barometric_pressure_not_derived_without_inputs() -> None:
    state = DeviceState(address="AA", family=DeviceFamily.DROP)
    state.measurements = {
        MeasurementKind.STATION_PRESSURE: _m(
            MeasurementKind.STATION_PRESSURE, 852.3, NativeUnit.HPA
        ),
        MeasurementKind.TEMPERATURE: _m(
            MeasurementKind.TEMPERATURE, 20.81, NativeUnit.CELSIUS
        ),
    }
    add_derived_measurements(state)  # no settings -> no altitude
    assert MeasurementKind.BAROMETRIC_PRESSURE not in state.measurements

    state.settings = DropSettings(reference_altitude_m=1525)
    state.measurements[MeasurementKind.STATION_PRESSURE] = _m(
        MeasurementKind.STATION_PRESSURE, None, NativeUnit.HPA
    )
    add_derived_measurements(state)
    baro = state.measurements[MeasurementKind.BAROMETRIC_PRESSURE]
    assert baro.present and baro.derived and not baro.valid and baro.value is None


def test_device_reported_barometric_pressure_is_kept() -> None:
    state = DeviceState(address="AA", family=DeviceFamily.KESTREL_5000)
    state.measurements = {
        MeasurementKind.STATION_PRESSURE: _m(
            MeasurementKind.STATION_PRESSURE, 852.3, NativeUnit.HPA
        ),
        MeasurementKind.TEMPERATURE: _m(
            MeasurementKind.TEMPERATURE, 20.81, NativeUnit.CELSIUS
        ),
        MeasurementKind.BAROMETRIC_PRESSURE: _m(
            MeasurementKind.BAROMETRIC_PRESSURE, 1000.0, NativeUnit.HPA
        ),
    }
    state.settings = DropSettings(reference_altitude_m=1525)
    add_derived_measurements(state)
    baro = state.measurements[MeasurementKind.BAROMETRIC_PRESSURE]
    assert baro.value == 1000.0 and not baro.derived
