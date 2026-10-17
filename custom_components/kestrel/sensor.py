"""Sensor platform for the Kestrel integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfIrradiance,
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .coordinator import KestrelConfigEntry
from .entity import KestrelEntity
from .kestrel_link.const import MeasurementKind, NativeUnit
from .kestrel_link.types import DeviceState

PARALLEL_UPDATES = 0

type ValueFn = Callable[[DeviceState], StateType | datetime]


@dataclass(frozen=True, kw_only=True)
class KestrelSensorDescription(SensorEntityDescription):
    """Describe a Kestrel sensor and how to read it from the device state."""

    value_fn: ValueFn


def _measurement(kind: MeasurementKind) -> ValueFn:
    """Return a value function reading one measurement."""
    return lambda state: state.value(kind)


def _temperature(kind: MeasurementKind) -> KestrelSensorDescription:
    return KestrelSensorDescription(
        key=kind.value,
        translation_key=kind.value,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_measurement(kind),
    )


def _pressure(
    kind: MeasurementKind, device_class: SensorDeviceClass
) -> KestrelSensorDescription:
    return KestrelSensorDescription(
        key=kind.value,
        translation_key=kind.value,
        device_class=device_class,
        native_unit_of_measurement=UnitOfPressure.HPA,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_measurement(kind),
    )


def _distance(kind: MeasurementKind) -> KestrelSensorDescription:
    return KestrelSensorDescription(
        key=kind.value,
        translation_key=kind.value,
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.METERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=_measurement(kind),
    )


def _speed(kind: MeasurementKind) -> KestrelSensorDescription:
    return KestrelSensorDescription(
        key=kind.value,
        translation_key=kind.value,
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_measurement(kind),
    )


def _direction(kind: MeasurementKind) -> KestrelSensorDescription:
    return KestrelSensorDescription(
        key=kind.value,
        translation_key=kind.value,
        device_class=SensorDeviceClass.WIND_DIRECTION,
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT_ANGLE,
        suggested_display_precision=0,
        value_fn=_measurement(kind),
    )


def _plain(
    kind: MeasurementKind,
    unit: str | None,
    precision: int = 2,
) -> KestrelSensorDescription:
    return KestrelSensorDescription(
        key=kind.value,
        translation_key=kind.value,
        native_unit_of_measurement=unit or None,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=precision,
        value_fn=_measurement(kind),
    )


MEASUREMENT_DESCRIPTIONS: dict[MeasurementKind, KestrelSensorDescription] = {
    MeasurementKind.TEMPERATURE: _temperature(MeasurementKind.TEMPERATURE),
    MeasurementKind.RELATIVE_HUMIDITY: KestrelSensorDescription(
        key=MeasurementKind.RELATIVE_HUMIDITY.value,
        translation_key=MeasurementKind.RELATIVE_HUMIDITY.value,
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_measurement(MeasurementKind.RELATIVE_HUMIDITY),
    ),
    MeasurementKind.HEAT_INDEX: _temperature(MeasurementKind.HEAT_INDEX),
    MeasurementKind.DEW_POINT: _temperature(MeasurementKind.DEW_POINT),
    MeasurementKind.WET_BULB_TEMPERATURE: _temperature(
        MeasurementKind.WET_BULB_TEMPERATURE
    ),
    MeasurementKind.DELTA_T: KestrelSensorDescription(
        key=MeasurementKind.DELTA_T.value,
        translation_key=MeasurementKind.DELTA_T.value,
        device_class=SensorDeviceClass.TEMPERATURE_DELTA,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_measurement(MeasurementKind.DELTA_T),
    ),
    MeasurementKind.STATION_PRESSURE: _pressure(
        MeasurementKind.STATION_PRESSURE, SensorDeviceClass.ATMOSPHERIC_PRESSURE
    ),
    MeasurementKind.BAROMETRIC_PRESSURE: _pressure(
        MeasurementKind.BAROMETRIC_PRESSURE, SensorDeviceClass.ATMOSPHERIC_PRESSURE
    ),
    MeasurementKind.PRESSURE_TREND: _pressure(
        MeasurementKind.PRESSURE_TREND, SensorDeviceClass.PRESSURE
    ),
    MeasurementKind.DENSITY_ALTITUDE: _distance(MeasurementKind.DENSITY_ALTITUDE),
    MeasurementKind.HUMIDITY_RATIO: _plain(
        MeasurementKind.HUMIDITY_RATIO, NativeUnit.GRAMS_PER_KG
    ),
    MeasurementKind.MOISTURE_CONTENT: _plain(
        MeasurementKind.MOISTURE_CONTENT, NativeUnit.GRAMS_PER_KG
    ),
    MeasurementKind.RELATIVE_AIR_DENSITY: _plain(
        MeasurementKind.RELATIVE_AIR_DENSITY, PERCENTAGE, 1
    ),
    MeasurementKind.THI_NRC: _plain(MeasurementKind.THI_NRC, None, 1),
    MeasurementKind.THI_YOUSEF: _plain(MeasurementKind.THI_YOUSEF, None, 1),
    MeasurementKind.WIND_SPEED: _speed(MeasurementKind.WIND_SPEED),
    MeasurementKind.GLOBE_TEMPERATURE: _temperature(MeasurementKind.GLOBE_TEMPERATURE),
    MeasurementKind.MAGNETIC_DIRECTION: _direction(MeasurementKind.MAGNETIC_DIRECTION),
    MeasurementKind.TRUE_DIRECTION: _direction(MeasurementKind.TRUE_DIRECTION),
    MeasurementKind.AIR_DENSITY: _plain(
        MeasurementKind.AIR_DENSITY, NativeUnit.KG_PER_M3, 3
    ),
    MeasurementKind.ALTITUDE: _distance(MeasurementKind.ALTITUDE),
    MeasurementKind.CROSSWIND: _speed(MeasurementKind.CROSSWIND),
    MeasurementKind.HEADWIND: _speed(MeasurementKind.HEADWIND),
    MeasurementKind.EVAPORATION_RATE: _plain(
        MeasurementKind.EVAPORATION_RATE, NativeUnit.KG_PER_M2_PER_HOUR
    ),
    MeasurementKind.THERMAL_WORK_LIMIT: _plain(
        MeasurementKind.THERMAL_WORK_LIMIT, UnitOfIrradiance.WATTS_PER_SQUARE_METER, 1
    ),
    MeasurementKind.WET_BULB_GLOBE_TEMPERATURE: _temperature(
        MeasurementKind.WET_BULB_GLOBE_TEMPERATURE
    ),
    MeasurementKind.NATURALLY_ASPIRATED_WET_BULB: _temperature(
        MeasurementKind.NATURALLY_ASPIRATED_WET_BULB
    ),
    MeasurementKind.WIND_CHILL: _temperature(MeasurementKind.WIND_CHILL),
    MeasurementKind.AIR_SPEED: _speed(MeasurementKind.AIR_SPEED),
    MeasurementKind.AIR_FLOW: KestrelSensorDescription(
        key=MeasurementKind.AIR_FLOW.value,
        translation_key=MeasurementKind.AIR_FLOW.value,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=_measurement(MeasurementKind.AIR_FLOW),
    ),
    MeasurementKind.HEAT_LOAD_INDEX: _plain(MeasurementKind.HEAT_LOAD_INDEX, None, 1),
    MeasurementKind.PROBABILITY_OF_IGNITION: _plain(
        MeasurementKind.PROBABILITY_OF_IGNITION, PERCENTAGE, 0
    ),
    MeasurementKind.AHLU_1: _plain(MeasurementKind.AHLU_1, None, 0),
    MeasurementKind.AHLU_2: _plain(MeasurementKind.AHLU_2, None, 0),
    MeasurementKind.AHLU_3: _plain(MeasurementKind.AHLU_3, None, 0),
    MeasurementKind.VAPOR_PRESSURE_DEFICIT: _pressure(
        MeasurementKind.VAPOR_PRESSURE_DEFICIT, SensorDeviceClass.PRESSURE
    ),
    MeasurementKind.HUMIDEX: _plain(MeasurementKind.HUMIDEX, None, 1),
    MeasurementKind.DISCOMFORT_INDEX: _temperature(MeasurementKind.DISCOMFORT_INDEX),
}


def _device_time(state: DeviceState) -> datetime | None:
    """Return the device clock as an aware datetime in HA's time zone."""
    if state.device_time is None:
        return None
    if state.device_time.tzinfo is not None:
        return state.device_time
    return state.device_time.replace(tzinfo=dt_util.get_default_time_zone())


