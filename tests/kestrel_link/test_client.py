"""Tests for LinkClient using a scripted fake transport."""

from __future__ import annotations

from datetime import datetime

import pytest

from custom_components.kestrel.kestrel_link.client import LinkClient
from custom_components.kestrel.kestrel_link.const import CommandCode, FieldName
from custom_components.kestrel.kestrel_link.transport import LinkResponse
from custom_components.kestrel.kestrel_link.types import (
    CommandPacket,
    DataPacket,
    FieldDescriptor,
    MetadataPacket,
    ProtocolError,
)

SNAPSHOT_FIELDS = (
    FieldDescriptor(FieldName.TIMESTAMP, 36, 7),
    FieldDescriptor(FieldName.DRY_BULB_TEMP, 28, 2),
    FieldDescriptor(FieldName.RELATIVE_HUMIDITY, 27, 2),
    FieldDescriptor(FieldName.HEAT_INDEX, 28, 2),
    FieldDescriptor(FieldName.DEW_POINT, 28, 2),
)
RECORD = bytes.fromhex("DD0701010000019209A00FD70AD007")


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[int, bytes, bool | None]] = []
        self.replies: dict[int, LinkResponse] = {}

    async def send_command(
        self, code: int, params: bytes = b"", *, expect_data: bool | None = None
    ) -> LinkResponse:
        self.calls.append((int(code), bytes(params), expect_data))
        return self.replies.get(int(code), LinkResponse(command=int(code), acked=True))

    def reply_data(self, code: int, payload: bytes) -> None:
        self.replies[int(code)] = LinkResponse(
            command=int(code), acked=True, data=[DataPacket(payload)]
        )


@pytest.fixture
def pair() -> tuple[LinkClient, FakeTransport]:
    transport = FakeTransport()
    return LinkClient(transport), transport  # type: ignore[arg-type]


async def test_identity_strings(pair: tuple[LinkClient, FakeTransport]) -> None:
    client, transport = pair
    transport.reply_data(CommandCode.GET_DEVICE_SERIAL, b"1234567")
    transport.reply_data(CommandCode.GET_DEVICE_MODEL, b"D3\x00\x00")
    transport.reply_data(CommandCode.GET_DEVICE_FIRMWARE, b"1.23")
    transport.reply_data(CommandCode.GET_DEVICE_HARDWARE, b"2")
    transport.reply_data(CommandCode.GET_DEVICE_NAME, b"Garage DROP")
    assert await client.get_serial() == "1234567"
    assert await client.get_model() == "D3"
    assert await client.get_firmware() == "1.23"
    assert await client.get_hardware() == "2"
    assert await client.get_name() == "Garage DROP"
    info = await client.read_identity()
    assert info.serial_number == "1234567"
    assert info.model_number == "D3"
    assert info.firmware_revision == "1.23"
    assert info.hardware_revision == "2"
    assert client.transport is transport


async def test_set_name(pair: tuple[LinkClient, FakeTransport]) -> None:
    client, transport = pair
    await client.set_name("Shed")
    assert transport.calls == [(CommandCode.SET_DEVICE_NAME, b"Shed", False)]


async def test_time(pair: tuple[LinkClient, FakeTransport]) -> None:
    client, transport = pair
    transport.reply_data(CommandCode.GET_TIME, bytes.fromhex("EA070A110C1E2D"))
    assert await client.get_time() == datetime(2026, 10, 17, 12, 30, 45)
    await client.set_time(datetime(2026, 10, 17, 12, 30, 45))
    assert transport.calls[-1] == (
        CommandCode.SET_TIME,
        bytes.fromhex("EA070A110C1E2D"),
        False,
    )


async def test_time_via_set_time_command(
    pair: tuple[LinkClient, FakeTransport],
) -> None:
    client, transport = pair
    transport.replies[CommandCode.GET_TIME] = LinkResponse(
        command=CommandCode.GET_TIME,
        acked=True,
        commands=[CommandPacket(CommandCode.SET_TIME, bytes.fromhex("EA070A110C1E2D"))],
    )
    assert await client.get_time() == datetime(2026, 10, 17, 12, 30, 45)


async def test_time_missing(pair: tuple[LinkClient, FakeTransport]) -> None:
    client, _ = pair
    assert await client.get_time() is None


async def test_battery(pair: tuple[LinkClient, FakeTransport]) -> None:
    client, transport = pair
    transport.reply_data(CommandCode.GET_BATTERY_LEVEL, b"\x57\x00")
    assert await client.get_battery() == 87


async def test_battery_short_payload(pair: tuple[LinkClient, FakeTransport]) -> None:
    client, transport = pair
    transport.reply_data(CommandCode.GET_BATTERY_LEVEL, b"\x57")
    with pytest.raises(ProtocolError):
        await client.get_battery()


