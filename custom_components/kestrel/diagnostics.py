"""Diagnostics support for the Kestrel integration."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import Enum
from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import KestrelConfigEntry


def _to_serialisable(value: Any) -> Any:
    """Convert dataclasses, bytes, datetimes and enums into JSON-friendly data."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: _to_serialisable(getattr(value, f.name))
            for f in dataclasses.fields(value)
        }
    if isinstance(value, dict):
        return {
            (k.value if isinstance(k, Enum) else str(k)): _to_serialisable(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_to_serialisable(v) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: KestrelConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": {
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "available": coordinator.available,
        "last_poll_successful": coordinator.last_poll_successful,
        "poll_interval": coordinator.poll_interval,
        "state": _to_serialisable(coordinator.data),
    }
