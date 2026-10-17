"""Shared data types for the Kestrel LiNK library.

These dataclasses form the contract between the protocol codec, the GATT
profile parsers, the BLE device wrapper and the Home Assistant entities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .const import (
    CommandCode,
    DeviceFamily,
    FieldName,
    FieldUnit,
    MeasurementKind,
    ModelCode,
    NackReason,
    NativeUnit,
    PacketType,
)

# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #


class KestrelError(Exception):
    """Base class for all library errors."""


class ProtocolError(KestrelError):
    """A frame or packet could not be decoded."""


class FrameError(ProtocolError):
    """An HDLC frame failed delimiting, escaping or FCS validation."""


class NackError(KestrelError):
    """The device rejected a command with a Nack."""

    def __init__(
        self,
        command: int,
        reason: int,
        information: bytes = b"",
    ) -> None:
        self.command = command
        self.reason = reason
        self.information = information
        try:
            reason_name = NackReason(reason).name
        except ValueError:
            reason_name = f"0x{reason:04X}"
        try:
            command_name = CommandCode(command).name
        except ValueError:
            command_name = f"0x{command:04X}"
        super().__init__(f"Command {command_name} nacked: {reason_name}")


class ResponseTimeoutError(KestrelError):
    """The device did not answer within the protocol timeout."""


class UnsupportedDeviceError(KestrelError):
    """The device is an NK product this library cannot read measurements from."""


class CharacteristicMissingError(KestrelError):
    """A required GATT characteristic was not found on the device."""


# --------------------------------------------------------------------------- #
# LiNK packets
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class FieldDescriptor:
    """One entry of a LiNK metadata packet."""

    name: int  # FieldName code (int to tolerate unknown codes)
    unit: int  # FieldUnit code
    size: int  # bytes occupied in each data record

    @property
    def field_name(self) -> FieldName | None:
        """Return the FieldName enum member, or None if unknown."""
        try:
            return FieldName(self.name)
        except ValueError:
            return None

    @property
    def field_unit(self) -> FieldUnit | None:
        """Return the FieldUnit enum member, or None if unknown."""
        try:
            return FieldUnit(self.unit)
        except ValueError:
            return None


@dataclass(frozen=True, slots=True)
class CommandPacket:
    """A command sent to or from a device."""

    command: int
    parameters: bytes = b""

    packet_type = PacketType.COMMAND


@dataclass(frozen=True, slots=True)
class AckPacket:
    """Acknowledgement of a packet or command."""

    command: int = 0xFFFF

    packet_type = PacketType.ACK


@dataclass(frozen=True, slots=True)
class NackPacket:
    """Negative acknowledgement."""

    command: int
    reason: int
    information: bytes = b""

    packet_type = PacketType.NACK


@dataclass(frozen=True, slots=True)
class MetadataPacket:
    """Describes the layout of subsequent data packets.

    ``start`` is True for a Metadata Start packet (which has no packet number
    and resets the accumulated layout).
    """

    fields: tuple[FieldDescriptor, ...]
    start: bool = False
    packet_number: int | None = None

    @property
    def packet_type(self) -> PacketType:
        """Return the wire packet type."""
        return PacketType.METADATA_START if self.start else PacketType.METADATA


@dataclass(frozen=True, slots=True)
class DataPacket:
    """Raw data payload; interpret with the preceding metadata."""

    payload: bytes

    packet_type = PacketType.DATA


LinkPacket = CommandPacket | AckPacket | NackPacket | MetadataPacket | DataPacket


@dataclass(slots=True)
class LinkRecord:
    """One decoded measurement record from a snapshot or data log."""

    timestamp: datetime | None
    values: dict[int, Any]  # FieldName code -> decoded value (None if bad value)

    def get(self, name: FieldName) -> Any:
        """Return a decoded value by field name."""
        return self.values.get(int(name))

    def measurements(self) -> dict[MeasurementKind, float | None]:
        """Return the record's weather measurements keyed by MeasurementKind."""
        from .const import FIELD_TO_MEASUREMENT  # noqa: PLC0415

        out: dict[MeasurementKind, float | None] = {}
        for code, value in self.values.items():
            try:
                kind = FIELD_TO_MEASUREMENT[FieldName(code)]
            except (ValueError, KeyError):
                continue
            out[kind] = value if isinstance(value, (int, float)) else None
        return out


