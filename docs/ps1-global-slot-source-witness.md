# Stage 240 — exact PS1 global-pointer slot source and private witness claims

Previous stages linked exact EXE bytes, *claimed* PC sequences, delayed
LW register values, and multi-site indexed addresses. Stage 239 accepted
the initial `v1` as a separately supplied register snapshot, however.
Even when both end-address and branch models agreed, a caller could
claim an arbitrary initial `v1`, causing the modeled **source address**
of `LW v1,offset(v1)` to differ from the address encoded by the
original preceding `LUI`. This is a genuine evidentiary gap.

Stage 240 adds an independent **read-only, opt-in**
`tools/audit_record_global_slot_witness.py` that rejects that gap.
It derives the global-pointer slot from the *exact checked-in
opcode signatures* in the supplied private EXE:

| MIPS instruction | Purely static result |
| --- | --- |
| `lui v1,0x800d` | LUI register base `0x800d0000` |
| `lw v1,0x2c3c(v1)` | Effective global slot `0x800d2c3c` |
| `sll v0,v0,2` | The subsequent independent load-delay-gap instruction |

The tool does **not** read PlayStation RAM and does not certify
that these instructions were executed in an original release.
It checks that each privately supplied claim of the initial
register base, `LW` instruction PC, effective memory slot address
and slot memory word agrees with the EXE-derived source; the claimed
memory word must also match the stage-239 loaded `v1` value and
the earlier indexed-address claim. The stage-239 delayed-load,
branch and cross-site checks must pass too.

## Private, local invocation

```sh
python3 -m tools.audit_record_global_slot_witness \
  /private/WildArms.bin \
  /private/disc-inventory.json \
  /private/global-slot-witness-claims.json
```

The final argument uses the following **illustrative-only** shape.
It is not a complete executable example: `joined_claim` must be
the complete stage-239 private capture, and the `slot_witnesses`
list must contain **one entry for every** previously submitted
`(site, record_index)` observation.

```json
{
  "schema": "wild-arms-ps1-global-slot-witness-claims-v1",
  "joined_claim": {},
  "slot_witnesses": [
    {
      "site": "site_1",
      "record_index": 0,
      "global_lw_pc_u32": "0x8006d27c",
      "lui_base_u32": "0x800d0000",
      "effective_slot_address_u32": "0x800d2c3c",
      "slot_memory_word_u32": "0x80120000"
    }
  ]
}
```

All hexadecimal words and PCs in the example are synthetic or
opcode-derived, **not** observed original-game RAM. Inputs require a
user-owned private raw PS1 image, local disc inventory, and an exact
EXE SHA-256 already checked by stage 239. Never upload original game
images, private RAM, raw debugger traces or these capture claims
to GitHub.

The checker uses the exact virtual address derived from the
instructions. Even if another KSEG address might physically alias
it, the checker does **not** silently equate such aliases. Physical
RAM aliasing and the address translation of an emulator have to be
independently demonstrated. It also does not infer who wrote the
global-pointer slot or whether its value changed over time.

## Report and verification boundary

The JSON report contains only counts, consistency booleans and
**explicitly false authenticity flags**. It never prints the
private memory word, guest PC, initial register, slot address, EXE
hash, input filename or game bytes. The exit codes are:

- **0:** full self-consistency of all claimed global-slot witnesses
  *and* all prior joined checks.
- **1:** a well-formed witness has a numerical/source contradiction.
- **2:** malformed, missing, unsupported or oversized private input;
  only a generic `invalid_private_input` JSON error is emitted.

The tool is intentionally dependent on **user-supplied memory
snapshots**. A matching claimed memory value is not an independent
memory read, evidence from a real PS1 debugger, or hardware
provenance. No actual record structure size is certified. The
checked-in index coefficient `2708` is still not a demonstrated
record size; the older `364` assumption is unsupported, and
an unrelated `88`-byte initializer pertains to another function.
No native Nintendo Switch game binary is established.

Regression tests check exact LUI/LW decoding, two- and three-site
witness coverage, the formerly unverified initial `v1` source,
mutations of slot base/address/value, corrupted EXE opcodes,
invalid/missing/foreign witnesses, KSEG alias refusal, original
stage-239 compatibility, and privacy-safe CLI operation. A future
verification step should compare this claimed memory word with an
**independently collected private debugger memory read**, bound to
the exact executed PC, capture order, game EXE hash and main-RAM
alias map.
