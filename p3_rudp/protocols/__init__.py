from .stop_and_wait import StopAndWaitSender, StopAndWaitReceiver
from .go_back_n import GoBackNSender, GoBackNReceiver
from .selective_repeat import SelectiveRepeatSender, SelectiveRepeatReceiver

PROTOCOLS = {
    "sw": (StopAndWaitSender, StopAndWaitReceiver),
    "gbn": (GoBackNSender, GoBackNReceiver),
    "sr": (SelectiveRepeatSender, SelectiveRepeatReceiver),
}
