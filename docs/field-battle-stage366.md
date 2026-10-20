# Stage 366 — newest WABJ CRC fault after two cumulative wins

Prerequisite: stage 365 PR #55 uses real guest boots 14, 15, and 16 on an
isolated NeXium SDMC root to establish generation-3 A with 2 wins,
1 retreat, EXP 16, Gella 24, and older valid generation-2 B with
2 wins, 0 retreats, EXP 16, Gella 24. Stage 366 is stacked on #55.

The seventeenth **independent NeXium guest** reuses that same SDMC after
the workflow archives exact valid A/B bytes. Only byte 48 of latest A
(the outer WABJ CRC32) is XOR-corrupted by 0x80. The guest must reject
damaged A and load older valid B. Before any fight, ZL must show the
same 2 wins and 16 EXP/24 Gella as the sixteenth guest's pre-battle
screen. After a new R→B retreat, the repaired generation-3 A must
be byte-identical to the original good generation-3 A. Older B must
be byte-identical to its unmodified copy.

The independent auditor requires exactly two real Xvfb screenshots,
five immutable 52-byte evidence copies, all nested WABJ/WABR CRC
verifications, correct single-byte fault provenance, panel and field
pixel identity, nonduplicated rewards, and four distinct guest PIDs.
Synthetic positive/adversarial fixtures detect swapped/forged PNGs,
CRC tampering, wrong counters, extra rewards, PID reuse and mutated B.

**Limits:** All values are synthetic gameplay placeholders, unrelated to
original PS1 balancing. This is an emulated SDMC verification of
application journal fallback, not a physical Switch SD/eject/power-failure
durability test. Do not claim success before exact-head CI completes.
