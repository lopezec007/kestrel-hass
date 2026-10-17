"""Actions exposed by the Kestrel integration."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Coroutine
from datetime import datetime
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.models.statistics import StatisticMeanType
from homeassistant.components.recorder.statistics import (
    STATISTIC_UNIT_TO_UNIT_CONVERTER,
    async_import_statistics,
)
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID, Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.util import dt as dt_util

try:  # Home Assistant >= 2026.10 validates schemas with probatio
    import probatio as vol
except ImportError:  # pragma: no cover - older cores
    import voluptuous as vol  # type: ignore[no-redef]

from .const import DOMAIN
from .kestrel_link.const import MEASUREMENT_FIELDS, MeasurementKind
from .kestrel_link.device import BLEAK_EXCEPTIONS
from .kestrel_link.types import KestrelError, LinkRecord

if TYPE_CHECKING:
    from .coordinator import KestrelCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_IMPORT_DATA_LOG = "import_data_log"
ATTR_MODE = "mode"
MODE_NEW = "new"
MODE_ALL = "all"
CONF_LAST_LOG_SEQUENCE = "last_log_sequence"
DATA_LAST_SEQUENCE = "last_sequence"

IMPORT_DATA_LOG_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Optional(ATTR_MODE, default=MODE_NEW): vol.In([MODE_NEW, MODE_ALL]),
    }
)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's actions (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_IMPORT_DATA_LOG):
        return
    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_DATA_LOG,
        _async_handle_import_data_log,
        schema=IMPORT_DATA_LOG_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


def _resolve_entry(hass: HomeAssistant, device_id: str) -> ConfigEntry:
    """Return the loaded Kestrel config entry behind a device id."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="device_not_found",
            translation_placeholders={"device_id": device_id},
        )
    # HA 2026.10 gives a device a single config entry; older releases expose
    # the (now deprecated) ``config_entries`` set.
    entry_ids = (
        [device.config_entry_id]
        if getattr(device, "config_entry_id", None)
        else list(device.config_entries)
    )
    for entry_id in entry_ids:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            continue
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_loaded",
                translation_placeholders={"device_id": device_id},
            )
        return entry
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="not_kestrel_device",
        translation_placeholders={"device_id": device_id},
    )


def _hour_floor(when: datetime) -> datetime:
    return when.replace(minute=0, second=0, microsecond=0)


def _localize(hass: HomeAssistant, naive: datetime) -> datetime:
    """Interpret a naive device timestamp in Home Assistant's time zone."""
    tz = dt_util.get_time_zone(hass.config.time_zone) or dt_util.DEFAULT_TIME_ZONE
    return dt_util.as_utc(naive.replace(tzinfo=tz))


def build_statistics(
    hass: HomeAssistant,
    records: list[LinkRecord],
) -> dict[MeasurementKind, list[StatisticData]]:
    """Aggregate records into hourly mean/min/max per measurement kind."""
    buckets: dict[MeasurementKind, dict[datetime, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for record in records:
        if record.timestamp is None:
            continue
        start = _hour_floor(_localize(hass, record.timestamp))
        for kind, value in record.measurements().items():
            if value is None:
                continue
            buckets[kind][start].append(float(value))
    stats: dict[MeasurementKind, list[StatisticData]] = {}
    for kind, hours in buckets.items():
        stats[kind] = [
            StatisticData(
                start=start,
                mean=sum(values) / len(values),
                min=min(values),
                max=max(values),
            )
            for start, values in sorted(hours.items())
        ]
    return stats


def _metadata(entity_id: str, kind: MeasurementKind) -> StatisticMetaData:
    unit = MEASUREMENT_FIELDS[kind][1].value or None
    converter = STATISTIC_UNIT_TO_UNIT_CONVERTER.get(unit)
    return StatisticMetaData(
        mean_type=StatisticMeanType.ARITHMETIC,
        has_sum=False,
        name=None,
        source="recorder",
        statistic_id=entity_id,
        unit_class=converter.UNIT_CLASS if converter is not None else None,
        unit_of_measurement=unit,
    )


def _stored_sequence(hass: HomeAssistant, entry: ConfigEntry) -> int | None:
    domain_data = hass.data.setdefault(DOMAIN, {})
    cached = domain_data.setdefault(DATA_LAST_SEQUENCE, {}).get(entry.entry_id)
    if cached is not None:
        return int(cached)
    stored = entry.data.get(CONF_LAST_LOG_SEQUENCE)
    return int(stored) if stored is not None else None


def _store_sequence(hass: HomeAssistant, entry: ConfigEntry, sequence: int) -> None:
    hass.data.setdefault(DOMAIN, {}).setdefault(DATA_LAST_SEQUENCE, {})[
        entry.entry_id
    ] = sequence
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_LAST_LOG_SEQUENCE: sequence}
    )


