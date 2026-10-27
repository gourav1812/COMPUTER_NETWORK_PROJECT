"""Common interface every ARQ protocol implements, so the application can swap transports."""
import socket
from dataclasses import dataclass, field


@dataclass
class Stats:
    packets_sent: int = 0
    retransmissions: int = 0
    acks_received: int = 0
    corrupt_dropped: int = 0
    duplicates_dropped: int = 0
    rtt_samples: list = field(default_factory=list)


class BaseSender:
    def __init__(self, sock: socket.socket, peer, window: int = 1, rto=None):
        self.sock, self.peer, self.window, self.rto = sock, peer, window, rto
        self.stats = Stats()

    def send_chunks(self, chunks: list[bytes]) -> None:
        """Reliably deliver chunks[0..n-1] in order. Returns once all are ACKed."""
        raise NotImplementedError


class BaseReceiver:
    def __init__(self, sock: socket.socket, window: int = 1):
        self.sock, self.window = sock, window
        self.stats = Stats()

    def receive_chunks(self):
        """Yield payloads in order until FIN. Returns (list_of_chunks, sender_addr)."""
        raise NotImplementedError
