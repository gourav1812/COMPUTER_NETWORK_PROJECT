# Build Guide

How to use this: read the section for your module, write the code yourself, then run the listed
test. When a test fails, read the "common failures" list before asking for help. Build in this order,
because each module depends on the one before it:

1. `packet.py` (Gourav)
2. `channel.py` (Vedang)
3. `protocols/stop_and_wait.py` (Amit)
4. `rto.py` (Chirag)
5. `protocols/go_back_n.py` (Amit)
6. `protocols/selective_repeat.py` (Chirag)

Setup once: `pip install pytest matplotlib pandas`. Run a single test file with
`python -m pytest tests/test_packet.py -v`.

---

## 0. Background everyone needs

**Why UDP needs help.** UDP sends a datagram and forgets it. The datagram may never arrive, arrive
twice, arrive out of order or arrive damaged. An ARQ protocol (Automatic Repeat reQuest) fixes this
with four tools:

| Tool | Problem it solves |
|---|---|
| Sequence number | Receiver can tell order, duplicates and gaps |
| Checksum | Receiver can detect damaged packets (and silently drop them) |
| ACK (acknowledgement) | Sender learns what arrived |
| Timer + retransmission | Sender resends what didn't arrive |

**Key rule: a corrupt packet is treated exactly like a lost one.** The receiver drops it and sends
nothing. The sender's timer eventually fires and it resends. That keeps the logic simple.

**How the pieces connect.** `file_transfer.py` splits the file into chunks and gives the list to a
Sender's `send_chunks()`. On the other side a Receiver's `receive_chunks()` returns the same list in
order. Your protocol only has to move a list of byte-strings reliably from one side to the other. It
never needs to know it's a file. Chunk 0 is the SHA-256 hash, which the application checks at the end.

**Useful socket calls** (all standard library, allowed):
- `sock.sendto(bytes, addr)` sends a datagram.
- `sock.recvfrom(4096)` returns `(bytes, sender_addr)` and blocks until something arrives.
- `sock.settimeout(seconds)` makes `recvfrom` raise `socket.timeout` if nothing arrives in time.
  This is how you build timers without threads.
- `time.monotonic()` is the clock to use for timers (it never jumps backwards).

