"""Tests for the kestrel.import_data_log action."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.recorder.models.statistics import StatisticMeanType
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kestrel.const import DOMAIN
from custom_components.kestrel.kestrel_link.const import FieldName, MeasurementKind
from custom_components.kestrel.kestrel_link.types import (
    DataLogResult,
    KestrelError,
    LinkRecord,
)
from custom_components.kestrel.services import (
    ATTR_MODE,
    CONF_LAST_LOG_SEQUENCE,
    SERVICE_IMPORT_DATA_LOG,
    async_setup_services,
    build_statistics,
)

from .conftest import DROP_ADDRESS, get_device_entry


def _record(ts: datetime, temp: float | None, rh: float) -> LinkRecord:
    return LinkRecord(
        timestamp=ts,
        values={
            int(FieldName.TIMESTAMP): ts,
            int(FieldName.DRY_BULB_TEMP): temp,
            int(FieldName.RELATIVE_HUMIDITY): rh,
            int(FieldName.CRC_CHECKSUM): 7,
        },
    )


RECORDS = [
    _record(datetime(2026, 10, 17, 10, 0, 0), 20.0, 50.0),
    _record(datetime(2026, 10, 17, 10, 30, 0), 22.0, 54.0),
    _record(datetime(2026, 10, 17, 11, 15, 0), None, 60.0),
    LinkRecord(timestamp=None, values={int(FieldName.DRY_BULB_TEMP): 99.0}),
]


async def test_build_statistics(hass: HomeAssistant) -> None:
    await hass.config.async_set_time_zone("UTC")
    stats = build_statistics(hass, RECORDS)
    temp = stats[MeasurementKind.TEMPERATURE]
    assert len(temp) == 1
    assert temp[0]["start"] == dt_util.as_utc(
        datetime(2026, 10, 17, 10, 0, tzinfo=dt_util.UTC)
    )
    assert temp[0]["mean"] == pytest.approx(21.0)
    assert temp[0]["min"] == 20.0
    assert temp[0]["max"] == 22.0
    rh = stats[MeasurementKind.RELATIVE_HUMIDITY]
    assert [h["start"].hour for h in rh] == [10, 11]
    assert rh[1]["mean"] == 60.0


async def test_build_statistics_uses_ha_time_zone(hass: HomeAssistant) -> None:
    await hass.config.async_set_time_zone("America/New_York")  # UTC-4 in October
    stats = build_statistics(hass, RECORDS[:1])
    start = stats[MeasurementKind.TEMPERATURE][0]["start"]
    assert start == datetime(2026, 10, 17, 14, 0, tzinfo=dt_util.UTC)


def _device_id(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    device = get_device_entry(hass, DROP_ADDRESS, entry.entry_id)
    assert device is not None
    return device.id


def _install_fake_link(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    result: DataLogResult | Exception,
) -> tuple[MagicMock, MagicMock, AsyncMock]:
    """Make the device's connection run our fake LiNK client."""
    fake_client = MagicMock(name="bleak_client")
    coordinator = entry.runtime_data

    async def _run(fn: Any) -> Any:
        return await fn(fake_client)

    coordinator.device.async_run = AsyncMock(side_effect=_run)
    transport = MagicMock()
    transport.start = AsyncMock()
    transport.stop = AsyncMock()
    link = MagicMock()
    if isinstance(result, Exception):
        link.get_data_log = AsyncMock(side_effect=result)
    else:
        link.get_data_log = AsyncMock(return_value=result)
    return transport, link, coordinator.device.async_run


@pytest.fixture
def recorder_loaded(hass: HomeAssistant) -> None:
    hass.config.components.add("recorder")


async def test_import_data_log(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    recorder_loaded: None,
) -> None:
    await hass.config.async_set_time_zone("UTC")
    async_setup_services(hass)
    async_setup_services(hass)  # idempotent
    assert hass.services.has_service(DOMAIN, SERVICE_IMPORT_DATA_LOG)
    entry = init_integration
    transport, link, run = _install_fake_link(
        hass, entry, DataLogResult(records=RECORDS, last_sequence=1234)
    )
    with (
        patch(
            "custom_components.kestrel.kestrel_link.transport.LinkTransport",
            return_value=transport,
        ) as transport_cls,
        patch(
            "custom_components.kestrel.kestrel_link.client.LinkClient",
            return_value=link,
        ),
        patch("custom_components.kestrel.services.async_import_statistics") as imp,
    ):
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_IMPORT_DATA_LOG,
            {ATTR_DEVICE_ID: _device_id(hass, init_integration)},
            blocking=True,
            return_response=True,
        )

    run.assert_awaited_once()
    transport_cls.assert_called_once()
    transport.start.assert_awaited_once()
    transport.stop.assert_awaited_once()
    link.get_data_log.assert_awaited_once_with(after=None)

    registry = er.async_get(hass)
    temp_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{DROP_ADDRESS}_{MeasurementKind.TEMPERATURE.value}"
    )
    rh_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{DROP_ADDRESS}_{MeasurementKind.RELATIVE_HUMIDITY.value}"
    )
    assert temp_id and rh_id
    assert imp.call_count == 2
    by_id = {call.args[1]["statistic_id"]: call for call in imp.call_args_list}
    temp_meta = by_id[temp_id].args[1]
    assert temp_meta["unit_of_measurement"] == "°C"
    assert temp_meta["unit_class"] == "temperature"
    assert temp_meta["mean_type"] is StatisticMeanType.ARITHMETIC
    assert temp_meta["has_sum"] is False
    assert temp_meta["source"] == "recorder"
    temp_stats = by_id[temp_id].args[2]
    assert len(temp_stats) == 1
    assert temp_stats[0]["mean"] == pytest.approx(21.0)
    rh_meta = by_id[rh_id].args[1]
    assert rh_meta["unit_of_measurement"] == "%"
    assert rh_meta["unit_class"] == "unitless"
    assert len(by_id[rh_id].args[2]) == 2

    assert response == {
        "records_downloaded": 4,
        "records_with_timestamp": 3,
        "first_record": "2026-10-17T10:00:00",
        "last_record": "2026-10-17T11:15:00",
        "last_sequence": 1234,
        "statistics": {temp_id: 1, rh_id: 2},
    }
    assert entry.data[CONF_LAST_LOG_SEQUENCE] == 1234
    assert hass.data[DOMAIN]["last_sequence"][entry.entry_id] == 1234


