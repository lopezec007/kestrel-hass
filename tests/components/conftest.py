"""Fixtures for the Kestrel component tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bluetooth_data_tools import monotonic_time_coarse
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.components.bluetooth.api import _get_manager
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kestrel.const import (
    CONF_FAMILY,
    CONF_MODEL_CODE,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)
from custom_components.kestrel.kestrel_link.const import (
    DeviceFamily,
    MeasurementKind,
    NativeUnit,
)
from custom_components.kestrel.kestrel_link.models import model_from_code
from custom_components.kestrel.kestrel_link.types import (
    DeviceInfo,
    DeviceState,
    DropSettings,
    Measurement,
)

# --------------------------------------------------------------------------- #
# Constants shared by the tests
# --------------------------------------------------------------------------- #

DROP_ADDRESS = "AA:BB:CC:DD:EE:FF"
DROP_NAME = "D3 - 1234567"
DROP_SERVICE_UUID = "12630000-cc25-497d-9854-9b6c02c77054"
DROP_MODEL_CODE = 552
OTHER_ADDRESS = "11:22:33:44:55:66"


def generate_ble_device(address: str, name: str | None) -> BLEDevice:
    """Create a BLEDevice for tests."""
    return BLEDevice(address, name, {"path": f"/org/bluez/hci0/dev_{address}"})


def generate_advertisement_data(**kwargs: Any) -> AdvertisementData:
    """Create AdvertisementData for tests."""
    defaults: dict[str, Any] = {
        "local_name": None,
        "manufacturer_data": {},
        "service_data": {},
        "service_uuids": [],
        "tx_power": None,
        "rssi": -60,
        "platform_data": (),
    }
    defaults.update(kwargs)
    return AdvertisementData(**defaults)


def make_service_info(
    address: str = DROP_ADDRESS,
    name: str = DROP_NAME,
    *,
    manufacturer_data: dict[int, bytes] | None = None,
    service_uuids: list[str] | None = None,
    rssi: int = -60,
    event: int = 0xFFFF,
) -> BluetoothServiceInfoBleak:
    """Build a BluetoothServiceInfoBleak for an NK device."""
    if manufacturer_data is None:
        manufacturer_data = {
            0xEA: DROP_MODEL_CODE.to_bytes(2, "little") + event.to_bytes(2, "little")
        }
    if service_uuids is None:
        service_uuids = [DROP_SERVICE_UUID]
    device = generate_ble_device(address, name)
    advertisement = generate_advertisement_data(
        local_name=name,
        manufacturer_data=manufacturer_data,
        service_uuids=service_uuids,
        rssi=rssi,
    )
    return BluetoothServiceInfoBleak(
        name=name,
        address=address,
        rssi=rssi,
        manufacturer_data=manufacturer_data,
        service_data={},
        service_uuids=service_uuids,
        source="local",
        device=device,
        advertisement=advertisement,
        connectable=True,
        time=monotonic_time_coarse(),
        tx_power=None,
    )


DROP_SERVICE_INFO = make_service_info()
SPEEDCOACH_SERVICE_INFO = make_service_info(
    OTHER_ADDRESS,
    "SpdCoach 123456",
    manufacturer_data={0xEA: bytes([0x82, 0x00])},
    service_uuids=["0e440000-ba99-4d39-be68-c9ab3ebb1900"],
)


def inject_bluetooth_service_info(
    hass: HomeAssistant, info: BluetoothServiceInfoBleak
) -> None:
    """Feed an advertisement into the Bluetooth manager."""
    _get_manager(hass).scanner_adv_received(info)


def _measurement(
    kind: MeasurementKind,
    value: float | None,
    unit: NativeUnit,
    *,
    present: bool = True,
) -> Measurement:
    return Measurement(
        kind=kind,
        value=value,
        unit=unit,
        present=present,
        enabled=present,
        valid=value is not None,
    )


def make_device_state(address: str = DROP_ADDRESS) -> DeviceState:
    """Return a DeviceState resembling a polled DROP D3."""
    return DeviceState(
        address=address,
        family=DeviceFamily.DROP,
        model=model_from_code(DROP_MODEL_CODE),
        name=DROP_NAME,
        info=DeviceInfo(
            manufacturer="Nielsen-Kellerman",
            model_number="D3",
            serial_number="1234567",
            hardware_revision="2",
            firmware_revision="1.23",
            ble_profile_version="1.0",
        ),
        battery_percent=87,
        device_time=datetime(2026, 10, 17, 12, 0, 0),
        measurements={
            MeasurementKind.TEMPERATURE: _measurement(
                MeasurementKind.TEMPERATURE, 23.47, NativeUnit.CELSIUS
            ),
            MeasurementKind.RELATIVE_HUMIDITY: _measurement(
                MeasurementKind.RELATIVE_HUMIDITY, 40.0, NativeUnit.PERCENT
            ),
            MeasurementKind.HEAT_INDEX: _measurement(
                MeasurementKind.HEAT_INDEX, 27.75, NativeUnit.CELSIUS
            ),
            MeasurementKind.DEW_POINT: _measurement(
                MeasurementKind.DEW_POINT, 20.0, NativeUnit.CELSIUS
            ),
            MeasurementKind.WET_BULB_TEMPERATURE: _measurement(
                MeasurementKind.WET_BULB_TEMPERATURE, 15.6, NativeUnit.CELSIUS
            ),
            MeasurementKind.DELTA_T: _measurement(
                MeasurementKind.DELTA_T, 7.9, NativeUnit.CELSIUS
            ),
            MeasurementKind.STATION_PRESSURE: _measurement(
                MeasurementKind.STATION_PRESSURE, 1013.2, NativeUnit.HPA
            ),
            MeasurementKind.BAROMETRIC_PRESSURE: _measurement(
                MeasurementKind.BAROMETRIC_PRESSURE, 1015.0, NativeUnit.HPA
            ),
            MeasurementKind.DENSITY_ALTITUDE: _measurement(
                MeasurementKind.DENSITY_ALTITUDE, 312.0, NativeUnit.METERS
            ),
            MeasurementKind.THI_NRC: _measurement(
                MeasurementKind.THI_NRC, None, NativeUnit.UNITLESS, present=False
            ),
            MeasurementKind.THI_YOUSEF: _measurement(
                MeasurementKind.THI_YOUSEF, None, NativeUnit.UNITLESS, present=False
            ),
        },
        settings=DropSettings(
            log_interval_s=600,
            wrap_log=True,
            transmission_rate_s=5,
            security_level=0,
            setup_complete=True,
            reference_altitude_m=120,
        ),
        raw={"12630001-cc25-497d-9854-9b6c02c77054": bytes([0x07, 0x2B, 0x09])},
    )


class FakeKestrelBleDevice:
    """Stand-in for KestrelBleDevice with AsyncMock methods."""

    def __init__(self, address: str, family: DeviceFamily, **kwargs: Any) -> None:
        self.address = address
        self.family = family
        self.kwargs = kwargs
        self.state = make_device_state(address)
        self.set_ble_device = MagicMock()
        self.async_poll = AsyncMock(side_effect=self._poll)
        self.async_write_settings = AsyncMock(side_effect=self._write_settings)
        self.async_send_command = AsyncMock()
        self.async_set_time = AsyncMock()

    async def _poll(self) -> DeviceState:
        return self.state

    async def _write_settings(self, settings: DropSettings) -> DeviceState:
        assert self.state.settings is not None
        for name in (
            "log_interval_s",
            "wrap_log",
            "transmission_rate_s",
            "security_level",
            "setup_complete",
            "reference_altitude_m",
        ):
            value = getattr(settings, name)
            if value is not None:
                setattr(self.state.settings, name, value)
        return self.state


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations for every test."""


