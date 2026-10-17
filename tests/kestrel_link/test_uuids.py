"""Tests for UUID helpers."""

import pytest

from custom_components.kestrel.kestrel_link import uuids


def test_drop_uuid_formatting() -> None:
    assert uuids.DROP_SERVICE_UUID == "12630000-cc25-497d-9854-9b6c02c77054"
    assert uuids.drop_uuid(0x0001) == "12630001-cc25-497d-9854-9b6c02c77054"
    assert uuids.DROP_SETTINGS_UUID == "12630101-cc25-497d-9854-9b6c02c77054"
    assert uuids.DROP_PROFILE_VERSION_UUID.startswith("12630200-")


def test_kestrel_uuid_formatting() -> None:
    assert uuids.KESTREL_SERVICE_UUID == "03290000-eab4-dea1-b24e-44ec023874db"
    assert uuids.K5_STATUS1_UUID == "03290300-eab4-dea1-b24e-44ec023874db"
    assert uuids.kestrel_uuid(0x0380) == "03290380-eab4-dea1-b24e-44ec023874db"


def test_mass_transfer_uuids() -> None:
    assert uuids.MASS_TRANSFER_SERVICE_UUID == "85920000-0338-4b83-ae4a-ac1d217adb03"
    assert uuids.MASS_TRANSFER_P2C_UUID == "85920001-0338-4b83-ae4a-ac1d217adb03"
    assert uuids.MASS_TRANSFER_P2C_UUID_ALT == "85920100-0338-4b83-ae4a-ac1d217adb03"
    assert uuids.MASS_TRANSFER_C2P_UUID_ALT == "85920200-0338-4b83-ae4a-ac1d217adb03"
    assert uuids.is_mass_transfer_uuid(uuids.MASS_TRANSFER_P2C_UUID_ALT.upper())
    assert not uuids.is_mass_transfer_uuid(uuids.DROP_SERVICE_UUID)


def test_super_mass_transfer_uuids() -> None:
    assert (
        uuids.SUPER_MASS_TRANSFER_SERVICE_UUID == "374952c9-c0e3-4a13-b487-910812b8182f"
    )
    assert uuids.SUPER_MASS_TRANSFER_P2C_UUID == "37490001-c0e3-4a13-b487-910812b8182f"
    assert uuids.is_super_mass_transfer_uuid(uuids.SUPER_MASS_TRANSFER_C2P_UUID)


def test_sig_uuids() -> None:
    assert uuids.sig_uuid(0x180F) == "0000180f-0000-1000-8000-00805f9b34fb"
    assert uuids.BATTERY_LEVEL_UUID == "00002a19-0000-1000-8000-00805f9b34fb"
    assert uuids.SERIAL_NUMBER_UUID == "00002a25-0000-1000-8000-00805f9b34fb"


def test_short_out_of_range() -> None:
    with pytest.raises(ValueError):
        uuids.drop_uuid(0x10000)


def test_lowercase_everywhere() -> None:
    for name in dir(uuids):
        value = getattr(uuids, name)
        if name.endswith("_UUID") and isinstance(value, str):
            assert value == value.lower()
