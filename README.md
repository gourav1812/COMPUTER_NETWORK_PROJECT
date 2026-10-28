# P3 — Reliable Data Transfer over UDP

A complete, high-performance reliable file transfer system implemented over UDP in Python. Features pluggable ARQ transports (**Stop-and-Wait**, **Go-Back-N**, and **Selective Repeat**), adaptive retransmission timeout estimation (**Jacobson/Karels** with **Karn's algorithm**), a seeded network impairment emulator, and **SHA-256** cryptographic integrity checks.

---

## Key Documentation
- **[PLAN.md](PLAN.md)**: Original design specifications, module breakdown, and timeline.
- **[REPORT.md](REPORT.md)**: Comprehensive experimental report analyzing goodput, window size scaling, packet reordering, and RTO sensitivity with empirical data.
- **[VIVA_PREP.md](VIVA_PREP.md)**: Viva / oral exam preparation guide containing technical questions and detailed answers for each team member.
- **[AI-USE.md](AI-USE.md)**: AI use disclosure and activity log.

---

## Project Structure
```
COMPUTER_NETWORK_PROJECT/
├── p3_rudp/
│   ├── packet.py               # RFC 1071 Checksum & packet format (!IIBHI)
│   ├── rto.py                  # Jacobson/Karels Adaptive RTO + Fixed RTO
│   ├── channel.py              # Seeded network emulator (loss, corrupt, dup, reorder, jitter)
│   ├── file_transfer.py        # CLI application & SHA-256 chunking
│   └── protocols/
│       ├── base.py             # Abstract BaseSender & BaseReceiver
│       ├── stop_and_wait.py    # Stop-and-Wait ARQ
│       ├── go_back_n.py        # Go-Back-N ARQ (cumulative ACKs)
│       └── selective_repeat.py # Selective Repeat ARQ (per-packet timers, buffering)
├── experiments/
│   ├── harness.py              # In-process concurrent transfer harness
│   ├── run_experiments.py      # Benchmark runner across network sweeps
│   └── plot.py                 # Matplotlib visualization generator
├── results/                    # Generated CSV data and PNG charts
│   ├── goodput_vs_loss.png
│   ├── goodput_vs_window.png
│   ├── retx_vs_reorder.png
│   └── rto_sensitivity.png
└── tests/
    ├── test_packet.py          # Packet encoding, decoding, bit corruption tests
    ├── test_rto.py             # Jacobson/Karels convergence and backoff tests
    └── test_transfer.py        # Full correctness matrix (protocols x profiles x seeds)
```

---

## Quickstart

### 1. Installation
```bash
pip install pytest matplotlib pandas
```

### 2. Manual CLI File Transfer
```bash
# Terminal 1: Start Receiver
python -m p3_rudp.file_transfer recv --port 9000 --out received.bin --protocol sr --window 8

# Terminal 2: Start Channel Emulator (Proxy on port 8999 -> forwarding to 9000)
python -m p3_rudp.file_transfer channel --listen 8999 --to 9000 --loss 0.1 --reorder 0.1 --seed 1

# Terminal 3: Send File
python -m p3_rudp.file_transfer send --port 8999 --file sample.bin --protocol sr --window 8
```

---

## Tests & Experiments

### Run Unit & Integration Tests (104/104 passing)
```bash
pytest -v
```

### Run Benchmarks & Generate Plots
```bash
python -m experiments.run_experiments all --seeds 3 --size 65536
python experiments/plot.py
```
Generated PNG plots and CSV datasets are saved to `results/`.
