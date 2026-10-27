import pytest

from p3_rudp.packet import ACK, DATA, CorruptPacket, Packet, decode, encode


@pytest.mark.parametrize("payload", [b"", b"a", b"hello world", bytes(range(256)) * 4])
def test_roundtrip(payload):
    p = Packet(seq=42, ack=7, ptype=DATA, payload=payload)
    assert decode(encode(p)) == p


def test_ack_roundtrip():
    assert decode(encode(Packet(0, 99, ACK))) == Packet(0, 99, ACK)


@pytest.mark.parametrize("pos", [0, 5, 9, 12, 20, -1])
def test_single_bit_flip_detected(pos):
    raw = bytearray(encode(Packet(1, 2, DATA, b"payload-bytes-here")))
    raw[pos] ^= 0x01
    with pytest.raises(CorruptPacket):
        decode(bytes(raw))


def test_truncated_detected():
    raw = encode(Packet(1, 2, DATA, b"abcdef"))
    with pytest.raises(CorruptPacket):
        decode(raw[:-2])
