# Stage414 — private CDSTG overlay writer audit

## Original PlayStation source

The user's private `Wild Arms (USA).bin` was previously verified against the local inventory and used to extract `CDSTG.BIN` (76,021,760 bytes) from ISO9660 Mode 2 Form 1 sectors. Original game bytes, executable code, textures and source-derived dumps remain **outside public GitHub**.

`CDSTG.BIN` divides exactly into 128 fixed 593,920-byte records. **127** have executable-like headers with coherent PS-X EXE-style load address, entry PC, code extent, initial stack and `Sony` region marker; record **#25** is structurally different. We deliberately exclude this exceptional record from executable-code assumptions without discarding or modifying it.

## Newly reproduced negative evidence

The Stage413 conservative straight-line MIPS constant-base scanner was extracted into a reusable function and applied privately to the declared text area of **all 127** PS-X EXE-like records.

- **127** records were scanned; #25 remained **unclassified**.
- **0** stores were proven to target the runtime source-pointer slot `0x800D2EA0` using the supported local constant-propagation operations.
- **0** unknown-base stores shared the precise 16-bit immediate `0x2EA0` in this scan.
- **159,527** branch/delay-slot reset events occurred while scanning the declared candidate text.

This is a restricted syntactic result, not a proof about what runs. It does **not** mean none of the overlays writes that slot at runtime. It misses dynamically computed pointers, calls returning pointers, loads from memory, path-sensitive computations, branch-delay-slot writes and stores via memory-copy subroutines. Candidate record text may also mix actual code with data. The exceptional block #25 and any other non-overlay game content are explicitly outside the result.

Combined with the negative Stage413 main-EXE scan, this makes a **private emulator write watchpoint** a better next diagnostic than inferring a file identity from another static marker.

## Reproduction on locally held originals

```sh
python tools/audit_wild_arms_cdstg_overlay_writes.py /private/path/CDSTG.BIN \
  > /private/path/cdstg-overlay-writer-evidence.json

python -m unittest discover -s tests -p test_audit_wild_arms_cdstg_overlay_writes.py
python -m unittest discover -s tests -p test_audit_wild_arms_slot_writes.py
```

Only record indexes, inferred store-site offsets, counts and explicit uncertainty flags appear in the report. Protected source bytes are never printed or exported.

## Next acceptance step

Use a trusted **PlayStation reference emulator**, not the Switch NeXium prototype, and set a 4-byte write watchpoint on `0x800D2EA0`. Capture the program counter, loaded overlay identity, call-site arguments and ISO9660 sector/LBA operations at the first write. Correlate the observed runtime PC against either the main EXE load base or one of the candidate CDSTG overlay load bases.

Only call the loader a `CDFLR.BIN` reader once actual runtime file selection and memory contents are matched. No original game resources should enter CI, public screenshots or artifacts.
