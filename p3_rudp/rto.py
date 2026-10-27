"""Adaptive retransmission timeout.  OWNER: Chirag  

Jacobson/Karels: SRTT, RTTVAR, RTO = SRTT + 4*RTTVAR, clamped; exponential backoff on timeout.
Karn: callers must NOT call sample() for packets that were retransmitted.
"""


class AdaptiveRTO:
    def __init__(self, initial=1.0, min_rto=0.05, max_rto=10.0):
        """Initialize RTO parameters and estimators."""
        self.rto = initial
        self.min_rto = min_rto
        self.max_rto = max_rto
        self.srtt = None      # Smoothed Round Trip Time
        self.rttvar = None    # Round Trip Time Variation

    def sample(self, rtt: float) -> None:
     """Jacobson/Karels algorithm (RFC 6298): alpha = 1/8, beta = 1/4."""
     if self.srtt is None:
        # First RTT measurement baseline
        self.srtt = rtt
        self.rttvar = rtt / 2.0    
     else:
        alpha = 0.125
        beta = 0.25
        self.rttvar = (1 - beta) * self.rttvar + beta * abs(self.srtt - rtt)
        self.srtt = (1 - alpha) * self.srtt + alpha * rtt

     # RTO = SRTT + 4 * RTTVAR, clamped within min and max
     self.rto = max(self.min_rto, min(self.srtt + 4.0 * self.rttvar, self.max_rto))     

    def backoff(self) -> None:
     """Exponential backoff on timeout, clamped to max_rto."""
     self.rto = min(self.rto * 2.0, self.max_rto)
