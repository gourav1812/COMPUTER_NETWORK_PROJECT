"""Correctness matrix: every protocol x impairment profile x several seeds must deliver identical bytes."""
import random

import pytest

from experiments.harness import run_transfer
from p3_rudp.channel import ChannelConfig
from p3_rudp.packet import MAX_PAYLOAD

PROFILES = {
    "clean": {},
    "loss10": {"loss": 0.1},
    "loss30": {"loss": 0.3},
    "corrupt20": {"corrupt": 0.2},
    "dup20": {"duplicate": 0.2},
    "reorder30": {"reorder": 0.3},
    "delay_jitter": {"delay_ms": 10, "jitter_ms": 5},
    "combined": {"loss": 0.1, "corrupt": 0.05, "duplicate": 0.1, "reorder": 0.2, "delay_ms": 5, "jitter_ms": 3},
}
SEEDS = range(3)


def rand_bytes(n, seed=0):
    return random.Random(seed).randbytes(n)


@pytest.mark.parametrize("protocol", ["sw", "gbn", "sr"])
@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("seed", SEEDS)
def test_matrix(protocol, profile, seed):
    r = run_transfer(rand_bytes(64 * 1024, seed), protocol, 8, ChannelConfig(seed=seed, **PROFILES[profile]))
    assert r["identical"] and r["sha256_ok"]


@pytest.mark.parametrize("protocol", ["sw", "gbn", "sr"])
@pytest.mark.parametrize("size", [0, 1, MAX_PAYLOAD, 3 * MAX_PAYLOAD, 3 * MAX_PAYLOAD + 1])
def test_edge_sizes(protocol, size):
    r = run_transfer(rand_bytes(size), protocol, 4, ChannelConfig(loss=0.2, seed=size))
    assert r["identical"]


def test_channel_is_deterministic():
    cfg = dict(loss=0.2, duplicate=0.1, reorder=0.1, seed=123)
    a = run_transfer(rand_bytes(32 * 1024), "sw", 1, ChannelConfig(**cfg))
    b = run_transfer(rand_bytes(32 * 1024), "sw", 1, ChannelConfig(**cfg))
    assert a["ch_dropped"] == b["ch_dropped"]
