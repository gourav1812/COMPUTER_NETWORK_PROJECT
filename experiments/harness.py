"""Runs one in-process transfer: receiver thread + channel thread + sender. Used by tests and experiments."""
import os
import socket
import tempfile
import threading

from p3_rudp.channel import Channel, ChannelConfig
from p3_rudp.file_transfer import receive_file, send_file


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def run_transfer(data: bytes, protocol: str, window: int, cfg: ChannelConfig, rto=None, timeout=120):
    recv_port, chan_port = free_port(), free_port()
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, "src"), os.path.join(d, "dst")
        open(src, "wb").write(data)
        result, ready, stop = {}, threading.Event(), threading.Event()
        rt = threading.Thread(target=lambda: result.update(receive_file(recv_port, dst, protocol, window, ready)))
        rt.start()
        ready.wait(5)
        chan = Channel(("127.0.0.1", chan_port), ("127.0.0.1", recv_port), cfg)
        ct = threading.Thread(target=chan.run, args=(stop,), daemon=True)
        ct.start()
        try:
            stats = send_file(src, ("127.0.0.1", chan_port), protocol, window, rto)
            rt.join(timeout)
            if rt.is_alive():
                raise TimeoutError("receiver did not finish")
            ok = open(dst, "rb").read() == data
        finally:
            stop.set()
        return {**stats, **result, "identical": ok, **{f"ch_{k}": v for k, v in chan.counters.items()}}
