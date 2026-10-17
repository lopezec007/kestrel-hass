"""Tests for device profiles."""

from datetime import datetime

import pytest

from custom_components.kestrel.kestrel_link import uuids
from custom_components.kestrel.kestrel_link.const import (
    DeviceFamily,
    MeasurementKind as MK,  # noqa: N817,
)
from custom_components.kestrel.kestrel_link.profiles import (
    DropProfile,
    KestrelProfile,
    ProfileCommand,
    get_profile,
)
from custom_components.kestrel.kestrel_link.types import (
    CharacteristicMissingError,
    DeviceState,
    DropSettings,
    KestrelSettings,
    UnsupportedDeviceError,
)

from .conftest import FakeGattClient

ADDR = "AA:BB:CC:DD:EE:FF"


def _drop_chars() -> dict[str, bytes]:
    chars = {
        uuids.BATTERY_LEVEL_UUID: b"\x5a",
        uuids.MANUFACTURER_NAME_UUID: b"Nielsen-Kellerman",
        uuids.MODEL_NUMBER_UUID: b"D3",
        uuids.SERIAL_NUMBER_UUID: b"12345678",
        uuids.HARDWARE_REVISION_UUID: b"1.0",
        uuids.FIRMWARE_REVISION_UUID: b"1.23",
        uuids.SOFTWARE_REVISION_UUID: b"",
        uuids.DROP_PROFILE_VERSION_UUID: b"0.05\x00\x00",
        uuids.DROP_NAME_UUID: b"D3 - 12345678\x00" + b"\x00" * 6,
        uuids.DROP_DATETIME_UUID: b"\xdd\x07\x01\x01\x00\x00\x01",
        uuids.DROP_SETTINGS_UUID: (600).to_bytes(3, "little")
        + b"\x01\x05\x00\x01"
        + (100).to_bytes(2, "little", signed=True)
        + b"\xff" * 11,
        uuids.DROP_COMMANDS_UUID: bytes(20),
        uuids.drop_uuid(1): b"\x07\x2b\x09",
        uuids.drop_uuid(2): b"\x07" + (4000).to_bytes(2, "little"),
        uuids.drop_uuid(3): b"\x07" + (2775).to_bytes(3, "little", signed=True),
        uuids.drop_uuid(4): b"\x03"
        + (2000).to_bytes(2, "little", signed=True),  # invalid
        uuids.drop_uuid(7): b"\x07" + (10132).to_bytes(2, "little"),
        uuids.drop_uuid(10): b"\x07" + (12345).to_bytes(3, "little", signed=True),
    }
    # chars 5,6,8,9,11..15 present on the service but flagged not present
    for short in (5, 6, 8, 9, 11, 12, 13, 14, 15):
        chars[uuids.drop_uuid(short)] = b"\x00\x00\x00"
    return chars


async def test_drop_read_device_info() -> None:
    client = FakeGattClient(_drop_chars())
    state = DeviceState(address=ADDR, family=DeviceFamily.DROP)
    await DropProfile().read_device_info(client, state)
    assert state.info.manufacturer == "Nielsen-Kellerman"
    assert state.info.model_number == "D3"
    assert state.info.serial_number == "12345678"
    assert state.info.firmware_revision == "1.23"
    assert state.info.software_revision is None
    assert state.info.ble_profile_version == "0.05"
    assert state.name == "D3 - 12345678"


