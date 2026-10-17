"""Encoding and decoding of LiNK packets.

A packet is a four byte little-endian header ``[type:u16][size:u16]`` followed
by ``size`` bytes of data.  Exactly one packet is carried per HDLC frame.
"""

from __future__ import annotations

import struct

from .const import NO_COMMAND, PacketType
from .hdlc import encode_frame
from .types import (
    AckPacket,
    CommandPacket,
    DataPacket,
    FieldDescriptor,
    LinkPacket,
    MetadataPacket,
    NackPacket,
    ProtocolError,
)

HEADER_SIZE = 4
_HEADER = struct.Struct("<HH")
_U16 = struct.Struct("<H")
_FIELD = struct.Struct("<HHH")


def _u16(value: int) -> bytes:
    if not 0 <= value <= 0xFFFF:
        raise ProtocolError(f"Value {value} does not fit in 16 bits")
    return _U16.pack(value)


def _packet_data(packet: LinkPacket) -> bytes:
    if isinstance(packet, CommandPacket):
        return _u16(packet.command) + bytes(packet.parameters)
    if isinstance(packet, AckPacket):
        return _u16(packet.command)
    if isinstance(packet, NackPacket):
        return _u16(packet.command) + _u16(packet.reason) + bytes(packet.information)
    if isinstance(packet, MetadataPacket):
        data = bytearray()
        if not packet.start:
            data += _u16(packet.packet_number or 0)
        for desc in packet.fields:
            data += _FIELD.pack(desc.name, desc.unit, desc.size)
        return bytes(data)
    if isinstance(packet, DataPacket):
        return bytes(packet.payload)
    raise ProtocolError(f"Unsupported packet {packet!r}")


def encode_packet(packet: LinkPacket) -> bytes:
    """Serialise a packet into header + data (not yet HDLC framed)."""
    data = _packet_data(packet)
    return _HEADER.pack(int(packet.packet_type), len(data)) + data


def _decode_fields(data: bytes, what: str) -> tuple[FieldDescriptor, ...]:
    if len(data) % _FIELD.size:
        raise ProtocolError(f"{what} field list has a partial descriptor")
    return tuple(
        FieldDescriptor(name, unit, size)
        for name, unit, size in _FIELD.iter_unpack(data)
    )


def decode_packet(data: bytes) -> LinkPacket:
    """Parse header + data bytes into a packet dataclass.

    Raises:
        ProtocolError: When the header is short, the declared size does not
            match the actual length, the type is unknown, or the payload is
            malformed for its type.
    """
    if len(data) < HEADER_SIZE:
        raise ProtocolError("Packet shorter than its header")
    type_code, size = _HEADER.unpack_from(data)
    body = data[HEADER_SIZE:]
    if len(body) != size:
        raise ProtocolError(
            f"Packet declares {size} data bytes but carries {len(body)}"
        )
    try:
        packet_type = PacketType(type_code)
    except ValueError as err:
        raise ProtocolError(f"Unknown packet type {type_code}") from err

    if packet_type is PacketType.COMMAND:
        if len(body) < 2:
            raise ProtocolError("Command packet lacks a command code")
        return CommandPacket(_U16.unpack_from(body)[0], bytes(body[2:]))
    if packet_type is PacketType.ACK:
        if len(body) < 2:
            raise ProtocolError("Ack packet lacks a command code")
        return AckPacket(_U16.unpack_from(body)[0])
    if packet_type is PacketType.NACK:
        if len(body) < 4:
            raise ProtocolError("Nack packet lacks command/reason codes")
        command, reason = struct.unpack_from("<HH", body)
        return NackPacket(command, reason, bytes(body[4:]))
    if packet_type is PacketType.METADATA_START:
        return MetadataPacket(_decode_fields(body, "Metadata Start"), start=True)
    if packet_type is PacketType.METADATA:
        if len(body) < 2:
            raise ProtocolError("Metadata packet lacks a packet number")
        number = _U16.unpack_from(body)[0]
        return MetadataPacket(
            _decode_fields(body[2:], "Metadata"), start=False, packet_number=number
        )
    return DataPacket(bytes(body))


def encode_command(code: int, params: bytes = b"") -> bytes:
    """Return a complete HDLC frame carrying a command packet."""
    return encode_frame(encode_packet(CommandPacket(int(code), params)))


def encode_ack(command: int = NO_COMMAND) -> bytes:
    """Return a complete HDLC frame carrying an Ack packet."""
    return encode_frame(encode_packet(AckPacket(int(command))))


def encode_nack(command: int, reason: int, information: bytes = b"") -> bytes:
    """Return a complete HDLC frame carrying a Nack packet."""
    return encode_frame(
        encode_packet(NackPacket(int(command), int(reason), information))
    )
