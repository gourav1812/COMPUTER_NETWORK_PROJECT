"""Stop-and-Wait ARQ: one data packet may be outstanding at a time."""
import socket
import time

from .base import BaseReceiver, BaseSender
from ..packet import ACK, DATA, FIN, FIN_ACK, CorruptPacket, Packet, decode, encode


def _timeout(rto) -> float:
    return max(0.001, float(rto.rto if rto is not None else 1.0))


def _send_fin(sock, peer, seq: int, stats, rto) -> None:
    """Complete transfer teardown, tolerating a lost FIN or FIN_ACK."""
    raw = encode(Packet(seq=seq, ack=0, ptype=FIN))
    timeout = _timeout(rto)
    for attempt in range(8):
        sock.sendto(raw, peer)
        stats.packets_sent += 1
        if attempt:
            stats.retransmissions += 1
        sock.settimeout(timeout)
        try:
            while True:
                response, _ = sock.recvfrom(4096)
                try:
                    pkt = decode(response)
                except CorruptPacket:
                    stats.corrupt_dropped += 1
                    continue
                if pkt.ptype == FIN_ACK and pkt.ack == seq:
                    return
        except socket.timeout:
            if rto is not None:
                rto.backoff()
                timeout = _timeout(rto)


class StopAndWaitSender(BaseSender):
    def send_chunks(self, chunks: list[bytes]) -> None:
        for seq, payload in enumerate(chunks):
            raw = encode(Packet(seq=seq, ack=0, ptype=DATA, payload=payload))
            retransmitted = False
            while True:
                self.sock.sendto(raw, self.peer)
                self.stats.packets_sent += 1
                sent_at = time.monotonic()
                if retransmitted:
                    self.stats.retransmissions += 1
                deadline = sent_at + _timeout(self.rto)
                acknowledged = False

                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self.sock.settimeout(remaining)
                    try:
                        response, _ = self.sock.recvfrom(4096)
                    except socket.timeout:
                        break
                    try:
                        pkt = decode(response)
                    except CorruptPacket:
                        self.stats.corrupt_dropped += 1
                        continue
                    if pkt.ptype != ACK or pkt.ack != seq:
                        continue

                    self.stats.acks_received += 1
                    acknowledged = True
                    if not retransmitted and self.rto is not None:
                        sample = time.monotonic() - sent_at
                        self.stats.rtt_samples.append(sample)
                        self.rto.sample(sample)
                    break
                if acknowledged:
                    break
                retransmitted = True
                if self.rto is not None:
                    self.rto.backoff()

        _send_fin(self.sock, self.peer, len(chunks), self.stats, self.rto)


class StopAndWaitReceiver(BaseReceiver):
    def receive_chunks(self):
        chunks: list[bytes] = []
        expected = 0
        sender_addr = None

        while True:
            raw, addr = self.sock.recvfrom(4096)
            sender_addr = addr
            try:
                pkt = decode(raw)
            except CorruptPacket:
                self.stats.corrupt_dropped += 1
                continue

            if pkt.ptype == DATA:
                if pkt.seq == expected:
                    chunks.append(pkt.payload)
                    expected += 1
                elif pkt.seq < expected:
                    self.stats.duplicates_dropped += 1
                else:
                    continue

                # Re-ACK duplicates so a lost ACK does not stall the sender.
                self.sock.sendto(encode(Packet(seq=0, ack=pkt.seq, ptype=ACK)), addr)
            elif pkt.ptype == FIN:
                fin_ack = encode(Packet(seq=0, ack=pkt.seq, ptype=FIN_ACK))
                self.sock.sendto(fin_ack, addr)
                # Linger so the sender can recover if the first FIN_ACK is lost.
                self.sock.settimeout(0.05)
                linger_until = time.monotonic() + 1.0
                while time.monotonic() < linger_until:
                    try:
                        extra, extra_addr = self.sock.recvfrom(4096)
                    except socket.timeout:
                        continue
                    try:
                        extra_pkt = decode(extra)
                    except CorruptPacket:
                        self.stats.corrupt_dropped += 1
                        continue
                    if extra_pkt.ptype == FIN:
                        self.sock.sendto(fin_ack, extra_addr)
                return chunks, sender_addr
