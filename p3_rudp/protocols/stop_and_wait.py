import socket
import time

from ..packet import ACK, DATA, FIN, FIN_ACK, CorruptPacket, Packet, decode, encode
from .base import BaseReceiver, BaseSender


class StopAndWaitSender(BaseSender):
    def send_chunks(self, chunks: list[bytes]) -> None:
        i = 0
        n = len(chunks)
        while i < n:
            pkt = Packet(seq=i, ack=0, ptype=DATA, payload=chunks[i])
            raw = encode(pkt)
            send_count = 0
            start_time = None

            while True:
                # Transmit
                self.sock.sendto(raw, self.peer)
                self.stats.packets_sent += 1
                send_count += 1
                if send_count == 1:
                    start_time = time.monotonic()
                else:
                    self.stats.retransmissions += 1

                # Set timeout from RTO
                timeout = self.rto.rto if self.rto else 1.0
                self.sock.settimeout(timeout)
                try:
                    resp_raw, _ = self.sock.recvfrom(4096)
                    try:
                        resp = decode(resp_raw)
                        if resp.ptype == ACK and resp.ack == i:
                            self.stats.acks_received += 1
                            # Karn's algorithm: only sample RTT if never retransmitted
                            if send_count == 1 and self.rto and start_time:
                                rtt = time.monotonic() - start_time
                                self.stats.rtt_samples.append(rtt)
                                self.rto.sample(rtt)
                            elif self.rto and hasattr(self.rto, "reset_backoff"):
                                self.rto.reset_backoff()
                            i += 1
                            break
                    except CorruptPacket:
                        self.stats.corrupt_dropped += 1
                except (socket.timeout, ConnectionResetError, OSError):
                    if self.rto:
                        self.rto.backoff()

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
            except (socket.timeout, CorruptPacket, ConnectionResetError, OSError):
                pass


class StopAndWaitReceiver(BaseReceiver):
    def receive_chunks(self):
        chunks = []
        expected = 0
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
                if pkt.seq == expected:
                    chunks.append(pkt.payload)
                    expected += 1
                    ack_pkt = Packet(seq=0, ack=pkt.seq, ptype=ACK)
                    self.sock.sendto(encode(ack_pkt), addr)
                elif pkt.seq < expected:
                    self.stats.duplicates_dropped += 1
                    # Re-send ACK for duplicate so sender can proceed
                    ack_pkt = Packet(seq=0, ack=pkt.seq, ptype=ACK)
                    self.sock.sendto(encode(ack_pkt), addr)
            elif pkt.ptype == FIN:
                # Reply FIN_ACK and linger briefly to handle lost FIN_ACK
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
                    except (socket.timeout, ConnectionResetError, OSError):
                        break
                break

        return chunks, sender_addr