async def test_snapshot(pair: tuple[LinkClient, FakeTransport]) -> None:
    client, transport = pair
    transport.replies[CommandCode.GET_DATA_SNAPSHOT] = LinkResponse(
        command=CommandCode.GET_DATA_SNAPSHOT,
        acked=True,
        metadata=[MetadataPacket(SNAPSHOT_FIELDS, start=True)],
        data=[DataPacket(RECORD)],
        end_of_data=b"",
    )
    record = await client.get_data_snapshot()
    assert record is not None
    assert record.timestamp == datetime(2013, 1, 1, 0, 0, 1)
    assert record.get(FieldName.DRY_BULB_TEMP) == pytest.approx(24.5)


async def test_snapshot_empty(pair: tuple[LinkClient, FakeTransport]) -> None:
    client, _ = pair
    assert await client.get_data_snapshot() is None


async def test_log_counts(pair: tuple[LinkClient, FakeTransport]) -> None:
    client, transport = pair
    transport.reply_data(
        CommandCode.GET_DATA_LOG_RECORD_COUNT, (1000).to_bytes(4, "little")
    )
    transport.reply_data(
        CommandCode.GET_DATA_LOG_RECORD_COUNT_AFTER, (12).to_bytes(4, "little")
    )
    assert await client.get_data_log_record_count() == 1000
    assert await client.get_data_log_record_count_after(988) == 12
    assert transport.calls[-1] == (
        CommandCode.GET_DATA_LOG_RECORD_COUNT_AFTER,
        (988).to_bytes(8, "little"),
        None,
    )


def _log_response(code: int, sequence: int | None) -> LinkResponse:
    return LinkResponse(
        command=code,
        acked=True,
        metadata=[MetadataPacket(SNAPSHOT_FIELDS, start=True)],
        data=[DataPacket(b"\x00\x00" + RECORD * 2), DataPacket(b"\x01\x00" + RECORD)],
        end_of_data=sequence.to_bytes(8, "little") if sequence is not None else b"",
    )


async def test_get_data_log_all(pair: tuple[LinkClient, FakeTransport]) -> None:
    client, transport = pair
    transport.replies[CommandCode.GET_DATA_LOG] = _log_response(
        CommandCode.GET_DATA_LOG, 42
    )
    result = await client.get_data_log()
    assert len(result.records) == 3
    assert result.last_sequence == 42
    assert transport.calls == [(CommandCode.GET_DATA_LOG, b"", None)]


async def test_get_data_log_after(pair: tuple[LinkClient, FakeTransport]) -> None:
    client, transport = pair
    transport.replies[CommandCode.GET_DATA_LOG_AFTER] = _log_response(
        CommandCode.GET_DATA_LOG_AFTER, None
    )
    result = await client.get_data_log(after=40)
    assert len(result.records) == 3
    assert result.last_sequence is None
    assert transport.calls == [
        (CommandCode.GET_DATA_LOG_AFTER, (40).to_bytes(8, "little"), None)
    ]


async def test_erase_and_wrap(pair: tuple[LinkClient, FakeTransport]) -> None:
    client, transport = pair
    await client.erase_data_log()
    await client.set_log_wrap(True)
    await client.set_log_wrap(False)
    assert transport.calls == [
        (CommandCode.ERASE_DATA_LOG, b"", False),
        (CommandCode.SET_LOG_WRAP_ENABLE, b"\x01", False),
        (CommandCode.SET_LOG_WRAP_ENABLE, b"\x00", False),
    ]


@pytest.mark.parametrize("seconds", [0, 2, 600, 43200])
async def test_set_log_interval(
    pair: tuple[LinkClient, FakeTransport], seconds: int
) -> None:
    client, transport = pair
    await client.set_log_interval(seconds)
    assert transport.calls == [
        (CommandCode.SET_LOG_INTERVAL, seconds.to_bytes(3, "little"), False)
    ]


@pytest.mark.parametrize("seconds", [1, 3, 86400, -5])
async def test_set_log_interval_invalid(
    pair: tuple[LinkClient, FakeTransport], seconds: int
) -> None:
    client, transport = pair
    with pytest.raises(ValueError):
        await client.set_log_interval(seconds)
    assert transport.calls == []


async def test_echo(pair: tuple[LinkClient, FakeTransport]) -> None:
    client, transport = pair
    transport.reply_data(CommandCode.ECHO_TEST_PACKET, b"ping")
    assert await client.echo(b"ping") == b"ping"
    assert transport.calls == [(CommandCode.ECHO_TEST_PACKET, b"ping", True)]
