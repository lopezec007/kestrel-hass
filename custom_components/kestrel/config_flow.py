"""Config flow for the Kestrel integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

try:  # Home Assistant >= 2026.10 validates schemas with probatio
    import probatio as vol
except ImportError:  # pragma: no cover - older Home Assistant
    import voluptuous as vol  # type: ignore[no-redef]

from .const import (
    CONF_FAMILY,
    CONF_MODEL_CODE,
    CONF_POLL_INTERVAL,
    CONF_SYNC_REFERENCE_ALTITUDE,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SYNC_REFERENCE_ALTITUDE,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
)
from .kestrel_link.advertising import clean_local_name, parse_advertisement
from .kestrel_link.const import WEATHER_FAMILIES
from .kestrel_link.types import NKAdvertisement

_LOGGER = logging.getLogger(__name__)


def _parse(info: BluetoothServiceInfoBleak) -> NKAdvertisement | None:
    """Return the NK advertisement if ``info`` is a supported weather device."""
    adv = parse_advertisement(info.name, info.manufacturer_data, info.service_uuids)
    if adv is None or adv.family not in WEATHER_FAMILIES:
        return None
    return adv


def _title(info: BluetoothServiceInfoBleak, adv: NKAdvertisement) -> str:
    """Build a human readable title for a discovered device."""
    name = clean_local_name(info.name)
    if name and name != info.address:
        return name
    if (model := adv.model) is not None:
        return f"{model.name} {info.address}"
    return f"Kestrel {info.address}"


class KestrelConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kestrel devices."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._advertisement: NKAdvertisement | None = None
        self._discovered: dict[
            str, tuple[BluetoothServiceInfoBleak, NKAdvertisement]
        ] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> KestrelOptionsFlow:
        """Return the options flow handler."""
        return KestrelOptionsFlow()

    def _create_entry(
        self, info: BluetoothServiceInfoBleak, adv: NKAdvertisement
    ) -> ConfigFlowResult:
        """Create the config entry for a device."""
        return self.async_create_entry(
            title=_title(info, adv),
            data={
                CONF_ADDRESS: info.address,
                CONF_FAMILY: adv.family.value,
                CONF_MODEL_CODE: adv.model_code,
            },
            options={
                CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
                CONF_SYNC_REFERENCE_ALTITUDE: DEFAULT_SYNC_REFERENCE_ALTITUDE,
            },
        )

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a device discovered via Bluetooth."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        adv = _parse(discovery_info)
        if adv is None:
            return self.async_abort(reason="not_supported")
        self._discovery_info = discovery_info
        self._advertisement = adv
        self.context["title_placeholders"] = {"name": _title(discovery_info, adv)}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered device."""
        assert self._discovery_info is not None
        assert self._advertisement is not None
        if user_input is not None:
            return self._create_entry(self._discovery_info, self._advertisement)
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders=self.context["title_placeholders"],
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick one of the discovered devices."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            info, adv = self._discovered[address]
            return self._create_entry(info, adv)

        current_addresses = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass, True):
            if info.address in current_addresses or info.address in self._discovered:
                continue
            if (parsed := _parse(info)) is None:
                continue
            self._discovered[info.address] = (info, parsed)

        if not self._discovered:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            address: f"{_title(info, adv)} ({address})"
                            for address, (info, adv) in self._discovered.items()
                        }
                    )
                }
            ),
        )


class KestrelOptionsFlow(OptionsFlowWithReload):
    """Handle Kestrel options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the poll interval."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_POLL_INTERVAL: int(user_input[CONF_POLL_INTERVAL]),
                    CONF_SYNC_REFERENCE_ALTITUDE: bool(
                        user_input.get(
                            CONF_SYNC_REFERENCE_ALTITUDE,
                            DEFAULT_SYNC_REFERENCE_ALTITUDE,
                        )
                    ),
                }
            )
        options = self.config_entry.options
        current = options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        current_sync = options.get(
            CONF_SYNC_REFERENCE_ALTITUDE, DEFAULT_SYNC_REFERENCE_ALTITUDE
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_POLL_INTERVAL, default=current): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_POLL_INTERVAL,
                            max=MAX_POLL_INTERVAL,
                            step=1,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                    vol.Required(
                        CONF_SYNC_REFERENCE_ALTITUDE, default=current_sync
                    ): BooleanSelector(),
                }
            ),
            description_placeholders={
                "elevation": str(round(self.hass.config.elevation))
            },
        )
