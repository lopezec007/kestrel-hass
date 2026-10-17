"""Select platform for the Kestrel integration (data log interval)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KestrelConfigEntry
from .entity import KestrelEntity
from .kestrel_link.const import LOG_INTERVALS_S
from .kestrel_link.types import DropSettings

PARALLEL_UPDATES = 1

LOG_INTERVAL_DESCRIPTION = SelectEntityDescription(
    key="log_interval",
    translation_key="log_interval",
    entity_category=EntityCategory.CONFIG,
    options=[str(interval) for interval in LOG_INTERVALS_S],
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KestrelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the log interval select when the device exposes settings."""
    coordinator = entry.runtime_data
    if coordinator.data.settings is None:
        return
    async_add_entities(
        [KestrelLogIntervalSelect(coordinator, LOG_INTERVAL_DESCRIPTION)]
    )


class KestrelLogIntervalSelect(KestrelEntity, SelectEntity):
    """Choose how often the device stores a log record."""

    @property
    def current_option(self) -> str | None:
        """Return the current log interval in seconds as a string."""
        state = self.coordinator.data
        if (
            state is None
            or state.settings is None
            or state.settings.log_interval_s is None
        ):
            return None
        option = str(state.settings.log_interval_s)
        return option if option in self.options else None

    async def async_select_option(self, option: str) -> None:
        """Write the chosen log interval to the device."""
        await self.coordinator.async_write_settings(
            DropSettings(log_interval_s=int(option))
        )
