"""Tests for LiNK packet encoding/decoding."""

from __future__ import annotations

import pytest

from custom_components.kestrel.kestrel_link.const import (
    CommandCode,
    FieldName,
    FieldUnit,
    NackReason,
    PacketType,
)
from custom_components.kestrel.kestrel_link.hdlc import decode_frame
from custom_components.kestrel.kestrel_link.packets import (
    decode_packet,
    encode_ack,
    encode_command,
    encode_nack,
    encode_packet,
)
from custom_components.kestrel.kestrel_link.types import (
    AckPacket,
    CommandPacket,
    DataPacket,
    FieldDescriptor,
    MetadataPacket,
    NackPacket,
    ProtocolError,
)

DOC_METADATA_START = bytes.fromhex(
    "01001E0000002400070002001C00020005001B0002000A001C0002000B001C000200"
)
DOC_FIELDS = (
    FieldDescriptor(FieldName.TIMESTAMP, FieldUnit.BLUETOOTH_DATE_TIME, 7),
    FieldDescriptor(FieldName.DRY_BULB_TEMP, FieldUnit.DEGREES_C_X100_I16, 2),
    FieldDescriptor(FieldName.RELATIVE_HUMIDITY, FieldUnit.PERCENT_X100_U16, 2),
    FieldDescriptor(FieldName.HEAT_INDEX, FieldUnit.DEGREES_C_X100_I16, 2),
    FieldDescriptor(FieldName.DEW_POINT, FieldUnit.DEGREES_C_X100_I16, 2),
)


def test_get_data_snapshot_command_bytes() -> None:
    assert encode_packet(CommandPacket(CommandCode.GET_DATA_SNAPSHOT)) == bytes.fromhex(
        "000002000000"
    )


def test_end_of_data_command_bytes() -> None:
    assert encode_packet(CommandPacket(CommandCode.END_OF_DATA)) == bytes.fromhex(
        "000002001200"
    )
    packet = decode_packet(bytes.fromhex("000002001200"))
    assert packet == CommandPacket(CommandCode.END_OF_DATA, b"")


def test_ack_bytes() -> None:
    assert encode_packet(AckPacket(CommandCode.GET_DATA_SNAPSHOT)) == bytes.fromhex(
        "040002000000"
    )
    assert decode_packet(bytes.fromhex("04000200FFFF")) == AckPacket(0xFFFF)


def test_metadata_start_doc_example() -> None:
    packet = decode_packet(DOC_METADATA_START)
    assert isinstance(packet, MetadataPacket)
    assert packet.start is True
    assert packet.packet_number is None
    assert packet.fields == DOC_FIELDS
    assert packet.fields[0].field_name is FieldName.TIMESTAMP
    assert packet.fields[0].field_unit is FieldUnit.BLUETOOTH_DATE_TIME
    assert encode_packet(packet) == DOC_METADATA_START


@pytest.mark.parametrize(
    "packet",
    [
        CommandPacket(CommandCode.SET_LOG_INTERVAL, b"\x3c\x00\x00"),
        CommandPacket(0x1234, b""),
        AckPacket(),
        AckPacket(CommandCode.GET_DATA_LOG),
        NackPacket(
            CommandCode.GET_DATA_LOG, NackReason.INVALID_PACKET_SEQUENCE, b"\x05\x00"
        ),
        NackPacket(0xFFFF, NackReason.BAD_CHECKSUM),
        MetadataPacket(DOC_FIELDS, start=True),
        MetadataPacket(DOC_FIELDS[:2], start=False, packet_number=3),
        MetadataPacket((), start=False, packet_number=0),
        DataPacket(b""),
        DataPacket(bytes(range(60))),
    ],
)
def test_round_trip(packet) -> None:
    encoded = encode_packet(packet)
    assert int.from_bytes(encoded[0:2], "little") == int(packet.packet_type)
    assert int.from_bytes(encoded[2:4], "little") == len(encoded) - 4
    assert decode_packet(encoded) == packet


def test_packet_type_property() -> None:
    assert MetadataPacket((), start=True).packet_type is PacketType.METADATA_START
    assert MetadataPacket((), packet_number=1).packet_type is PacketType.METADATA
    assert DataPacket(b"").packet_type is PacketType.DATA


def test_unknown_field_codes_tolerated() -> None:
    desc = FieldDescriptor(0x7FFF, 0x7FFE, 1)
    assert desc.field_name is None
    assert desc.field_unit is None
    packet = decode_packet(encode_packet(MetadataPacket((desc,), start=True)))
    assert packet.fields == (desc,)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\x00\x00\x02",
        bytes.fromhex("000003000600"),  # size too large
        bytes.fromhex("000001000600"),  # size too small
        bytes.fromhex("090000"),  # short
        bytes.fromhex("09000000"),  # unknown type
        bytes.fromhex("0000010000"),  # odd length
        bytes.fromhex("00000000"),  # command without code
        bytes.fromhex("04000000"),  # ack without code
        bytes.fromhex("050002000100"),  # nack without reason
        bytes.fromhex("0100030001000000"),  # partial descriptor
        bytes.fromhex("020001000A"),  # metadata without packet number
    ],
)
def test_decode_rejects_malformed(data: bytes) -> None:
    with pytest.raises(ProtocolError):
        decode_packet(data)


def test_encode_rejects_oversized_values() -> None:
    with pytest.raises(ProtocolError):
        encode_packet(CommandPacket(0x10000))


def test_encode_command_is_framed() -> None:
    frame = encode_command(CommandCode.GET_DEVICE_SERIAL)
    assert frame[0] == 0x7E
    assert frame[-1] == 0x7E
    assert decode_frame(frame) == bytes.fromhex("000002000600")
    assert decode_packet(decode_frame(frame)) == CommandPacket(
        CommandCode.GET_DEVICE_SERIAL
    )


def test_encode_ack_and_nack_framed() -> None:
    assert decode_packet(decode_frame(encode_ack())) == AckPacket(0xFFFF)
    assert decode_packet(
        decode_frame(encode_ack(CommandCode.END_OF_DATA))
    ) == AckPacket(CommandCode.END_OF_DATA)
    nack = decode_packet(
        decode_frame(
            encode_nack(
                CommandCode.GET_DATA_LOG,
                NackReason.INVALID_PACKET_SEQUENCE,
                b"\x02\x00",
            )
        )
    )
    assert nack == NackPacket(
        CommandCode.GET_DATA_LOG, NackReason.INVALID_PACKET_SEQUENCE, b"\x02\x00"
    )
