"""Data update coordinator for Kestrel Bluetooth devices."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from bleak.backends.device import BLEDevice
from bluetooth_data_tools import monotonic_time_coarse
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.components.bluetooth.active_update_coordinator import (
    ActiveBluetoothDataUpdateCoordinator,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, EVENT_CORE_CONFIG_UPDATE
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    CONF_FAMILY,
    CONF_MODEL_CODE,
    CONF_POLL_INTERVAL,
    CONF_SYNC_REFERENCE_ALTITUDE,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SYNC_REFERENCE_ALTITUDE,
)
from .kestrel_link.const import DeviceFamily
from .kestrel_link.device import BLEAK_EXCEPTIONS, KestrelBleDevice
from .kestrel_link.models import model_from_code
from .kestrel_link.profiles import ProfileCommand
from .kestrel_link.types import DeviceState, DropSettings, KestrelError

_LOGGER = logging.getLogger(__name__)

type KestrelConfigEntry = ConfigEntry[KestrelCoordinator]


class KestrelCoordinator(ActiveBluetoothDataUpdateCoordinator[DeviceState]):
    """Poll a Kestrel device whenever it advertises and a poll is due.

    The device only advertises its name and model; every measurement has to be
    read over a GATT connection.  Advertisements trigger ``needs_poll`` and a
    poll connects, reads everything and disconnects.

    Home Assistant only dispatches advertisement callbacks when the payload
    changes, and a Kestrel's advertisement is static between button presses, so
    a timer additionally schedules a poll whenever the interval has elapsed and
    the device is still reachable.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: KestrelConfigEntry,
        ble_device: BLEDevice,
    ) -> None:
        """Initialise the coordinator and the underlying BLE device wrapper."""
        self.entry = entry
        address: str = entry.data[CONF_ADDRESS]
        family = DeviceFamily(entry.data.get(CONF_FAMILY, DeviceFamily.DROP))
        self.device = KestrelBleDevice(
            address,
            family,
            ble_device=ble_device,
            name=entry.title,
            model_code=entry.data.get(CONF_MODEL_CODE),
        )
        super().__init__(
            hass,
            _LOGGER,
            address=address,
            mode=BluetoothScanningMode.ACTIVE,
            needs_poll_method=self._needs_poll,
            poll_method=self._async_poll_device,
            connectable=True,
        )

    @property
    def poll_interval(self) -> int:
        """Return the configured minimum seconds between polls."""
        return int(self.entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL))

    @property
    def sync_reference_altitude(self) -> bool:
        """Return True if the device's reference altitude follows HA's elevation."""
        return bool(
            self.entry.options.get(
                CONF_SYNC_REFERENCE_ALTITUDE, DEFAULT_SYNC_REFERENCE_ALTITUDE
            )
        )

    def _target_reference_altitude(self, state: DeviceState) -> int | None:
        """Return the altitude to write, or None if no change is needed."""
        if not self.sync_reference_altitude or state.settings is None:
            return None
        target = round(self.hass.config.elevation)
        if state.settings.reference_altitude_m == target:
            return None
        return target

    async def _async_apply_reference_altitude(self, state: DeviceState) -> DeviceState:
        """Write HA's elevation as the device reference altitude if it differs."""
        if (target := self._target_reference_altitude(state)) is None:
            return state
        _LOGGER.info(
            "%s: setting reference altitude to %s m (Home Assistant elevation)",
            self.address,
            target,
        )
        return await self.device.async_write_settings(
            DropSettings(reference_altitude_m=target)
        )

    @callback
    def _async_core_config_updated(self, _event: Event) -> None:
        """Re-check the reference altitude when the home elevation changes."""
        if self.data is None or self._target_reference_altitude(self.data) is None:
            return
        self._last_poll = None  # make the next check poll immediately
        if (
            service_info := bluetooth.async_last_service_info(
                self.hass, self.address, True
            )
        ) is not None:
            self._last_service_info = service_info
            self._debounced_poll.async_schedule_call()

    @callback
    def _async_start(self) -> None:
        """Start advertisement tracking plus the timed poll fallback."""
        super()._async_start()
        # Check a few times per interval so a poll happens shortly after it is
        # due even when no (changed) advertisement arrives.
        check_every = max(self.poll_interval // 3, 10)
        self._on_stop.append(
            async_track_time_interval(
                self.hass,
                self._async_scheduled_poll,
                timedelta(seconds=check_every),
                name=f"Kestrel {self.address} poll check",
            )
        )
        self._on_stop.append(
            self.hass.bus.async_listen(
                EVENT_CORE_CONFIG_UPDATE, self._async_core_config_updated
            )
        )

    @callback
    def _async_scheduled_poll(self, _now: datetime) -> None:
        """Schedule a poll from the timer if one is due and the device is seen."""
        if self.hass.is_stopping:
            return
        service_info = bluetooth.async_last_service_info(self.hass, self.address, True)
        if service_info is None:
            return
        poll_age = (
            monotonic_time_coarse() - self._last_poll if self._last_poll else None
        )
        if not self._needs_poll(service_info, poll_age):
            return
        self._last_service_info = service_info
        self._debounced_poll.async_schedule_call()

    def _needs_poll(
        self,
        service_info: BluetoothServiceInfoBleak,
        seconds_since_last_poll: float | None,
    ) -> bool:
        """Return True when a poll is due and the device is connectable."""
        if (
            bluetooth.async_ble_device_from_address(
                self.hass, service_info.address, True
            )
            is None
        ):
            return False
        return (
            seconds_since_last_poll is None
            or seconds_since_last_poll >= self.poll_interval
        )

    def _finish_state(self, state: DeviceState, rssi: int | None) -> DeviceState:
        """Fill in details the device layer may not know."""
        if state.model is None and (code := self.entry.data.get(CONF_MODEL_CODE)):
            state.model = model_from_code(int(code))
        if rssi is not None:
            state.rssi = rssi
        if state.name is None:
            state.name = self.entry.title
        return state

    async def _async_poll_device(
        self, service_info: BluetoothServiceInfoBleak
    ) -> DeviceState:
        """Connect to the device and read its full state."""
        self.device.set_ble_device(service_info.device)
        state = await self.device.async_poll()
        state = await self._async_apply_reference_altitude(state)
        return self._finish_state(state, service_info.rssi)

    async def async_initial_poll(self) -> None:
        """Perform the first poll during entry setup.

        Raises:
            ConfigEntryNotReady: if the device cannot be reached.
        """
        try:
            state = await self.device.async_poll()
            state = await self._async_apply_reference_altitude(state)
        except (*BLEAK_EXCEPTIONS, KestrelError, TimeoutError) as err:
            raise ConfigEntryNotReady(
                f"Unable to connect to Kestrel device {self.address}: {err}"
            ) from err
        service_info = bluetooth.async_last_service_info(self.hass, self.address, True)
        self.data = self._finish_state(
            state, service_info.rssi if service_info else None
        )
        # Treat the setup poll as the first poll so the next advertisement does
        # not immediately trigger another connection.
        self._last_poll = monotonic_time_coarse()

    async def async_write_settings(self, settings: DropSettings) -> None:
        """Write settings to the device and publish the refreshed state."""
        state = await self.device.async_write_settings(settings)
        self.data = self._finish_state(state, self.data.rssi if self.data else None)
        self.async_update_listeners()

    async def async_send_command(self, command: ProfileCommand) -> None:
        """Send a one-shot command (identify, erase log, ...)."""
        await self.device.async_send_command(command)

    async def async_set_time(self, when: datetime | None = None) -> None:
        """Set the device clock to ``when`` (default: now, local time)."""
        when = when or dt_util.now()
        device_time = await self.device.async_set_time(when)
        if self.data is not None:
            self.data.device_time = device_time or when.replace(
                tzinfo=None, microsecond=0
            )
            self.async_update_listeners()
