"""Channel emulator: a UDP proxy between sender and receiver.  OWNER: Vedang  (core)

Listens on `listen_addr`. Packets from the sender are forwarded to `receiver_addr`; packets from
the receiver go back to the last seen sender address. Every forwarded datagram passes through
impair(), which may drop, corrupt, duplicate, hold back (reorder) or delay it.
All randomness MUST come from self.rng so runs are reproducible from the seed.
"""
import random
from dataclasses import dataclass


@dataclass
class ChannelConfig:
    loss: float = 0.0
    corrupt: float = 0.0
    duplicate: float = 0.0
    reorder: float = 0.0
    delay_ms: float = 0.0
    jitter_ms: float = 0.0
    seed: int = 0


class Channel:
    def __init__(self, listen_addr, receiver_addr, cfg: ChannelConfig):
        self.listen_addr, self.receiver_addr, self.cfg = listen_addr, receiver_addr, cfg
        self.rng = random.Random(cfg.seed)
        self.counters = {"forwarded": 0, "dropped": 0, "corrupted": 0, "duplicated": 0, "reordered": 0}

    def run(self, stop_event) -> None:
        """Proxy loop; return when stop_event is set."""
        raise NotImplementedError  # TODO(Vedang)
