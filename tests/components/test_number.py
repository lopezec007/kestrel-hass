"""Tests for the Kestrel number entities."""

from __future__ import annotations

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kestrel.const import DOMAIN
from custom_components.kestrel.kestrel_link.types import DropSettings

from .conftest import DROP_ADDRESS, FakeKestrelBleDevice


@pytest.mark.parametrize(
    ("key", "current", "unit", "new_value", "expected"),
    [
        ("transmission_rate", "5.0", "s", 10, DropSettings(transmission_rate_s=10)),
        (
            "reference_altitude",
            "120.0",
            "m",
            250,
            DropSettings(reference_altitude_m=250),
        ),
    ],
)
async def test_number_entities(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    mock_device: FakeKestrelBleDevice,
    key: str,
    current: str,
    unit: str,
    new_value: int,
    expected: DropSettings,
) -> None:
    """Numbers reflect settings and write only their own field."""
    entity_id = entity_registry.async_get_entity_id(
        NUMBER_DOMAIN, DOMAIN, f"{DROP_ADDRESS}_{key}"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state.state == current
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == unit
    assert state.attributes["mode"] == "box"

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: new_value},
        blocking=True,
    )
    mock_device.async_write_settings.assert_awaited_once_with(expected)
    assert hass.states.get(entity_id).state == f"{new_value}.0"
