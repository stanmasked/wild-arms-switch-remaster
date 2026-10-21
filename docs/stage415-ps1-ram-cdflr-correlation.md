# Stage415 — private PS1 RAM snapshot versus CDFLR byte-equivalence test

## Why this changes the verification strategy

Stages 411–414 found a shared copy/transfer routine and investigated a
runtime pointer slot at `0x800D2EA0`. No *constant-proven writer* was found
in the main executable or 127 candidate overlays. Those negative **static**
results cannot prove which ISO9660 resource is transferred.

A much stronger, independently falsifiable question is:

**Does a real PlayStation RAM snapshot at `0x80183000` contain the same
237,568 bytes as the beginning of the privately extracted `CDFLR.BIN`?**

The executable constructs `0x80183000` and has a 16-byte-step copy pattern
with length `0x3A000` (237,568 bytes), but those code patterns alone do not
establish that the named CDFLR container supplies the bytes.

## Inputs (PRIVATE, never put on GitHub)

1. A verified user-owned `CDFLR.BIN`, extracted from the original USA
   MODE2/2352 disc image. Its catalogued file length is 15,917,056 bytes.
2. A **real, raw 2 MiB RAM dump** taken by a trusted PS1 reference
   emulator/debugger at a precisely documented execution checkpoint.
   Save the frame/cycle, PC, loaded overlay, transfer-call arguments and
   any nearby disc-sector/LBA activity in a private note.

This environment does not currently have a working PS1 reference emulator
with debugger and a real RAM dump; therefore **no dynamic match has yet
been performed**. Neither a simulated dump nor a constructed test fixture
is acceptable as evidence for game behavior.

## Test command

```sh
python tools/verify_ps1_ram_container_snapshot.py \
  /private/WildArms/CDFLR.BIN \
  /private/WildArms/ps1-ram-2mib.bin \
  --address 0x80183000 \
  --bytes 0x3A000 \
  --container-offset 0 \
  --window-bytes 2048 \
  > /private/WildArms/stage415-ram-compare.json
```

The input RAM dump must contain the complete 2,097,152 bytes of physical
PS1 RAM in ascending address order. The requested KSEG0 RAM address
`0x80183000` maps to physical offset `0x183000`. The candidate copy
covers physical range `0x183000..0x1BD000` (exclusive end), safely within
the 2 MiB buffer. Equivalent KSEG1 aliases are supported.

For the user's privately extracted `CDFLR.BIN`, the proposed slice
`CDFLR[0:0x3A000]` has SHA-256
`359a7ab10a2ab2395eebe9b88bd2660a523d2dcd21653dd606d5e360c02f153d`.
This is only a source fingerprint, **not** evidence the RAM contains it.
The tool independently recomputes both slice digests, compares every byte
in 2,048-byte windows, and reports the first mismatch, matching prefix,
matched-window indexes, counts and digests; it never exports source bytes.

### Interpretation

- **EXACT_MATCH:** the two requested byte slices were identical at this
  checkpoint. This is strong evidence for RAM content equivalence, not
  standalone proof of the CD read or the program that loaded it.
- **NOT_IDENTICAL_AT_SNAPSHOT:** the slices differed at this checkpoint.
  This may be a wrong game moment, another resource, transformations, or
  in-memory mutations; it does **not** prove CDFLR was never loaded.
- **Invalid input:** file size, RAM region, sample size and source bounds
  are validated before comparison. Do not interpret a malformed dump.

Synthetic CI tests validate matching/mutated sample logic and bounds, but
**cannot establish real gameplay behavior**.

## Runtime capture gate

At the earliest relevant point in a *real* PS1 debugger, place a 4-byte
**write watchpoint on `0x800D2EA0`**. Record the **actual writer PC and
registers**, then follow the call with `a0` source pointer,
`a1=0x80183000`, `a2=0x3A000`. Dump RAM only at a documented point
*after* completion of the associated transfer and before unrelated writes.
Cross-check observed sector/LBA operations against the true ISO9660
directory inventory. A RAM match plus time-ordered source/LBA evidence
would justify identifying the CDFLR load path. Neither exists yet here.

Never commit original disc files, ROM images, RAM dumps, private captures,
decoded textures, or game dialogue to public source control.
