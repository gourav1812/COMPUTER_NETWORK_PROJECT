"""Runs the four experiments from the brief and writes CSVs to results/.

  python -m experiments.run_experiments [loss|window|reorder|rto|all] --seeds 5 --size 262144
"""
import argparse
import csv
import os
import random

from experiments.harness import run_transfer
from p3_rudp.channel import ChannelConfig
from p3_rudp.rto import FixedRTO

OUT = os.path.join(os.path.dirname(__file__), "..", "results")


def sweep(name, points, seeds, size):
    rows = []
    for label, protocol, window, cfg_kw, rto in points:
        for seed in range(seeds):
            data = random.Random(seed).randbytes(size)
            r = run_transfer(data, protocol, window, ChannelConfig(seed=seed, **cfg_kw), rto)
            rows.append({"x": label, "protocol": protocol, "window": window, "seed": seed, **r})
            print(name, label, protocol, seed, f"{r['goodput_Bps'] / 1e3:.1f} kB/s", "retx", r["retransmissions"])
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, f"{name}.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)


BASE = {"delay_ms": 5, "jitter_ms": 1}


def exp_loss(seeds, size):
    pts = [(l, p, 1 if p == "sw" else 16, {**BASE, "loss": l}, None)
           for l in (0, 0.05, 0.1, 0.2, 0.3, 0.4) for p in ("sw", "gbn", "sr")]
    sweep("goodput_vs_loss", pts, seeds, size)


def exp_window(seeds, size):
    pts = [(w, p, w, {**BASE, "loss": 0.05}, None) for w in (1, 2, 4, 8, 16, 32, 64) for p in ("gbn", "sr")]
    sweep("goodput_vs_window", pts, seeds, size)


def exp_reorder(seeds, size):
    pts = [(r, p, 1 if p == "sw" else 16, {**BASE, "reorder": r}, None)
           for r in (0, 0.1, 0.2, 0.3, 0.5) for p in ("sw", "gbn", "sr")]
    sweep("retx_vs_reorder", pts, seeds, size)


def exp_rto(seeds, size):
    cfg = {"delay_ms": 20, "jitter_ms": 10, "loss": 0.05}
    pts = [(str(v), p, 16, cfg, FixedRTO(v)) for v in (0.02, 0.05, 0.1, 0.2, 0.5) for p in ("gbn", "sr")]
    pts += [("adaptive", p, 16, cfg, None) for p in ("gbn", "sr")]
    sweep("rto_sensitivity", pts, seeds, size)


EXPS = {"loss": exp_loss, "window": exp_window, "reorder": exp_reorder, "rto": exp_rto}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("which", nargs="?", default="all", choices=[*EXPS, "all"])
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--size", type=int, default=256 * 1024)
    a = ap.parse_args()
    for k, fn in EXPS.items():
        if a.which in (k, "all"):
            fn(a.seeds, a.size)
