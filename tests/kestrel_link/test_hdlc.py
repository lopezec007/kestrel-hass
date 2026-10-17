"""Tests for HDLC framing."""

from __future__ import annotations

import pytest

from custom_components.kestrel.kestrel_link.hdlc import (
    FrameDecoder,
    decode_frame,
    encode_frame,
    fcs16,
)
from custom_components.kestrel.kestrel_link.types import FrameError

DOC_INPUT = bytes.fromhex("04807E287D48")
DOC_FRAME = bytes.fromhex("7E04807D5E287D5D4878D27E")
GET_SERIAL_PACKET = bytes.fromhex("000002000600")


def test_fcs_matches_doc_example() -> None:
    fcs = fcs16(DOC_INPUT)
    assert bytes((fcs & 0xFF, fcs >> 8)) == bytes.fromhex("78D2")


def test_fcs_rfc1662_check_value() -> None:
    # CRC-16/X-25 check value for "123456789".
    assert fcs16(b"123456789") == 0x906E


def test_encode_frame_matches_doc_example() -> None:
    assert encode_frame(DOC_INPUT) == DOC_FRAME


def test_decode_frame_matches_doc_example() -> None:
    assert decode_frame(DOC_FRAME) == DOC_INPUT


def test_get_serial_round_trip() -> None:
    frame = encode_frame(GET_SERIAL_PACKET)
    assert frame[0] == 0x7E
    assert frame[-1] == 0x7E
    assert frame[1:7] == GET_SERIAL_PACKET
    assert decode_frame(frame) == GET_SERIAL_PACKET


@pytest.mark.parametrize(
    "frame",
    [
        b"",
        b"\x7e",
        b"\x7e\x7e",
        b"\x7e\x01\x7e",
        b"\x01\x02\x03",
        bytes.fromhex("7E04807D5E287D5D4878D37E"),  # bad FCS
        bytes.fromhex("7E04807D7E"),  # dangling escape
    ],
)
def test_decode_frame_rejects_bad_frames(frame: bytes) -> None:
    with pytest.raises(FrameError):
        decode_frame(frame)


def test_decode_frame_rejects_unescaped_flag_inside() -> None:
    with pytest.raises(FrameError):
        decode_frame(b"\x7e\x01\x7e\x02\x7e\x7e")


def test_decoder_single_frame() -> None:
    decoder = FrameDecoder()
    assert decoder.feed(DOC_FRAME) == [DOC_INPUT]


def test_decoder_partial_chunks() -> None:
    decoder = FrameDecoder()
    assert decoder.feed(DOC_FRAME[:3]) == []
    assert decoder.feed(DOC_FRAME[3:9]) == []
    assert decoder.feed(DOC_FRAME[9:]) == [DOC_INPUT]


def test_decoder_ignores_zero_padding_and_garbage() -> None:
    decoder = FrameDecoder()
    chunk = DOC_FRAME + b"\x00" * (20 - len(DOC_FRAME))
    assert decoder.feed(b"\x55\xaa" + chunk) == [DOC_INPUT]
    # Padding carried into the next chunk before a new frame starts.
    assert decoder.feed(b"\x00\x00" + encode_frame(GET_SERIAL_PACKET)) == [
        GET_SERIAL_PACKET
    ]


def test_decoder_back_to_back_and_shared_flag() -> None:
    decoder = FrameDecoder()
    frames = DOC_FRAME + encode_frame(GET_SERIAL_PACKET)
    assert decoder.feed(frames) == [DOC_INPUT, GET_SERIAL_PACKET]
    # Shared closing/opening flag between two frames.
    shared = DOC_FRAME + encode_frame(GET_SERIAL_PACKET)[1:]
    assert decoder.feed(shared) == [DOC_INPUT, GET_SERIAL_PACKET]


def test_decoder_skips_empty_frames() -> None:
    decoder = FrameDecoder()
    assert decoder.feed(b"\x7e\x7e\x7e" + DOC_FRAME[1:]) == [DOC_INPUT]


def test_decoder_drops_corrupt_frame_and_continues() -> None:
    decoder = FrameDecoder()
    corrupt = bytearray(DOC_FRAME)
    corrupt[2] ^= 0xFF
    out = decoder.feed(bytes(corrupt) + encode_frame(GET_SERIAL_PACKET))
    assert out == [GET_SERIAL_PACKET]
    assert decoder.dropped_frames == 1


def test_decoder_reset() -> None:
    decoder = FrameDecoder()
    decoder.feed(DOC_FRAME[:5])
    decoder.reset()
    assert decoder.feed(DOC_FRAME) == [DOC_INPUT]


def test_payload_with_all_special_bytes_round_trips() -> None:
    payload = bytes(range(256))
    decoder = FrameDecoder()
    assert decoder.feed(encode_frame(payload)) == [payload]


def test_feed_ignores_fcs_only_padding_frame() -> None:
    """Two zero padding bytes after a frame must not surface as an empty payload."""
    frame = encode_frame(bytes([0x00, 0x00, 0x02, 0x00, 0x12, 0x00]))
    decoder = FrameDecoder()
    # 20-byte chunk: frame + zero padding, then a second frame starts.
    chunk = frame + b"\x00" * (20 - len(frame))
    payloads = decoder.feed(chunk + frame)
    assert payloads == [bytes([0x00, 0x00, 0x02, 0x00, 0x12, 0x00])] * 2
    assert decoder.dropped_frames == 0
    # The pathological case: exactly two zero bytes between flags.
    decoder = FrameDecoder()
    assert (
        decoder.feed(frame + b"\x00\x00" + frame)
        == [bytes([0x00, 0x00, 0x02, 0x00, 0x12, 0x00])] * 2
    )
