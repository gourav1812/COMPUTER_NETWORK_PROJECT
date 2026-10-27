"""GoBackN ARQ.  OWNER: Amit  (core — implement yourselves, see PLAN.md)"""
from .base import BaseSender, BaseReceiver


class GoBackNSender(BaseSender):
    def send_chunks(self, chunks):
        # TODO(Amit)
        raise NotImplementedError


class GoBackNReceiver(BaseReceiver):
    def receive_chunks(self):
        # TODO(Amit)
        raise NotImplementedError
