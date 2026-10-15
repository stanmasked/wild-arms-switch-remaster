# Importing actual gte-fuzz RTPS register captures

Upstream verified sources:
- https://github.com/JaCzekanski/ps1-tests/blob/master/gte-fuzz/main.c
- https://github.com/JaCzekanski/ps1-tests/blob/master/gte-fuzz/gte.h

The actual fuzzer prints 64 input lines `> r[N] = 0x12345678`, then `GTE 0x01 RTPS (sf=1, lm=0, tx=0, vx=0, mx=0)`, then 64 output lines `< r[N] = 0x12345678`. The GTE register indexing is **0..31 data** and **32..63 control**.

Added `tools/import_gte_fuzz_rtps.py`, which requires **complete 64+64 snapshots** and extracts:
- Rotation: control registers 32..36, packed signed 16-bit coefficients;
- Translation: control registers 37,38,39;
- Vertex VX0/VY0/VZ0: data registers 0,1;
- H, OFX, OFY, DQA, DQB: control registers 58,56,57,59,60;
- sf/lm from the printed command;
- Captured SXY2(14), SZ3(19), IR0..3(8..11), MAC0..3(24..27), FLAG(63).

The resulting 22-input/11-output JSONL is compatible with `tools/compare_gte_rtps_vectors.py`. It rejects duplicate register indices, missing entries, bad command syntax, and inputs with no complete RTPS sample. Other complete GTE commands are skipped.

## Usage

```sh
python3 tools/import_gte_fuzz_rtps.py captured-fuzz.log captured-rtps.jsonl --source hardware
python3 tools/compare_gte_rtps_vectors.py build/wa_gte_reference_runner captured-rtps.jsonl
```

Choose `--source external_emulator` for emulator captures. **The source label is user-declared; conversion cannot prove whether the log was captured on a real console.** Do not use synthetic logs as hardware evidence.

## Verification

Locally configured/built the complete portable C++ host project and ran **21/21 CTest suites successfully**, including 7 new parser contract tests. Those test cases are **synthetic examples matching the upstream log grammar**, not captured PlayStation output. No actual raw fuzz logs with 64+64 register values were available to import in this session; consequently no independent GTE accuracy result can be claimed.

The GTE model is still incomplete (register FIFO, exact pipeline timing/overflow peculiarities, hardware differential verification). The project does not yet build a playable Nintendo Switch game. Original Wild Arms binary/image assets remain local.

Next: obtain genuine full GTE fuzzer serial logs, verify their provenance, convert and run differential comparisons; investigate mismatch clusters against documented GTE semantics.
