"""Device profiles: how to read and control each Kestrel family over GATT."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import UTC, datetime
from enum import StrEnum
import logging
from typing import Any, Protocol, runtime_checkable

from .const import DeviceFamily, MeasurementKind
from .drop import (
    DROP_MEASUREMENT_CHARS,
    decode_sig_datetime,
    encode_drop_command,
    encode_drop_settings,
    encode_sig_datetime,
    parse_ascii,
    parse_drop_measurement,
    parse_drop_settings,
)
from .k5 import (
    K5_LAYOUTS,
    encode_kestrel_command,
    encode_kestrel_settings,
    parse_k5_characteristic,
    parse_k5_status,
    parse_kestrel_settings,
)
from .types import (
    CharacteristicMissingError,
    DeviceState,
    DropSettings,
    KestrelError,
    KestrelSettings,
    Measurement,
    UnsupportedDeviceError,
)
from .uuids import (
    BATTERY_LEVEL_UUID,
    DROP_COMMANDS_UUID,
    DROP_DATETIME_UUID,
    DROP_NAME_UUID,
    DROP_PROFILE_VERSION_UUID,
    DROP_SERVICE_UUID,
    DROP_SETTINGS_UUID,
    FIRMWARE_REVISION_UUID,
    HARDWARE_REVISION_UUID,
    K5_COMMANDS_UUID,
    K5_DATETIME_UUID,
    K5_NAME_UUID,
    K5_PROFILE_VERSION_UUID,
    K5_SETTINGS_UUID,
    K5_STATUS1_UUID,
    K5_STATUS2_UUID,
    KESTREL_SERVICE_UUID,
    MANUFACTURER_NAME_UUID,
    MODEL_NUMBER_UUID,
    SERIAL_NUMBER_UUID,
    SOFTWARE_REVISION_UUID,
    drop_uuid,
    kestrel_uuid,
)

_LOGGER = logging.getLogger(__name__)


class ProfileCommand(StrEnum):
    """Device-side actions exposed through the commands characteristic."""

    IDENTIFY = "identify"  # blink LED / visual identify
    ERASE_LOG = "erase_log"
    RESTORE_DEFAULTS = "restore_defaults"
    STORE_LOG_POINT = "store_log_point"
    SYNC_BLE_DATA = "sync_ble_data"


@runtime_checkable
class GattClient(Protocol):
    """Subset of the bleak client API used by profiles."""

    async def read_gatt_char(self, char_specifier: Any, **kwargs: Any) -> bytearray:
        """Read a characteristic value."""
        ...

    async def write_gatt_char(
        self, char_specifier: Any, data: bytes | bytearray, response: bool | None = None
    ) -> None:
        """Write a characteristic value."""
        ...


def _gatt_exceptions() -> tuple[type[BaseException], ...]:
    """Return the exception types a failed GATT operation may raise."""
    try:
        from bleak.exc import BleakError  # noqa: PLC0415
    except ImportError:  # pragma: no cover - bleak always present in HA
        return (OSError,)
    return (BleakError, OSError, TimeoutError)


def _resolve_char(client: GattClient, uuid: str) -> Any:
    """Return a characteristic object for ``uuid`` if the client exposes services.

    DROP firmware advertises some Device Information characteristics twice;
    bleak then refuses a plain UUID lookup ("Multiple Characteristics with
    this UUID"), so the first matching characteristic from the service tree is
    used instead.  Falls back to the UUID string when services are unknown.
    """
    services = getattr(client, "services", None)
    if services is None:
        return uuid
    try:
        for service in services:
            for char in service.characteristics:
                if char.uuid.lower() == uuid:
                    return char
    except (AttributeError, TypeError):  # pragma: no cover - exotic clients
        return uuid
    return uuid


async def _read_optional(client: GattClient, uuid: str) -> bytes | None:
    """Read a characteristic, returning None if it is missing or unreadable."""
    try:
        return bytes(await client.read_gatt_char(_resolve_char(client, uuid)))
    except _gatt_exceptions() as err:
        _LOGGER.debug("Characteristic %s not readable: %s", uuid, err)
        return None


async def _read_ascii(client: GattClient, uuid: str) -> str | None:
    return parse_ascii(await _read_optional(client, uuid))


class DeviceProfile(ABC):
    """Family-specific GATT behaviour."""

    family: DeviceFamily
    service_uuid: str
    supported_commands: frozenset[ProfileCommand] = frozenset()
    settings_uuid: str
    commands_uuid: str
    name_uuid: str
    datetime_uuid: str
    profile_version_uuid: str

    def supports(self, command: ProfileCommand) -> bool:
        """Return True if the family implements ``command``."""
        return command in self.supported_commands

    async def read_device_info(self, client: GattClient, state: DeviceState) -> None:
        """Populate ``state.info`` and ``state.name`` from the device."""
        info = state.info
        info.manufacturer = await _read_ascii(client, MANUFACTURER_NAME_UUID)
        info.model_number = await _read_ascii(client, MODEL_NUMBER_UUID)
        info.serial_number = await _read_ascii(client, SERIAL_NUMBER_UUID)
        info.hardware_revision = await _read_ascii(client, HARDWARE_REVISION_UUID)
        info.firmware_revision = await _read_ascii(client, FIRMWARE_REVISION_UUID)
        info.software_revision = await _read_ascii(client, SOFTWARE_REVISION_UUID)
        info.ble_profile_version = await _read_ascii(client, self.profile_version_uuid)
        name = await _read_ascii(client, self.name_uuid)
        if name:
            state.name = name

    async def _read_common(self, client: GattClient, state: DeviceState) -> bool:
        """Read battery and device time; return True if battery was readable."""
        battery = await _read_optional(client, BATTERY_LEVEL_UUID)
        if battery:
            state.raw[BATTERY_LEVEL_UUID] = battery
            state.battery_percent = min(100, max(0, battery[0]))
        dt_raw = await _read_optional(client, self.datetime_uuid)
        if dt_raw is not None:
            state.raw[self.datetime_uuid] = dt_raw
            state.device_time = decode_sig_datetime(dt_raw)
        return battery is not None

    @abstractmethod
    async def _read_measurements(
        self, client: GattClient, state: DeviceState
    ) -> dict[MeasurementKind, Measurement]:
        """Read every measurement characteristic."""

    @abstractmethod
    async def _read_settings(
        self, client: GattClient, state: DeviceState
    ) -> DropSettings | KestrelSettings | None:
        """Read the settings characteristic."""

    async def read_state(self, client: GattClient, state: DeviceState) -> DeviceState:
        """Refresh measurements, battery, settings and time in ``state``."""
        got_battery = await self._read_common(client, state)
        measurements = await self._read_measurements(client, state)
        if not got_battery and not any(m.present for m in measurements.values()):
            raise CharacteristicMissingError(
                f"{state.address}: no battery level and no measurements readable"
            )
        state.measurements = measurements
        state.settings = await self._read_settings(client, state)
        state.updated_at = datetime.now(UTC)
        return state

    @abstractmethod
    def encode_settings(self, settings: DropSettings | KestrelSettings) -> bytes:
        """Encode a settings dataclass for the settings characteristic."""

    @abstractmethod
    def encode_command(self, command: ProfileCommand) -> bytes:
        """Encode a command for the commands characteristic."""

    async def write_settings(
        self, client: GattClient, settings: DropSettings | KestrelSettings
    ) -> None:
        """Write settings; fields left None are preserved on the device."""
        if settings.is_empty():
            return
        await client.write_gatt_char(
            self.settings_uuid, self.encode_settings(settings), response=True
        )

    async def send_command(self, client: GattClient, command: ProfileCommand) -> None:
        """Trigger a device-side command."""
        if not self.supports(command):
            raise UnsupportedDeviceError(f"{self.family} does not support {command}")
        await client.write_gatt_char(
            self.commands_uuid, self.encode_command(command), response=True
        )

    async def write_time(self, client: GattClient, when: datetime) -> None:
        """Set the device clock (``when`` is interpreted as device-local time)."""
        await client.write_gatt_char(
            self.datetime_uuid, encode_sig_datetime(when), response=True
        )

    async def write_name(self, client: GattClient, name: str) -> None:
        """Set the advertised device name."""
        from .drop import encode_name  # noqa: PLC0415

        await client.write_gatt_char(self.name_uuid, encode_name(name), response=True)


class DropProfile(DeviceProfile):
    """Kestrel DROP D1/D2/D3."""

    family = DeviceFamily.DROP
    service_uuid = DROP_SERVICE_UUID
    supported_commands = frozenset(
        {
            ProfileCommand.IDENTIFY,
            ProfileCommand.ERASE_LOG,
            ProfileCommand.RESTORE_DEFAULTS,
        }
    )
    settings_uuid = DROP_SETTINGS_UUID
    commands_uuid = DROP_COMMANDS_UUID
    name_uuid = DROP_NAME_UUID
    datetime_uuid = DROP_DATETIME_UUID
    profile_version_uuid = DROP_PROFILE_VERSION_UUID

    async def _read_measurements(
        self, client: GattClient, state: DeviceState
    ) -> dict[MeasurementKind, Measurement]:
        out: dict[MeasurementKind, Measurement] = {}
        # After the first poll, skip characteristics whose status byte said the
        # measurement is not implemented on this model.  A characteristic that
        # merely failed to read (empty raw) is retried on every poll so a
        # transient BLE error cannot hide a sensor until the next restart.
        for short, spec in DROP_MEASUREMENT_CHARS.items():
            previous = state.measurements.get(spec.kind)
            if previous is not None and not previous.present and previous.raw:
                out[spec.kind] = previous
                continue
            uuid = drop_uuid(short)
            raw = await _read_optional(client, uuid)
            if raw is not None:
                state.raw[uuid] = raw
            out[spec.kind] = parse_drop_measurement(spec, raw)
        return out

    async def _read_settings(
        self, client: GattClient, state: DeviceState
    ) -> DropSettings | None:
        raw = await _read_optional(client, self.settings_uuid)
        if raw is None or len(raw) < 9:
            return None
        state.raw[self.settings_uuid] = raw
        return parse_drop_settings(raw)

    def encode_settings(self, settings: DropSettings | KestrelSettings) -> bytes:
        return encode_drop_settings(settings)

    def encode_command(self, command: ProfileCommand) -> bytes:
        return encode_drop_command(
            erase_log=command is ProfileCommand.ERASE_LOG,
            blink_led=command is ProfileCommand.IDENTIFY,
            restore_defaults=command is ProfileCommand.RESTORE_DEFAULTS,
        )


class KestrelProfile(DeviceProfile):
    """Kestrel 5000 / 7000 / 3550 (shared BLE profile)."""

    family = DeviceFamily.KESTREL_5000
    service_uuid = KESTREL_SERVICE_UUID
    supported_commands = frozenset(
        {
            ProfileCommand.IDENTIFY,
            ProfileCommand.ERASE_LOG,
            ProfileCommand.RESTORE_DEFAULTS,
            ProfileCommand.STORE_LOG_POINT,
            ProfileCommand.SYNC_BLE_DATA,
        }
    )
    settings_uuid = K5_SETTINGS_UUID
    commands_uuid = K5_COMMANDS_UUID
    name_uuid = K5_NAME_UUID
    datetime_uuid = K5_DATETIME_UUID
    profile_version_uuid = K5_PROFILE_VERSION_UUID

    def __init__(self, family: DeviceFamily = DeviceFamily.KESTREL_5000) -> None:
        self.family = family

    async def _read_measurements(
        self, client: GattClient, state: DeviceState
    ) -> dict[MeasurementKind, Measurement]:
        status1 = await _read_optional(client, K5_STATUS1_UUID)
        status2 = await _read_optional(client, K5_STATUS2_UUID)
        if status1 is not None:
            state.raw[K5_STATUS1_UUID] = status1
        if status2 is not None:
            state.raw[K5_STATUS2_UUID] = status2
        present = parse_k5_status(status1, status2)
        out: dict[MeasurementKind, Measurement] = {}
        for short, fields in K5_LAYOUTS.items():
            if not any(f.kind in present for f in fields):
                out.update(parse_k5_characteristic(short, None, present))
                continue
            uuid = kestrel_uuid(short)
            raw = await _read_optional(client, uuid)
            if raw is not None:
                state.raw[uuid] = raw
            out.update(parse_k5_characteristic(short, raw, present))
        return out

    async def _read_settings(
        self, client: GattClient, state: DeviceState
    ) -> KestrelSettings | None:
        raw = await _read_optional(client, self.settings_uuid)
        if raw is None or len(raw) < 10:
            return None
        state.raw[self.settings_uuid] = raw
        return parse_kestrel_settings(raw)

    def encode_settings(self, settings: DropSettings | KestrelSettings) -> bytes:
        if not isinstance(settings, KestrelSettings):
            settings = KestrelSettings(
                log_interval_s=settings.log_interval_s,
                wrap_log=settings.wrap_log,
                transmission_rate_s=settings.transmission_rate_s,
                security_level=settings.security_level,
                setup_complete=settings.setup_complete,
                reference_altitude_m=settings.reference_altitude_m,
            )
        return encode_kestrel_settings(settings)

    def encode_command(self, command: ProfileCommand) -> bytes:
        return encode_kestrel_command(
            erase_log=command is ProfileCommand.ERASE_LOG,
            restore_defaults=command is ProfileCommand.RESTORE_DEFAULTS,
            visual_identify=command is ProfileCommand.IDENTIFY,
            sync_ble_data=command is ProfileCommand.SYNC_BLE_DATA,
            store_log_point=command is ProfileCommand.STORE_LOG_POINT,
        )


_KESTREL_FAMILIES: frozenset[DeviceFamily] = frozenset(
    {DeviceFamily.KESTREL_5000, DeviceFamily.KESTREL_7000, DeviceFamily.KESTREL_3550}
)


def get_profile(family: DeviceFamily) -> DeviceProfile:
    """Return the profile for a device family.

    Raises:
        UnsupportedDeviceError: if the family has no measurement profile.
    """
    if family is DeviceFamily.DROP:
        return DropProfile()
    if family in _KESTREL_FAMILIES:
        return KestrelProfile(family)
    raise UnsupportedDeviceError(f"No GATT profile for family {family}")


def supported_families() -> Iterable[DeviceFamily]:
    """Return families for which ``get_profile`` succeeds."""
    return (DeviceFamily.DROP, *sorted(_KESTREL_FAMILIES))


__all__ = [
    "DeviceProfile",
    "DropProfile",
    "GattClient",
    "KestrelError",
    "KestrelProfile",
    "ProfileCommand",
    "get_profile",
    "supported_families",
]
