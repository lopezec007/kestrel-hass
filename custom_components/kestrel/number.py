"""Number platform for the Kestrel integration (device settings)."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KestrelConfigEntry
from .entity import KestrelEntity
from .kestrel_link.types import DropSettings

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class KestrelNumberDescription(NumberEntityDescription):
    """Describe a numeric device setting."""

    settings_field: str


NUMBER_DESCRIPTIONS: tuple[KestrelNumberDescription, ...] = (
    KestrelNumberDescription(
        key="transmission_rate",
        translation_key="transmission_rate",
        settings_field="transmission_rate_s",
        entity_category=EntityCategory.CONFIG,
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        native_min_value=2,
        native_max_value=60,
        native_step=1,
        mode=NumberMode.BOX,
    ),
    KestrelNumberDescription(
        key="reference_altitude",
        translation_key="reference_altitude",
        settings_field="reference_altitude_m",
        entity_category=EntityCategory.CONFIG,
        device_class=NumberDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.METERS,
        native_min_value=-2000,
        native_max_value=9200,
        native_step=1,
        mode=NumberMode.BOX,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KestrelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up numeric settings when the device exposes settings."""
    coordinator = entry.runtime_data
    if coordinator.data.settings is None:
        return
    async_add_entities(
        KestrelNumber(coordinator, description) for description in NUMBER_DESCRIPTIONS
    )


class KestrelNumber(KestrelEntity, NumberEntity):
    """A writable numeric setting on the device."""

    entity_description: KestrelNumberDescription

    @property
    def native_value(self) -> float | None:
        """Return the current setting value."""
        state = self.coordinator.data
        if state is None or state.settings is None:
            return None
        value = getattr(state.settings, self.entity_description.settings_field, None)
        return None if value is None else float(value)

    async def async_set_native_value(self, value: float) -> None:
        """Write the new value to the device."""
        settings = DropSettings()
        setattr(settings, self.entity_description.settings_field, int(value))
        await self.coordinator.async_write_settings(settings)