@dataclass(slots=True)
class DataLogResult:
    """Result of a Get Data Log / Get Data Log After transfer."""

    records: list[LinkRecord]
    last_sequence: int | None  # sequence number reported in End of Data
    fields: tuple[FieldDescriptor, ...] = ()  # record layout from metadata


# --------------------------------------------------------------------------- #
# Device description
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """Static information about a Kestrel model."""

    code: int
    name: str  # marketing name, e.g. "DROP D3"
    family: DeviceFamily
    advertising_name: str | None = None  # default local-name prefix, e.g. "D3"

    @property
    def model_code(self) -> ModelCode | None:
        """Return the ModelCode enum member if known."""
        try:
            return ModelCode(self.code)
        except ValueError:
            return None


@dataclass(frozen=True, slots=True)
class NKAdvertisement:
    """Parsed content of an NK scan response / advertisement."""

    model_code: int | None
    event_field: int | None  # FieldName code of a pending event, None if 0xFFFF/absent
    family: DeviceFamily
    local_name: str | None = None

    @property
    def model(self) -> ModelInfo | None:
        """Return model info if the model code is known."""
        from .models import model_from_code  # noqa: PLC0415

        return model_from_code(self.model_code) if self.model_code is not None else None


# --------------------------------------------------------------------------- #
# Measurements & device state
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Measurement:
    """A single measurement read from a device.

    ``present`` is False when the device model does not implement the
    measurement at all (such entities should not be created).  ``enabled``
    reflects the device-side on/off flag.  ``value`` is None whenever the
    device flagged the reading invalid or sent a bad-value sentinel.
    """

    kind: MeasurementKind
    value: float | None
    unit: NativeUnit
    present: bool = True
    enabled: bool = True
    valid: bool = True
    raw: bytes = b""
    derived: bool = False  # computed by the library, not read from the device


@dataclass(slots=True)
class DeviceInfo:
    """Identity information from the Device Information Service."""

    manufacturer: str | None = None
    model_number: str | None = None
    serial_number: str | None = None
    hardware_revision: str | None = None
    firmware_revision: str | None = None
    software_revision: str | None = None
    ble_profile_version: str | None = None


@dataclass(slots=True)
class DropSettings:
    """Kestrel DROP settings characteristic (20 bytes).

    None means "unknown / unsupported" on read and "leave unchanged" on write.
    """

    log_interval_s: int | None = None  # 0 disables logging
    wrap_log: bool | None = None
    transmission_rate_s: int | None = None  # 2-60 seconds between notifications
    security_level: int | None = None  # 0 open, 1 shared, 2 private
    setup_complete: bool | None = None
    reference_altitude_m: int | None = None  # signed 16-bit metres

    def is_empty(self) -> bool:
        """Return True if no setting is specified."""
        return all(
            v is None
            for v in (
                self.log_interval_s,
                self.wrap_log,
                self.transmission_rate_s,
                self.security_level,
                self.setup_complete,
                self.reference_altitude_m,
            )
        )


@dataclass(slots=True)
class KestrelSettings(DropSettings):
    """Kestrel 5000/3550 settings characteristic adds an auto-shutdown timeout."""

    auto_shutdown_min: int | None = None  # 0 disables, 0xFF unsupported


@dataclass(slots=True)
class DeviceState:
    """Everything the integration knows about a device after a poll."""

    address: str
    family: DeviceFamily
    model: ModelInfo | None = None
    name: str | None = None  # device name characteristic / advertised name
    info: DeviceInfo = field(default_factory=DeviceInfo)
    battery_percent: int | None = None
    battery_source: str | None = None  # "link" or "gatt"
    device_time: datetime | None = None  # naive, in the device's local time
    measurements: dict[MeasurementKind, Measurement] = field(default_factory=dict)
    settings: DropSettings | KestrelSettings | None = None
    rssi: int | None = None
    raw: dict[str, bytes] = field(default_factory=dict)  # char uuid -> raw bytes
    updated_at: datetime | None = None

    def present_measurements(self) -> dict[MeasurementKind, Measurement]:
        """Return only measurements the device implements."""
        return {k: m for k, m in self.measurements.items() if m.present}

    def value(self, kind: MeasurementKind) -> float | None:
        """Return the value of a measurement, or None if absent/invalid."""
        m = self.measurements.get(kind)
        return m.value if m is not None else None
