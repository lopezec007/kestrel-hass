"""LiNK protocol over the Bluetooth Mass Transfer Service.

The Mass Transfer Service exposes two characteristics: *central to
peripheral* (write) and *peripheral to central* (indicate).  Every LiNK
packet is HDLC framed and sent in fixed-size chunks (20 bytes, zero padded).
The peripheral acknowledges commands and expects every metadata / data packet
it sends to be acknowledged in turn.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, field
import logging
from typing import Any

from .const import (
    MASS_TRANSFER_CHUNK_SIZE,
    NO_COMMAND,
    CommandCode,
    NackReason,
)
from .decoding import MetadataAccumulator
from .hdlc import FrameDecoder
from .packets import decode_packet, encode_ack, encode_command, encode_nack
from .types import (
    AckPacket,
    CharacteristicMissingError,
    CommandPacket,
    DataPacket,
    KestrelError,
    LinkRecord,
    MetadataPacket,
    NackError,
    NackPacket,
    ProtocolError,
    ResponseTimeoutError,
)
from .uuids import (
    MASS_TRANSFER_C2P_UUID,
    MASS_TRANSFER_C2P_UUID_ALT,
    MASS_TRANSFER_P2C_UUID,
    MASS_TRANSFER_P2C_UUID_ALT,
    is_mass_transfer_uuid,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_PACKET_TIMEOUT_S = 3.0
DEFAULT_RESPONSE_TIMEOUT_S = 7.0

# Commands whose data packets are prefixed with a u16 packet number and that
# finish with an End of Data command.
LOG_COMMANDS: frozenset[int] = frozenset(
    {
        CommandCode.GET_DATA_LOG,
        CommandCode.GET_DATA_LOG_AFTER,
        CommandCode.GET_MAGNETOMETER_CAL_BUFFER,
    }
)
# Commands that stream metadata + data and finish with End of Data.
MULTI_PACKET_COMMANDS: frozenset[int] = LOG_COMMANDS | {CommandCode.GET_DATA_SNAPSHOT}
# Commands answered with a single data packet (or a single inbound command)
# and no End of Data.
SINGLE_PACKET_COMMANDS: frozenset[int] = frozenset(
    {
        CommandCode.GET_DATA_LOG_RECORD_COUNT,
        CommandCode.GET_DATA_LOG_RECORD_COUNT_AFTER,
        CommandCode.GET_DEVICE_SERIAL,
        CommandCode.GET_DEVICE_MODEL,
        CommandCode.GET_DEVICE_FIRMWARE,
        CommandCode.GET_DEVICE_HARDWARE,
        CommandCode.GET_DEVICE_NAME,
        CommandCode.GET_AUTOSTORE,
        CommandCode.GET_TIME,
        CommandCode.GET_BATTERY_LEVEL,
        CommandCode.GET_EEPROM_VERSION_NUMBERS,
        CommandCode.GET_BLUETOOTH_PROFILE_VERSION,
        CommandCode.GET_BLE_MODE,
        CommandCode.GET_CONTRAST_PERCENT,
        CommandCode.GET_BACKLIGHT_COLOR,
        CommandCode.GET_LANGUAGE,
        CommandCode.GET_BATTERY_CHEMISTRY,
        CommandCode.GET_AUTO_SHUTDOWN,
        CommandCode.GET_HEAT_STRESS_SETTING,
        CommandCode.GET_DIAGNOSTICS,
        CommandCode.GET_LOCK_ID,
        CommandCode.GET_PRIVACY_MODE_STATUS,
        CommandCode.GET_SETTINGS,
        CommandCode.GET_ACTIVE_INDEX,
        CommandCode.ECHO_TEST_PACKET,
        CommandCode.GET_SCREEN_MODE,
        CommandCode.GET_SUPPORTED_UNITS,
        CommandCode.GET_UNITS,
        CommandCode.GET_THI_MODEL,
        CommandCode.GET_WEATHER_STATION_DIAGNOSTICS,
        CommandCode.GET_DEVICE_STATUS,
        CommandCode.GET_CHARGER_VERSION,
        CommandCode.GET_BLE_ADDRESS,
    }
)
DATA_COMMANDS: frozenset[int] = MULTI_PACKET_COMMANDS | SINGLE_PACKET_COMMANDS

_INDICATE_PROPERTIES = ("indicate", "notify")
_WRITE_PROPERTIES = ("write", "write-without-response")


@dataclass(slots=True)
class LinkResponse:
    """Everything a device sent in reply to one command."""

    command: int
    acked: bool = False
    metadata: list[MetadataPacket] = field(default_factory=list)
    data: list[DataPacket] = field(default_factory=list)
    commands: list[CommandPacket] = field(default_factory=list)
    end_of_data: bytes | None = None

    @property
    def numbered(self) -> bool:
        """Return True if the data packets carry a packet number."""
        return self.command in LOG_COMMANDS

    @property
    def payload(self) -> bytes:
        """Return the concatenated data payload (single-packet replies)."""
        return b"".join(packet.payload for packet in self.data)

    def records(self, *, numbered: bool | None = None) -> list[LinkRecord]:
        """Decode the data packets into records using the received metadata.

        Args:
            numbered: Whether data packets start with a u16 packet number.
                Defaults to True for data-log commands.

        Returns:
            Decoded records in transmission order.  Empty if no metadata was
            received.
        """
        if numbered is None:
            numbered = self.numbered
        accumulator = MetadataAccumulator()
        for meta in self.metadata:
            accumulator.add(meta)
        if not accumulator.has_metadata:
            return []
        layout = accumulator.layout()
        records: list[LinkRecord] = []
        for packet in self.data:
            try:
                _number, decoded = layout.decode_records(
                    packet.payload, numbered=numbered
                )
            except ProtocolError as err:
                _LOGGER.debug("Skipping undecodable data packet: %s", err)
                continue
            records.extend(decoded)
        return records


@dataclass(slots=True)
class _Pending:
    """Bookkeeping for the command currently in flight."""

    response: LinkResponse
    acked: asyncio.Future[None]
    packet_event: asyncio.Event
    done: bool = False
    expected_packet_number: int = 0


def _iter_services(services: Any) -> Iterable[Any]:
    """Yield service objects from a bleak service collection or iterable."""
    if services is None:
        return ()
    inner = getattr(services, "services", None)
    if isinstance(inner, dict):
        return inner.values()
    try:
        return list(services)
    except TypeError:
        return ()


class LinkTransport:
    """Send LiNK commands and collect responses over the Mass Transfer Service."""

    def __init__(
        self,
        client: Any,
        *,
        chunk_size: int = MASS_TRANSFER_CHUNK_SIZE,
        timeout: float = DEFAULT_PACKET_TIMEOUT_S,
        response_timeout: float = DEFAULT_RESPONSE_TIMEOUT_S,
    ) -> None:
        """Create a transport around a connected GATT client.

        Args:
            client: A bleak-like client (``services``, ``write_gatt_char``,
                ``start_notify``, ``stop_notify``).
            chunk_size: Characteristic write size; chunks are zero padded.
            timeout: Idle timeout between consecutive packets and for the
                initial Ack.
            response_timeout: Maximum wait for the first data packet after
                the Ack (some devices compute for several seconds).
        """
        self._client = client
        self._chunk_size = chunk_size
        self._timeout = timeout
        self._response_timeout = response_timeout
        self._decoder = FrameDecoder()
        self._cmd_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._pending: _Pending | None = None
        self._p2c: Any = None
        self._c2p: Any = None
        self._started = False
        self._tasks: set[asyncio.Task[None]] = set()
        self.unsolicited: list[Any] = []

    # ------------------------------------------------------------------ #
    # Characteristic discovery
    # ------------------------------------------------------------------ #

    def locate(self, services: Any) -> tuple[Any, Any]:
        """Find the (peripheral→central, central→peripheral) characteristics.

        Characteristics are chosen by their properties inside the Mass
        Transfer service; the documented short ids (in either byte order) are
        only a fallback.

        Raises:
            CharacteristicMissingError: If the service or a characteristic is
                absent.
        """
        p2c: Any = None
        c2p: Any = None
        found_service = False
        for service in _iter_services(services):
            uuid = str(getattr(service, "uuid", "")).lower()
            if not is_mass_transfer_uuid(uuid):
                continue
            found_service = True
            for char in getattr(service, "characteristics", ()):
                props = {str(p).lower() for p in getattr(char, "properties", ())}
                if p2c is None and any(p in props for p in _INDICATE_PROPERTIES):
                    p2c = char
                elif c2p is None and any(p in props for p in _WRITE_PROPERTIES):
                    c2p = char
            if p2c is None or c2p is None:
                by_uuid = {
                    str(c.uuid).lower(): c
                    for c in getattr(service, "characteristics", ())
                }
                if p2c is None:
                    p2c = by_uuid.get(MASS_TRANSFER_P2C_UUID) or by_uuid.get(
                        MASS_TRANSFER_P2C_UUID_ALT
                    )
                if c2p is None:
                    c2p = by_uuid.get(MASS_TRANSFER_C2P_UUID) or by_uuid.get(
                        MASS_TRANSFER_C2P_UUID_ALT
                    )
            break
        if not found_service:
            raise CharacteristicMissingError("Mass Transfer Service not found")
        if p2c is None or c2p is None:
            raise CharacteristicMissingError(
                "Mass Transfer Service lacks the indicate/write characteristics"
            )
        return p2c, c2p

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        """Locate the characteristics and subscribe to indications."""
        if self._started:
            return
        self._p2c, self._c2p = self.locate(getattr(self._client, "services", None))
        self._decoder.reset()
        await self._client.start_notify(self._p2c, self._on_indication)
        self._started = True

    async def stop(self) -> None:
        """Unsubscribe from indications and cancel background acks."""
        if not self._started:
            return
        self._started = False
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()
        try:
            await self._client.stop_notify(self._p2c)
        except Exception as err:
            _LOGGER.debug("stop_notify failed: %s", err)

    # ------------------------------------------------------------------ #
    # Sending
    # ------------------------------------------------------------------ #

    def _chunks(self, frame: bytes) -> list[bytes]:
        size = self._chunk_size
        chunks = [frame[i : i + size] for i in range(0, len(frame), size)]
        if chunks and len(chunks[-1]) < size:
            chunks[-1] = chunks[-1].ljust(size, b"\x00")
        return chunks

    async def _send_frame(self, frame: bytes) -> None:
        async with self._write_lock:
            for chunk in self._chunks(frame):
                await self._client.write_gatt_char(self._c2p, chunk, response=True)

    def _schedule_send(self, frame: bytes) -> None:
        task = asyncio.get_running_loop().create_task(self._send_frame_logged(frame))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _send_frame_logged(self, frame: bytes) -> None:
        try:
            await self._send_frame(frame)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.debug("Failed to send ack/nack: %s", err)

    # ------------------------------------------------------------------ #
    # Receiving
    # ------------------------------------------------------------------ #

    def _on_indication(self, _sender: Any, data: bytearray) -> None:
        """Handle an indication from the peripheral (sync bleak callback)."""
        for payload in self._decoder.feed(bytes(data)):
            if not payload:
                # Two zero padding bytes after a closing flag validate as an
                # empty frame (FCS of b"" is 0x0000); ignore them.
                continue
            try:
                packet = decode_packet(payload)
            except ProtocolError as err:
                _LOGGER.debug("Dropping undecodable packet %s: %s", payload.hex(), err)
                self._schedule_send(encode_nack(NO_COMMAND, NackReason.BAD_DATA))
                continue
            self._dispatch(packet)

    def _signal(self, pending: _Pending) -> None:
        pending.packet_event.set()

    def _dispatch(self, packet: Any) -> None:
        pending = self._pending
        if isinstance(packet, AckPacket):
            if pending is not None and not pending.acked.done():
                pending.response.acked = True
                pending.acked.set_result(None)
            return
        if isinstance(packet, NackPacket):
            if pending is not None and not pending.acked.done():
                pending.acked.set_exception(
                    NackError(packet.command, packet.reason, packet.information)
                )
            else:
                _LOGGER.debug("Unexpected nack: %r", packet)
            return
        if isinstance(packet, MetadataPacket):
            self._schedule_send(encode_ack(NO_COMMAND))
            if pending is not None:
                pending.response.metadata.append(packet)
                self._implicit_ack(pending)
                self._signal(pending)
            else:
                self.unsolicited.append(packet)
            return
        if isinstance(packet, DataPacket):
            if pending is None:
                self.unsolicited.append(packet)
                self._schedule_send(encode_ack(NO_COMMAND))
                return
            if pending.response.numbered:
                if len(packet.payload) < 2:
                    self._schedule_send(
                        encode_nack(NO_COMMAND, NackReason.SHORT_PACKET)
                    )
                    return
                number = packet.payload[0] | (packet.payload[1] << 8)
                if number != pending.expected_packet_number:
                    expected = pending.expected_packet_number
                    _LOGGER.debug(
                        "Out of sequence data packet %d (expected %d)", number, expected
                    )
                    self._schedule_send(
                        encode_nack(
                            NO_COMMAND,
                            NackReason.INVALID_PACKET_SEQUENCE,
                            expected.to_bytes(2, "little"),
                        )
                    )
                    return
                pending.expected_packet_number = (number + 1) & 0xFFFF
            self._schedule_send(encode_ack(NO_COMMAND))
            pending.response.data.append(packet)
            self._implicit_ack(pending)
            self._signal(pending)
            return
        if isinstance(packet, CommandPacket):
            self._schedule_send(encode_ack(packet.command))
            if packet.command == CommandCode.END_OF_DATA:
                if pending is not None:
                    pending.response.end_of_data = packet.parameters
                    pending.done = True
                    self._implicit_ack(pending)
                    self._signal(pending)
                return
            if pending is not None:
                pending.response.commands.append(packet)
                self._implicit_ack(pending)
                self._signal(pending)
            else:
                self.unsolicited.append(packet)

    @staticmethod
    def _implicit_ack(pending: _Pending) -> None:
        """Treat data arriving before an Ack as an implicit acknowledgement."""
        if not pending.acked.done():
            pending.response.acked = True
            pending.acked.set_result(None)

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #

    async def send_command(
        self,
        code: int,
        params: bytes = b"",
        *,
        expect_data: bool | None = None,
    ) -> LinkResponse:
        """Send a command and collect the device's response.

        Args:
            code: Command code.
            params: Command parameters.
            expect_data: Force waiting (or not) for data packets; by default
                decided from the command code.

        Returns:
            The collected response.

        Raises:
            NackError: The device rejected the command.
            ResponseTimeoutError: The device did not answer in time.
            KestrelError: The transport was not started.
        """
        if not self._started:
            raise KestrelError("Transport not started")
        code = int(code)
        wants_data = expect_data if expect_data is not None else code in DATA_COMMANDS
        single = code not in MULTI_PACKET_COMMANDS
        loop = asyncio.get_running_loop()
        async with self._cmd_lock:
            pending = _Pending(
                response=LinkResponse(command=code),
                acked=loop.create_future(),
                packet_event=asyncio.Event(),
            )
            self._pending = pending
            try:
                await self._send_frame(encode_command(code, params))
                try:
                    async with asyncio.timeout(self._timeout):
                        await pending.acked
                except TimeoutError as err:
                    raise ResponseTimeoutError(
                        f"No acknowledgement for command {code}"
                    ) from err
                if wants_data:
                    await self._collect(pending, single=single)
                return pending.response
            finally:
                self._pending = None

    def _has_reply(self, pending: _Pending) -> bool:
        return bool(pending.response.data or pending.response.commands)

    async def _collect(self, pending: _Pending, *, single: bool) -> None:
        """Wait for data packets until End of Data (or the first for ``single``)."""
        first = True
        while not pending.done:
            if single and self._has_reply(pending):
                return
            wait = self._response_timeout if first else self._timeout
            try:
                async with asyncio.timeout(wait):
                    await pending.packet_event.wait()
            except TimeoutError as err:
                raise ResponseTimeoutError(
                    f"Timed out waiting for data after command {pending.response.command}"
                ) from err
            pending.packet_event.clear()
            first = False


__all__ = [
    "DATA_COMMANDS",
    "LOG_COMMANDS",
    "MULTI_PACKET_COMMANDS",
    "SINGLE_PACKET_COMMANDS",
    "LinkResponse",
    "LinkTransport",
]
