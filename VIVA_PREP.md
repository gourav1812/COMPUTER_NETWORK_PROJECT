# P3 Reliable UDP — Viva / Oral Defense Preparation Guide

This guide prepares each project member to defend their assigned module, explain cross-module integration, and answer common networking viva questions with full technical depth.

---

## 1. Gourav Kejriwal (`packet.py`, `file_transfer.py`, CLI)

### Module Overview
- **`packet.py`**: Custom packet encoder, decoder, and RFC 1071 16-bit Internet Checksum implementation.
- **`file_transfer.py`**: Application layer CLI supporting `send`, `recv`, and `channel` modes with SHA-256 end-to-end file integrity verification.

### Core Architecture & Header Format
Header format string: `!IIBHI` (15 bytes total, big-endian network byte order)
- `seq` (4 bytes, `I`, unsigned 32-bit int): Packet sequence number
- `ack` (4 bytes, `I`, unsigned 32-bit int): Acknowledgment number
- `ptype` (1 byte, `B`, unsigned 8-bit int): Packet type (`0 = DATA`, `1 = ACK`, `2 = FIN`, `3 = FIN_ACK`)
- `length` (2 bytes, `H`, unsigned 16-bit int): Payload length in bytes (max 1024)
- `checksum` (4 bytes, `I`, unsigned 32-bit int): 16-bit Internet checksum (zero-padded)

### Viva Questions & Sample Answers

#### Q1: Why do we use network byte order (`!`), and what happens if you omit it?
**Answer:** Network byte order is big-endian (most significant byte first). Different processor architectures use different native byte orders (e.g., x86/ARM are little-endian, while network standards are big-endian). Omitting `!` causes `struct.pack` to use native endianness, so a sender on a little-endian machine would send integers backwards, causing a big-endian receiver (or another architecture) to misinterpret sequence numbers and checksums.

#### Q2: Explain the RFC 1071 Internet Checksum algorithm and how it detects bit flips.
**Answer:**
1. Group byte stream into 16-bit words (if the byte array length is odd, pad one zero byte at the end).
2. Compute the 32-bit sum of all 16-bit words.
3. Fold carries: While the sum exceeds 16 bits (`s > 0xFFFF`), add the carry bits (`s >> 16`) back to the lower 16 bits (`s & 0xFFFF`).
4. Take the one's complement: Invert all bits (`~s & 0xFFFF`).
5. **Detection:** When the receiver computes the checksum over header (with checksum in place) and payload, a clean packet yields `0x0000` (or `0xFFFF`). Any single bit-flip alters the sum and fails verification, raising `CorruptPacket`.

#### Q3: Can the 16-bit Internet Checksum miss errors?
**Answer:** Yes. It cannot detect:
- Word reordering (addition is commutative: $A + B = B + A$).
- Compensating bit errors (e.g., one bit flipped from 0 to 1, and another in the same column flipped from 1 to 0).
- Insertion or deletion of 16-bit zero words.
*(For stronger error detection, CRC32 or cryptographic hashes like SHA-256 are used).*

#### Q4: How does end-to-end integrity verification work in `file_transfer.py`?
**Answer:** Before sending the file data chunks, the sender computes `hashlib.sha256(data).digest()` (32 bytes) and transmits it as Chunk 0. The receiver reconstructs the file, computes its SHA-256 hash, and compares it to Chunk 0. If they match, `sha256_ok: True` is reported.

---

## 2. Amit (`protocols/stop_and_wait.py`, `protocols/go_back_n.py`)

### Module Overview
- **`stop_and_wait.py`**: Sender transmits one packet, starts timer, and waits for ACK before sending next.
- **`go_back_n.py`**: Pipelined ARQ with window $N$, cumulative acknowledgments, and a single timer for the oldest unacknowledged packet (`base`).

### Viva Questions & Sample Answers

#### Q1: Explain how Go-Back-N sender and receiver interact under packet loss.
**Answer:**
- **Sender:** Maintains a window `[base, base + window - 1]`. Up to $N$ packets can be in flight. A single timer tracks the oldest unacknowledged packet (`base`).
- **Receiver:** Maintains only `expected`. It accepts *only* in-order packets (`seq == expected`). If an out-of-order packet arrives (e.g., packet 2 arrives while packet 1 is lost), the receiver drops it and re-sends a cumulative ACK for `expected - 1`.
- **On Timeout:** When the timer for `base` expires, the sender assumes all packets from `base` through `next_seq - 1` were lost or discarded, and retransmits all of them ("Goes back N").

