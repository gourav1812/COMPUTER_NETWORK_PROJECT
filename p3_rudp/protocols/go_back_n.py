"""Go-Back-N ARQ with cumulative acknowledgements and one base timer."""
import socket
import time

from .base import BaseReceiver, BaseSender
from ..packet import ACK, DATA, FIN, FIN_ACK, CorruptPacket, Packet, decode, encode


def _timeout(rto) -> float:
    return max(0.001, float(rto.rto if rto is not None else 1.0))


class GoBackNSender(BaseSender):
    def send_chunks(self, chunks: list[bytes]) -> None:
        if self.window < 1:
            raise ValueError("Go-Back-N window must be at least 1")

        base = 0
        next_seq = 0
        count = len(chunks)
        sent_at: dict[int, float] = {}
        transmissions: dict[int, int] = {}
        base_deadline = None

        while base < count:
            # Keep the pipe full while staying within the fixed send window.
            while next_seq < count and next_seq < base + self.window:
                raw = encode(Packet(seq=next_seq, ack=0, ptype=DATA, payload=chunks[next_seq]))
                now = time.monotonic()
                self.sock.sendto(raw, self.peer)
                self.stats.packets_sent += 1
                sent_at[next_seq] = now
                transmissions[next_seq] = 1
                if base == next_seq:
                    base_deadline = now + _timeout(self.rto)
                next_seq += 1

            if base_deadline is None:
                base_deadline = time.monotonic() + _timeout(self.rto)
            remaining = base_deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
            else:
                self.sock.settimeout(remaining)
                try:
                    response, _ = self.sock.recvfrom(4096)
                    timed_out = False
                except socket.timeout:
                    timed_out = True

            if not timed_out:
                try:
                    pkt = decode(response)
                except CorruptPacket:
                    self.stats.corrupt_dropped += 1
                    continue
                if pkt.ptype != ACK:
                    continue
                self.stats.acks_received += 1

                # ACK k confirms all packets through k. Ignore stale/future ACKs.
                if base <= pkt.ack < next_seq:
                    acknowledged_seq = pkt.ack
                    if transmissions.get(acknowledged_seq) == 1 and self.rto is not None:
                        sample = time.monotonic() - sent_at[acknowledged_seq]
                        self.stats.rtt_samples.append(sample)
                        self.rto.sample(sample)
                    base = acknowledged_seq + 1
                    if base < next_seq:
                        # Restart the single timer for the new oldest unACKed packet.
                        base_deadline = time.monotonic() + _timeout(self.rto)
                    else:
                        base_deadline = None
                continue

            # One timeout retransmits the entire outstanding window.
            if self.rto is not None:
                self.rto.backoff()
            now = time.monotonic()
            for seq in range(base, next_seq):
                raw = encode(Packet(seq=seq, ack=0, ptype=DATA, payload=chunks[seq]))
                self.sock.sendto(raw, self.peer)
                self.stats.packets_sent += 1
                self.stats.retransmissions += 1
                transmissions[seq] = transmissions.get(seq, 0) + 1
                sent_at[seq] = now
            base_deadline = now + _timeout(self.rto)

        # FIN is retransmitted until FIN_ACK arrives (or the bounded retry budget ends).
        fin_raw = encode(Packet(seq=count, ack=0, ptype=FIN))
        timeout = _timeout(self.rto)
        for attempt in range(8):
            self.sock.sendto(fin_raw, self.peer)
            self.stats.packets_sent += 1
            if attempt:
                self.stats.retransmissions += 1
            self.sock.settimeout(timeout)
            try:
                while True:
                    response, _ = self.sock.recvfrom(4096)
                    try:
                        pkt = decode(response)
                    except CorruptPacket:
                        self.stats.corrupt_dropped += 1
                        continue
                    if pkt.ptype == FIN_ACK and pkt.ack == count:
                        return
            except socket.timeout:
                if self.rto is not None:
                    self.rto.backoff()
                    timeout = _timeout(self.rto)


class GoBackNReceiver(BaseReceiver):
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
                    ack = Packet(seq=0, ack=expected - 1, ptype=ACK)
                    self.sock.sendto(encode(ack), addr)
                else:
                    self.stats.duplicates_dropped += 1
                    # No sentinel ACK is sent before the first in-order packet.
                    if expected:
                        ack = Packet(seq=0, ack=expected - 1, ptype=ACK)
                        self.sock.sendto(encode(ack), addr)
            elif pkt.ptype == FIN:
                fin_ack = encode(Packet(seq=0, ack=pkt.seq, ptype=FIN_ACK))
                self.sock.sendto(fin_ack, addr)
                # Keep the receiver alive briefly to answer retransmitted FINs.
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
