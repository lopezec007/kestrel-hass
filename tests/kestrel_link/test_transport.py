"""Tests for the LiNK Mass Transfer transport."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest

from custom_components.kestrel.kestrel_link.const import (
    NO_COMMAND,
    CommandCode,
    FieldName,
    NackReason,
    PacketType,
)
from custom_components.kestrel.kestrel_link.hdlc import FrameDecoder, encode_frame
from custom_components.kestrel.kestrel_link.packets import (
    decode_packet,
    encode_ack,
    encode_command,
    encode_nack,
    encode_packet,
)
from custom_components.kestrel.kestrel_link.transport import (
    DATA_COMMANDS,
    LinkResponse,
    LinkTransport,
)
from custom_components.kestrel.kestrel_link.types import (
    AckPacket,
    CharacteristicMissingError,
    CommandPacket,
    DataPacket,
    FieldDescriptor,
    KestrelError,
    MetadataPacket,
    NackError,
    NackPacket,
    ResponseTimeoutError,
)
from custom_components.kestrel.kestrel_link.uuids import (
    MASS_TRANSFER_C2P_UUID,
    MASS_TRANSFER_C2P_UUID_ALT,
    MASS_TRANSFER_P2C_UUID,
    MASS_TRANSFER_P2C_UUID_ALT,
    MASS_TRANSFER_SERVICE_UUID,
)

# Metadata start packet from the NK worked example (DROP 2 snapshot).
METADATA_START = bytes.fromhex(
    "01001E0000002400070002001C00020005001B0002000A001C0002000B001C000200"
)
SNAPSHOT_DATA = bytes.fromhex("03000F0007DD01010000019209A00FD70AD007")
END_OF_DATA = bytes.fromhex("000002001200")
ACK_SNAPSHOT = bytes.fromhex("040002000000")
RECORD = bytes.fromhex("07DD01010000019209A00FD70AD007")


class FakeChar:
    def __init__(self, uuid: str, properties: list[str]) -> None:
        self.uuid = uuid
        self.properties = properties


class FakeService:
    def __init__(self, uuid: str, characteristics: list[FakeChar]) -> None:
        self.uuid = uuid
        self.characteristics = characteristics


def mass_transfer_services(
    p2c_uuid: str = MASS_TRANSFER_P2C_UUID,
    c2p_uuid: str = MASS_TRANSFER_C2P_UUID,
    *,
    with_properties: bool = True,
) -> list[FakeService]:
    p2c = FakeChar(p2c_uuid, ["indicate"] if with_properties else [])
    c2p = FakeChar(c2p_uuid, ["write"] if with_properties else [])
    # Put the write characteristic first to prove selection is by property.
    return [
        FakeService(
            "0000180f-0000-1000-8000-00805f9b34fb",
            [FakeChar("00002a19-0000-1000-8000-00805f9b34fb", ["read"])],
        ),
        FakeService(MASS_TRANSFER_SERVICE_UUID, [c2p, p2c]),
    ]


class FakeLinkClient:
    """A scripted peripheral speaking LiNK over the Mass Transfer Service."""

    def __init__(self, services: list[FakeService] | None = None) -> None:
        self.services = services if services is not None else mass_transfer_services()
        self.writes: list[bytes] = []
        self.received: list[Any] = []  # decoded packets the device received
        self.callback: Callable[[Any, bytearray], Any] | None = None
        self.notify_char: Any = None
        self.stopped = False
        self._decoder = FrameDecoder()
        self.responder: Callable[[Any], list[bytes]] | None = None
        self.chunk_size = 20

    async def start_notify(self, char: Any, callback: Callable[..., Any]) -> None:
        self.notify_char = char
        self.callback = callback

    async def stop_notify(self, char: Any) -> None:
        assert char is self.notify_char
        self.stopped = True

    async def write_gatt_char(
        self, char: Any, data: bytes, response: bool = True
    ) -> None:
        assert response is True
        self.writes.append(bytes(data))
        for payload in self._decoder.feed(bytes(data)):
            if not payload:  # two zero pad bytes validate as an empty frame
                continue
            packet = decode_packet(payload)
            self.received.append(packet)
            if self.responder is not None:
                for frame in self.responder(packet):
                    self.indicate(frame)

    def indicate(self, frame: bytes) -> None:
        """Deliver a frame to the central in zero padded chunks, asynchronously."""
        assert self.callback is not None
        loop = asyncio.get_running_loop()
        for i in range(0, len(frame), self.chunk_size):
            chunk = frame[i : i + self.chunk_size].ljust(self.chunk_size, b"\x00")
            loop.call_soon(self.callback, self.notify_char, bytearray(chunk))


def frame_packet(packet: Any) -> bytes:
    return encode_frame(encode_packet(packet))


async def flush(ticks: int = 4) -> None:
    """Let scheduled ack tasks run."""
    for _ in range(ticks):
        await asyncio.sleep(0)


@pytest.fixture
async def transport_pair() -> tuple[LinkTransport, FakeLinkClient]:
    client = FakeLinkClient()
    transport = LinkTransport(client, timeout=0.2, response_timeout=0.3)
    await transport.start()
    return transport, client


async def test_locate_by_property() -> None:
    client = FakeLinkClient()
    transport = LinkTransport(client)
    p2c, c2p = transport.locate(client.services)
    assert p2c.uuid == MASS_TRANSFER_P2C_UUID
    assert c2p.uuid == MASS_TRANSFER_C2P_UUID


async def test_locate_by_uuid_fallback_either_byte_order() -> None:
    services = mass_transfer_services(
        MASS_TRANSFER_P2C_UUID_ALT, MASS_TRANSFER_C2P_UUID_ALT, with_properties=False
    )
    transport = LinkTransport(FakeLinkClient(services))
    p2c, c2p = transport.locate(services)
    assert p2c.uuid == MASS_TRANSFER_P2C_UUID_ALT
    assert c2p.uuid == MASS_TRANSFER_C2P_UUID_ALT


async def test_locate_accepts_bleak_style_collection() -> None:
    class Collection:
        def __init__(self, services: list[FakeService]) -> None:
            self.services = dict(enumerate(services))

    transport = LinkTransport(FakeLinkClient())
    p2c, _ = transport.locate(Collection(mass_transfer_services()))
    assert p2c.uuid == MASS_TRANSFER_P2C_UUID


async def test_locate_missing_service() -> None:
    transport = LinkTransport(FakeLinkClient([]))
    with pytest.raises(CharacteristicMissingError):
        transport.locate([])


async def test_locate_missing_characteristic() -> None:
    services = [
        FakeService(
            MASS_TRANSFER_SERVICE_UUID, [FakeChar(MASS_TRANSFER_C2P_UUID, ["write"])]
        )
    ]
    transport = LinkTransport(FakeLinkClient(services))
    with pytest.raises(CharacteristicMissingError):
        transport.locate(services)


async def test_send_requires_start() -> None:
    transport = LinkTransport(FakeLinkClient())
    with pytest.raises(KestrelError):
        await transport.send_command(CommandCode.GET_DEVICE_SERIAL)


async def test_start_and_stop(
    transport_pair: tuple[LinkTransport, FakeLinkClient],
) -> None:
    transport, client = transport_pair
    assert client.callback is not None
    await transport.stop()
    assert client.stopped
    await transport.stop()  # idempotent


async def test_chunking_and_padding(
    transport_pair: tuple[LinkTransport, FakeLinkClient],
) -> None:
    transport, client = transport_pair
    client.responder = lambda packet: [encode_ack(CommandCode.ERASE_DATA_LOG)]
    await transport.send_command(CommandCode.ERASE_DATA_LOG, expect_data=False)
    assert len(client.writes) == 1
    chunk = client.writes[0]
    assert len(chunk) == 20
    frame = encode_command(CommandCode.ERASE_DATA_LOG)
    assert len(frame) == 10  # 7E + 6 packet bytes + 2 FCS + 7E
    assert chunk[: len(frame)] == frame
    assert chunk[len(frame) :] == bytes(10)
    assert client.received == [CommandPacket(CommandCode.ERASE_DATA_LOG, b"")]


async def test_large_frame_spans_chunks(
    transport_pair: tuple[LinkTransport, FakeLinkClient],
) -> None:
    transport, client = transport_pair
    client.responder = lambda packet: [encode_ack(CommandCode.SET_DEVICE_NAME)]
    await transport.send_command(
        CommandCode.SET_DEVICE_NAME, b"A" * 30, expect_data=False
    )
    assert len(client.writes) == 2
    assert all(len(w) == 20 for w in client.writes)
    assert client.received[-1] == CommandPacket(CommandCode.SET_DEVICE_NAME, b"A" * 30)


async def test_nack_raises(
    transport_pair: tuple[LinkTransport, FakeLinkClient],
) -> None:
    transport, client = transport_pair
    client.responder = lambda packet: [
        encode_nack(packet.command, NackReason.FEATURE_NOT_PRESENT, b"\x01\x02")
    ]
    with pytest.raises(NackError) as excinfo:
        await transport.send_command(CommandCode.GET_AUTOSTORE)
    assert excinfo.value.reason == NackReason.FEATURE_NOT_PRESENT
    assert excinfo.value.command == CommandCode.GET_AUTOSTORE
    assert excinfo.value.information == b"\x01\x02"
    assert "FEATURE_NOT_PRESENT" in str(excinfo.value)


async def test_ack_timeout(
    transport_pair: tuple[LinkTransport, FakeLinkClient],
) -> None:
    transport, _client = transport_pair
    with pytest.raises(ResponseTimeoutError):
        await transport.send_command(CommandCode.GET_DEVICE_SERIAL)
    # The transport is usable again afterwards.
    assert transport._pending is None


async def test_data_timeout_after_ack(
    transport_pair: tuple[LinkTransport, FakeLinkClient],
) -> None:
    transport, client = transport_pair
    client.responder = lambda packet: (
        [encode_ack(packet.command)] if isinstance(packet, CommandPacket) else []
    )
    with pytest.raises(ResponseTimeoutError):
        await transport.send_command(CommandCode.GET_DEVICE_SERIAL)


async def test_single_packet_identity(
    transport_pair: tuple[LinkTransport, FakeLinkClient],
) -> None:
    transport, client = transport_pair

    def responder(packet: Any) -> list[bytes]:
        if isinstance(packet, CommandPacket):
            return [encode_ack(packet.command), frame_packet(DataPacket(b"1234567"))]
        return []

    client.responder = responder
    response = await transport.send_command(CommandCode.GET_DEVICE_SERIAL)
    assert response.acked
    assert response.payload == b"1234567"
    await flush()
    # The data packet was acknowledged with Ack(0xFFFF).
    assert client.received[-1] == AckPacket(NO_COMMAND)


async def test_data_before_ack_is_implicit_ack(
    transport_pair: tuple[LinkTransport, FakeLinkClient],
) -> None:
    transport, client = transport_pair
    client.responder = lambda packet: (
        [frame_packet(DataPacket(b"\x57\x00"))]
        if isinstance(packet, CommandPacket)
        else []
    )
    response = await transport.send_command(CommandCode.GET_BATTERY_LEVEL)
    assert response.acked
    assert response.payload == b"\x57\x00"


async def test_snapshot_sequence_from_doc(
    transport_pair: tuple[LinkTransport, FakeLinkClient],
) -> None:
    """Replay the Get Data Snapshot exchange from the NK Weather Protocol."""
    transport, client = transport_pair
    state = {"step": 0}

    def responder(packet: Any) -> list[bytes]:
        if (
            isinstance(packet, CommandPacket)
            and packet.command == CommandCode.GET_DATA_SNAPSHOT
        ):
            state["step"] = 1
            return [ACK_SNAPSHOT_FRAME, encode_frame(METADATA_START)]
        if (
            isinstance(packet, AckPacket)
            and packet.command == NO_COMMAND
            and state["step"] == 1
        ):
            state["step"] = 2
            return [encode_frame(SNAPSHOT_DATA)]
        if (
            isinstance(packet, AckPacket)
            and packet.command == NO_COMMAND
            and state["step"] == 2
        ):
            state["step"] = 3
            return [encode_frame(END_OF_DATA)]
        return []

    client.responder = responder
    response = await transport.send_command(CommandCode.GET_DATA_SNAPSHOT)
    await flush()
    assert response.acked
    assert response.end_of_data == b""
    assert len(response.metadata) == 1 and response.metadata[0].start
    assert len(response.data) == 1
    records = response.records()
    assert len(records) == 1
    rec = records[0]
    assert rec.get(FieldName.DRY_BULB_TEMP) == pytest.approx(24.5)
    assert rec.get(FieldName.RELATIVE_HUMIDITY) == pytest.approx(40.0)
    assert rec.get(FieldName.HEAT_INDEX) == pytest.approx(27.75)
    assert rec.get(FieldName.DEW_POINT) == pytest.approx(20.0)
    assert rec.timestamp is not None and rec.timestamp.year == 2013
    # Device saw: command, Ack(meta), Ack(data), Ack(End of Data=18)
    assert [type(p) for p in client.received] == [
        CommandPacket,
        AckPacket,
        AckPacket,
        AckPacket,
    ]
    assert client.received[-1] == AckPacket(CommandCode.END_OF_DATA)


ACK_SNAPSHOT_FRAME = encode_frame(ACK_SNAPSHOT)


def _numbered(number: int, body: bytes) -> bytes:
    return frame_packet(DataPacket(number.to_bytes(2, "little") + body))


async def test_data_log_sequence(
    transport_pair: tuple[LinkTransport, FakeLinkClient],
) -> None:
    transport, client = transport_pair
    acks = {"n": 0}

    def responder(packet: Any) -> list[bytes]:
        if isinstance(packet, CommandPacket):
            return [encode_ack(packet.command), encode_frame(METADATA_START)]
        if isinstance(packet, AckPacket) and packet.command == NO_COMMAND:
            acks["n"] += 1
            if acks["n"] == 1:
                return [_numbered(0, RECORD * 2)]
            if acks["n"] == 2:
                return [_numbered(1, RECORD)]
            if acks["n"] == 3:
                return [
                    frame_packet(
                        CommandPacket(
                            CommandCode.END_OF_DATA, (42).to_bytes(8, "little")
                        )
                    )
                ]
        return []

    client.responder = responder
    response = await transport.send_command(CommandCode.GET_DATA_LOG)
    assert response.numbered
    assert response.end_of_data == (42).to_bytes(8, "little")
    assert len(response.records()) == 3


async def test_out_of_sequence_packet_is_nacked(
    transport_pair: tuple[LinkTransport, FakeLinkClient],
) -> None:
    transport, client = transport_pair
    acks = {"n": 0}

    def responder(packet: Any) -> list[bytes]:
        if isinstance(packet, CommandPacket):
            return [encode_ack(packet.command), encode_frame(METADATA_START)]
        if isinstance(packet, AckPacket) and packet.command == NO_COMMAND:
            acks["n"] += 1
            if acks["n"] == 1:
                return [_numbered(0, RECORD)]
            if acks["n"] == 2:
                return [_numbered(2, RECORD)]  # wrong: expected 1
            if acks["n"] == 3:
                return [frame_packet(CommandPacket(CommandCode.END_OF_DATA, b""))]
        if isinstance(packet, NackPacket):
            # Device retransmits the expected packet after the nack.
            expected = int.from_bytes(packet.information, "little")
            return [_numbered(expected, RECORD)]
        return []

    client.responder = responder
    response = await transport.send_command(CommandCode.GET_DATA_LOG_AFTER, bytes(8))
    nacks = [p for p in client.received if isinstance(p, NackPacket)]
    assert len(nacks) == 1
    assert nacks[0].reason == NackReason.INVALID_PACKET_SEQUENCE
    assert nacks[0].information == (1).to_bytes(2, "little")
    assert len(response.data) == 2
    assert len(response.records()) == 2


async def test_inbound_command_reply(
    transport_pair: tuple[LinkTransport, FakeLinkClient],
) -> None:
    """Get THI Model is answered with a Set THI Model command."""
    transport, client = transport_pair

    def responder(packet: Any) -> list[bytes]:
        if (
            isinstance(packet, CommandPacket)
            and packet.command == CommandCode.GET_THI_MODEL
        ):
            return [
                encode_ack(packet.command),
                frame_packet(CommandPacket(CommandCode.SET_THI_MODEL, b"\x42\x00")),
            ]
        return []

    client.responder = responder
    response = await transport.send_command(CommandCode.GET_THI_MODEL)
    assert response.commands == [CommandPacket(CommandCode.SET_THI_MODEL, b"\x42\x00")]
    await flush()
    assert client.received[-1] == AckPacket(CommandCode.SET_THI_MODEL)


async def test_corrupt_payload_is_nacked_bad_data(
    transport_pair: tuple[LinkTransport, FakeLinkClient],
) -> None:
    _transport, client = transport_pair
    # Valid HDLC frame carrying a packet whose declared size is wrong.
    client.indicate(encode_frame(bytes.fromhex("0300FF000102")))
    await flush()
    assert any(
        isinstance(p, NackPacket) and p.reason == NackReason.BAD_DATA
        for p in client.received
    )


async def test_unsolicited_packets_are_kept_and_acked(
    transport_pair: tuple[LinkTransport, FakeLinkClient],
) -> None:
    transport, client = transport_pair
    client.indicate(frame_packet(DataPacket(b"\x01")))
    client.indicate(encode_frame(METADATA_START))
    client.indicate(frame_packet(CommandPacket(CommandCode.KEEP_ALIVE)))
    await flush(8)
    assert len(transport.unsolicited) == 3
    assert [p.command for p in client.received if isinstance(p, AckPacket)] == [
        NO_COMMAND,
        NO_COMMAND,
        CommandCode.KEEP_ALIVE,
    ]


async def test_commands_are_serialised(
    transport_pair: tuple[LinkTransport, FakeLinkClient],
) -> None:
    transport, client = transport_pair
    order: list[int] = []

    def responder(packet: Any) -> list[bytes]:
        if isinstance(packet, CommandPacket):
            order.append(packet.command)
            return [
                encode_ack(packet.command),
                frame_packet(DataPacket(bytes([packet.command]))),
            ]
        return []

    client.responder = responder
    results = await asyncio.gather(
        transport.send_command(CommandCode.GET_DEVICE_SERIAL),
        transport.send_command(CommandCode.GET_DEVICE_MODEL),
    )
    assert order == [CommandCode.GET_DEVICE_SERIAL, CommandCode.GET_DEVICE_MODEL]
    assert results[0].payload == bytes([CommandCode.GET_DEVICE_SERIAL])
    assert results[1].payload == bytes([CommandCode.GET_DEVICE_MODEL])


def test_response_records_without_metadata() -> None:
    response = LinkResponse(
        command=CommandCode.GET_DATA_SNAPSHOT, data=[DataPacket(b"\x01\x02")]
    )
    assert response.records() == []


def test_response_records_skips_short_numbered_packet() -> None:
    response = LinkResponse(
        command=CommandCode.GET_DATA_LOG,
        metadata=[
            MetadataPacket(
                (FieldDescriptor(FieldName.DRY_BULB_TEMP, 28, 2),), start=True
            )
        ],
        data=[DataPacket(b"\x00"), DataPacket(b"\x00\x00\x92\x09")],
    )
    recs = response.records()
    assert len(recs) == 1
    assert recs[0].get(FieldName.DRY_BULB_TEMP) == pytest.approx(24.5)


def test_data_commands_table() -> None:
    assert CommandCode.GET_DATA_SNAPSHOT in DATA_COMMANDS
    assert CommandCode.ERASE_DATA_LOG not in DATA_COMMANDS
    assert PacketType.ACK == 4


async def test_two_byte_zero_padding_is_ignored(
    transport_pair: tuple[LinkTransport, FakeLinkClient],
) -> None:
    """A frame whose chunk leaves exactly two zero pad bytes must not be nacked."""
    transport, client = transport_pair
    # METADATA_START frame is 38 bytes -> 20 + 18, leaving 2 zero bytes.
    assert len(encode_frame(METADATA_START)) == 38
    client.indicate(encode_frame(METADATA_START))
    await flush(6)
    assert not any(isinstance(p, NackPacket) for p in client.received)
    assert len(transport.unsolicited) == 1