#### Q2: What is the maximum window size for Go-Back-N in terms of sequence space $2^k$?
**Answer:** For a $k$-bit sequence number space ($2^k$ distinct sequence numbers), the maximum allowable window size in Go-Back-N is:
$$W \le 2^k - 1$$
**Why:** If $W = 2^k$, suppose the sender sends packets $0, 1, \dots, 2^k-1$. The receiver accepts all of them and expects packet $0$ (wrapped around). If all ACKs are lost, the sender times out and retransmits packet $0$. The receiver cannot tell if this is a retransmitted duplicate of old packet $0$ or brand new packet $0$. With $W \le 2^k - 1$, the sender's window and receiver's expected sequence numbers never overlap ambiguously. *(Note: Our implementation uses 32-bit sequence numbers, $2^{32} \approx 4.29 \times 10^9$, so wrapping does not occur in practice, but the theoretical limit is $2^k - 1$).*

#### Q3: Why is Go-Back-N inefficient over high-loss or large-bandwidth-delay product links?
**Answer:** Because ACKs are strictly cumulative and the receiver cannot buffer out-of-order packets. The loss of a single packet invalidates all subsequent packets currently in flight. If window $W=64$, one dropped packet causes up to 63 successfully received packets to be discarded by the receiver and retransmitted by the sender, wasting bandwidth and triggering congestion collapse.

