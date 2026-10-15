# Cross-file global pointer audit — WILDARMS.EXE / CDEF.BIN

Read-only scan performed on user's Wild Arms (USA) MODE2/Form1 disc image. Searches exact *adjacent* MIPS `LUI` followed by load/store referencing `0x800D2C3C`. Only metadata in repo, not game contents.

| File | Bytes analyzed | Loads | Stores | Coverage |
|---|---:|---:|---:|---|
| WILDARMS.EXE | 792576 (after 2048-byte PS-X EXE header) | 39 | 0 | complete |
| CDEF.BIN | 372736 | 6 | 0 | complete |
| OPENING.EXE | 225280 | 0 | 0 | complete |
| SCUS_946.08 | 145408 | 0 | 0 | complete |
| CDPL00.BIN | 212216 | 0 | 0 | complete |
| CDPL01.BIN | 217448 | 0 | 0 | complete |
| CDEN.BIN | 1048576 | 0 | 0 | **prefix only** |
| CDFLR.BIN | 1048576 | 0 | 0 | **prefix only** |
| CDGD.BIN | 1048576 | 0 | 0 | **prefix only** |
| CDSTG.BIN | 1048576 | 0 | 0 | **prefix only** |

CDEF.BIN's six candidate loads occur at **LUI instruction** file offsets:
`0x38778`, `0x39744`, `0x39928`, `0x3C778`, `0x3D744`, `0x3D928`.
The two groups are displaced by exactly `0x4000` (16384) bytes.
Bytes beginning at `0x38000` and `0x3C000` agree for **12288 consecutive bytes**, in each case examining at most a 16KiB region. These duplicates are not yet assigned to separate runtime overlays.

**Interpretation:** The CDEF sequences are surrounded by plausible MIPS calculations, increasing confidence that they are code-like, but code reachability and the target pointer's initialization remain unproven. No adjacent direct stores were found in checked ranges. Do not generalize results from the prefix-only files to their unexamined extents.

Reproduce locally:
```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 -m tools.audit_overlay_global_refs 'Wild Arms (USA).bin' inventory.json
python3 -m unittest discover -s tests -p 'test_*.py'
```
