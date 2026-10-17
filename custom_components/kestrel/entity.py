"""Base entity for the Kestrel integration."""

from __future__ import annotations

from homeassistant.components.bluetooth.passive_update_coordinator import (
    PassiveBluetoothCoordinatorEntity,
)
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import EntityDescription

from .const import MANUFACTURER
from .coordinator import KestrelCoordinator


class KestrelEntity(PassiveBluetoothCoordinatorEntity[KestrelCoordinator]):
    """Common behaviour for all Kestrel entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KestrelCoordinator,
        description: EntityDescription,
    ) -> None:
        """Initialise the entity from its description."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        state = coordinator.data
        model = state.model if state else None
        info = state.info if state else None
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            name=coordinator.entry.title,
            manufacturer=MANUFACTURER,
            model=model.name if model else None,
            model_id=str(model.code) if model else None,
            serial_number=info.serial_number if info else None,
            sw_version=info.firmware_revision if info else None,
            hw_version=info.hardware_revision if info else None,
        )

    @property
    def available(self) -> bool:
        """Return True when the device advertises and has been polled."""
        return super().available and self.coordinator.data is not None
