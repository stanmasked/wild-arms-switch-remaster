# Stage 238 — PS1 delayed LW register value in a branch predicate

Stages 236–237 correlate privately **claimed** PC sequences with an
EXE and bounded MIPS BEQ/BNE branch paths. They intentionally do not
authenticate actual MIPS register values or cycle-accurate hardware
execution.

Stage 238 adds a **separate and opt-in** synthetic/private-claim
checker: `tools/audit_mips_load_delay_predicates.py`. It models the
restricted MIPS-I **one-instruction load-delay** dependency in
immediate `LW → BEQ/BNE` sequences. It does not change the
stage-237 branch-path validator or the original linear-only audit.

## Restricted model

- Input is a short **claimed**, explicit-PC instruction sequence of 3–32
  MIPS words (hex-encoded), a partial initial GPR snapshot and values
  that the caller says each `LW` returned. Those values are not obtained
  from original RAM or checked against an authentic EXE.
- Supported instructions are literal NOP, aligned `LW`, simple
  `SLL`, `ADDU`, and normal `BEQ/BNE`. Unknown opcode,
  undocumented operands, mismatched PC order, out-of-range address,
  same-destination write collisions, and unsupported memory behavior
  cause the checker to **fail closed**.
- At instruction *N*, branch operands are read from the state **before**
  the pending `LW` value from instruction *N−1* is retired. Thus a
  branch immediately after `LW t0,...` reads the **old t0**, while a
  branch after one intervening NOP can read the supplied loaded value.
- Every `BEQ/BNE` requires an actually listed **literal NOP delay
  slot**, followed by the correct target or fallthrough PC. Encoded
  backward targets, branch-likely, jumps, memory operations in delay
  slots, and branch outcomes that contradict the modeled operand values
  are refused.
- Existing stage-237 checks of actual EXE signatures, offsets, and
  multi-site addresses must **still** be run separately. Passing
  both tools is not a proof that the supplied snapshots correspond
  to a genuine runtime trace or to the same program instance.

## Local private claim format

The following is a small, entirely **synthetic** example. Both the PC
and data values are illustrative, not genuine Wild Arms evidence.

```json
{
  "schema": "wild-arms-ps1-load-delay-predicate-claims-v1",
  "source": "synthetic",
  "initial_gprs_u32": {
    "4": "0x80120000",
    "8": "0x00000000"
  },
  "steps": [
    {
      "pc_u32": "0x80010000",
      "word_u32": "0x8c880000",
      "load_result_u32": "0x00000001"
    },
    {
      "pc_u32": "0x80010004",
      "word_u32": "0x11000002",
      "claimed_taken": true
    },
    {
      "pc_u32": "0x80010008",
      "word_u32": "0x00000000"
    },
    {
      "pc_u32": "0x80010010",
      "word_u32": "0x00000000"
    }
  ]
}
```

Here `LW t0,0(a0)` *claims* to load 1; the very next `BEQ t0,zero`
compares the **previous** t0 value 0, so `claimed_taken: true` is
consistent with the model. The instruction at PC+8 is the mandatory
NOP branch-delay slot; PC+16 is the encoded forward branch target.
Claiming that the branch was **not** taken would be inconsistent
with the supplied initial register state. Inserting an independent
instruction before the branch changes which value the branch reads.

Run privately:

```sh
python3 -m tools.audit_mips_load_delay_predicates \
  /private/load-delay-predicate-claim.json
```

The input file is limited to 64 KiB and the output contains **counts
and booleans only**, never claimed PC addresses, GPR values, load
results, private paths, or instruction words. A coherent claim exits
0. Malformed, contradictory or unsupported input exits 2 and prints
only `invalid_private_input`, without a Python traceback or
sensitive data. There is no genuine-game hardware confirmation status.

## Boundaries and next work

This restricted checker is a model of **one** MIPS-I load-delay
convention; it is not a PS1 cycle-level simulator. It does not
handle unaligned loads, load-linked arithmetic, interrupts,
exceptions, caches, back-to-back conflicting register writes,
branch-likely instructions or all R3000A pipeline corner cases.

Synthetic tests cover old-versus-new operand timing, BEQ/BNE branch
outcomes, intervening NOPs, required delay slots, invalid branch
targets, collisions, private input handling and compatibility with the
separate stage-237 path checker. The real original-game record stride
is still **unverified**; the checked-in coefficient 2708 remains a
static instruction result, not a certified game structure length.
The independent 88-byte initializer is unrelated and a native
Nintendo Switch game build is not yet verified.
