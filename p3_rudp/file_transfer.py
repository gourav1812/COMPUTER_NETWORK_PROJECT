"""Application layer + CLI. Protocol-agnostic: picks a transport from PROTOCOLS.

The first chunk sent is the SHA-256 digest of the file, so the receiver can verify integrity
without any protocol-specific metadata.

  python -m p3_rudp.file_transfer recv --port 9000 --out received.bin --protocol sr --window 8
  python -m p3_rudp.file_transfer send --host 127.0.0.1 --port 9000 --file big.bin --protocol sr --window 8
  python -m p3_rudp.file_transfer channel --listen 8999 --to 9000 --loss 0.1 --seed 1
"""
import argparse
import hashlib
import json
import socket
import threading
import time

from .channel import Channel, ChannelConfig
from .packet import MAX_PAYLOAD
from .protocols import PROTOCOLS
from .rto import AdaptiveRTO, FixedRTO


def split(data: bytes, size: int = MAX_PAYLOAD) -> list[bytes]:
    return [data[i:i + size] for i in range(0, len(data), size)]


def send_file(path, peer, protocol, window, rto=None):
    data = open(path, "rb").read()
    digest = hashlib.sha256(data).digest()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sender = PROTOCOLS[protocol][0](sock, peer, window=window, rto=rto or AdaptiveRTO())
    start = time.perf_counter()
    sender.send_chunks([digest] + split(data))
    elapsed = time.perf_counter() - start
    sock.close()
    s = sender.stats
    return {
        "protocol": protocol, "window": window, "bytes": len(data), "time_s": elapsed,
        "goodput_Bps": len(data) / elapsed if elapsed else 0.0,
        "packets_sent": s.packets_sent, "retransmissions": s.retransmissions,
    }


def receive_file(port, out_path, protocol, window, ready: threading.Event | None = None):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", port))
    if ready:
        ready.set()
    receiver = PROTOCOLS[protocol][1](sock, window=window)
    chunks, _ = receiver.receive_chunks()
    sock.close()
    expected, data = chunks[0], b"".join(chunks[1:])
    with open(out_path, "wb") as f:
        f.write(data)
    return {"bytes": len(data), "sha256_ok": hashlib.sha256(data).digest() == expected}


def main():
    p = argparse.ArgumentParser(description="Reliable file transfer over UDP")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("send", "recv"):
        sp = sub.add_parser(name)
        sp.add_argument("--port", type=int, required=True)
        sp.add_argument("--protocol", choices=PROTOCOLS, default="sr")
        sp.add_argument("--window", type=int, default=8)
    sub.choices["send"].add_argument("--host", default="127.0.0.1")
    sub.choices["send"].add_argument("--file", required=True)
    sub.choices["send"].add_argument("--fixed-rto", type=float, help="seconds; default adaptive")
    sub.choices["recv"].add_argument("--out", required=True)
    ch = sub.add_parser("channel")
    ch.add_argument("--listen", type=int, required=True)
    ch.add_argument("--to", type=int, required=True)
    for k in ("loss", "corrupt", "duplicate", "reorder", "delay-ms", "jitter-ms"):
        ch.add_argument(f"--{k}", type=float, default=0.0)
    ch.add_argument("--seed", type=int, default=0)
    a = p.parse_args()

    if a.cmd == "send":
        rto = FixedRTO(a.fixed_rto) if a.fixed_rto else None
        print(json.dumps(send_file(a.file, (a.host, a.port), a.protocol, a.window, rto), indent=2))
    elif a.cmd == "recv":
        print(json.dumps(receive_file(a.port, a.out, a.protocol, a.window), indent=2))
    else:
        cfg = ChannelConfig(a.loss, a.corrupt, a.duplicate, a.reorder, a.delay_ms, a.jitter_ms, a.seed)
        Channel(("127.0.0.1", a.listen), ("127.0.0.1", a.to), cfg).run(threading.Event())


if __name__ == "__main__":
    main()
