# Stage417 — 67 independent fixed-size CDFLR resource slots

## Real-original evidence

The original `Wild Arms (USA).bin` was provided privately by the user and extracted locally. The previously sector-validated `BIN/CDFLR.BIN;1` file has **15,917,056 bytes**. This is **exactly 67 × 237,568 bytes** (`0x3A000`), no remainder.

The Stage410 original `WILDARMS.EXE` static MIPS analysis separately found an address `0x80183000` and copy size `0x3A000` (237,568 bytes). The exact agreement is strong structural corroboration that the CDFLR container consists of independently addressable transfer-size chunks. It does **not** prove which gameplay events select each chunk or that the observed routine loads this named file.

The original container was inspected independently across **all 67** slots. Results:

| Observation | Measured result |
| --- | --- |
| Fixed-length slots | 67 of 67 |
| Size per slot | `0x3A000` = 237,568 bytes = 116 Form1 logical sectors |
| First little-endian u32 in every slot | `0x80183100` |
| Increasing in-range aligned PS1 RAM-like pointer entries | 58 of 58 in each slot |
| Candidate RAM base inferred from pointer #0 at slot-relative offset `0x100` | `0x80183000` in every slot |
| Word `0x41` header at pointers 2–40 | 39 of 39 in **67** slots |
| Exact relation `next_pointer - current_pointer = word_3 + 8×word_4 + 12` | 39/39 in **67** slots |
| Paired data pointers 43,45,...57 starting with word `0x8000` | 8 of 8 in **67** slots |
| Palette-*sized* 512-byte pointer spans at 42,44,...56 | 8/8 in **65** slots; 6/8 in slots **#4 and #28** |
| Unique full-slot SHA-256 hashes | **53** |
| One exact duplicate slot group | **15** slots: #36, #48, #54–66 |

All 67 slots have a 256-byte table prefix and the same *number* of pointers, but the full 256-byte table differs between the 53 distinct slots.

The repeated group is **exact byte identity**, not proof that these are empty slots or unused map IDs. A data set can intentionally reuse a default/placeholder graphic. Do not remove the duplicate slots without loader evidence.

### Crucial limit on final pointer #57

Previously the first slot's final pointer #57 had no following pointer, so its size was unknown. The new fixed-slot geometry supplies an **upper bound** from its start to the next slot boundary. For slot #0 this bound is `0x3A000 - 0x35110 = 0x4EF0` (20,208 bytes), but this is **not** proof that all remaining bytes belong to that record: padding or other structures may intervene. The same upper-bound treatment applies to each of 67 slots.

### Exceptional candidate palette spans

Slots #4 and #28 have candidate even-index pair spans **224** and **64** bytes at indices 42 and 44 instead of 512. All later even-index pairs 46–56 are 512 bytes. The paired odd-index data markers remain `0x8000` for all eight pairs in both exceptional slots. This is a meaningful structural exception, not a malformed file or evidence that palettes were damaged.

No PS1 CLUT, pixel layout, pixel dimensions, texture compression or first map is verified yet. The “palette” name remains only a size-based hypothesis.

## Public reproducible analyzer

```sh
python tools/audit_cdflr_fixed_slots.py /private/path/CDFLR.BIN \
  > /private/path/stage417-cdflr-slot-metadata.json
python -m unittest discover -s tests -p test_audit_cdflr_fixed_slots.py
```

The analyzer enforces exact slot geometry, bounds, 58-pointer count/ordering, zero terminator/padding, record length rules and per-slot SHA-256. It reports **metadata/hashes/indices only**, not payload bytes or decoded art. The public tests are synthetic; actual original scans run privately.

Never place the original disc image, `CDFLR.BIN`, raw RAM, original screenshots, decoded graphics or complete original disassembly into public GitHub or CI artifacts.

## Next steps

1. Investigate the repeated 15-slot group and anomalous 224-/64-byte candidate palette spans while preserving their positions/identity.
2. Test the remaining asset/header grammar across all 53 distinct slot variants rather than assuming slot #0 is representative.
3. Establish which logical slot IDs are selected at runtime through original-PS1 debugging or a loader-control-flow proof. The 67 slots and copy-sized memory region are corroborating but not sufficient for causality.
4. Only when a particular region's graphic encoding is independently confirmed should a private-only texture/CLUT decoder and first-scene comparison be attempted.