async def test_drop_read_state() -> None:
    client = FakeGattClient(_drop_chars())
    state = DeviceState(address=ADDR, family=DeviceFamily.DROP)
    out = await DropProfile().read_state(client, state)
    assert out is state
    assert state.battery_percent == 90
    assert state.device_time == datetime(2013, 1, 1, 0, 0, 1)
    assert state.value(MK.TEMPERATURE) == 23.47
    assert state.value(MK.RELATIVE_HUMIDITY) == 40.0
    assert state.value(MK.HEAT_INDEX) == 27.75
    assert state.value(MK.STATION_PRESSURE) == 1013.2
    assert state.value(MK.DENSITY_ALTITUDE) == 1234.5
    assert state.value(MK.DEW_POINT) is None
    assert state.measurements[MK.DEW_POINT].present is True
    assert state.measurements[MK.WET_BULB_TEMPERATURE].present is False
    assert set(state.present_measurements()) == {
        MK.TEMPERATURE,
        MK.RELATIVE_HUMIDITY,
        MK.HEAT_INDEX,
        MK.DEW_POINT,
        MK.STATION_PRESSURE,
        MK.DENSITY_ALTITUDE,
    }
    assert state.settings == DropSettings(600, True, 5, 0, True, 100)
    assert state.updated_at is not None
    assert uuids.drop_uuid(1) in state.raw and uuids.BATTERY_LEVEL_UUID in state.raw

    # Second poll skips characteristics known to be absent.
    client.reads.clear()
    await DropProfile().read_state(client, state)
    assert uuids.drop_uuid(5) not in client.reads
    assert uuids.drop_uuid(1) in client.reads
    assert state.measurements[MK.WET_BULB_TEMPERATURE].present is False


async def test_drop_read_state_missing_optional_chars() -> None:
    chars = _drop_chars()
    for short in range(5, 16):
        chars.pop(uuids.drop_uuid(short), None)
    chars.pop(uuids.DROP_SETTINGS_UUID)
    chars.pop(uuids.DROP_DATETIME_UUID)
    client = FakeGattClient(chars)
    state = DeviceState(address=ADDR, family=DeviceFamily.DROP)
    await DropProfile().read_state(client, state)
    assert state.value(MK.TEMPERATURE) == 23.47
    assert state.settings is None
    assert state.device_time is None
    assert state.measurements[MK.THI_NRC].present is False


async def test_drop_read_state_nothing_readable() -> None:
    client = FakeGattClient({uuids.DROP_SETTINGS_UUID: bytes(20)})
    state = DeviceState(address=ADDR, family=DeviceFamily.DROP)
    with pytest.raises(CharacteristicMissingError):
        await DropProfile().read_state(client, state)


async def test_drop_battery_only_is_ok() -> None:
    client = FakeGattClient({uuids.BATTERY_LEVEL_UUID: b"\x64"})
    state = DeviceState(address=ADDR, family=DeviceFamily.DROP)
    await DropProfile().read_state(client, state)
    assert state.battery_percent == 100
    assert not state.present_measurements()


async def test_drop_write_settings_command_time_name() -> None:
    client = FakeGattClient(_drop_chars())
    profile = DropProfile()
    await profile.write_settings(client, DropSettings(log_interval_s=300))
    uuid, data, response = client.writes[-1]
    assert uuid == uuids.DROP_SETTINGS_UUID
    assert data[0:3] == (300).to_bytes(3, "little") and data[3] == 0xFF and response

    await profile.write_settings(client, DropSettings())  # no-op
    assert len(client.writes) == 1

    await profile.send_command(client, ProfileCommand.IDENTIFY)
    assert client.writes[-1][0] == uuids.DROP_COMMANDS_UUID
    assert client.writes[-1][1][1] == 1
    await profile.send_command(client, ProfileCommand.ERASE_LOG)
    assert client.writes[-1][1][0] == 1
    with pytest.raises(UnsupportedDeviceError):
        await profile.send_command(client, ProfileCommand.STORE_LOG_POINT)

    await profile.write_time(client, datetime(2026, 10, 17, 14, 30, 5))
    assert client.writes[-1] == (
        uuids.DROP_DATETIME_UUID,
        b"\x05\x1e\x0e\x11\x0a\xea\x07",
        True,
    )

    await profile.write_name(client, "Patio")
    assert client.writes[-1][1] == b"Patio" + bytes(15)

    with pytest.raises(ValueError):
        await profile.write_settings(client, DropSettings(transmission_rate_s=99))


