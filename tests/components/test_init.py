"""Tests for Kestrel entry setup, polling and unloading."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.kestrel import coordinator as coordinator_module
from custom_components.kestrel.const import CONF_POLL_INTERVAL, DOMAIN
from custom_components.kestrel.kestrel_link.models import model_from_code

from .conftest import (
    DROP_ADDRESS,
    DROP_MODEL_CODE,
    DROP_NAME,
    DROP_SERVICE_INFO,
    FakeKestrelBleDevice,
    get_device_entry,
    inject_bluetooth_service_info,
    make_service_info,
)


async def test_setup_and_unload(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: FakeKestrelBleDevice,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Setup polls once, registers the device, and unloads cleanly."""
    entry = init_integration
    assert entry.state is ConfigEntryState.LOADED
    assert mock_device.async_poll.await_count == 1
    assert mock_device.kwargs["ble_device"].address == DROP_ADDRESS

    device = get_device_entry(hass, DROP_ADDRESS, entry.entry_id)
    assert device is not None
    assert device.name == DROP_NAME
    assert device.manufacturer == "Nielsen-Kellerman"
    assert device.model == model_from_code(DROP_MODEL_CODE).name
    assert device.serial_number == "1234567"
    assert device.sw_version == "1.23"
    assert device.hw_version == "2"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_no_ble_device(
    hass: HomeAssistant,
    setup_bluetooth: None,
    mock_device: FakeKestrelBleDevice,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Setup retries when the device has not been seen advertising."""
    mock_config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert not mock_device.created


@pytest.mark.parametrize("error", [BleakError("boom"), TimeoutError()])
async def test_setup_initial_poll_fails(
    hass: HomeAssistant,
    setup_bluetooth: None,
    mock_device: FakeKestrelBleDevice,
    mock_config_entry: MockConfigEntry,
    error: Exception,
) -> None:
    """A failed first connection leaves the entry in retry state."""
    inject_bluetooth_service_info(hass, DROP_SERVICE_INFO)
    mock_config_entry.add_to_hass(hass)

    original = coordinator_module.KestrelBleDevice

    def failing_factory(*args, **kwargs):
        fake = original(*args, **kwargs)
        fake.async_poll.side_effect = error
        return fake

    coordinator_module.KestrelBleDevice = failing_factory  # type: ignore[assignment]
    try:
        assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    finally:
        coordinator_module.KestrelBleDevice = original  # type: ignore[assignment]
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_poll_on_advertisement_when_due(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: FakeKestrelBleDevice,
) -> None:
    """Advertisements trigger a poll only once the poll interval elapsed."""
    coordinator = init_integration.runtime_data
    assert mock_device.async_poll.await_count == 1

    # Fresh advertisement right after setup: interval not elapsed -> no poll.
    # (The Bluetooth manager only dispatches advertisements whose payload
    # changed, so each injection carries a different event field.)
    inject_bluetooth_service_info(hass, make_service_info(rssi=-55, event=0x007E))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_device.async_poll.await_count == 1

    # Pretend the last poll was long ago.
    coordinator._last_poll -= init_integration.options[CONF_POLL_INTERVAL] + 1
    inject_bluetooth_service_info(hass, make_service_info(rssi=-50, event=0x0001))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_device.async_poll.await_count == 2
    mock_device.set_ble_device.assert_called()
    assert coordinator.data.rssi == -50


async def test_unavailable_when_device_disappears(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry,
) -> None:
    """Entities go unavailable when Bluetooth reports the device gone."""
    entity_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"{DROP_ADDRESS}_temperature"
    )
    assert entity_id is not None
    assert hass.states.get(entity_id).state == "23.47"

    coordinator = init_integration.runtime_data
    coordinator._async_handle_unavailable(DROP_SERVICE_INFO)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unavailable"
    assert not coordinator.available

    inject_bluetooth_service_info(hass, make_service_info(event=0x007E))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(entity_id).state == "23.47"
    assert bluetooth.async_address_present(hass, DROP_ADDRESS, True)


async def test_timer_polls_without_advertisement_change(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: FakeKestrelBleDevice,
) -> None:
    """A static advertisement still gets polled once the interval elapses."""
    coordinator = init_integration.runtime_data
    interval = init_integration.options[CONF_POLL_INTERVAL]
    assert mock_device.async_poll.await_count == 1

    # Timer fires but the interval has not elapsed: nothing happens.
    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=interval // 3 + 1)
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_device.async_poll.await_count == 1

    # Interval elapsed (monotonic clock) and the device is still present.
    coordinator._last_poll -= interval + 1
    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=2 * (interval // 3) + 2)
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_device.async_poll.await_count == 2


async def test_timer_skips_poll_when_device_gone(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: FakeKestrelBleDevice,
) -> None:
    """The timer never connects to a device Bluetooth no longer sees."""
    coordinator = init_integration.runtime_data
    interval = init_integration.options[CONF_POLL_INTERVAL]
    coordinator._last_poll -= interval + 1

    with patch(
        "custom_components.kestrel.coordinator.bluetooth.async_ble_device_from_address",
        return_value=None,
    ):
        async_fire_time_changed(
            hass, dt_util.utcnow() + timedelta(seconds=interval // 3 + 1)
        )
        await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_device.async_poll.await_count == 1
