"""HDLC framing for the LiNK Communications Protocol.

Every LiNK packet travels inside an HDLC frame as described in RFC 1662:
a 16-bit frame check sequence (FCS) is appended to the payload, the
``0x7E``/``0x7D`` bytes are escaped, and the result is delimited by ``0x7E``
flag bytes on both ends.
"""

from __future__ import annotations

from .types import FrameError

FLAG = 0x7E
ESCAPE = 0x7D
ESCAPE_XOR = 0x20

FCS_INIT = 0xFFFF
FCS_FINAL_XOR = 0xFFFF
_FCS_POLY = 0x8408  # reflected CRC-16/X-25 polynomial


def _build_fcs_table() -> tuple[int, ...]:
    table: list[int] = []
    for byte in range(256):
        value = byte
        for _ in range(8):
            if value & 1:
                value = (value >> 1) ^ _FCS_POLY
            else:
                value >>= 1
        table.append(value & 0xFFFF)
    return tuple(table)


_FCS_TABLE = _build_fcs_table()


def fcs16(data: bytes) -> int:
    """Compute the RFC 1662 16-bit frame check sequence of ``data``.

    Args:
        data: Payload bytes (without FCS).

    Returns:
        The FCS value; transmit it least significant byte first.
    """
    fcs = FCS_INIT
    for byte in data:
        fcs = (fcs >> 8) ^ _FCS_TABLE[(fcs ^ byte) & 0xFF]
    return fcs ^ FCS_FINAL_XOR


def _escape(data: bytes) -> bytes:
    out = bytearray()
    for byte in data:
        if byte in (FLAG, ESCAPE):
            out.append(ESCAPE)
            out.append(byte ^ ESCAPE_XOR)
        else:
            out.append(byte)
    return bytes(out)


def _unescape(data: bytes) -> bytes:
    out = bytearray()
    pending_escape = False
    for byte in data:
        if pending_escape:
            out.append(byte ^ ESCAPE_XOR)
            pending_escape = False
        elif byte == ESCAPE:
            pending_escape = True
        elif byte == FLAG:
            raise FrameError("Unescaped flag byte inside frame")
        else:
            out.append(byte)
    if pending_escape:
        raise FrameError("Frame ends with a dangling escape byte")
    return bytes(out)


def encode_frame(payload: bytes) -> bytes:
    """Wrap ``payload`` in an HDLC frame (FCS, escaping, flag delimiters)."""
    fcs = fcs16(payload)
    body = payload + bytes((fcs & 0xFF, fcs >> 8))
    return bytes((FLAG,)) + _escape(body) + bytes((FLAG,))


def _decode_body(escaped_body: bytes) -> bytes:
    body = _unescape(escaped_body)
    if len(body) < 2:
        raise FrameError("Frame too short to contain an FCS")
    payload, fcs_bytes = body[:-2], body[-2:]
    expected = fcs16(payload)
    received = fcs_bytes[0] | (fcs_bytes[1] << 8)
    if expected != received:
        raise FrameError(
            f"FCS mismatch: expected 0x{expected:04X}, received 0x{received:04X}"
        )
    return payload


def decode_frame(frame: bytes) -> bytes:
    """Decode a single complete HDLC frame and return its payload.

    Args:
        frame: Bytes starting and ending with the ``0x7E`` flag.

    Returns:
        The validated payload with the FCS removed.

    Raises:
        FrameError: On missing delimiters, bad escapes, or FCS mismatch.
    """
    if len(frame) < 2 or frame[0] != FLAG or frame[-1] != FLAG:
        raise FrameError("Frame is not delimited by flag bytes")
    return _decode_body(frame[1:-1])


class FrameDecoder:
    """Streaming HDLC decoder.

    Feed arbitrary chunks of bytes; complete, validated payloads are returned
    as they appear.  Bytes outside a frame (such as the zero padding of Mass
    Transfer chunks) are ignored, back-to-back frames are handled, empty
    frames are skipped and corrupt frames are dropped without stopping the
    decoder.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._in_frame = False
        self.dropped_frames = 0

    def reset(self) -> None:
        """Discard any partially received frame."""
        self._buffer.clear()
        self._in_frame = False

    def feed(self, data: bytes) -> list[bytes]:
        """Consume ``data`` and return every payload completed by it."""
        payloads: list[bytes] = []
        for byte in data:
            if byte == FLAG:
                if self._in_frame:
                    if self._buffer:
                        try:
                            payload = _decode_body(bytes(self._buffer))
                        except FrameError:
                            # Zero padding between frames (Mass Transfer pads
                            # chunks to 20 bytes) is not a corrupt frame.
                            if any(self._buffer):
                                self.dropped_frames += 1
                        else:
                            # A body of only an FCS (e.g. two zero padding bytes
                            # after a closing flag) carries no packet.
                            if payload:
                                payloads.append(payload)
                        self._buffer.clear()
                    # An empty frame (7E 7E) simply restarts the frame.
                    self._in_frame = True
                else:
                    self._in_frame = True
                    self._buffer.clear()
            elif self._in_frame:
                self._buffer.append(byte)
        return payloads