DIAGNOSTIC_DESCRIPTIONS: tuple[KestrelSensorDescription, ...] = (
    KestrelSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
        value_fn=lambda state: state.battery_percent,
    ),
    KestrelSensorDescription(
        key="device_time",
        translation_key="device_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_device_time,
    ),
    KestrelSensorDescription(
        key="signal_strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda state: state.rssi,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KestrelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create sensors for every measurement the device implements."""
    coordinator = entry.runtime_data
    created: set[MeasurementKind] = set()

    @callback
    def _async_add_new_measurements() -> None:
        """Create sensors for measurements that have become present."""
        state = coordinator.data
        if state is None:
            return
        new = [
            kind
            for kind in state.present_measurements()
            if kind in MEASUREMENT_DESCRIPTIONS and kind not in created
        ]
        if not new:
            return
        created.update(new)
        async_add_entities(
            KestrelSensor(coordinator, MEASUREMENT_DESCRIPTIONS[kind]) for kind in new
        )

    async_add_entities(
        KestrelSensor(coordinator, description)
        for description in DIAGNOSTIC_DESCRIPTIONS
    )
    _async_add_new_measurements()
    # A measurement can appear later, e.g. barometric pressure once a
    # reference altitude is known, so keep watching the coordinator.
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_measurements))


class KestrelSensor(KestrelEntity, SensorEntity):
    """A Kestrel measurement or diagnostic sensor."""

    entity_description: KestrelSensorDescription

    @property
    def native_value(self) -> StateType | datetime:
        """Return the current value from the last poll."""
        if (state := self.coordinator.data) is None:
            return None
        return self.entity_description.value_fn(state)
