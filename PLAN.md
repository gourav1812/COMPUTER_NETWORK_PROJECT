# P3 Reliable UDP — Implementation Plan

Deadline: end of October 2026. Today: 19 Sep 2026 → ~6 weeks left.

## Architecture

```
 sender app ──► Transport (SW | GBN | SR) ──► UDP socket ──► Channel emulator ──► UDP socket ──► Transport ──► receiver app
                      ▲                                        (loss/dup/reorder/                     │
                      └──────────── ACKs ◄──────────────────── corrupt/delay+jitter, seeded) ◄────────┘
```

- **Same application, swappable transport**: `file_transfer.py` only talks to an abstract
  `Sender`/`Receiver` interface (`protocols/base.py`). `--protocol sw|gbn|sr` selects the class.
- **Emulator is a UDP proxy process/thread** sitting between sender and receiver, applying
  impairments in both directions. Seeded `random.Random(seed)` → reproducible runs.
- **Packet header** (`!IIBHI` → seq, ack, type, payload_len, checksum) + payload.
  Types: DATA, ACK, FIN, FIN_ACK. Checksum = 16-bit Internet checksum (hand-written) or CRC32
  (decide & justify; `zlib.crc32` is allowed as a hash fn but hand-written is better for the viva).
- **Timers**: SR needs one logical timer per outstanding packet → implement as a dict
  `seq -> send_time` checked in the sender's event loop (single thread + `socket.settimeout`/`select`),
  avoiding thread-per-timer races.
- **RTO**: Jacobson/Karels (α=1/8, β=1/4, RTO = SRTT + 4·RTTVAR, clamp [min,max], doubling backoff on
  timeout) + Karn (never sample retransmitted packets).
- **End of transfer**: FIN with total length + SHA-256 of file; receiver compares hash.

## Module ownership (from proposal)

| Module | Owner |
|---|---|
| `packet.py` (format, checksum), `file_transfer.py`, CLI | Gourav |
| `protocols/stop_and_wait.py`, `protocols/go_back_n.py` | Amit |
| `protocols/selective_repeat.py`, `rto.py` | Chirag |
| `channel.py`, tests, experiments | Vedang |

## Build order (each step ends with a passing test)

1. `packet.py` encode/decode + checksum → `tests/test_packet.py` passes.
2. Stop-and-Wait over a perfect channel (no emulator) → 1 MB file, hash matches.
3. `channel.py` loss + corruption → SW still passes at 20% loss.
4. Go-Back-N (cumulative ACK, window N, single timer).
5. Selective Repeat (per-packet ACK, receiver buffer, per-packet timers, window ≤ seqspace/2).
6. Channel duplication, reordering, delay+jitter.
7. `rto.py` adaptive RTO + Karn; compare with fixed RTO.
8. FIN/teardown + SHA-256 verification.
9. Experiments + plots + report.

## Correctness tests (not "one successful transfer")

`tests/test_transfer.py` runs, for each protocol × seed in 0..9 × impairment profile
(clean, 10% loss, 30% loss, 20% corrupt, 20% dup, 30% reorder, all-combined):
transfer a random file, assert SHA-256 matches. Plus edge cases: empty file, 1-byte file,
file size an exact multiple of payload size, lost final ACK, lost FIN.

## Experiments (required by brief)

`experiments/run_experiments.py` → CSV in `results/`, `experiments/plot.py` → PNG.

1. Goodput vs loss rate (0–40%) for SW/GBN/SR, fixed window.
2. Goodput vs window size (1–64) for GBN/SR at fixed loss.
3. Retransmissions vs reordering probability.
4. RTO sensitivity: fixed RTO {50,100,200,500 ms} vs adaptive, under delay+jitter.
Each point = mean of ≥5 seeds with error bars. **Claim to test**: "SR's goodput degrades less
than GBN's as loss rises, and the gap widens with window size."

## Weekly plan

| Week | Target |
|---|---|
| 1 (Sep 19–25) | packet.py + SW on clean channel |
| 2 (Sep 26–Oct 2) | channel emulator (loss/corrupt) + GBN |
| 3 (Oct 3–9) | SR + dup/reorder/delay |
| 4 (Oct 10–16) | adaptive RTO + Karn, FIN + hash |
| 5 (Oct 17–23) | full test matrix green, run experiments |
| 6 (Oct 24–31) | plots, analysis, README, viva prep |

## Rules to remember
- Each member commits their own module under their own name/email.
- Keep `AI-USE.md` updated.
