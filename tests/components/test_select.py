"""Tests for the Kestrel log interval select."""

from __future__ import annotations

from homeassistant.components.select import (
    ATTR_OPTION,
    ATTR_OPTIONS,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.const import ATTR_ENTITY_ID, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kestrel.const import DOMAIN
from custom_components.kestrel.kestrel_link.const import LOG_INTERVALS_S
from custom_components.kestrel.kestrel_link.types import DropSettings

from .conftest import DROP_ADDRESS, FakeKestrelBleDevice


async def test_log_interval_select(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    mock_device: FakeKestrelBleDevice,
) -> None:
    """The select shows the current interval and writes a new one."""
    entity_id = entity_registry.async_get_entity_id(
        SELECT_DOMAIN, DOMAIN, f"{DROP_ADDRESS}_log_interval"
    )
    assert entity_id is not None
    assert entity_registry.async_get(entity_id).entity_category is EntityCategory.CONFIG

    state = hass.states.get(entity_id)
    assert state.state == "600"
    assert state.attributes[ATTR_OPTIONS] == [str(i) for i in LOG_INTERVALS_S]
    assert "0" in state.attributes[ATTR_OPTIONS]

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: entity_id, ATTR_OPTION: "300"},
        blocking=True,
    )
    mock_device.async_write_settings.assert_awaited_once_with(
        DropSettings(log_interval_s=300)
    )
    assert hass.states.get(entity_id).state == "300"
