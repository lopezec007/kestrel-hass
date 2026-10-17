"""Tests for Kestrel diagnostics."""

from __future__ import annotations

import json

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kestrel.diagnostics import async_get_config_entry_diagnostics
from custom_components.kestrel.kestrel_link.models import model_from_code

from .conftest import DROP_ADDRESS, DROP_MODEL_CODE


async def test_config_entry_diagnostics(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Diagnostics include entry data and a JSON-friendly device state."""
    diag = await async_get_config_entry_diagnostics(hass, init_integration)

    assert diag["entry"]["data"]["address"] == DROP_ADDRESS
    assert diag["entry"]["options"] == {"poll_interval": 300}
    assert diag["available"] is True
    assert diag["poll_interval"] == 300

    state = diag["state"]
    assert state["address"] == DROP_ADDRESS
    assert state["family"] == "drop"
    assert state["model"]["name"] == model_from_code(DROP_MODEL_CODE).name
    assert state["battery_percent"] == 87
    assert state["device_time"] == "2026-10-17T12:00:00"
    assert state["measurements"]["temperature"]["value"] == 23.47
    assert state["measurements"]["temperature"]["unit"] == "°C"
    assert state["settings"]["log_interval_s"] == 600
    assert state["raw"] == {"12630001-cc25-497d-9854-9b6c02c77054": "072b09"}

    json.dumps(diag)  # must be serialisable
