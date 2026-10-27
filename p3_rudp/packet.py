"""Packet format and checksum.  OWNER: Gourav  (core — implement yourselves)

Header layout (network byte order): seq (u32), ack (u32), type (u8), length (u16), checksum (u32)
followed by `length` bytes of payload. Checksum is computed over the header (with checksum=0)
plus the payload.
"""
import struct
from dataclasses import dataclass

HEADER_FMT = "!IIBHI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
MAX_PAYLOAD = 1024

DATA, ACK, FIN, FIN_ACK = 0, 1, 2, 3


class CorruptPacket(Exception):
    """Raised by decode() when the checksum does not match or the packet is malformed."""


@dataclass
class Packet:
    seq: int
    ack: int
    ptype: int
    payload: bytes = b""


def checksum(data: bytes) -> int:
    """16-bit Internet checksum (RFC 1071)."""
    if len(data) % 2 == 1:
        data = data + b"\x00"
    s = sum(struct.unpack(f"!{len(data)//2}H", data))
    while s > 0xFFFF:
        s = (s & 0xFFFF) + (s >> 16)
    return (~s) & 0xFFFF



def encode(pkt: Packet) -> bytes:
    """Pack header with checksum=0, compute checksum over header+payload, repack."""
    payload = pkt.payload if pkt.payload is not None else b""
    # Header format: seq (4B), ack (4B), type (1B), length (2B), checksum (4B)
    header_zero_cksum = struct.pack(HEADER_FMT, pkt.seq, pkt.ack, pkt.ptype, len(payload), 0)
    c = checksum(header_zero_cksum + payload)
    return struct.pack(HEADER_FMT, pkt.seq, pkt.ack, pkt.ptype, len(payload), c) + payload



def decode(raw: bytes) -> Packet:
    """Unpack header, verify length and checksum, raise CorruptPacket on mismatch."""
    if len(raw) < HEADER_SIZE:
        raise CorruptPacket(f"Packet too short: {len(raw)} < {HEADER_SIZE}")
    seq, ack, ptype, length, cksum = struct.unpack(HEADER_FMT, raw[:HEADER_SIZE])
    payload = raw[HEADER_SIZE:]
    if len(payload) != length:
        raise CorruptPacket(f"Payload length mismatch: expected {length}, got {len(payload)}")
    header_zero_cksum = struct.pack(HEADER_FMT, seq, ack, ptype, length, 0)
    calculated_cksum = checksum(header_zero_cksum + payload)
    if calculated_cksum != cksum:
        raise CorruptPacket(f"Checksum mismatch: received {cksum}, calculated {calculated_cksum}")
    return Packet(seq=seq, ack=ack, ptype=ptype, payload=payload)

