"""Tests for the Kestrel wrap-log switch."""

from __future__ import annotations

from homeassistant.components.switch import (
    DOMAIN as SWITCH_DOMAIN,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kestrel.const import DOMAIN
from custom_components.kestrel.kestrel_link.types import DropSettings

from .conftest import DROP_ADDRESS, FakeKestrelBleDevice


async def test_wrap_log_switch(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    mock_device: FakeKestrelBleDevice,
) -> None:
    """The switch mirrors and writes the wrap-log setting."""
    entity_id = entity_registry.async_get_entity_id(
        SWITCH_DOMAIN, DOMAIN, f"{DROP_ADDRESS}_wrap_log"
    )
    assert entity_id is not None
    assert hass.states.get(entity_id).state == STATE_ON

    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    mock_device.async_write_settings.assert_awaited_with(DropSettings(wrap_log=False))
    assert hass.states.get(entity_id).state == STATE_OFF

    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    mock_device.async_write_settings.assert_awaited_with(DropSettings(wrap_log=True))
    assert hass.states.get(entity_id).state == STATE_ON
    assert mock_device.async_write_settings.await_count == 2