async def test_import_new_uses_stored_sequence_and_all_ignores_it(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    recorder_loaded: None,
) -> None:
    async_setup_services(hass)
    entry = init_integration
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_LAST_LOG_SEQUENCE: 500}
    )
    transport, link, _ = _install_fake_link(
        hass, entry, DataLogResult(records=[], last_sequence=None)
    )
    with (
        patch(
            "custom_components.kestrel.kestrel_link.transport.LinkTransport",
            return_value=transport,
        ),
        patch(
            "custom_components.kestrel.kestrel_link.client.LinkClient",
            return_value=link,
        ),
        patch("custom_components.kestrel.services.async_import_statistics") as imp,
    ):
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_IMPORT_DATA_LOG,
            {ATTR_DEVICE_ID: _device_id(hass, init_integration)},
            blocking=True,
            return_response=True,
        )
        link.get_data_log.assert_awaited_with(after=500)
        await hass.services.async_call(
            DOMAIN,
            SERVICE_IMPORT_DATA_LOG,
            {ATTR_DEVICE_ID: _device_id(hass, init_integration), ATTR_MODE: "all"},
            blocking=True,
        )
        link.get_data_log.assert_awaited_with(after=None)
    imp.assert_not_called()
    assert response["records_downloaded"] == 0
    assert response["last_sequence"] is None
    # Unchanged because the device reported no sequence number.
    assert entry.data[CONF_LAST_LOG_SEQUENCE] == 500


async def test_import_download_failure(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    recorder_loaded: None,
) -> None:
    async_setup_services(hass)
    transport, link, _ = _install_fake_link(
        hass, init_integration, KestrelError("boom")
    )
    with (
        patch(
            "custom_components.kestrel.kestrel_link.transport.LinkTransport",
            return_value=transport,
        ),
        patch(
            "custom_components.kestrel.kestrel_link.client.LinkClient",
            return_value=link,
        ),
        pytest.raises(HomeAssistantError) as excinfo,
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_IMPORT_DATA_LOG,
            {ATTR_DEVICE_ID: _device_id(hass, init_integration)},
            blocking=True,
        )
    assert excinfo.value.translation_key == "download_failed"
    transport.stop.assert_awaited_once()


async def test_import_requires_recorder(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    async_setup_services(hass)
    assert "recorder" not in hass.config.components
    with pytest.raises(HomeAssistantError) as excinfo:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_IMPORT_DATA_LOG,
            {ATTR_DEVICE_ID: _device_id(hass, init_integration)},
            blocking=True,
        )
    assert excinfo.value.translation_key == "recorder_not_loaded"


async def test_import_unknown_device(
    hass: HomeAssistant, init_integration: MockConfigEntry, recorder_loaded: None
) -> None:
    async_setup_services(hass)
    with pytest.raises(ServiceValidationError) as excinfo:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_IMPORT_DATA_LOG,
            {ATTR_DEVICE_ID: "does-not-exist"},
            blocking=True,
        )
    assert excinfo.value.translation_key == "device_not_found"


async def test_import_non_kestrel_device(
    hass: HomeAssistant, init_integration: MockConfigEntry, recorder_loaded: None
) -> None:
    async_setup_services(hass)
    other_entry = MockConfigEntry(domain="other")
    other_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=other_entry.entry_id,
        identifiers={("other", "x")},
    )
    with pytest.raises(ServiceValidationError) as excinfo:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_IMPORT_DATA_LOG,
            {ATTR_DEVICE_ID: device.id},
            blocking=True,
        )
    assert excinfo.value.translation_key == "not_kestrel_device"


async def test_import_entry_not_loaded(
    hass: HomeAssistant, init_integration: MockConfigEntry, recorder_loaded: None
) -> None:
    async_setup_services(hass)
    device_id = _device_id(hass, init_integration)
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError) as excinfo:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_IMPORT_DATA_LOG,
            {ATTR_DEVICE_ID: device_id},
            blocking=True,
        )
    assert excinfo.value.translation_key == "entry_not_loaded"
