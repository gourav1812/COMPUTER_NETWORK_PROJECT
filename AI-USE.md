# AI Use Disclosure

| Date | Tool | What it was used for |
|---|---|---|
| 2026-09-19 | Claude (Claude Code) | Implementation plan (`PLAN.md`); project scaffolding and interfaces; application CLI (`file_transfer.py`); test suite (`tests/`); experiment harness, runner and plotting scripts (`experiments/`). |
| 2026-10-28 | Antigravity (Google DeepMind) | Cross-platform Windows Winsock UDP `ConnectionResetError` (WinError 10054) resolution across transport protocols and channel proxy; RFC 6298 5.6 RTO backoff recovery implementation; execution of complete test matrix (104/104 tests green); empirical benchmarking and plot generation (`results/`); report authoring (`REPORT.md`); and viva preparation guide (`VIVA_PREP.md`). |

Core protocol code — `packet.py` checksum/encode/decode, the three ARQ protocols, `rto.py`, and
`channel.py` impairment logic — is written and owned by the team members named in each file.