**The ending problem (applies to all three protocols).** After the last data packet is ACKed, the
sender sends a FIN packet and waits for FIN_ACK, retransmitting FIN on timeout. The receiver, on FIN,
replies FIN_ACK and finishes. But if that FIN_ACK is lost, the sender resends FIN to a receiver that
has already stopped. Two accepted fixes, pick one and be ready to explain it in the viva:
- The receiver keeps answering FINs for a short linger period (say 2 seconds) before closing
  (this is the idea behind TCP's TIME_WAIT).
- The sender gives up after N FIN retries and treats the transfer as done, since all data was
  already ACKed.

---

## 1. `packet.py` (Gourav)

**Job.** Turn a `Packet` into bytes and back, and detect damage.

**Header.** `HEADER_FMT = "!IIBHI"`: `!` is network byte order (big-endian); `I` is a 4-byte
unsigned int, `B` is 1 byte and `H` is 2 bytes. So the fields are seq (4), ack (4), type (1),
payload length (2), checksum (4), 15 bytes in total. Use `struct.pack` / `struct.unpack` with this
format.

**Checksum.** Write it yourself; don't call a library. The standard choice is the **16-bit Internet
checksum** (RFC 1071), the one IP, TCP and UDP use:
- Treat the data as a sequence of 16-bit big-endian words. If the length is odd, pad one zero byte.
- Add all the words together.
- "Fold" the carries: while the sum is bigger than 16 bits, add the high part back onto the low 16
  bits.
- Take the one's complement (flip all bits) and keep the low 16 bits.

**Encoding steps.** Pack the header with checksum = 0, append the payload, compute the checksum over
all of it, then pack the header again with the real checksum.

**Decoding steps.**
1. If the data is shorter than `HEADER_SIZE`, raise `CorruptPacket`.
2. Unpack the header.
3. If the length field doesn't match the actual payload size, raise `CorruptPacket`.
4. Rebuild the bytes with the checksum field set to 0, recompute the checksum and compare it with
   the received value. If they differ, raise `CorruptPacket`.

**Test:** `tests/test_packet.py`

**Common failures.**
- The checksum was computed with the real checksum already in the header. It must be 0 while you
  compute.
- Forgot the odd-length padding.
- Didn't check the length field, so truncated packets slip through.

**Viva questions.**
- Why network byte order?
- Can the Internet checksum miss an error? (Yes. Swapping two 16-bit words gives the same sum.)
- Why is CRC32 stronger?

---

## 2. `channel.py` (Vedang)

**Job.** A fake, unreliable network. It's a UDP proxy: the sender sends to the channel's port; the
channel forwards to the receiver; the receiver's replies come back to the channel, which forwards
them to the sender.

**Setup.** Bind a socket to `listen_addr`. When a datagram arrives, look at who sent it. If it came
from `receiver_addr`, it's an ACK going back, so forward it to the remembered sender address.
Otherwise it's from the sender: remember that address, then forward the datagram to the receiver.

**Loop.** Keep going until `stop_event.is_set()`. Use a short `settimeout` (for example 0.05 s) so
the loop regularly checks the stop flag and releases any delayed packets that are due.

**Impairments.** Roll `self.rng.random()` separately for each one, in a fixed order, and update
`self.counters` each time one happens:
- **Loss:** drop the datagram.
- **Corruption:** flip one random bit in the payload part of a copy. The checksum should then
  catch it.
- **Duplication:** schedule the datagram twice.
- **Reordering:** hold this datagram back and release it after the next one goes out (or after a
  short timeout if no next one comes).
- **Delay and jitter:** send time = now + delay ± a random jitter drawn from `rng`. Keep scheduled
  packets in a heap (`heapq`, keyed by send time) and send whatever is due on each loop pass.

**Determinism.** Every random choice must come from `self.rng`, never the `random` module
directly. Then the same seed always makes the same decisions.

**Tests:** `test_channel_is_deterministic`; every test in `test_transfer.py` also exercises it.

**Common failures.**
- Using `random.random()` instead of `self.rng`.
- Blocking forever in `recvfrom` so the thread never stops.
- Corrupting the original bytes, so a duplicated copy is corrupted too.

**Viva questions.**
- Why must the emulator be seeded?
- Why does delay with jitter naturally cause reordering?

---

## 3. `protocols/stop_and_wait.py` (Amit)

**Idea.** Send one packet. Wait for its ACK. Then send the next one. Sequence numbers alternate
0/1, or you can simply use the chunk index; say which you chose and why.

**Sender state.** The current index `i` and the packet being waited on.

**Sender events.**
- *Start and after each ACK:* send chunk `i` and start the timer (set the socket timeout to the RTO).
- *ACK for `i` arrives (and it isn't corrupt):* take an RTT sample if this packet was never
  retransmitted, then move to `i + 1`.
- *Wrong or duplicate ACK:* ignore it and keep waiting. The time already spent waiting counts, so
  don't restart the full timeout.
- *Timeout:* resend, mark the packet as retransmitted, and call `rto.backoff()`.
- Count every send in `stats.packets_sent` and every resend in `stats.retransmissions`.

**Receiver state.** `expected`: the next sequence number it wants.

**Receiver events.**
- *Corrupt packet:* drop it and send nothing.
- *DATA with seq == expected:* store the payload, send an ACK for that seq, and add 1 to `expected`.
- *DATA with an old seq (a duplicate because our ACK was lost):* **send the ACK again**, but don't
  store the payload twice. Missing this is the classic bug.
- *FIN:* see "the ending problem" in section 0.

**Tests:** `test_transfer.py -k sw`

**Common failures.**
- Transfers hang when an ACK is lost: the receiver doesn't re-ACK duplicates.
- The file is received with repeated chunks: duplicates are stored instead of discarded.

**Viva questions.**
- What is the channel utilisation of Stop-and-Wait? (Transmission time divided by transmission
  time + RTT.)
- Why is it terrible on long links?

---

## 4. `rto.py` (Chirag)

**Idea.** The retransmission timeout (RTO) should follow the measured round-trip time (RTT). Too
short and the sender retransmits packets that weren't lost; too long and it sits idle after a loss.

**Jacobson/Karels, from RFC 6298** (use α = 1/8 and β = 1/4):
- *First sample R:* SRTT = R, RTTVAR = R / 2.
- *Later samples:* first RTTVAR = (1 − β)·RTTVAR + β·|SRTT − R|, *then*
  SRTT = (1 − α)·SRTT + α·R. The order matters: RTTVAR must use the old SRTT.
- RTO = SRTT + 4·RTTVAR, clamped to the range [min_rto, max_rto].
- *backoff() on a timeout:* double the RTO, clamped to max_rto.

**Karn's algorithm.** Enforced by the callers (the protocols), not by `rto.py` itself. When an ACK
arrives for a packet that was ever retransmitted, you can't tell which copy it's acknowledging, so
don't take an RTT sample from it.

**Test:** `tests/test_rto.py`

**Viva questions.**
- Why 4·RTTVAR?
- What goes wrong without Karn's algorithm? (Retransmission ambiguity: the RTT estimate collapses
  or grows too large.)
- Why exponential backoff?

---

## 5. `protocols/go_back_n.py` (Amit)

**Idea.** Up to N packets can be in flight without an ACK. ACKs are **cumulative**: "ACK k" means
"I have everything up to k". The receiver accepts only in-order packets. On a timeout, the sender
resends **everything** from the oldest unACKed packet onwards.

**Sender state.**
- `base`: the oldest packet not yet ACKed.
- `next_seq`: the next packet never sent.
- **One** timer, for `base`.
- The send time of each packet, and whether it was ever retransmitted (for RTT samples and Karn).

**Sender loop.**
1. While `next_seq < base + N` and chunks remain: send `next_seq`, and if it's the only packet in
   flight, start the timer. Increment `next_seq`.
2. Wait for an ACK, with the time left on the timer as the socket timeout.
3. *ACK k where k ≥ base:* set `base = k + 1`. Take an RTT sample only if packet k was never
   retransmitted. If packets are still in flight, restart the timer; otherwise stop it.
4. *Timeout:* resend every packet from `base` to `next_seq − 1`, count each one as a
   retransmission, back off the RTO and restart the timer.

**Receiver.**
- Only `expected` is tracked.
- *In-order packet:* store it, move `expected` on, and ACK `expected − 1`.
- *Anything else (out of order, duplicate or corrupt but decodable):* discard it and re-send the
  ACK for `expected − 1`.
- *Corrupt packet:* drop it silently.
- *Before anything has arrived:* you need a rule for which ACK to send. Either send nothing, or
  use a sentinel value; document which.

**Tests:** `test_transfer.py -k gbn`

**Common failures.**
- The timer isn't restarted after `base` advances, which causes spurious timeouts.
- A stale ACK (k < base) moves `base` backwards.
- The window isn't refilled after an ACK.

**Viva questions.**
- Why does one loss cost up to N retransmissions?
- Why is the receiver so simple?
- What is the maximum window size for a given number of sequence-number bits? (2^k − 1.)

---

## 6. `protocols/selective_repeat.py` (Chirag)

**Idea.** Like Go-Back-N, but ACKs are **individual** and the receiver **buffers** out-of-order
packets. Only the packets that were actually lost get resent.

**Sender state.**
- `base` and `next_seq`, as in Go-Back-N.
- A set of acked sequence numbers.
- **A timer per unacked packet**, stored as a dict of `seq -> deadline`. There's no need for a
  thread per timer: each loop pass, find the earliest deadline, use the time until it as the socket
  timeout, and when you wake up, resend every packet whose deadline has passed.

**Sender events.**
- *Send:* while the window has room, send `next_seq` and set its deadline to now + RTO.
- *ACK s:* mark s as acked and remove its timer. Take an RTT sample if s was never retransmitted.
  If s == base, slide `base` forward past every consecutive acked packet.
- *Timer for s expires:* resend **only s**, back off, and set a new deadline for s.

**Receiver state.**
- `rcv_base`: the next in-order seq it's waiting for.
- A buffer dict of `seq -> payload`.

**Receiver events.**
- *seq in [rcv_base, rcv_base + N − 1]:* ACK it, and buffer it if it's new. If seq == rcv_base,
  deliver every consecutive buffered packet and move `rcv_base` forward.
- *seq in [rcv_base − N, rcv_base − 1]:* an old packet whose ACK was lost. **ACK it again**, or the
  sender will be stuck forever.
- *Anything else:* ignore it.

**Window rule.** If sequence numbers wrap around, the window must be at most half the
sequence-number space. Otherwise the receiver can't tell a new packet from a retransmitted old one.
This project uses 32-bit numbers and never wraps, but you **will** be asked to explain it.

**Tests:** `test_transfer.py -k sr`

**Common failures.**
- Old packets aren't re-ACKed (the transfer hangs under ACK loss).
- `base` doesn't slide past packets that were already acked.
- Karn's rule is applied per window instead of per packet.

**Viva questions.**
- Draw the window-size-too-large ambiguity scenario on the board.
- When does Selective Repeat beat Go-Back-N, and when doesn't it matter?

---

## 7. After everything passes

1. `python -m pytest -q`: every test must be green.
2. `python -m experiments.run_experiments all --seeds 5`, then `python experiments/plot.py`.
3. Write up each plot:
   - what you expected, what happened, and why;
   - whether the claim held (Selective Repeat degrades less than Go-Back-N as loss rises);
   - any surprises, such as Go-Back-N matching Selective Repeat at low loss, or a fixed RTO beating
     the adaptive one on a very stable link.
4. Each person must be able to explain their own module **and** the basics of everyone else's.
