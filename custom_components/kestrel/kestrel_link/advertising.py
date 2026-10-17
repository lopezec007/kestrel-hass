"""Parsing of NK Bluetooth advertisements and scan responses."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Final, Literal

from .const import NK_COMPANY_ID, NO_FIELD, DeviceFamily
from .models import (
    family_from_local_name,
    family_from_model_code,
    family_from_service_uuids,
)
from .types import NKAdvertisement
from .uuids import SERVICE_FAMILIES

# Wire byte order (typed so int.from_bytes/to_bytes accept it).
LE: Final[Literal["little"]] = "little"


def clean_local_name(local_name: str | None) -> str | None:
    """Strip the NUL padding Kestrel devices append to their advertised name.

    A DROP fills the 21-byte Complete Local Name field, so a name such as
    ``"D3 - 3103865"`` arrives followed by nine NUL bytes.
    """
    if local_name is None:
        return None
    cleaned = local_name.replace("\x00", "").strip()
    return cleaned or None


def _has_nk_service(service_uuids: Iterable[str]) -> bool:
    return any(uuid.lower() in SERVICE_FAMILIES for uuid in service_uuids)


def parse_manufacturer_data(
    payload: bytes | bytearray | None,
) -> tuple[int | None, int | None]:
    """Decode NK manufacturer-specific data into ``(model_code, event_field)``.

    The payload (company id already stripped) is ``model u16 LE`` optionally
    followed by ``event u16 LE``.  Unparseable payloads yield ``None`` values.
    """
    if payload is None or len(payload) < 2:
        return None, None
    model = int.from_bytes(payload[0:2], LE)
    event: int | None = None
    if len(payload) >= 4:
        event = int.from_bytes(payload[2:4], LE)
        if event == NO_FIELD:
            event = None
    return model, event


def parse_advertisement(
    local_name: str | None,
    manufacturer_data: Mapping[int, bytes | bytearray] | None,
    service_uuids: Iterable[str] | None,
) -> NKAdvertisement | None:
    """Parse an advertisement; return None if it is not an NK device."""
    manufacturer_data = manufacturer_data or {}
    uuids = [u.lower() for u in (service_uuids or [])]
    local_name = clean_local_name(local_name)

    nk_payload = manufacturer_data.get(NK_COMPANY_ID)
    has_nk_service = _has_nk_service(uuids)
    if nk_payload is None and not has_nk_service:
        return None

    model_code, event_field = parse_manufacturer_data(nk_payload)

    family = DeviceFamily.UNKNOWN
    if model_code is not None:
        family = family_from_model_code(model_code)
    if family is DeviceFamily.UNKNOWN:
        family = family_from_service_uuids(uuids) or DeviceFamily.UNKNOWN
    if family is DeviceFamily.UNKNOWN:
        family = family_from_local_name(local_name) or DeviceFamily.UNKNOWN

    return NKAdvertisement(
        model_code=model_code,
        event_field=event_field,
        family=family,
        local_name=local_name,
    )


def is_kestrel_advertisement(
    local_name: str | None,
    manufacturer_data: Mapping[int, bytes | bytearray] | None,
    service_uuids: Iterable[str] | None,
) -> bool:
    """Return True if the advertisement comes from an NK device."""
    return parse_advertisement(local_name, manufacturer_data, service_uuids) is not None
