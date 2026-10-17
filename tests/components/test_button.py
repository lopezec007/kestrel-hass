"""Tests for the Kestrel buttons."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kestrel.const import DOMAIN
from custom_components.kestrel.kestrel_link.profiles import ProfileCommand

from .conftest import DROP_ADDRESS, FakeKestrelBleDevice


async def test_identify_button(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    mock_device: FakeKestrelBleDevice,
) -> None:
    """Identify sends the blink-LED command."""
    entity_id = entity_registry.async_get_entity_id(
        BUTTON_DOMAIN, DOMAIN, f"{DROP_ADDRESS}_identify"
    )
    assert entity_id is not None
    assert hass.states.get(entity_id).attributes["device_class"] == "identify"
    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    mock_device.async_send_command.assert_awaited_once_with(ProfileCommand.IDENTIFY)


async def test_sync_time_button(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    mock_device: FakeKestrelBleDevice,
) -> None:
    """Sync time writes the current time and updates the device time sensor."""
    entity_id = entity_registry.async_get_entity_id(
        BUTTON_DOMAIN, DOMAIN, f"{DROP_ADDRESS}_sync_time"
    )
    assert entity_id is not None
    time_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"{DROP_ADDRESS}_device_time"
    )
    before = hass.states.get(time_id).state

    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    mock_device.async_set_time.assert_awaited_once()
    when = mock_device.async_set_time.await_args.args[0]
    assert isinstance(when, datetime)
    assert when.tzinfo is not None
    assert hass.states.get(time_id).state != before


async def test_erase_log_button_disabled_by_default(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    mock_device: FakeKestrelBleDevice,
) -> None:
    """Erase log exists but is disabled until the user opts in."""
    entity_id = entity_registry.async_get_entity_id(
        BUTTON_DOMAIN, DOMAIN, f"{DROP_ADDRESS}_erase_log"
    )
    assert entity_id is not None
    entry = entity_registry.async_get(entity_id)
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert entry.entity_category is EntityCategory.CONFIG
    assert hass.states.get(entity_id) is None

    entity_registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id) is not None

    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    mock_device.async_send_command.assert_awaited_once_with(ProfileCommand.ERASE_LOG)
