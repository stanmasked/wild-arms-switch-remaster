# Stage 241 — claimed before/LW/after global-slot memory snapshots

Stage 240 compared a **user-supplied** global slot memory word with
the exact global slot address derived from the original MIPS
`LUI v1,0x800d` / `LW v1,0x2c3c(v1)` opcode pattern. It could not
establish **when** the alleged slot value was read or whether more
than one observation would agree around an executed load.

Stage 241 adds a separate, opt-in, read-only analyzer
`tools/audit_record_temporal_slot_snapshots.py` that introduces an
explicit **claimed chronology** around each `(site,record_index)`
observation. It rechecks all stage-240 EXE hash, slot address,
branch, delayed-load and indexed-address consistency before evaluating
the new temporal claims.

## What is required of each memory window

Supply exactly one pair of alleged memory reads for every indexed
observation, at two or three investigated code sites. Each pair:

- **Before:** the claimed debugger PC equals the global `LW` PC
  (site entry + 36 bytes), with the slot word supposedly read
  before that instruction executes.
- **LW event:** a claimed integer sequence number strictly later
  than the before-read and earlier than the after-read.
- **After:** the claimed PC equals the first instruction at `LW PC+8`.
  The independent `SLL` between `LW` and this instruction is the
  known load-delay gap. A matching snapshot claims the same slot
  value on both sides; that is a conservative **stability
  precondition**, not an assertion that original game RAM never changes.
- **Slot address:** both reads must use the exact unaliased virtual
  slot address derived from the checked EXE. Physical KSEG aliases
  are deliberately **not** silently substituted.
- **Value:** both reads must match the same claimed word supplied
  to stage 240, which in turn matches the earlier global-pointer
  loaded value and candidate indexed-access base.
- **Collection labels:** the pair must contain two *distinct*
  syntactically valid collector tags. The distinct labels are
  **not cryptographic evidence of distinct collectors**.
- **Chronology:** event numbers are unsigned 32-bit integers,
  are strictly ordered within each pair, and windows must not
  overlap each other in the claimed global ordering. Each sample
  carries a unique, opaque execution tag.

The static analyzer emits only **counts and booleans** for coherent
source, ordering, and values. No game bytes, user addresses, raw memory,
original opcode stream, register contents, private filenames, exact
capture event numbers, or per-site private records are printed.

## Private input format

The top-level schema is
`wild-arms-ps1-temporal-slot-snapshot-claims-v1`. The `slot_claim`
must be the **complete**, private stage-240
`wild-arms-ps1-global-slot-witness-claims-v1` input object,
including its nested joined PC/register and index/address claims.

The example below is a fragment **only**, not a complete ready-to-run
file or authentic original-game data.

```json
{
  "schema": "wild-arms-ps1-temporal-slot-snapshot-claims-v1",
  "slot_claim": {},
  "read_windows": [
    {
      "site": "site_1",
      "record_index": 0,
      "execution_tag": "local-event-001",
      "lw_event_sequence": 11,
      "before": {
        "at_pc_u32": "0x8006d27c",
        "slot_address_u32": "0x800d2c3c",
        "slot_word_u32": "0x80120000",
        "event_sequence": 10,
        "collector_tag": "memory_watch"
      },
      "after": {
        "at_pc_u32": "0x8006d284",
        "slot_address_u32": "0x800d2c3c",
        "slot_word_u32": "0x80120000",
        "event_sequence": 12,
        "collector_tag": "memory_snapshot"
      }
    }
  ]
}
```

Only three site names are recognized, and **one window for each**
`(site,index)` in the nested stage-240 claim is mandatory.
There are 6–96 bounded windows and a 256 KiB input file limit.

Run locally with privately owned PS1 source data:

```sh
python3 -m tools.audit_record_temporal_slot_snapshots \
  /private/WildArms.bin \
  /private/disc-inventory.json \
  /private/temporal-slot-snapshots.json
```

Exit codes: **0** for complete claimed self-consistency, **1** for
a numerically or source-contradictory but well-formed claim, and
**2** for malformed, unsupported, missing or overlapping data
(generic `invalid_private_input` output). No private content
appears in the normal JSON output or sanitized error result.

## Evidentiary boundary

Even a perfect match merely shows that *provided* snapshots,
PCs, event counters, source tags, slot words, delayed-loaded values
and indexed-address claims are **internally consistent** with the
supplied PS-X EXE. Since the assistant does not possess a trustworthy
original-game runtime capture or a separately authenticated emulator
memory reader, none of the following is proved:

- That snapshots were actually collected independently.
- That the claimed sequence numbers, PCs or RAM words originated
  from a genuine PlayStation execution.
- That no intervening writes or DMA operations occurred.
- That physical aliases or cache effects match actual R3000A hardware.
- That the opcode-derived coefficient `2708` is the game's true
  record allocation size (the older `364` claim remains unverified).
- That a native Switch executable runs the original game.

A later stage can add **provenance-bound capture manifests** and
compare independently exported debugger log digests, but merely
including a file hash or stream name will still not authenticate
the contents. Such evidence must be collected and verified
separately from the synthetic repository tests.

The stage-241 regressions cover two/three sites, non-overlapping
sequence windows, claimed separate collection streams, stable and
changed words, PC misalignment, wrong slot addresses, alias
refusal, missing/repeated/foreign records, bad types, and
non-leaking local CLI handling.