#### Q4: How does connection teardown work (FIN / FIN_ACK)?
**Answer:** After all data chunks are acknowledged, the sender dispatches a `FIN` packet and awaits a `FIN_ACK`. On receiving `FIN`, the receiver replies with `FIN_ACK` and enters a 1-second "linger" state (akin to TCP's `TIME_WAIT`), continuing to respond with `FIN_ACK` if duplicate `FIN`s arrive, ensuring the sender exits cleanly even if initial `FIN_ACK`s are lost.

---

## 3. Chirag Varma (`protocols/selective_repeat.py`, `rto.py`)

### Module Overview
- **`selective_repeat.py`**: Pipelined ARQ with individual acknowledgments, receiver out-of-order buffering, and per-packet logical timers.
- **`rto.py`**: RFC 6298 Jacobson/Karels adaptive RTO estimation with Karn's rule and exponential backoff.

### Viva Questions & Sample Answers

#### Q1: What is the maximum window size in Selective Repeat, and why is it $W \le 2^{k-1}$?
**Answer:** In Selective Repeat, both the sender and the receiver maintain sliding windows of size $W$. The maximum window size is:
$$W \le \frac{2^k}{2} = 2^{k-1}$$
**Why (Ambiguity Scenario):**
Suppose sequence numbers are $0, 1, 2, 3$ ($k=2$, sequence space size $= 4$). If $W = 3 > 2$:
1. Sender sends packets $0, 1, 2$.
2. Receiver receives $0, 1, 2$, buffers/delivers them, sends ACKs $0, 1, 2$, and advances its window to $[3, 0, 1]$.
3. If all ACKs are lost in the network, sender times out on packet $0$ and retransmits packet $0$.
4. Receiver receives packet $0$. Its window is $[3, 0, 1]$. It cannot distinguish whether packet $0$ is an old retransmission from the previous window or a brand new packet from the next window!
With $W \le 2^{k-1}$, the receiver's window $[rcv\_base, rcv\_base + W - 1]$ and previous window $[rcv\_base - W, rcv\_base - 1]$ never overlap.

#### Q2: How are per-packet timers implemented in `selective_repeat.py` without thread races?
**Answer:** Rather than spawning a thread per packet (which introduces synchronization overhead and race conditions), the sender event loop tracks deadlines in a dictionary `deadlines: dict[int, float]` (`seq -> deadline_timestamp`).
On each iteration:
1. `timeout = max(0.001, min(deadlines.values()) - time.monotonic())` is passed to `sock.settimeout()`.
2. When the socket times out or an ACK is processed, any packet whose deadline has passed (`deadline <= time.monotonic()`) is selectively resent, and its deadline is pushed back by the current RTO.

#### Q3: Explain the Jacobson/Karels algorithm (RFC 6298).
**Answer:** Jacobson/Karels computes smoothed round-trip time ($\text{SRTT}$) and RTT variation ($\text{RTTVAR}$):
- For the first measurement $R$:
  $$\text{SRTT} \leftarrow R, \quad \text{RTTVAR} \leftarrow \frac{R}{2}, \quad \text{RTO} \leftarrow \text{SRTT} + 4 \cdot \text{RTTVAR}$$
- For subsequent measurements ($\alpha = 1/8 = 0.125, \beta = 1/4 = 0.25$):
  $$\text{RTTVAR} \leftarrow (1-\beta)\text{RTTVAR} + \beta|\text{SRTT} - R|$$
  $$\text{SRTT} \leftarrow (1-\alpha)\text{SRTT} + \alpha R$$
  $$\text{RTO} \leftarrow \max(\text{min\_rto}, \min(\text{SRTT} + 4 \cdot \text{RTTVAR}, \text{max\_rto}))$$

#### Q4: What is Karn's algorithm, and what goes wrong without it?
**Answer:**
- **Karn's Rule:** Do *not* update $\text{SRTT}$ or $\text{RTTVAR}$ from an ACK for a packet that has been retransmitted.
- **The Retransmission Ambiguity Problem:** If packet $s$ is sent at $t_1$, timed out, and resent at $t_2$, and an ACK arrives at $t_3$:
  - If we assume the ACK is for the first transmission, $RTT = t_3 - t_1$ (grossly overestimated).
  - If we assume the ACK is for the second transmission, $RTT = t_3 - t_2$ (grossly underestimated if the first packet actually arrived late).
  Karn's rule eliminates this ambiguity by discarding samples from retransmitted packets.

---

## 4. Vedang (`channel.py`, Test Suite, Experiments)

### Module Overview
- **`channel.py`**: Seeded UDP proxy simulating network loss, single-bit payload corruption, duplication, reordering, and jittered latency.
- **`tests/`**: Automated test suite (packet round-trips, corruptions, edge sizes, deterministic channel, full matrix).
- **`experiments/`**: Benchmark runner (`run_experiments.py`) and visualization generator (`plot.py`).

### Viva Questions & Sample Answers

#### Q1: How does `channel.py` implement packet reordering and delay without blocking?
**Answer:**
- `channel.py` maintains a min-heap `pending` containing tuples `(send_at, insertion_order, destination, datagram)` and a list `held` for reordered datagrams.
- When packet reordering is triggered (`random() < reorder`), the current packet is placed into `held`.
- When the *next* packet arrives, it is scheduled immediately, while earlier held packets are scheduled with a slight delay ($send\_at + 0.005s$), causing the later packet to be transmitted before the earlier one.
- Datagrams are popped and forwarded from the priority heap as their timestamps expire.

#### Q2: Why is the channel emulator seeded (`random.Random(seed)`)?
**Answer:** Determinism and reproducibility. If a transfer fails under a specific test condition, reproducing it with `seed=123` produces the exact same packet loss and corruption sequence every time. This enables deterministic regression testing (verified in `test_channel_is_deterministic`).

#### Q3: How did you fix the Windows Winsock `WinError 10054` issue in UDP?
**Answer:** On Windows, when a remote UDP socket closes, the operating system generates an ICMP Port Unreachable message. Winsock converts this into a `WSAECONNRESET` error on the *next* `recvfrom()` call.
We handled this by catching `(socket.timeout, ConnectionResetError, OSError)` on all receiver and sender socket loops, treating connection resets as normal connection teardowns rather than unhandled fatal exceptions.

#### Q4: Summarize the findings of your 4 experimental plots.
**Answer:**
1. **Goodput vs. Loss:** Selective Repeat sustains high throughput under up to 30% loss, whereas Go-Back-N collapses due to full-window retransmissions.
2. **Goodput vs. Window:** Selective Repeat goodput scales with window size ($W=1 \to 64$), whereas GBN degrades because one loss causes $W$ retransmissions.
3. **Retransmissions vs. Reorder:** Selective Repeat buffers out-of-order packets with negligible retransmissions; GBN drops them and re-ACKs old packets, causing spurious retransmissions.
4. **RTO Sensitivity:** Fixed RTO below RTT causes excessive spurious retransmissions; fixed RTO above RTT causes long recovery stalls. Adaptive RTO automatically tracks network latency.
