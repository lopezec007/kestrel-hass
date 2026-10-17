"""Connection management for a single Kestrel BLE device."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import copy
from datetime import datetime
import logging
from typing import TYPE_CHECKING, Any

from bleak.exc import BleakError as _BleakError

from .const import DeviceFamily
from .models import model_from_code
from .profiles import DeviceProfile, ProfileCommand, get_profile
from .types import DeviceState, DropSettings, KestrelError, KestrelSettings

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.device import BLEDevice

_LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 3


# Fixed-length so ``except (*BLEAK_EXCEPTIONS, Other)`` type-checks.
BLEAK_EXCEPTIONS: tuple[type[_BleakError], type[TimeoutError], type[OSError]] = (
    _BleakError,
    TimeoutError,
    OSError,
)


class KestrelBleDevice:
    """Short-lived, serialised connections to one Kestrel device."""

    def __init__(
        self,
        address: str,
        family: DeviceFamily,
        *,
        ble_device: BLEDevice | None = None,
        name: str | None = None,
        model_code: int | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        profile: DeviceProfile | None = None,
    ) -> None:
        self.address = address
        self.family = family
        ble_name = getattr(ble_device, "name", None) if ble_device is not None else None
        self.name = name or ble_name or address
        self.profile: DeviceProfile = profile or get_profile(family)
        self._ble_device = ble_device
        self._max_attempts = max_attempts
        self._lock = asyncio.Lock()
        self._info_loaded = False
        self.state: DeviceState = DeviceState(
            address=address,
            family=family,
            model=model_from_code(model_code),
            name=name,
        )

    # ------------------------------------------------------------------ #
    # Configuration
    # ------------------------------------------------------------------ #

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        """Update the BLEDevice used for the next connection."""
        self._ble_device = ble_device
        ble_name = getattr(ble_device, "name", None)
        if ble_name:
            if self.name == self.address:
                self.name = ble_name
            if not self.state.name:
                self.state.name = ble_name

    def set_max_attempts(self, attempts: int) -> None:
        """Change how many connection attempts are made per operation."""
        self._max_attempts = attempts

    @property
    def ble_device(self) -> BLEDevice | None:
        """Return the current BLEDevice."""
        return self._ble_device

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #

    async def _connect(self) -> BleakClient:
        if self._ble_device is None:
            raise KestrelError(f"{self.address}: no BLEDevice available to connect")
        from bleak_retry_connector import (  # noqa: PLC0415
            BleakClientWithServiceCache,
            establish_connection,
        )

        return await establish_connection(
            BleakClientWithServiceCache,
            self._ble_device,
            self.name,
            disconnected_callback=self._on_disconnect,
            max_attempts=self._max_attempts,
        )

    def _on_disconnect(self, _client: Any) -> None:
        _LOGGER.debug("%s: disconnected", self.address)

    async def async_run[T](self, fn: Callable[[BleakClient], Awaitable[T]]) -> T:
        """Run ``fn`` with a connected client, serialised per device."""
        async with self._lock:
            client = await self._connect()
            try:
                return await fn(client)
            finally:
                try:
                    await client.disconnect()
                except BLEAK_EXCEPTIONS as err:  # pragma: no cover - best effort
                    _LOGGER.debug("%s: disconnect failed: %s", self.address, err)

    # ------------------------------------------------------------------ #
    # Operations
    # ------------------------------------------------------------------ #

    async def _poll(self, client: BleakClient) -> DeviceState:
        if not self._info_loaded:
            await self.profile.read_device_info(client, self.state)
            self._info_loaded = True
            self._fill_info_fallbacks()
        await self.profile.read_state(client, self.state)
        return self.state

    async def async_poll(self, *, rssi: int | None = None) -> DeviceState:
        """Connect, read everything, disconnect, and return a state snapshot."""
        await self.async_run(self._poll)
        if rssi is not None:
            self.state.rssi = rssi
        return self.snapshot()

    async def async_write_settings(
        self, settings: DropSettings | KestrelSettings
    ) -> DeviceState:
        """Write settings and re-read the device state in one connection."""

        async def _do(client: BleakClient) -> DeviceState:
            await self.profile.write_settings(client, settings)
            return await self._poll(client)

        await self.async_run(_do)
        return self.snapshot()

    async def async_send_command(self, command: ProfileCommand) -> None:
        """Send a device command (identify, erase log, ...)."""

        async def _do(client: BleakClient) -> None:
            await self.profile.send_command(client, command)

        await self.async_run(_do)

    async def async_set_time(self, when: datetime | None = None) -> None:
        """Set the device clock; defaults to the current local time."""
        target = when if when is not None else datetime.now().astimezone()

        async def _do(client: BleakClient) -> None:
            await self.profile.write_time(client, target)

        await self.async_run(_do)
        self.state.device_time = target.replace(tzinfo=None)

    def _fill_info_fallbacks(self) -> None:
        """Derive identity fields the device did not expose over GATT.

        DROP units do not answer Device Information Service reads, but their
        advertised name is ``"<model> - <serial>"``.
        """
        info = self.state.info
        name = self.state.name or self.name
        if info.serial_number is None and name and " - " in name:
            serial = name.rsplit(" - ", 1)[1].strip()
            if serial:
                info.serial_number = serial
        if info.model_number is None and self.state.model is not None:
            info.model_number = self.state.model.name
        if info.manufacturer is None:
            info.manufacturer = "Nielsen-Kellerman"

    def snapshot(self) -> DeviceState:
        """Return a deep copy of the current state."""
        return copy.deepcopy(self.state)


__all__ = ["BLEAK_EXCEPTIONS", "KestrelBleDevice"]
