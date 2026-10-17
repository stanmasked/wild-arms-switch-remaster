# Stage 235 — private PS1 index-to-address delta comparison

Stages 232–234 established only **syntactic evidence** from checked-in
MIPS signatures: an index multiplier of **2708**, a candidate global
pointer load, and bounded possible paths to memory accesses. They did
**not** prove the runtime pointer, its targets, or the record size.

Stage 235 adds a separate numerical checker,
`tools/audit_record_address_deltas.py`. It can compare **privately
provided** effective memory addresses from at least three distinct
record indices against the existing opcode-derived coefficient, without
uploading addresses, registers or copyrighted data.

## Local private capture format

The following is a **synthetic example**, not original-game evidence.
The address strings are illustrative and must be replaced by actual
user-owned debugger observations when available.

```json
{
  "schema": "wild-arms-ps1-index-address-observations-v1",
  "source": "synthetic",
  "site": "site_1",
  "field_offset_s16": 6,
  "samples": [
    {"record_index": 0, "global_base_u32": "0x80120000",
     "effective_address_u32": "0x80120006"},
    {"record_index": 1, "global_base_u32": "0x80120000",
     "effective_address_u32": "0x80120a9a"},
    {"record_index": 5, "global_base_u32": "0x80120000",
     "effective_address_u32": "0x801234ea"}
  ]
}
```

Run locally:

```sh
python3 -m tools.audit_record_address_deltas /private/record-address-observations.json
```

Only one **claimed executed code site**, one field displacement, and
one presumed global pointer may be compared in one input. Accepted site
labels are `site_1`, `site_2`, `site_3`, and exactly one is required.
`source` is either `synthetic` or
`external_ps1_capture_claim`. The latter is a **user-supplied
unauthenticated claim**, not evidence of hardware provenance by itself.
No original EXE, memory dump or private debugger capture should be
committed to the repository.

Indices must be distinct integers between 0 and 65535; signed field
displacement must fit 16 bits. Provide between 3 and 128 samples,
each containing exactly three fields: `record_index`,
`global_base_u32`, `effective_address_u32` (addresses are explicit
eight-hex-digit 32-bit strings).

## Checks performed

- All observations must claim the **same** pointer base.
- For each row, the candidate effective address must equal
  `global_base + record_index × 2708 + signed_field_offset`.
- Every independent index pair must obey
  `address_difference = index_difference × 2708`.
- The calculation must fit the unsigned 32-bit address range
  **without wrap**. PS1 address-space mirroring and wrapping are
  outside this restricted oracle; such captures never count as a match.
- Even if all conditions pass, only **agreement with the submitted
  observations** is established. The tool never claims that the
  observations are genuine, that a pointer was loaded from the
  original global variable, that a given branch path ran, or that
  a memory allocation's element size is 2708.

The checker returns JSON with only counts, booleans, and the
previously published constant 2708. It emits no supplied addresses,
register contents, absolute offsets, input filename or guest PCs.
The exit status is **0** for full agreement, **1** for a coherent
but numerically mismatching reference, and **2** for invalid/private
input. The latter produces a generic JSON error without a traceback.
The private JSON file is capped at 64 KiB.

The synthetic regression suite covers matching and divergent
slopes, wrong intercepts, changed base pointers, 32-bit wrapping,
malformed indices/addresses, duplicate records, 128-sample bounds,
unverified external-source claims, and private CLI output suppression.
The test suite runs in the Disc analysis workflow and is explicitly
included in the matrix research audits.

## Evidence still missing

To infer the original game's **true structure layout**, first obtain
a debugger capture with a verified authentic game executable and
executed PC sequence, plus actual `a1`, the global pointer load value,
memory access width/offset, and effective address for at least three
distinct indices at the **same code site and object instance**.
Tie that capture to the precise EXE/version and reconcile KSEG
physical aliases. The numerical audit only checks a proposed
relationship; it **cannot authenticate any of those prerequisites**.
The legacy 364-byte claim remains rejected; the independent 88-byte
initializer belongs to another data structure. No native Switch
executable is implied by this research.
