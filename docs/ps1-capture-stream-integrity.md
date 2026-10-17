# Stage 242 — exact-byte binding of private PS1 debugger capture streams

Stage 241 compares **claimed** before/LW/after snapshots, global-slot
values, PCs and event ordering. Its collection labels and sequence
numbers are user-provided, rather than independently authenticated.
Stage 242 adds a separate, read-only **raw-byte integrity gate**:
`tools/audit_record_capture_stream_binding.py`.

The tool checks two private newline-delimited JSON files — one for
the before-read and one for the after-read — against an exact
manifest, user-owned executable and complete temporal claim.

## Integrity model

The manifest contains the SHA-256 of:
- The exact original PS-X EXE bytes returned by the private disc
  extractor (not the disc image as a whole).
- The exact bytes of the full stage-241 temporal claim JSON file.
- Each **raw JSONL byte stream**, including original whitespace and
  newlines, not a reserialized approximation.

The two file digests must differ, each stream must declare a separate
collector label, and each stream must have one record for **every**
claimed `(site, record_index)`. The strict parser rejects duplicate
JSON keys, missing or extra fields, duplicate indices, unordered or
reused event counters, inappropriate session tags, and files without
a final newline. The records must match the corresponding **claimed**
stage-241 window values, execution tags, PC, source slot, event
sequence and collection label exactly. Stage 241 itself is rerun,
including its upstream checks of the EXE signature, global-pointer
source, delayed load and indexed-memory access.

Two files and two source labels are *not* two authenticated,
independent observers. Hashes detect accidental change relative to a
given manifest; an author controlling both a file and its manifest
can always recompute matching hashes. This checker therefore **does
not certify emulator provenance or PS1 hardware execution**.

## Minimal private manifest shape

The following is *illustrative*, with placeholder SHA values; it is
not a complete or executable original-game capture:

```json
{
  "schema": "wild-arms-ps1-capture-stream-binding-v1",
  "session_tag": "my-private-session",
  "exe_sha256": "<64 lowercase hexadecimal digits>",
  "temporal_claim_sha256": "<64 lowercase hexadecimal digits>",
  "streams": [
    {
      "role": "before",
      "collector_tag": "memory_watch",
      "sha256": "<64 lowercase hexadecimal digits>"
    },
    {
      "role": "after",
      "collector_tag": "memory_snapshot",
      "sha256": "<64 lowercase hexadecimal digits>"
    }
  ]
}
```

Each JSONL row is one object with **exactly** these keys:

```json
{
  "session_tag": "my-private-session",
  "site": "site_1",
  "record_index": 0,
  "execution_tag": "local-event-001",
  "at_pc_u32": "0x8006d27c",
  "slot_address_u32": "0x800d2c3c",
  "slot_word_u32": "0x80120000",
  "event_sequence": 10,
  "collector_tag": "memory_watch"
}
```

All addresses and sample values above are synthetic/illustrative
and **not** original Wild Arms debugger evidence. The after-file
uses the after-PC, sequence and its own collector label as specified
by the private temporal claim. Both streams have 6–96 rows matching
the claim, ordered by event sequence, one UTF-8 JSON object per line
with a terminal newline. No other columns or whole-RAM dumps are
allowed.

## Local use

```sh
python3 -m tools.audit_record_capture_stream_binding \
  /private/WildArms.bin \
  /private/disc-inventory.json \
  /private/temporal-slot-snapshots.json \
  /private/capture-manifest.json \
  /private/before-watch.jsonl \
  /private/after-snapshot.jsonl
```

File bounds: temporal JSON **256 KiB**, manifest **16 KiB**, each
JSONL stream **128 KiB**. No private file is written or changed.
Exit codes are **0** for complete input self-consistency,
**1** for coherent but conflicting capture rows, and **2** for
invalid/corrupted input, including digest mismatches, using an
uninformative `invalid_private_input` JSON error.

Published output is limited to aggregate counts and conservative
boolean flags. It intentionally omits EXE hashes, local file names,
user-supplied PCs, addresses, register values and raw JSONL records.

## Next evidence boundary

A matching digest and exact pairwise comparison can show that the
supplied logs **haven't changed relative to the supplied manifest**
and that all submitted data agrees with an EXE and temporal claim.
It cannot show that the logs were originally captured on a real PS1,
that different collectors actually ran, or that no hardware event
was missed. Authenticate the collector identity, capture session,
software version, PC/CPU emulation state and independently exported
raw log provenance **outside this tool** before treating it as a
reliable runtime observation.

In particular, the current `2708` multiplication coefficient
remains a static checked-in instruction property, not the verified
size of a real game structure. The older `364` assumption and the
independent `88`-byte initializer remain separate from this
experiment. No native Nintendo Switch game binary is verified.

The stage-242 synthetic test suite includes positive multi-site
correlation, raw-stream tampering, recomputed digests with altered
memory values, wrong sessions and collectors, duplicate JSON keys,
lost/reordered rows, malformed inputs, and private-safe CLI results.
