"""Tests for the Kestrel sensor platform."""

from __future__ import annotations

from datetime import datetime

from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kestrel.const import DOMAIN
from custom_components.kestrel.kestrel_link.const import MeasurementKind, NativeUnit
from custom_components.kestrel.kestrel_link.types import Measurement

from .conftest import DROP_ADDRESS, FakeKestrelBleDevice


def _entity_id(entity_registry: er.EntityRegistry, key: str) -> str:
    entity_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"{DROP_ADDRESS}_{key}"
    )
    assert entity_id is not None, key
    return entity_id


@pytest.mark.parametrize(
    ("key", "state", "unit", "device_class"),
    [
        ("temperature", "23.47", "°C", "temperature"),
        ("relative_humidity", "40.0", "%", "humidity"),
        ("heat_index", "27.75", "°C", "temperature"),
        ("dew_point", "20.0", "°C", "temperature"),
        ("wet_bulb_temperature", "15.6", "°C", "temperature"),
        ("delta_t", "7.9", "°C", "temperature_delta"),
        ("station_pressure", "1013.2", "hPa", "atmospheric_pressure"),
        ("barometric_pressure", "1015.0", "hPa", "atmospheric_pressure"),
        ("density_altitude", "312.0", "m", "distance"),
        ("battery", "87", "%", "battery"),
    ],
)
async def test_measurement_sensors(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    key: str,
    state: str,
    unit: str,
    device_class: str,
) -> None:
    """Each present measurement becomes a sensor with the right metadata."""
    entity_id = _entity_id(entity_registry, key)
    st = hass.states.get(entity_id)
    assert st is not None
    assert st.state == state
    assert st.attributes[ATTR_UNIT_OF_MEASUREMENT] == unit
    assert st.attributes["device_class"] == device_class
    assert st.attributes["state_class"] == "measurement"


async def test_absent_measurements_not_created(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Measurements the model does not implement get no entity."""
    for key in ("thi_nrc", "thi_yousef", "wind_speed"):
        assert (
            entity_registry.async_get_entity_id(
                "sensor", DOMAIN, f"{DROP_ADDRESS}_{key}"
            )
            is None
        )


async def test_diagnostic_sensors(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Battery, device time and signal strength are diagnostic sensors."""
    battery = entity_registry.async_get(_entity_id(entity_registry, "battery"))
    assert battery.entity_category is EntityCategory.DIAGNOSTIC

    time_id = _entity_id(entity_registry, "device_time")
    assert (
        entity_registry.async_get(time_id).entity_category is EntityCategory.DIAGNOSTIC
    )
    st = hass.states.get(time_id)
    expected = datetime(2026, 10, 17, 12, 0, 0, tzinfo=dt_util.get_default_time_zone())
    assert dt_util.parse_datetime(st.state) == expected
    assert st.state == dt_util.as_utc(expected).isoformat()
    assert st.attributes["device_class"] == "timestamp"

    rssi = entity_registry.async_get(_entity_id(entity_registry, "signal_strength"))
    assert rssi.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert rssi.entity_category is EntityCategory.DIAGNOSTIC


async def test_invalid_measurement_is_unknown(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    mock_device: FakeKestrelBleDevice,
) -> None:
    """A present-but-invalid reading reports unknown after the next update."""
    entity_id = _entity_id(entity_registry, "temperature")
    coordinator = init_integration.runtime_data
    coordinator.data.measurements[MeasurementKind.TEMPERATURE] = Measurement(
        kind=MeasurementKind.TEMPERATURE, value=None, unit="°C", valid=False
    )
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unknown"


async def test_sensor_added_when_measurement_appears_later(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: FakeKestrelBleDevice,
) -> None:
    """A measurement that becomes present after setup gets its own sensor."""
    assert hass.states.get("sensor.d3_1234567_temperature_humidity_index_nrc") is None
    mock_device.state.measurements[MeasurementKind.THI_NRC] = Measurement(
        kind=MeasurementKind.THI_NRC,
        value=12.5,
        unit=NativeUnit.UNITLESS,
    )
    coordinator = init_integration.runtime_data
    coordinator.data = mock_device.state
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    state = hass.states.get("sensor.d3_1234567_temperature_humidity_index_nrc")
    assert state is not None
    assert state.state not in ("unknown", "unavailable")
