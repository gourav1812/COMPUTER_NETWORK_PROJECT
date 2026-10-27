import pytest

from p3_rudp.rto import AdaptiveRTO


def test_first_sample_initialises():
    r = AdaptiveRTO(initial=1.0, min_rto=0.0)
    r.sample(0.1)
    # RFC 6298: SRTT=R, RTTVAR=R/2, RTO=SRTT+4*RTTVAR = 0.3
    assert r.rto == pytest.approx(0.3)


def test_converges_to_stable_rtt():
    r = AdaptiveRTO(min_rto=0.0)
    for _ in range(200):
        r.sample(0.05)
    assert r.rto == pytest.approx(0.05, abs=1e-3)


def test_backoff_doubles_and_clamps():
    r = AdaptiveRTO(initial=1.0, max_rto=3.0)
    r.backoff()
    assert r.rto == pytest.approx(2.0)
    r.backoff()
    assert r.rto == pytest.approx(3.0)


def test_min_clamp():
    r = AdaptiveRTO(min_rto=0.2)
    for _ in range(50):
        r.sample(0.001)
    assert r.rto >= 0.2
