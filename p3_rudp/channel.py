"""Seeded UDP proxy for simulating network loss, corruption and delay."""
import heapq
import random
import socket
import time
from dataclasses import dataclass

from .packet import HEADER_SIZE


@dataclass
class ChannelConfig:
    loss: float = 0.0
    corrupt: float = 0.0
    duplicate: float = 0.0
    reorder: float = 0.0
    delay_ms: float = 0.0
    jitter_ms: float = 0.0
    seed: int = 0

    def __post_init__(self):
        for name in ("loss", "corrupt", "duplicate", "reorder"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} probability must be between 0 and 1")
        if self.delay_ms < 0 or self.jitter_ms < 0:
            raise ValueError("delay_ms and jitter_ms must be non-negative")


class Channel:
    def __init__(self, listen_addr, receiver_addr, cfg: ChannelConfig):
        self.listen_addr, self.receiver_addr, self.cfg = listen_addr, receiver_addr, cfg
        self.rng = random.Random(cfg.seed)
        self.counters = {
            "forwarded": 0,
            "dropped": 0,
            "corrupted": 0,
            "duplicated": 0,
            "reordered": 0,
        }

    def _corrupt(self, data: bytes) -> bytes:
        """Flip one bit in a copy, preferring payload bytes so checksums catch it."""
        if not data:
            return data
        corrupted = bytearray(data)
        if len(corrupted) > HEADER_SIZE:
            index = self.rng.randrange(HEADER_SIZE, len(corrupted))
        else:
            index = self.rng.randrange(len(corrupted))
        corrupted[index] ^= 1 << self.rng.randrange(8)
        return bytes(corrupted)

    def run(self, stop_event) -> None:
        """Forward datagrams until stopped, applying configured impairments."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(self.listen_addr)
        # A short timeout lets the loop notice stop_event and drain the send heap.
        sock.settimeout(0.02)

        last_sender_addr = None
        # (send_time, insertion_order, destination, bytes)
        pending = []
        # (held_at, destination, bytes, configured_delay_seconds)
        held = []
        insertion_order = 0

        def schedule(send_at, destination, datagram):
            nonlocal insertion_order
            insertion_order += 1
            heapq.heappush(pending, (send_at, insertion_order, destination, datagram))

        try:
            while not stop_event.is_set():
                now = time.monotonic()
                try:
                    data, source = sock.recvfrom(65535)
                except socket.timeout:
                    data = source = None

                if data is not None:
                    if source == self.receiver_addr:
                        destination = last_sender_addr
                    else:
                        last_sender_addr = source
                        destination = self.receiver_addr

                    if destination is not None:
                        # Apply impairment decisions in a fixed order. All random
                        # draws use the seeded instance so runs are reproducible.
                        if self.rng.random() < self.cfg.loss:
                            self.counters["dropped"] += 1
                        else:
                            if self.rng.random() < self.cfg.corrupt:
                                data = self._corrupt(data)
                                self.counters["corrupted"] += 1

                            copies = [data]
                            if self.rng.random() < self.cfg.duplicate:
                                copies.append(data)
                                self.counters["duplicated"] += 1

                            reorder_packet = self.rng.random() < self.cfg.reorder
                            if reorder_packet:
                                self.counters["reordered"] += 1

                            for datagram in copies:
                                jitter_ms = (
                                    self.rng.uniform(-self.cfg.jitter_ms, self.cfg.jitter_ms)
                                    if self.cfg.jitter_ms
                                    else 0.0
                                )
                                delay = max(0.0, (self.cfg.delay_ms + jitter_ms) / 1000.0)
                                if reorder_packet:
                                    held.append((now, destination, datagram, delay))
                                else:
                                    send_at = now + delay
                                    schedule(send_at, destination, datagram)
                                    # Put earlier held datagrams just after this one.
                                    while held:
                                        _, held_dest, held_data, held_delay = held.pop(0)
                                        schedule(send_at + 0.005 + held_delay, held_dest, held_data)

                # A lost or reordered successor may never arrive. Release held
                # datagrams after a brief timeout so the proxy cannot strand them.
                now = time.monotonic()
                while held and now - held[0][0] >= 0.02:
                    _, held_dest, held_data, held_delay = held.pop(0)
                    schedule(now + 0.005 + held_delay, held_dest, held_data)

                # Send every datagram whose delay/reordering deadline has passed.
                now = time.monotonic()
                while pending and pending[0][0] <= now:
                    _, _, destination, datagram = heapq.heappop(pending)
                    try:
                        sock.sendto(datagram, destination)
                    except OSError:
                        continue
                    self.counters["forwarded"] += 1
        finally:
            sock.close()
