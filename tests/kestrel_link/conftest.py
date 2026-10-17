"""Shared fixtures for kestrel_link tests."""

from __future__ import annotations

from typing import Any

from bleak.exc import BleakCharacteristicNotFoundError
import pytest


class FakeGattClient:
    """Minimal in-memory GATT client."""

    def __init__(self, chars: dict[str, bytes] | None = None) -> None:
        self.chars: dict[str, bytes] = {k.lower(): v for k, v in (chars or {}).items()}
        self.writes: list[tuple[str, bytes, bool | None]] = []
        self.reads: list[str] = []
        self.disconnected = False
        self.is_connected = True

    async def read_gatt_char(self, char_specifier: Any, **kwargs: Any) -> bytearray:
        uuid = str(char_specifier).lower()
        self.reads.append(uuid)
        if uuid not in self.chars:
            raise BleakCharacteristicNotFoundError(uuid)
        return bytearray(self.chars[uuid])

    async def write_gatt_char(
        self, char_specifier: Any, data: bytes | bytearray, response: bool | None = None
    ) -> None:
        uuid = str(char_specifier).lower()
        if uuid not in self.chars:
            raise BleakCharacteristicNotFoundError(uuid)
        self.writes.append((uuid, bytes(data), response))
        self.chars[uuid] = bytes(data)

    async def disconnect(self) -> bool:
        self.disconnected = True
        self.is_connected = False
        return True


@pytest.fixture
def fake_client_cls() -> type[FakeGattClient]:
    return FakeGattClient
