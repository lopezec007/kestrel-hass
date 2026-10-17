"""Tests for the model registry."""

from custom_components.kestrel.kestrel_link import models
from custom_components.kestrel.kestrel_link.const import DeviceFamily, ModelCode
from custom_components.kestrel.kestrel_link.uuids import (
    DROP_SERVICE_UUID,
    KESTREL_SERVICE_UUID,
)


def test_every_model_code_registered() -> None:
    for code in ModelCode:
        assert int(code) in models.MODELS, code


def test_model_from_code() -> None:
    info = models.model_from_code(552)
    assert info is not None
    assert info.name == "Kestrel DROP D3"
    assert info.family is DeviceFamily.DROP
    assert info.advertising_name == "D3"
    assert info.model_code is ModelCode.DROP_3
    assert models.model_from_code(None) is None
    assert models.model_from_code(4) is None


def test_family_from_model_code() -> None:
    assert models.family_from_model_code(553) is DeviceFamily.DROP
    assert models.family_from_model_code(555) is DeviceFamily.DROP
    assert models.family_from_model_code(5) is DeviceFamily.KESTREL_5000
    assert models.family_from_model_code(856) is DeviceFamily.KESTREL_7000
    assert models.family_from_model_code(321) is DeviceFamily.KESTREL_3550
    assert models.family_from_model_code(999) is DeviceFamily.UNKNOWN
    assert models.family_from_model_code(None) is DeviceFamily.UNKNOWN


def test_family_from_service_uuids() -> None:
    assert (
        models.family_from_service_uuids([DROP_SERVICE_UUID.upper()])
        is DeviceFamily.DROP
    )
    assert (
        models.family_from_service_uuids(
            ["0000180f-0000-1000-8000-00805f9b34fb", KESTREL_SERVICE_UUID]
        )
        is DeviceFamily.KESTREL_5000
    )
    assert models.family_from_service_uuids([]) is None


def test_family_from_local_name() -> None:
    assert models.family_from_local_name("D3 - 12345678") is DeviceFamily.DROP
    assert models.family_from_local_name("D3 FIRE - 1") is DeviceFamily.DROP
    assert models.family_from_local_name("d1 probe - 1") is DeviceFamily.DROP
    assert models.family_from_local_name("Kestrel DROP 123456") is DeviceFamily.DROP
    assert (
        models.family_from_local_name("ENVIRO - 12345678") is DeviceFamily.KESTREL_5000
    )
    assert models.family_from_local_name("K5000 12345678") is DeviceFamily.KESTREL_5000
    assert models.family_from_local_name("HUMIDITY - 1") is DeviceFamily.KESTREL_7000
    assert models.family_from_local_name("3550AG 12345678") is DeviceFamily.KESTREL_3550
    assert models.family_from_local_name("2700-1") is DeviceFamily.KESTREL_2700
    assert models.family_from_local_name("D3XYZ") is None
    assert models.family_from_local_name("Living Room Lamp") is None
    assert models.family_from_local_name(None) is None
    assert models.family_from_local_name("") is None
