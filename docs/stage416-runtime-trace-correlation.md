# Stage416 — private PS1 runtime trace correlation gate

## Evidence established before this stage

The user's original Wild Arms (USA) disc and extracted files are available privately. Static machine-code analysis identified a shared function at PS1 runtime address 0x8002356C, one call preparing destination 0x80183000 and size 0x3A000 (237,568 bytes), and a dynamic source argument read from RAM slot 0x800D2EA0.

The source file CDFLR.BIN is catalogued at logical Mode2/Form1 LBA 38503, 7,772 sectors long. The SHA-256 of the original private CDFLR.BIN first 0x3A000 bytes is 359a7ab10a2ab2395eebe9b88bd2660a523d2dcd21653dd606d5e360c02f153d.

These facts DO NOT prove which file was transferred. This runtime has no installed reference PS1 emulator/debugger, BIOS, or genuine PS1 RAM snapshot. No real debugger trace or game scene is claimed.

## Private required capture

Use a trusted original-PS1 reference debugger, keeping all copyrighted resources outside GitHub. Capture a single bounded transaction:
- a write watchpoint at RAM 0x800D2EA0; record PC, written width and new value;
- the call to routine 0x8002356C; record PC, a0, a1, a2;
- if supported, an actual disc read event with logical LBA and number of sectors;
- a raw 2,097,152-byte PlayStation physical RAM snapshot at an exactly documented tick *after* completion of the associated transfer.

Raw original game, RAM dumps, unredacted debugger logs, screenshots and decoded assets must remain PRIVATE. The trace JSON contains numerical metadata, but should also be kept private.

## Input event schema

JSON object with schema:1, kind:"PRIVATE_PS1_RUNTIME_EVENTS", and an events array sorted by strictly increasing emulator tick values. Events must have one of these kinds:

watchpoint_write: tick, address, width (1, 2 or 4), pc, after
transfer_call: tick, pc, target, a0, a1, a2
disc_read: tick, lba, sectors
ram_snapshot: tick, pc

Numbers can be JSON integers or hex strings prefixed with 0x. For example, a *synthetic illustrative* four-event trace would be:

    {
      "schema": 1,
      "kind": "PRIVATE_PS1_RUNTIME_EVENTS",
      "events": [
        {"kind":"watchpoint_write","tick":100,"address":"0x800D2EA0","width":4,"pc":"0x80012340","after":"0x801E0000"},
        {"kind":"transfer_call","tick":200,"pc":"0x80058B00","target":"0x8002356C","a0":"0x801E0000","a1":"0x80183000","a2":"0x3A000"},
        {"kind":"disc_read","tick":250,"lba":38503,"sectors":2},
        {"kind":"ram_snapshot","tick":300,"pc":"0x80058B4C"}
      ]
    }

The sample event values ARE FAKE and are NOT evidence of original gameplay. Use real captured register values and ticks; if disc events cannot be captured, omit them and retain PARTIAL status. Do not generate a synthetic RAM dump for original-game claims.

## Run on private assets

    python tools/audit_ps1_runtime_trace.py /private/trace-events.json /private/CDFLR.BIN /private/ram-2mib.bin --buffer 0x80183000 --bytes 0x3A000 > /private/correlation-metadata.json

The utility requires exactly one matching transfer call and one RAM checkpoint, in the correct order. A previous full-width watchpoint is ignored if a later byte/halfword write overlaps the same slot. The shared Stage415 comparator checks all bytes of the requested RAM/source slice and reports first mismatch, window counts and hashes. No source bytes or actual RAM content are emitted.

## Interpretation

TRACE_AND_BYTES_CORRELATED: The SUPPLIED trace is internally consistent, the latest full-width source-slot write agrees with a0, a disc read overlaps the catalogued CDFLR extent before the snapshot, and RAM bytes equal the private source bytes. This DOES NOT independently authenticate the user-provided trace, prove the payload was transferred by this call, or establish disc-read causality.

PARTIAL_OR_CONTRADICTORY_EVIDENCE: Some evidence is absent or disagrees. This does not prove CDFLR was never loaded; the checkpoint may be incorrect or the game may have mutated memory.

Invalid events, sizes, address regions, event order or ambiguous transactions cause an error, never a fabricated success.

A read overlapping the 7,772-sector CDFLR catalog range is a weak co-occurrence indicator, not proof of transfer source identity. A future trusted emulator capture and source/LBA causal reconstruction remain required before declaring any loader or original scene recovered.

All public CI tests use synthetic bytes and synthetic event logs only. No original BIN, EXE, raw RAM capture, pixels or script content is ever committed.
