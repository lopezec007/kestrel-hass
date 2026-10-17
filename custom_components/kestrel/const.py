"""Constants for the Kestrel integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "kestrel"
MANUFACTURER = "Nielsen-Kellerman"

CONF_POLL_INTERVAL = "poll_interval"
CONF_SYNC_REFERENCE_ALTITUDE = "sync_reference_altitude"
CONF_FAMILY = "family"
CONF_MODEL_CODE = "model_code"

DEFAULT_POLL_INTERVAL = 300
DEFAULT_SYNC_REFERENCE_ALTITUDE = True
MIN_POLL_INTERVAL = 30
MAX_POLL_INTERVAL = 3600

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.BUTTON,
]