@pytest.fixture
async def setup_bluetooth(hass: HomeAssistant, mock_bluetooth: None) -> None:
    """Set up the Bluetooth integration with mocked adapters."""
    assert await async_setup_component(hass, "bluetooth", {})
    await hass.async_block_till_done()


@pytest.fixture
def mock_device() -> Generator[FakeKestrelBleDevice]:
    """Replace KestrelBleDevice in the coordinator with a fake."""
    holder: dict[str, FakeKestrelBleDevice] = {}

    def factory(
        address: str, family: DeviceFamily, **kwargs: Any
    ) -> FakeKestrelBleDevice:
        fake = FakeKestrelBleDevice(address, family, **kwargs)
        holder["device"] = fake
        return fake

    with patch(
        "custom_components.kestrel.coordinator.KestrelBleDevice", side_effect=factory
    ):
        # Expose the fake lazily: tests read attributes after setup.
        proxy = _LazyFake(holder)
        yield proxy  # type: ignore[misc]


class _LazyFake:
    """Proxy that forwards attribute access to the created fake device."""

    def __init__(self, holder: dict[str, FakeKestrelBleDevice]) -> None:
        self._holder = holder

    @property
    def created(self) -> bool:
        return "device" in self._holder

    def __getattr__(self, name: str) -> Any:
        return getattr(self._holder["device"], name)


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry for the DROP D3."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=DROP_NAME,
        unique_id=DROP_ADDRESS,
        data={
            CONF_ADDRESS: DROP_ADDRESS,
            CONF_FAMILY: DeviceFamily.DROP.value,
            CONF_MODEL_CODE: DROP_MODEL_CODE,
        },
        options={CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL},
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    setup_bluetooth: None,
    mock_device: FakeKestrelBleDevice,
    mock_config_entry: MockConfigEntry,
) -> MockConfigEntry:
    """Inject the DROP advertisement and set up the integration."""
    inject_bluetooth_service_info(hass, DROP_SERVICE_INFO)
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry


def get_device_entry(
    hass: HomeAssistant, address: str, entry_id: str
) -> dr.DeviceEntry | None:
    """Look up the device registry entry for a BLE address.

    ``async_get_device_by_connection`` exists from Home Assistant 2026.10; older
    releases only offer ``async_get_device``.
    """
    registry = dr.async_get(hass)
    lookup = getattr(registry, "async_get_device_by_connection", None)
    if lookup is not None:
        return lookup((dr.CONNECTION_BLUETOOTH, address), entry_id)
    return registry.async_get_device(connections={(dr.CONNECTION_BLUETOOTH, address)})
