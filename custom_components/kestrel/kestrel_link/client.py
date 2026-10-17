"""High-level LiNK commands on top of :class:`LinkTransport`."""

from __future__ import annotations

from datetime import datetime
import logging

from .const import LOG_INTERVALS_S, CommandCode
from .decoding import decode_bt_datetime, decode_int, encode_bt_datetime
from .transport import LinkResponse, LinkTransport
from .types import DataLogResult, DeviceInfo, LinkRecord, ProtocolError

_LOGGER = logging.getLogger(__name__)

_SEQUENCE_SIZE = 8


def _ascii(response: LinkResponse) -> str:
    return response.payload.split(b"\x00", 1)[0].decode("ascii", errors="replace")


def _uint(response: LinkResponse, size: int) -> int:
    payload = response.payload
    if len(payload) < size:
        raise ProtocolError(
            f"Expected {size} byte integer, got {len(payload)} bytes for command "
            f"{response.command}"
        )
    return decode_int(payload[:size], signed=False)


class LinkClient:
    """Convenience wrappers for the LiNK commands weather devices implement."""

    def __init__(self, transport: LinkTransport) -> None:
        self._transport = transport

    @property
    def transport(self) -> LinkTransport:
        """Return the underlying transport."""
        return self._transport

    # ------------------------------------------------------------------ #
    # Identity
    # ------------------------------------------------------------------ #

    async def get_serial(self) -> str:
        """Return the device serial number."""
        return _ascii(await self._transport.send_command(CommandCode.GET_DEVICE_SERIAL))

    async def get_model(self) -> str:
        """Return the device model number string."""
        return _ascii(await self._transport.send_command(CommandCode.GET_DEVICE_MODEL))

    async def get_firmware(self) -> str:
        """Return the firmware version string."""
        return _ascii(
            await self._transport.send_command(CommandCode.GET_DEVICE_FIRMWARE)
        )

    async def get_hardware(self) -> str:
        """Return the hardware version string."""
        return _ascii(
            await self._transport.send_command(CommandCode.GET_DEVICE_HARDWARE)
        )

    async def get_name(self) -> str:
        """Return the user-visible device name."""
        return _ascii(await self._transport.send_command(CommandCode.GET_DEVICE_NAME))

    async def set_name(self, name: str) -> None:
        """Set the device name (ASCII, no terminator)."""
        await self._transport.send_command(
            CommandCode.SET_DEVICE_NAME, name.encode("ascii"), expect_data=False
        )

    async def read_identity(self) -> DeviceInfo:
        """Read serial, model, firmware and hardware strings."""
        return DeviceInfo(
            model_number=await self.get_model(),
            serial_number=await self.get_serial(),
            hardware_revision=await self.get_hardware(),
            firmware_revision=await self.get_firmware(),
        )

    # ------------------------------------------------------------------ #
    # Clock & battery
    # ------------------------------------------------------------------ #

    async def get_time(self) -> datetime | None:
        """Return the device clock (naive, device-local time)."""
        response = await self._transport.send_command(CommandCode.GET_TIME)
        raw = response.payload
        if not raw:
            for command in response.commands:
                if command.command == CommandCode.SET_TIME:
                    raw = command.parameters
                    break
        return decode_bt_datetime(raw) if raw else None

    async def set_time(self, when: datetime) -> None:
        """Set the device clock."""
        await self._transport.send_command(
            CommandCode.SET_TIME, encode_bt_datetime(when), expect_data=False
        )

    async def get_battery(self) -> int:
        """Return the battery percentage (0-100)."""
        return _uint(
            await self._transport.send_command(CommandCode.GET_BATTERY_LEVEL), 2
        )

    # ------------------------------------------------------------------ #
    # Data
    # ------------------------------------------------------------------ #

    async def get_data_snapshot(self) -> LinkRecord | None:
        """Return the current values of all measurements, or None."""
        response = await self._transport.send_command(CommandCode.GET_DATA_SNAPSHOT)
        records = response.records(numbered=False)
        return records[0] if records else None

    async def get_data_log_record_count(self) -> int:
        """Return the number of records in the data log."""
        return _uint(
            await self._transport.send_command(CommandCode.GET_DATA_LOG_RECORD_COUNT),
            4,
        )

    async def get_data_log_record_count_after(self, sequence: int) -> int:
        """Return the number of log records after ``sequence``."""
        return _uint(
            await self._transport.send_command(
                CommandCode.GET_DATA_LOG_RECORD_COUNT_AFTER,
                sequence.to_bytes(_SEQUENCE_SIZE, "little"),
            ),
            4,
        )

    async def get_data_log(self, after: int | None = None) -> DataLogResult:
        """Download the data log, optionally only records after ``after``."""
        if after is None:
            response = await self._transport.send_command(CommandCode.GET_DATA_LOG)
        else:
            response = await self._transport.send_command(
                CommandCode.GET_DATA_LOG_AFTER,
                int(after).to_bytes(_SEQUENCE_SIZE, "little"),
            )
        last_sequence: int | None = None
        if response.end_of_data and len(response.end_of_data) >= _SEQUENCE_SIZE:
            last_sequence = decode_int(
                response.end_of_data[:_SEQUENCE_SIZE], signed=False
            )
        fields = tuple(f for meta in response.metadata for f in meta.fields)
        return DataLogResult(
            records=response.records(numbered=True),
            last_sequence=last_sequence,
            fields=fields,
        )

    async def erase_data_log(self) -> None:
        """Erase every record in the data log."""
        await self._transport.send_command(
            CommandCode.ERASE_DATA_LOG, expect_data=False
        )

    # ------------------------------------------------------------------ #
    # Settings
    # ------------------------------------------------------------------ #

    async def set_log_interval(self, seconds: int) -> None:
        """Set the data log interval; 0 disables logging.

        Raises:
            ValueError: If ``seconds`` is not one of the documented intervals.
        """
        if seconds not in LOG_INTERVALS_S:
            raise ValueError(f"Unsupported log interval {seconds}s")
        await self._transport.send_command(
            CommandCode.SET_LOG_INTERVAL,
            int(seconds).to_bytes(3, "little"),
            expect_data=False,
        )

    async def set_log_wrap(self, enabled: bool) -> None:
        """Enable or disable overwriting the oldest log records when full."""
        await self._transport.send_command(
            CommandCode.SET_LOG_WRAP_ENABLE,
            bytes([1 if enabled else 0]),
            expect_data=False,
        )

    # ------------------------------------------------------------------ #
    # Diagnostics
    # ------------------------------------------------------------------ #

    async def echo(self, data: bytes) -> bytes:
        """Send an echo test packet and return what the device sent back."""
        response = await self._transport.send_command(
            CommandCode.ECHO_TEST_PACKET, data, expect_data=True
        )
        return response.payload


__all__ = ["LinkClient"]
