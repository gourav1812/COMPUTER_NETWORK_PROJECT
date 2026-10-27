"""StopAndWait ARQ.  OWNER: Amit  (core — implement yourselves, see PLAN.md)"""
from .base import BaseSender, BaseReceiver


class StopAndWaitSender(BaseSender):
    def send_chunks(self, chunks):
        # TODO(Amit)
        raise NotImplementedError


class StopAndWaitReceiver(BaseReceiver):
    def receive_chunks(self):
        # TODO(Amit)
        raise NotImplementedError
