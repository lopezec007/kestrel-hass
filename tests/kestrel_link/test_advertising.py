"""Tests for advertisement parsing."""

from custom_components.kestrel.kestrel_link.advertising import (
    clean_local_name,
    is_kestrel_advertisement,
    parse_advertisement,
    parse_manufacturer_data,
)
from custom_components.kestrel.kestrel_link.const import NK_COMPANY_ID, DeviceFamily
from custom_components.kestrel.kestrel_link.uuids import (
    DROP_SERVICE_UUID,
    KESTREL_SERVICE_UUID,
)


def _mfr(model: int, event: int | None = 0xFFFF) -> bytes:
    data = model.to_bytes(2, "little")
    if event is not None:
        data += event.to_bytes(2, "little")
    return data


def test_drop3_full_scan_response() -> None:
    adv = parse_advertisement(
        "D3 - 12345678", {NK_COMPANY_ID: _mfr(552)}, [DROP_SERVICE_UUID]
    )
    assert adv is not None
    assert adv.model_code == 552
    assert adv.event_field is None
    assert adv.family is DeviceFamily.DROP
    assert adv.local_name == "D3 - 12345678"
    assert adv.model is not None and adv.model.name == "Kestrel DROP D3"


def test_d3_fire_with_event() -> None:
    adv = parse_advertisement("D3 FIRE - 1", {NK_COMPANY_ID: _mfr(553, 126)}, [])
    assert adv is not None
    assert adv.model_code == 553
    assert adv.event_field == 126
    assert adv.family is DeviceFamily.DROP


def test_k5_by_uuid_only() -> None:
    adv = parse_advertisement("Custom Name", {}, [KESTREL_SERVICE_UUID.upper()])
    assert adv is not None
    assert adv.model_code is None
    assert adv.family is DeviceFamily.KESTREL_5000


def test_two_byte_manufacturer_payload() -> None:
    adv = parse_advertisement(None, {NK_COMPANY_ID: _mfr(551, None)}, [])
    assert adv is not None
    assert adv.model_code == 551
    assert adv.event_field is None
    assert adv.family is DeviceFamily.DROP


def test_short_manufacturer_payload_falls_back_to_name() -> None:
    adv = parse_advertisement("D2 - 1", {NK_COMPANY_ID: b"\x01"}, [])
    assert adv is not None
    assert adv.model_code is None
    assert adv.family is DeviceFamily.DROP


def test_unknown_model_code_falls_back_to_uuid() -> None:
    adv = parse_advertisement("X", {NK_COMPANY_ID: _mfr(4)}, [DROP_SERVICE_UUID])
    assert adv is not None
    assert adv.model_code == 4
    assert adv.family is DeviceFamily.DROP


def test_non_nk_device_returns_none() -> None:
    assert (
        parse_advertisement(
            "Thing", {0x004C: b"\x01\x02"}, ["0000180f-0000-1000-8000-00805f9b34fb"]
        )
        is None
    )
    assert parse_advertisement(None, None, None) is None
    assert not is_kestrel_advertisement("D3 - 1", {}, [])


def test_parse_manufacturer_data_edge_cases() -> None:
    assert parse_manufacturer_data(None) == (None, None)
    assert parse_manufacturer_data(b"") == (None, None)
    assert parse_manufacturer_data(bytearray(b"\x28\x02\x7e\x00")) == (552, 126)
    assert parse_manufacturer_data(b"\x28\x02\xff\xff\x00\x00") == (552, None)


def test_real_drop3_advertisement_with_nul_padding() -> None:
    """A capture from a real DROP D3: NUL-padded name, model 552, no event."""
    name = "D3 - 3103865" + "\x00" * 9
    adv = parse_advertisement(
        name,
        {234: bytes.fromhex("2802ffff")},
        ["12630000-cc25-497d-9854-9b6c02c77054"],
    )
    assert adv is not None
    assert adv.model_code == 552
    assert adv.family is DeviceFamily.DROP
    assert adv.event_field is None
    assert adv.local_name == "D3 - 3103865"
    assert adv.model is not None and adv.model.name == "Kestrel DROP D3"
    assert clean_local_name("\x00\x00") is None
    assert clean_local_name(None) is None
