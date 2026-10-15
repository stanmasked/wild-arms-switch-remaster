# CDGD.BIN: probable overlay load base

A read-only analysis of the user's original **Wild Arms (USA)** disc image produced the following *static inference*.

| Evidence | Raw instruction / address | Interpretation |
| --- | --- | --- |
| CDGD file offset 0x64 | 0x104000a6 (BEQ) | relative branch target, file offset 0x300 if mapped contiguously |
| CDGD file offset 0xf4 | 0x0805f0c0 (J) | low 28 bits of target = 0x017c300 |
| Hypothetical base | 0x017c300 - 0x300 | low 28-bit base = 0x017c000 |
| First header address | 0x8017c088 | base 0x8017c000 + offset 0x88 |
| Other header addresses | 0x8017c0fc, 0x8017c160, 0x8017c1e4, 0x8017c1e4, 0x8017c258, 0x8017c2d4 | offsets 0xfc, 0x160, 0x1e4, 0x1e4, 0x258, 0x2d4 |

**Probable KSEG0 base: `0x8017C000`.** A matching conditional-branch target and absolute J instruction, together with seven in-range header addresses, provide independent consistency checks. The first branch target's contents were also confirmed present in the actual image.

MIPS J/JAL encodes a 26-bit target plus high PC bits; the leading `0x8` here is justified by the observed header addresses, not by the jump instruction alone.

**Limitations:** no runtime trace of CD loading, overlay mapping, relocation or execution was performed. A contiguous code mapping is inferred, not proven. This does not establish whether the overlay contains original source-like functions or independent resource tables.

Reproduce locally:

```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 tools/infer_overlay_base.py 'Wild Arms (USA).bin' inventory.json
python3 -m unittest discover -s tests -p 'test_*.py'
```

No original binary contents are committed.