def _k5_chars() -> dict[str, bytes]:
    status1 = (1 << 1 | 1 << 3 | 1 << 14 | 1 << 15).to_bytes(8, "little")
    status2 = (1 << 1).to_bytes(8, "little")
    sensor = (
        bytes(2)
        + (2347).to_bytes(2, "little", signed=True)
        + bytes(2)
        + (5512).to_bytes(2, "little")
        + bytes(12)
    )
    derived2 = (
        (1200).to_bytes(2, "little", signed=True)
        + (2775).to_bytes(3, "little", signed=True)
        + bytes(15)
    )
    derived4 = bytes(2) + (6800).to_bytes(2, "little", signed=True) + bytes(16)
    return {
        uuids.BATTERY_LEVEL_UUID: b"\x32",
        uuids.K5_STATUS1_UUID: status1,
        uuids.K5_STATUS2_UUID: status2,
        uuids.kestrel_uuid(uuids.K5_SENSOR_SHORT): sensor,
        uuids.kestrel_uuid(uuids.K5_DERIVED2_SHORT): derived2,
        uuids.kestrel_uuid(uuids.K5_DERIVED4_SHORT): derived4,
        uuids.K5_SETTINGS_UUID: (60).to_bytes(3, "little")
        + b"\x00\x02\x00\x01"
        + (0).to_bytes(2, "little")
        + b"\x0f"
        + b"\xff" * 10,
        uuids.K5_COMMANDS_UUID: bytes(20),
        uuids.K5_DATETIME_UUID: b"\xea\x07\x01\x02\x03\x04\x05",
        uuids.K5_NAME_UUID: b"ENVIRO - 1\x00" + bytes(9),
        uuids.K5_PROFILE_VERSION_UUID: b"0.09",
    }


async def test_kestrel_profile_read_state() -> None:
    client = FakeGattClient(_k5_chars())
    profile = KestrelProfile(DeviceFamily.KESTREL_7000)
    assert profile.family is DeviceFamily.KESTREL_7000
    state = DeviceState(address=ADDR, family=DeviceFamily.KESTREL_7000)
    await profile.read_device_info(client, state)
    assert state.name == "ENVIRO - 1"
    assert state.info.ble_profile_version == "0.09"
    await profile.read_state(client, state)
    assert state.battery_percent == 50
    assert state.device_time == datetime(2026, 1, 2, 3, 4, 5)
    assert set(state.present_measurements()) == {
        MK.TEMPERATURE,
        MK.RELATIVE_HUMIDITY,
        MK.DEW_POINT,
        MK.HEAT_INDEX,
        MK.THI_NRC,
    }
    assert state.value(MK.TEMPERATURE) == 23.47
    assert state.value(MK.HEAT_INDEX) == 27.75
    assert state.value(MK.THI_NRC) == 68.0
    assert state.measurements[MK.WIND_SPEED].present is False
    # Characteristics with no present measurement are never read.
    assert uuids.kestrel_uuid(uuids.K5_DERIVED1_SHORT) not in client.reads
    assert isinstance(state.settings, KestrelSettings)
    assert state.settings.auto_shutdown_min == 15
    assert state.settings.transmission_rate_s == 2


async def test_kestrel_profile_commands_and_settings() -> None:
    client = FakeGattClient(_k5_chars())
    profile = KestrelProfile()
    await profile.send_command(client, ProfileCommand.STORE_LOG_POINT)
    assert client.writes[-1][1][5] == 1
    await profile.send_command(client, ProfileCommand.IDENTIFY)
    assert client.writes[-1][1][3] == 1
    # DropSettings instance is upgraded to KestrelSettings transparently.
    await profile.write_settings(client, DropSettings(reference_altitude_m=12))
    assert client.writes[-1][1][7:9] == (120).to_bytes(2, "little", signed=True)
    assert client.writes[-1][1][9] == 0xFF


def test_get_profile() -> None:
    assert isinstance(get_profile(DeviceFamily.DROP), DropProfile)
    for fam in (
        DeviceFamily.KESTREL_5000,
        DeviceFamily.KESTREL_7000,
        DeviceFamily.KESTREL_3550,
    ):
        p = get_profile(fam)
        assert isinstance(p, KestrelProfile) and p.family is fam
    for fam in (
        DeviceFamily.SPEEDCOACH,
        DeviceFamily.UNKNOWN,
        DeviceFamily.KESTREL_2700,
    ):
        with pytest.raises(UnsupportedDeviceError):
            get_profile(fam)
    assert get_profile(DeviceFamily.DROP).supports(ProfileCommand.IDENTIFY)
    assert not get_profile(DeviceFamily.DROP).supports(ProfileCommand.SYNC_BLE_DATA)
