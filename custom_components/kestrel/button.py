"""Button platform for the Kestrel integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KestrelConfigEntry, KestrelCoordinator
from .entity import KestrelEntity
from .kestrel_link.profiles import ProfileCommand

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class KestrelButtonDescription(ButtonEntityDescription):
    """Describe a button and the coordinator action it triggers."""

    press_fn: Callable[[KestrelCoordinator], Awaitable[None]]
    command: ProfileCommand | None = None


BUTTON_DESCRIPTIONS: tuple[KestrelButtonDescription, ...] = (
    KestrelButtonDescription(
        key="identify",
        device_class=ButtonDeviceClass.IDENTIFY,
        entity_category=EntityCategory.CONFIG,
        command=ProfileCommand.IDENTIFY,
        press_fn=lambda c: c.async_send_command(ProfileCommand.IDENTIFY),
    ),
    KestrelButtonDescription(
        key="sync_time",
        translation_key="sync_time",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c: c.async_set_time(),
    ),
    KestrelButtonDescription(
        key="erase_log",
        translation_key="erase_log",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        command=ProfileCommand.ERASE_LOG,
        press_fn=lambda c: c.async_send_command(ProfileCommand.ERASE_LOG),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KestrelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the buttons supported by this device."""
    coordinator = entry.runtime_data
    supported = getattr(coordinator.device, "supported_commands", None)
    async_add_entities(
        KestrelButton(coordinator, description)
        for description in BUTTON_DESCRIPTIONS
        if description.command is None
        or supported is None
        or description.command in supported
    )


class KestrelButton(KestrelEntity, ButtonEntity):
    """A momentary action on the device."""

    entity_description: KestrelButtonDescription

    async def async_press(self) -> None:
        """Run the button's action."""
        await self.entity_description.press_fn(self.coordinator)
