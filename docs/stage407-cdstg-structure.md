# Stage407 — candidate CDSTG fixed-stride record structure

## Local source/provenance

A user-supplied private ZIP contains a 637,163,856-byte `Wild Arms (USA).bin` and its 81-byte `MODE2/2352` cue. The ZIP passed CRC verification, and the full BIN SHA-256 matched the previously saved **local candidate** hash. This comparison is not an external authenticity certification.

The ISO9660 primary volume identifier is `WILDARMS`. Sector-validated local extraction of `BIN/CDSTG.BIN;1` (76,021,760 bytes, LBA 1383) and `BIN/CDFLR.BIN;1` (15,917,056 bytes, LBA 38503) matched both previously recorded **256-byte prefix hashes**. These original files and analysis reports remain outside git.

## Observed candidate structure of CDSTG.BIN

- Exact division: 76,021,760 / 593,920 = **128 fixed-length blocks**, no remainder.
- 593,920 bytes = **290** logical Form1 sectors of 2048 bytes.
- **127 of 128** blocks have ASCII `Sony` at relative offset `0x3C`.
- **127 of 128** blocks have PS1 KSEG0 RAM-address-like little-endian words at both relative byte offsets `0x00` and `0x08`.
- Block index **25** (zero-based) is the sole exception to the marker and RAM-like-header patterns. Its bytes must **not** be discarded or reinterpreted as a standard block without further proof.
- All **128 block SHA-256 hashes are distinct**.

## Stronger header correspondence with native PS-X EXE

We also inspected the actual `EXE/WILDARMS.EXE;1` and `EXE/OPENING.EXE;1` headers from the same private disc. Both contain `PS-X EXE` and `Sony Computer Entertainment Inc.` at the expected native header positions. The 127 regular CDSTG block headers have the same field *layout shifted left by 16 bytes*:

| Header element | Native PS-X EXE offset | CDSTG candidate offset |
| --- | ---: | ---: |
| Entry PC | `0x10` | `0x00` |
| Text load address | `0x18` | `0x08` |
| Text length | `0x1C` | `0x0C` |
| Initial stack | `0x30` | `0x20` |
| Beginning of Sony region string | `0x4C` | `0x3C` |

For all 127 regular records the candidate text load address is `0x8014F040`, GP is zero, and initial stack is `0x801FFFF0`. The entry PC is four-byte aligned and lies in the declared text range. Text sizes are 2048-byte aligned, with 27 distinct sizes ranging from `0x4000` to `0x12800`.

## MIPS entry stub cross-check

The 127 regular block headers provide a candidate entry PC and load address. Reading **only 16 bytes** at each corresponding in-record entry offset (`0x40 + entry_pc - text_load`) gives matching MIPS code in all 127 cases:

- `lui gp, immediate`;
- `addiu gp, gp, signed_immediate`;
- `j destination`;
- one delay-slot `nop`.

The first two instructions calculate **GP = entry_PC + 16** in 127/127 cases. The `j` destination resolves to an address **inside that block's declared text range** in 127/127 cases. The analyzer records only boolean results and counts, never opcode bytes or complete disassembly.

This is stronger evidence that these 127 records are executable overlay-like modules. It still does not determine whether a particular overlay describes a map, combat, menus, or another subsystem, and does not establish a safe way to execute the code. The exceptional record #25 fails the header prerequisite and is excluded from stub interpretation.

This supports a **trimmed PS-X EXE-like overlay-header hypothesis**, not a claim that a record can already be executed, nor that a block equals a map. The special block #25 does not match and is not treated as a corrupted or disposable record. More loader/relocation evidence is required.

This demonstrates a repeatable *candidate* record layout. It **does not** prove that the blocks correspond one-to-one with maps, scenes, levels, or executable overlays. A `Sony` marker and RAM-like words are insufficient to infer their roles or decode graphics.

## Reproducing the metadata-only verification

```sh
python tools/inspect_stage_records.py /private/path/CDSTG.BIN \
  > /private/path/cdstg-record-index.json
```

The output includes only record indexes, hashes, flags and offsets. Do not publish the private report, original ZIP/BIN, extracted files, dialogue, art, or sound assets. CI uses synthetic fixtures only.

## Next verification gate

1. Compare repeated internal offsets and size fields between normal blocks without assuming their meanings.
2. Investigate exceptional block #25 separately.
3. Identify a verifiable and safely bounded graphics/layout section in one block.
4. Produce a local-only decoded frame and compare it against a known PS1 reference capture before calling it an original scene.
5. Integrate proven scene data through a local asset pipeline, without shipping original game assets in the public repository.

Keep this track independent from battle/ARM persistence and do not modify existing field-save formats.