async def _async_handle_import_data_log(call: ServiceCall) -> ServiceResponse:
    """Download the device data log and import it as long-term statistics."""
    hass = call.hass
    if "recorder" not in hass.config.components:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="recorder_not_loaded"
        )
    entry = _resolve_entry(hass, call.data[ATTR_DEVICE_ID])
    coordinator: KestrelCoordinator = entry.runtime_data
    mode: str = call.data[ATTR_MODE]
    after = _stored_sequence(hass, entry) if mode == MODE_NEW else None

    from .kestrel_link.client import LinkClient  # noqa: PLC0415
    from .kestrel_link.transport import LinkTransport  # noqa: PLC0415

    async def _download(client: Any) -> tuple[Any, Any, int | None]:
        transport = LinkTransport(client)
        await transport.start()
        try:
            link = LinkClient(transport)
            device_time = await link.get_time()
            count = await link.get_data_log_record_count()
            result = await link.get_data_log(after=after)
        finally:
            await transport.stop()
        return result, device_time, count

    download: Callable[[Any], Coroutine[Any, Any, Any]] = _download
    try:
        result, device_time, record_count = await coordinator.device.async_run(download)
    except (*BLEAK_EXCEPTIONS, KestrelError) as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="download_failed",
            translation_placeholders={"error": str(err)},
        ) from err

    records: list[LinkRecord] = result.records
    _LOGGER.debug(
        "%s: data log layout %s; first record %s",
        coordinator.address,
        [(f.name, f.unit, f.size) for f in getattr(result, "fields", ())],
        records[0] if records else None,
    )
    stats = build_statistics(hass, records)
    registry = er.async_get(hass)
    imported: dict[str, int] = {}
    for kind, data in stats.items():
        entity_id = registry.async_get_entity_id(
            Platform.SENSOR, DOMAIN, f"{coordinator.address}_{kind.value}"
        )
        if entity_id is None or not data:
            continue
        async_import_statistics(hass, _metadata(entity_id, kind), data)
        imported[entity_id] = len(data)

    if result.last_sequence is not None:
        _store_sequence(hass, entry, int(result.last_sequence))

    timestamps = sorted(r.timestamp for r in records if r.timestamp is not None)
    response: dict[str, Any] = {
        "records_downloaded": len(records),
        "records_with_timestamp": len(timestamps),
        "first_record": timestamps[0].isoformat() if timestamps else None,
        "last_record": timestamps[-1].isoformat() if timestamps else None,
        "last_sequence": result.last_sequence,
        "device_time": device_time.isoformat() if device_time else None,
        "device_record_count": record_count,
        "statistics": imported,
    }
    _LOGGER.debug("Imported Kestrel data log for %s: %s", coordinator.address, response)
    return response


__all__ = [
    "ATTR_MODE",
    "CONF_LAST_LOG_SEQUENCE",
    "SERVICE_IMPORT_DATA_LOG",
    "async_setup_services",
    "build_statistics",
]
