"""The Kestrel integration."""

from __future__ import annotations

from homeassistant.components import bluetooth
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import PLATFORMS
from .coordinator import KestrelConfigEntry, KestrelCoordinator
from .services import async_setup_services


async def async_setup_entry(hass: HomeAssistant, entry: KestrelConfigEntry) -> bool:
    """Set up a Kestrel device from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    ble_device = bluetooth.async_ble_device_from_address(hass, address.upper(), True)
    if ble_device is None:
        raise ConfigEntryNotReady(
            f"Could not find Kestrel device with address {address}"
        )

    coordinator = KestrelCoordinator(hass, entry, ble_device)
    await coordinator.async_initial_poll()
    entry.runtime_data = coordinator

    async_setup_services(hass)
    entry.async_on_unload(coordinator.async_start())
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KestrelConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
