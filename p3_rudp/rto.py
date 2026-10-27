"""Adaptive retransmission timeout.  OWNER: Chirag  (core — implement yourselves)

Jacobson/Karels: SRTT, RTTVAR, RTO = SRTT + 4*RTTVAR, clamped; exponential backoff on timeout.
Karn: callers must NOT call sample() for packets that were retransmitted.
"""


class AdaptiveRTO:
    def __init__(self, initial=1.0, min_rto=0.05, max_rto=10.0):
        self.rto = initial
        self.min_rto, self.max_rto = min_rto, max_rto

    def sample(self, rtt: float) -> None:
        raise NotImplementedError  # TODO(Chirag)

    def backoff(self) -> None:
        raise NotImplementedError  # TODO(Chirag)


class FixedRTO:
    """Baseline for the RTO-sensitivity experiment."""

    def __init__(self, value):
        self.rto = value

    def sample(self, rtt):
        pass

    def backoff(self):
        pass
