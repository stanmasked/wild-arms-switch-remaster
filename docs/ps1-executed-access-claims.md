# Stage 236 — privately claimed executed-PC and cross-site address correlation

Stages 232–235 measured only static opcode shapes and the arithmetic
agreement of **user-supplied** index/address data. Stage 236 links these
two domains **without promoting a claim to authentic PS1 evidence**.

`tools/audit_record_executed_access_claims.py` checks a private,
user-owned PS-X EXE against a private capture-claim JSON:
- the exact SHA-256 of all supplied EXE bytes, load boundaries, and the
  previously checked-in index/global-pointer opcode signature;
- at least two distinct candidate function sites (site_1/site_2/site_3);
- a **strictly straight-line** sequence from the first index opcode
  through the claimed memory instruction, allowing only NOPs, a single
  supported `ADDU` and one `v1`-based load/store;
- an exact, contiguous **claimed executed-PC list for each observation**
  matching that candidate sequence, including the `LW` load and the
  following instruction that provides its load-delay gap;
- the signed 16-bit displacement encoded in the actual memory opcode
  and required alignment (e.g. 4-byte alignment for `LW/SW`);
- the stage-235 nonwrapping address equation and every within-site
  index/address difference;
- one unchanged *claimed* base pointer across the compared sites and,
  for at least three **common indices**, matching normalized effective
  addresses across sites (after subtracting their distinct field offsets).

The tool deliberately does **not** follow branches or infer a delayed
branch-slot path. A tail containing `BEQ`, `BNE`, `J`, `JR`, `JAL`,
branch-likely, a different arithmetic instruction, or an unsupported
intermediate memory operation **cannot** be correlated by this strict
mode. A future branch-aware capture verifier will need an independent
PC sequence oracle and load-delay/branch-delay modeling.

## Private capture shape

Use only a user-owned EXE image and a local `inspect_disc.py --json`
inventory for `/EXE/WILDARMS.EXE;1`. Prepare a private JSON file with
this **illustrative synthetic structure** (the ellipsis is illustrative,
not valid input):

```json
{
  "schema": "wild-arms-ps1-executed-record-access-claims-v1",
  "source": "synthetic",
  "exe_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "observations": [
    {
      "site": "site_1",
      "field_offset_s16": 0,
      "samples": [
        {
          "record_index": 0,
          "global_base_u32": "0x80120000",
          "effective_address_u32": "0x80120000",
          "executed_pcs": ["0x8006d258"]
        }
      ]
    }
  ]
}
```

The example is intentionally **not a passing fixture**. An actual
input requires **2–3 sites**, **3–32 distinct indices per site**, and
at least **3 shared indices across all sites**, and every
`executed_pcs` array must contain all 11 prefix instruction PCs and
all subsequent instructions through the candidate access (11–21 PCs).
The `exe_sha256` must match the exact user-owned extracted executable,
not just the prefix. Numbers are bounded and addresses/PCs use
8-hex-digit unsigned strings. The JSON file is capped at 256 KiB.

Run locally:

```sh
python3 -m tools.audit_record_executed_access_claims \
  /private/WildArms.bin \
  /private/disc-inventory.json \
  /private/record-access-capture.json
```

On matching data, exit status is **0**; on well-formed but contradictory
claims it is **1**; on missing, malformed, inconsistent-signature,
unreadable, or oversized private inputs, it is **2**. Output is only
aggregate counts, booleans and a fixed schema: **no EXE hash**, absolute
guest PC, addresses, register values, field offsets, memory bytes or
private paths are printed. Errors contain no traceback or original
exception detail.

## What a successful result means — and does not mean

A matching result says that privately **claimed** instruction PCs and
addresses are *self-consistent* with the specific supplied executable
bytes and the known 2708 instruction-derived index coefficient.
The checker cannot establish that a debugger actually captured those
PCs, that the EXE is the genuine commercial Wild Arms revision, or that
its instructions were executed without runtime code modification.
It does not model PS1 KSEG aliasing, DMA, all load-delay interactions,
indirect control flow, allocator layout, record size, or native Switch
execution. All authenticity and record-size proof flags remain **false**.
Numerical 2708 is *not* promoted to a verified record size; the legacy
364 claim remains unsupported and the separate 88-byte initializer
is unrelated.

Synthetic tests cover multi-site correlations, different field offsets,
correct and false PC sequences, SHA mismatch, unrecognized branches,
base drift, address corruption, insufficient shared indices,
alignment, size bounds, and privacy-safe CLI errors. **No original
game asset or authentic debugger trace is committed to the repository.**
