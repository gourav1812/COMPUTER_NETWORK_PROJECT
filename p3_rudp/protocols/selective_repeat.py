"""SelectiveRepeat ARQ.  OWNER: Chirag  """
import socket
import time
from ..packet import ACK, DATA, FIN, FIN_ACK, CorruptPacket, Packet, decode, encode
from .base import BaseReceiver, BaseSender

class SelectiveRepeatSender(BaseSender):
    def send_chunks(self, chunks: list[bytes]) -> None:
        base = 0
        next_seq = 0
        n = len(chunks)
        window = self.window

        acked = set()
        deadlines = {}   # seq -> deadline timestamp
        send_times = {}  # seq -> first transmission time
        send_counts = {} # seq -> attempts count

        while base < n:
            now = time.monotonic()
            current_rto = self.rto.rto if self.rto else 1.0

            # 1. Send new packets that fit in the window
            while next_seq < base + window and next_seq < n:
                pkt = Packet(seq=next_seq, ack=0, ptype=DATA, payload=chunks[next_seq])
                self.sock.sendto(encode(pkt), self.peer)
                self.stats.packets_sent += 1
                deadlines[next_seq] = now + current_rto
                send_times[next_seq] = now
                send_counts[next_seq] = 1
                next_seq += 1

            # 2. Compute socket timeout from earliest pending deadline
            now = time.monotonic()
            if deadlines:
                earliest_deadline = min(deadlines.values())
                timeout = max(0.001, earliest_deadline - now)
            else:
                timeout = current_rto
            self.sock.settimeout(timeout)

            # 3. Wait for ACKs
            try:
                raw, _ = self.sock.recvfrom(4096)
                try:
                    pkt = decode(raw)
                    if pkt.ptype == ACK:
                        s = pkt.ack
                        if s not in acked and s < n:
                            acked.add(s)
                            self.stats.acks_received += 1
                            if s in deadlines:
                                del deadlines[s]
                            # Karn's rule: sample only if never retransmitted
                            if send_counts.get(s, 0) == 1 and self.rto and s in send_times:
                                rtt = time.monotonic() - send_times[s]
                                self.stats.rtt_samples.append(rtt)
                                self.rto.sample(rtt)
                            elif self.rto and hasattr(self.rto, "reset_backoff"):
                                self.rto.reset_backoff()
                            # Slide window base forward past consecutive acked packets
                            while base in acked:
                                base += 1
                except CorruptPacket:
                    self.stats.corrupt_dropped += 1
            except (socket.timeout, ConnectionResetError, OSError):
                pass

            # 4. Resend expired packets (only those with deadlines in the past)
            now = time.monotonic()
            expired = [seq for seq, dl in deadlines.items() if dl <= now]
            if expired:
                if self.rto:
                    self.rto.backoff()
                current_rto = self.rto.rto if self.rto else 1.0
                for seq in expired:
                    pkt = Packet(seq=seq, ack=0, ptype=DATA, payload=chunks[seq])
                    self.sock.sendto(encode(pkt), self.peer)
                    self.stats.packets_sent += 1
                    self.stats.retransmissions += 1
                    send_counts[seq] = send_counts.get(seq, 0) + 1
                    deadlines[seq] = now + current_rto

        # Teardown with FIN handshake
        fin_pkt = Packet(seq=n, ack=0, ptype=FIN)
        fin_raw = encode(fin_pkt)
        for _ in range(20):
            self.sock.sendto(fin_raw, self.peer)
            self.stats.packets_sent += 1
            self.sock.settimeout(0.5)
            try:
                resp_raw, _ = self.sock.recvfrom(4096)
                resp = decode(resp_raw)
                if resp.ptype == FIN_ACK:
                    break
            except (socket.timeout, CorruptPacket, ConnectionResetError, OSError):
                pass

class SelectiveRepeatReceiver(BaseReceiver):
    def receive_chunks(self):
        rcv_base = 0
        window = self.window
        buffer = {}  # seq -> payload
        chunks = []
        sender_addr = None

        while True:
            try:
                raw, addr = self.sock.recvfrom(4096)
            except (socket.timeout, ConnectionResetError, OSError):
                continue
            sender_addr = addr
            try:
                pkt = decode(raw)
            except CorruptPacket:
                self.stats.corrupt_dropped += 1
                continue

            if pkt.ptype == DATA:
                seq = pkt.seq
                # Packet within receiver window [rcv_base, rcv_base + window - 1]
                if rcv_base <= seq < rcv_base + window:
                    ack_pkt = Packet(seq=0, ack=seq, ptype=ACK)
                    self.sock.sendto(encode(ack_pkt), addr)
                    buffer[seq] = pkt.payload
                    # Slide window and deliver consecutive buffered in-order chunks
                    while rcv_base in buffer:
                        chunks.append(buffer.pop(rcv_base))
                        rcv_base += 1
                # Old packet [rcv_base - window, rcv_base - 1] whose ACK was lost
                elif (rcv_base - window) <= seq < rcv_base:
                    self.stats.duplicates_dropped += 1
                    ack_pkt = Packet(seq=0, ack=seq, ptype=ACK)
                    self.sock.sendto(encode(ack_pkt), addr)
                else:
                    self.stats.duplicates_dropped += 1
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
                        continue
                    except (ConnectionResetError, OSError):
                        continue
                break

        return chunks, sender_addr
