"""Tests for syncing the device reference altitude with HA's home elevation."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, EVENT_CORE_CONFIG_UPDATE
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kestrel.const import (
    CONF_FAMILY,
    CONF_MODEL_CODE,
    CONF_POLL_INTERVAL,
    CONF_SYNC_REFERENCE_ALTITUDE,
    DOMAIN,
)
from custom_components.kestrel.kestrel_link.const import DeviceFamily
from custom_components.kestrel.kestrel_link.types import DropSettings

from .conftest import (
    DROP_ADDRESS,
    DROP_MODEL_CODE,
    DROP_NAME,
    DROP_SERVICE_INFO,
    FakeKestrelBleDevice,
    inject_bluetooth_service_info,
)


def _entry(sync: bool) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=DROP_NAME,
        unique_id=DROP_ADDRESS,
        data={
            CONF_ADDRESS: DROP_ADDRESS,
            CONF_FAMILY: DeviceFamily.DROP.value,
            CONF_MODEL_CODE: DROP_MODEL_CODE,
        },
        options={CONF_POLL_INTERVAL: 300, CONF_SYNC_REFERENCE_ALTITUDE: sync},
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    inject_bluetooth_service_info(hass, DROP_SERVICE_INFO)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.state is ConfigEntryState.LOADED


async def test_reference_altitude_written_on_setup(
    hass: HomeAssistant, setup_bluetooth: None, mock_device: FakeKestrelBleDevice
) -> None:
    """With the option on, the device gets HA's elevation when it differs."""
    hass.config.elevation = 1525
    await _setup(hass, _entry(sync=True))
    mock_device.async_write_settings.assert_awaited_once_with(
        DropSettings(reference_altitude_m=1525)
    )
    state = hass.states.get("number.d3_1234567_reference_altitude")
    assert state is not None
    assert float(state.state) == 1525


async def test_reference_altitude_not_written_when_equal_or_disabled(
    hass: HomeAssistant, setup_bluetooth: None, mock_device: FakeKestrelBleDevice
) -> None:
    """No write when the device already matches, or when the option is off."""
    hass.config.elevation = 120  # fixture device already reports 120 m
    await _setup(hass, _entry(sync=True))
    mock_device.async_write_settings.assert_not_awaited()


async def test_reference_altitude_disabled(
    hass: HomeAssistant, setup_bluetooth: None, mock_device: FakeKestrelBleDevice
) -> None:
    """The option off leaves the device alone."""
    hass.config.elevation = 1525
    await _setup(hass, _entry(sync=False))
    mock_device.async_write_settings.assert_not_awaited()


async def test_elevation_change_triggers_update(
    hass: HomeAssistant, setup_bluetooth: None, mock_device: FakeKestrelBleDevice
) -> None:
    """Changing the home elevation re-syncs the device."""
    hass.config.elevation = 120
    await _setup(hass, _entry(sync=True))
    mock_device.async_write_settings.assert_not_awaited()

    hass.config.elevation = 1600
    hass.bus.async_fire(EVENT_CORE_CONFIG_UPDATE, {"elevation": 1600})
    await hass.async_block_till_done(wait_background_tasks=True)
    mock_device.async_write_settings.assert_awaited_with(
        DropSettings(reference_altitude_m=1600)
    )
