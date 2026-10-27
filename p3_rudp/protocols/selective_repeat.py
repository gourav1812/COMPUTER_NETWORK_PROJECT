"""SelectiveRepeat ARQ.  OWNER: Chirag  (core — implement yourselves, see PLAN.md)"""
from .base import BaseSender, BaseReceiver


class SelectiveRepeatSender(BaseSender):
    def send_chunks(self, chunks):
        # TODO(Chirag)
        raise NotImplementedError


class SelectiveRepeatReceiver(BaseReceiver):
    def receive_chunks(self):
        # TODO(Chirag)
        raise NotImplementedError
