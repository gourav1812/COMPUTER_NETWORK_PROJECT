# P3 — Reliable Data Transfer over UDP

File transfer over UDP with pluggable ARQ transports (Stop-and-Wait, Go-Back-N, Selective Repeat),
adaptive RTO (Jacobson/Karels + Karn), a seeded channel emulator, and SHA-256 integrity checks.
See `PLAN.md` for design and schedule.

## Run
```
pip install pytest matplotlib pandas
# terminal 1
python -m p3_rudp.file_transfer recv --port 9000 --out out.bin --protocol sr --window 8
# terminal 2 (emulator between sender and receiver)
python -m p3_rudp.file_transfer channel --listen 8999 --to 9000 --loss 0.1 --reorder 0.1 --seed 1
# terminal 3
python -m p3_rudp.file_transfer send --port 8999 --file some.bin --protocol sr --window 8
```

## Test & experiments
```
pytest -q
python -m experiments.run_experiments all --seeds 5
python experiments/plot.py
```
