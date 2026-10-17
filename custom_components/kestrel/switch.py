"""Switch platform for the Kestrel integration (log wrap)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KestrelConfigEntry
from .entity import KestrelEntity
from .kestrel_link.types import DropSettings

PARALLEL_UPDATES = 1

WRAP_LOG_DESCRIPTION = SwitchEntityDescription(
    key="wrap_log",
    translation_key="wrap_log",
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KestrelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the wrap-log switch when the device exposes settings."""
    coordinator = entry.runtime_data
    if coordinator.data.settings is None:
        return
    async_add_entities([KestrelWrapLogSwitch(coordinator, WRAP_LOG_DESCRIPTION)])


class KestrelWrapLogSwitch(KestrelEntity, SwitchEntity):
    """Whether the data log overwrites its oldest records when full."""

    @property
    def is_on(self) -> bool | None:
        """Return True when log wrapping is enabled."""
        state = self.coordinator.data
        if state is None or state.settings is None:
            return None
        return state.settings.wrap_log

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable log wrapping."""
        await self.coordinator.async_write_settings(DropSettings(wrap_log=True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable log wrapping."""
        await self.coordinator.async_write_settings(DropSettings(wrap_log=False))
