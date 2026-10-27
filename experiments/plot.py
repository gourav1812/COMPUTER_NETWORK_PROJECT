"""Plots results/*.csv -> results/*.png (mean ± std over seeds)."""
import os

import matplotlib.pyplot as plt
import pandas as pd

R = os.path.join(os.path.dirname(__file__), "..", "results")
COLORS = {"sw": "#4C72B0", "gbn": "#DD8452", "sr": "#55A868"}
PLOTS = [
    ("goodput_vs_loss", "goodput_Bps", "Loss probability", "Goodput (kB/s)", 1e-3, False),
    ("goodput_vs_window", "goodput_Bps", "Window size", "Goodput (kB/s)", 1e-3, True),
    ("retx_vs_reorder", "retransmissions", "Reordering probability", "Retransmissions", 1, False),
    ("rto_sensitivity", "goodput_Bps", "RTO (s)", "Goodput (kB/s)", 1e-3, False),
]

for name, col, xl, yl, scale, logx in PLOTS:
    path = os.path.join(R, f"{name}.csv")
    if not os.path.exists(path):
        continue
    df = pd.read_csv(path)
    fig, ax = plt.subplots(figsize=(6, 4))
    for proto, g in df.groupby("protocol"):
        agg = g.groupby("x", sort=False)[col].agg(["mean", "std"])
        ax.errorbar(agg.index.astype(str) if name == "rto_sensitivity" else agg.index,
                    agg["mean"] * scale, yerr=agg["std"] * scale, marker="o", capsize=3,
                    label=proto.upper(), color=COLORS[proto])
    if logx:
        ax.set_xscale("log", base=2)
    ax.set(xlabel=xl, ylabel=yl, title=name.replace("_", " "))
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(R, f"{name}.png"), dpi=150)
    print("wrote", name)
