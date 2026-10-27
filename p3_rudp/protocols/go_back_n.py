import socket
import time

from ..packet import ACK, DATA, FIN, FIN_ACK, CorruptPacket, Packet, decode, encode
from .base import BaseReceiver, BaseSender


class GoBackNSender(BaseSender):
    def send_chunks(self, chunks: list[bytes]) -> None:
        base = 0
        next_seq = 0
        n = len(chunks)
        window = self.window

        timers = {}       # seq -> send_time
        send_counts = {}  # seq -> transmission count
        base_timer = None

        while base < n:
            # 1. Send all packets allowed within window
            while next_seq < base + window and next_seq < n:
                pkt = Packet(seq=next_seq, ack=0, ptype=DATA, payload=chunks[next_seq])
                self.sock.sendto(encode(pkt), self.peer)
                self.stats.packets_sent += 1
                timers[next_seq] = time.monotonic()
                send_counts[next_seq] = send_counts.get(next_seq, 0) + 1
                if base == next_seq:
                    base_timer = timers[next_seq]
                next_seq += 1

            # 2. Wait for ACK with remaining time on base timer
            current_rto = self.rto.rto if self.rto else 1.0
            time_left = max(0.001, (base_timer + current_rto) - time.monotonic()) if base_timer else current_rto
            self.sock.settimeout(time_left)

            try:
                raw, _ = self.sock.recvfrom(4096)
                try:
                    pkt = decode(raw)
                    if pkt.ptype == ACK and pkt.ack >= base:
                        self.stats.acks_received += 1
                        # Cumulative ACK: advances base
                        old_base = base
                        base = pkt.ack + 1

                        # Karn's rule on acked packet
                        if pkt.ack in send_counts and send_counts[pkt.ack] == 1 and self.rto and pkt.ack in timers:
                            rtt = time.monotonic() - timers[pkt.ack]
                            self.stats.rtt_samples.append(rtt)
                            self.rto.sample(rtt)

                        if base == next_seq:
                            base_timer = None
                        else:
                            base_timer = time.monotonic()
                except CorruptPacket:
                    self.stats.corrupt_dropped += 1
            except socket.timeout:
                # Timeout on base: resend everything from base to next_seq - 1
                if self.rto:
                    self.rto.backoff()
                base_timer = time.monotonic()
                for seq in range(base, next_seq):
                    pkt = Packet(seq=seq, ack=0, ptype=DATA, payload=chunks[seq])
                    self.sock.sendto(encode(pkt), self.peer)
                    self.stats.packets_sent += 1
                    self.stats.retransmissions += 1
                    send_counts[seq] = send_counts.get(seq, 0) + 1

        # Teardown with FIN handshake
        fin_pkt = Packet(seq=n, ack=0, ptype=FIN)
        fin_raw = encode(fin_pkt)
        for _ in range(5):
            self.sock.sendto(fin_raw, self.peer)
            self.stats.packets_sent += 1
            self.sock.settimeout(0.5)
            try:
                resp_raw, _ = self.sock.recvfrom(4096)
                resp = decode(resp_raw)
                if resp.ptype == FIN_ACK:
                    break
            except (socket.timeout, CorruptPacket):
                pass


class GoBackNReceiver(BaseReceiver):
    def receive_chunks(self):
        chunks = []
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
                    ack_pkt = Packet(seq=0, ack=expected - 1, ptype=ACK)
                    self.sock.sendto(encode(ack_pkt), addr)
                else:
                    self.stats.duplicates_dropped += 1
                    # Resend cumulative ACK for the last in-order received chunk
                    if expected > 0:
                        ack_pkt = Packet(seq=0, ack=expected - 1, ptype=ACK)
                        self.sock.sendto(encode(ack_pkt), addr)
            elif pkt.ptype == FIN:
                fin_ack = Packet(seq=0, ack=pkt.seq, ptype=FIN_ACK)
                self.sock.sendto(encode(fin_ack), addr)
                self.sock.settimeout(0.4)
                linger_until = time.monotonic() + 1.0
                while time.monotonic() < linger_until:
                    try:
                        extra_raw, extra_addr = self.sock.recvfrom(4096)
                        try:
                            extra_pkt = decode(extra_raw)
                            if extra_pkt.ptype == FIN:
                                self.sock.sendto(encode(fin_ack), extra_addr)
                        except CorruptPacket:
                            pass
                    except socket.timeout:
                        break
                break

        return chunks, sender_addr
