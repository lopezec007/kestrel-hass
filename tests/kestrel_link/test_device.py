"""Tests for KestrelBleDevice."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
import pytest

from custom_components.kestrel.kestrel_link import uuids
from custom_components.kestrel.kestrel_link.const import (
    DeviceFamily,
    MeasurementKind as MK,  # noqa: N817,
)
from custom_components.kestrel.kestrel_link.device import (
    BLEAK_EXCEPTIONS,
    KestrelBleDevice,
)
from custom_components.kestrel.kestrel_link.profiles import ProfileCommand
from custom_components.kestrel.kestrel_link.types import (
    CharacteristicMissingError,
    DropSettings,
    KestrelError,
    UnsupportedDeviceError,
)

from .conftest import FakeGattClient

ADDR = "AA:BB:CC:DD:EE:FF"
ESTABLISH = "bleak_retry_connector.establish_connection"


def _chars() -> dict[str, bytes]:
    return {
        uuids.BATTERY_LEVEL_UUID: b"\x5a",
        uuids.SERIAL_NUMBER_UUID: b"12345678",
        uuids.DROP_NAME_UUID: b"D3 - 12345678" + bytes(7),
        uuids.DROP_SETTINGS_UUID: (600).to_bytes(3, "little")
        + b"\x01\x05\x00\x01"
        + bytes(2)
        + b"\xff" * 11,
        uuids.DROP_COMMANDS_UUID: bytes(20),
        uuids.DROP_DATETIME_UUID: b"\xdd\x07\x01\x01\x00\x00\x01",
        uuids.drop_uuid(1): b"\x07\x2b\x09",
        uuids.drop_uuid(2): b"\x07" + (4000).to_bytes(2, "little"),
    }


def _ble_device() -> BLEDevice:
    return BLEDevice(ADDR, "D3 - 12345678", {})


async def test_poll_reads_info_once_and_returns_snapshot() -> None:
    client = FakeGattClient(_chars())
    calls = []

    async def fake_establish(cls, device, name, **kwargs):
        calls.append((cls.__name__, device.address, name, kwargs))
        return client

    dev = KestrelBleDevice(
        ADDR, DeviceFamily.DROP, ble_device=_ble_device(), model_code=552
    )
    with patch(ESTABLISH, side_effect=fake_establish):
        state = await dev.async_poll(rssi=-60)
        assert client.disconnected
        client.disconnected = False
        client.reads.clear()
        state2 = await dev.async_poll()

    assert calls[0][0] == "BleakClientWithServiceCache"
    assert calls[0][2] == "D3 - 12345678"
    assert calls[0][3]["max_attempts"] == 3
    assert state.info.serial_number == "12345678"
    assert state.model is not None and state.model.name == "Kestrel DROP D3"
    assert state.value(MK.TEMPERATURE) == 23.47
    assert state.rssi == -60
    assert state.battery_percent == 90
    assert state is not dev.state  # snapshot is a copy
    assert uuids.SERIAL_NUMBER_UUID not in client.reads  # info read only once
    assert state2.rssi == -60
    assert client.disconnected


async def test_disconnect_in_finally_on_error() -> None:
    client = FakeGattClient({uuids.DROP_SETTINGS_UUID: bytes(20)})
    dev = KestrelBleDevice(ADDR, DeviceFamily.DROP, ble_device=_ble_device())
    with (
        patch(ESTABLISH, return_value=client),
        pytest.raises(CharacteristicMissingError),
    ):
        await dev.async_poll()
    assert client.disconnected


async def test_bleak_error_propagates() -> None:
    dev = KestrelBleDevice(ADDR, DeviceFamily.DROP, ble_device=_ble_device())
    with (
        patch(ESTABLISH, side_effect=BleakError("boom")),
        pytest.raises(BLEAK_EXCEPTIONS),
    ):
        await dev.async_poll()


async def test_no_ble_device_raises() -> None:
    dev = KestrelBleDevice(ADDR, DeviceFamily.DROP)
    with pytest.raises(KestrelError):
        await dev.async_poll()
    dev.set_ble_device(_ble_device())
    assert dev.ble_device is not None and dev.state.name == "D3 - 12345678"


def test_unsupported_family() -> None:
    with pytest.raises(UnsupportedDeviceError):
        KestrelBleDevice(ADDR, DeviceFamily.SPEEDCOACH)


async def test_lock_serialises_connections() -> None:
    client = FakeGattClient(_chars())
    active = 0
    max_active = 0

    async def fake_establish(*args, **kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return client

    dev = KestrelBleDevice(ADDR, DeviceFamily.DROP, ble_device=_ble_device())
    with patch(ESTABLISH, side_effect=fake_establish):
        await asyncio.gather(
            dev.async_poll(),
            dev.async_poll(),
            dev.async_send_command(ProfileCommand.IDENTIFY),
        )
    assert max_active == 1


async def test_write_settings_command_and_time() -> None:
    client = FakeGattClient(_chars())
    dev = KestrelBleDevice(ADDR, DeviceFamily.DROP, ble_device=_ble_device())
    dev.use_link_clock = False  # the fake client has no Mass Transfer service
    with patch(ESTABLISH, return_value=client):
        state = await dev.async_write_settings(DropSettings(log_interval_s=300))
        assert state.settings is not None and state.settings.log_interval_s == 300
        await dev.async_send_command(ProfileCommand.IDENTIFY)
        assert client.writes[-1][0] == uuids.DROP_COMMANDS_UUID
        when = datetime(2026, 10, 17, 12, 0, 0)
        await dev.async_set_time(when)
        assert client.writes[-1] == (
            uuids.DROP_DATETIME_UUID,
            b"\x00\x00\x0c\x11\x0a\xea\x07",
            True,
        )
        assert dev.state.device_time == when
        await dev.async_set_time()
        assert (
            dev.state.device_time is not None and dev.state.device_time.tzinfo is None
        )
    dev.set_max_attempts(5)
    assert dev._max_attempts == 5


async def test_link_clock_read_and_sync() -> None:
    """DROP polls read the LiNK clock and time sync goes through LiNK too."""
    client = FakeGattClient(_chars())
    dev = KestrelBleDevice(ADDR, DeviceFamily.DROP, ble_device=_ble_device())
    link = MagicMock()
    link.get_time = AsyncMock(return_value=datetime(2026, 10, 17, 12, 44, 22))
    link.get_battery = AsyncMock(return_value=23)
    link.set_time = AsyncMock()
    transport = MagicMock()
    transport.start = AsyncMock()
    transport.stop = AsyncMock()
    with (
        patch(ESTABLISH, return_value=client),
        patch(
            "custom_components.kestrel.kestrel_link.device.LinkTransport",
            return_value=transport,
        ),
        patch(
            "custom_components.kestrel.kestrel_link.device.LinkClient",
            return_value=link,
        ),
    ):
        state = await dev.async_poll()
        assert state.device_time == datetime(2026, 10, 17, 12, 44, 22)
        assert state.battery_percent == 23
        assert state.battery_source == "link"
        transport.start.assert_awaited()
        transport.stop.assert_awaited()

        link.get_time = AsyncMock(return_value=datetime(2026, 10, 17, 10, 30, 0))
        result = await dev.async_set_time(datetime(2026, 10, 17, 10, 30, 0))
        link.set_time.assert_awaited_once_with(
            datetime(2026, 10, 17, 10, 30, 0), drop_layout=True
        )
        assert result == datetime(2026, 10, 17, 10, 30, 0)
        assert dev.state.device_time == result


async def test_link_clock_failure_is_tolerated() -> None:
    """A failing LiNK clock read must not fail the poll."""
    client = FakeGattClient(_chars())
    dev = KestrelBleDevice(ADDR, DeviceFamily.DROP, ble_device=_ble_device())
    with patch(ESTABLISH, return_value=client):
        state = await dev.async_poll()  # fake client has no Mass Transfer service
    assert state.device_time is None
    assert state.battery_percent is not None
    assert state.battery_source == "gatt"
