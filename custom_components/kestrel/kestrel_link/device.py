"""Connection management for a single Kestrel BLE device."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import copy
from datetime import UTC, datetime
import logging
from typing import TYPE_CHECKING, Any

from bleak.exc import BleakError as _BleakError

from .client import LinkClient
from .const import DeviceFamily, FieldName
from .derived import add_derived_measurements
from .models import model_from_code
from .profiles import DeviceProfile, ProfileCommand, get_profile
from .transport import LinkTransport
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


def _field_label(code: int) -> str:
    """Return a readable label for a LiNK field name code."""
    try:
        return FieldName(code).name.lower()
    except ValueError:
        return f"field_{code}"


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
        # DROP firmware treats the GATT Date/Time characteristic as a plain
        # register: it returns whatever was last written and never advances.
        # The running clock is only reachable through the LiNK Get/Set Time
        # commands, so the DROP profile reads/sets the clock over LiNK.
        self.use_link_clock = family is DeviceFamily.DROP
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
        self.state.battery_source = (
            "gatt" if self.state.battery_percent is not None else None
        )
        if self.use_link_clock:
            await self._read_link_status(client)
            # The LiNK session can take a while on a weak link; stamp the
            # state when it actually finished.
            self.state.updated_at = datetime.now(UTC)
        add_derived_measurements(self.state)
        return self.state

    async def _with_link[T](
        self, client: BleakClient, fn: Callable[[LinkClient], Awaitable[T]]
    ) -> T:
        """Run ``fn`` with a LiNK client over the Mass Transfer Service."""
        transport = LinkTransport(client)
        await transport.start()
        try:
            return await fn(LinkClient(transport))
        finally:
            await transport.stop()

    async def _read_link_status(self, client: BleakClient) -> None:
        """Read the running clock and battery level over LiNK (best effort).

        The DROP's Battery Service characteristic only reports coarse steps,
        whereas LiNK Get Battery Level returns the percentage the Kestrel app
        shows, so the LiNK value is preferred when available.
        """

        async def _read(
            link: LinkClient,
        ) -> tuple[datetime | None, int | None, dict[str, Any] | None]:
            clock = await link.get_time()
            try:
                battery: int | None = await link.get_battery()
            except KestrelError as err:
                _LOGGER.debug("%s: LiNK battery read failed: %s", self.address, err)
                battery = None
            snapshot: dict[str, Any] | None = None
            try:
                record = await link.get_data_snapshot()
            except KestrelError as err:
                _LOGGER.debug("%s: LiNK snapshot failed: %s", self.address, err)
            else:
                if record is not None:
                    snapshot = {
                        _field_label(code): value
                        for code, value in record.values.items()
                    }
                    snapshot["timestamp"] = record.timestamp
            return clock, battery, snapshot

        try:
            clock, battery, snapshot = await self._with_link(client, _read)
        except (*BLEAK_EXCEPTIONS, KestrelError, AttributeError, TypeError) as err:
            _LOGGER.debug("%s: LiNK status read failed: %s", self.address, err)
            self.state.device_time = None
            return
        self.state.device_time = clock
        self.state.link_snapshot = snapshot
        if battery is not None and 0 <= battery <= 100:
            self.state.raw["link:battery"] = battery.to_bytes(2, "little")
            self.state.battery_percent = battery
            self.state.battery_source = "link"

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

    async def async_set_time(self, when: datetime | None = None) -> datetime | None:
        """Set the device clock; defaults to the current local time.

        Writes the GATT Date/Time characteristic and, for families whose
        running clock lives behind LiNK, also issues Set Time over LiNK and
        reads the clock back.  Returns the device's clock after the write.
        """
        target = when if when is not None else datetime.now().astimezone()
        naive = target.replace(tzinfo=None, microsecond=0)

        async def _do(client: BleakClient) -> datetime | None:
            await self.profile.write_time(client, naive)
            if not self.use_link_clock:
                return naive

            async def _sync(link: LinkClient) -> datetime | None:
                await link.set_time(naive, drop_layout=True)
                return await link.get_time()

            return await self._with_link(client, _sync)

        result = await self.async_run(_do)
        self.state.device_time = result if result is not None else naive
        return self.state.device_time

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
